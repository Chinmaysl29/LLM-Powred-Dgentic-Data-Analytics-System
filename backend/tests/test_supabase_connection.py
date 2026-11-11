"""Hosted connection guards and real isolated PostgreSQL migration mechanics."""
from datetime import datetime, timezone
from decimal import Decimal
import os
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption
from fastapi import HTTPException
from jose import jwk, jwt
import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, MetaData, Numeric, String, Table, create_engine, text
from sqlalchemy.engine import make_url

from backend.app.core.config import Settings
from backend.app.core.database_target import bind_database_schema, hosted_postgres_dsn
from backend.app.core.security import verify_token
from backend.app.database.schema_contract import inspect_schema
from scripts.migrate_to_supabase import application_tables, copy_tables, migrate_schema, provision_runtime
from backend.tests.test_verified_learning_integration import environment  # noqa: F401

PROJECT='https://qjcudbkamhldswcyxypv.supabase.co'


def test_hosted_connection_uses_project_bound_session_pooler_and_tls():
    raw='postgresql://postgres.qjcudbkamhldswcyxypv:encoded%40password@aws-0-ap-south-1.pooler.supabase.com:5432/postgres'
    uri=make_url(hosted_postgres_dsn(raw,PROJECT))
    assert uri.drivername=='postgresql+psycopg' and uri.password=='encoded@password'
    assert uri.query['sslmode']=='require' and 'options' not in uri.query
    local=Settings(_env_file=None,database_target='local',database_url='postgresql+psycopg://example/local')
    assert local.database_schema=='public' and local.postgres_dsn.endswith('/local')
    missing=local.model_copy(update={'database_target':'supabase'})
    with pytest.raises(ValueError,match='SUPABASE_RUNTIME_DATABASE_URL'): _=missing.postgres_dsn
    hosted=Settings(_env_file=None,database_target='supabase',supabase_url=PROJECT,supabase_runtime_database_url=raw)
    assert hosted.database_schema=='analyst' and make_url(hosted.postgres_dsn).host==uri.host


@pytest.mark.parametrize('uri',[
    PROJECT,
    'postgresql://postgres@db.qjcudbkamhldswcyxypv.supabase.co/postgres',
    'postgresql://postgres:secret@db.other.supabase.co/postgres',
    'postgresql://postgres.other:secret@aws-0-ap-south-1.pooler.supabase.com/postgres',
    'postgresql://postgres.qjcudbkamhldswcyxypv:secret@aws-0-ap-south-1.pooler.supabase.com:6543/postgres',
])
def test_hosted_connection_refuses_public_urls_wrong_projects_and_transaction_pooling(uri):
    with pytest.raises(ValueError) as error:hosted_postgres_dsn(uri,PROJECT)
    assert 'secret' not in str(error.value)


def test_verified_jwt_requires_the_configured_supabase_issuer_and_audience(monkeypatch):
    private=ec.generate_private_key(ec.SECP256R1())
    pem=private.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()).decode()
    public=private.public_key().public_bytes(Encoding.PEM,PublicFormat.SubjectPublicKeyInfo).decode()
    key=jwk.construct(public,'ES256')
    monkeypatch.setattr('backend.app.core.security._get_supabase_jwks',lambda project:{'test-key':key})
    settings=Settings(_env_file=None,supabase_url=PROJECT,jwt_secret_key='synthetic-local-test-secret')
    claims={'sub':str(uuid4()),'aud':'authenticated','iss':PROJECT+'/auth/v1',
        'exp':int(datetime.now(timezone.utc).timestamp())+60}
    token=lambda payload:jwt.encode(payload,pem,algorithm='ES256',headers={'kid':'test-key'})
    assert verify_token(token(claims),settings)['sub']==claims['sub']
    for changes in ({'iss':'https://other.supabase.co/auth/v1'},{'aud':'wrong'},{'exp':1}):
        with pytest.raises(HTTPException) as error:verify_token(token({**claims,**changes}),settings)
        assert error.value.status_code==401


@pytest.fixture
def database():
    url=os.environ.get('DATABASE_URL','');parsed=make_url(url)
    assert parsed.database in {'analyst_setup_test', 'analyst_test'} and parsed.username in {'setup', 'postgres'} and os.environ.get('ENVIRONMENT')=='test'
    engine=create_engine(url)
    yield engine,url
    engine.dispose()


def test_copy_preserves_json_null_decimal_timestamp_csv_and_refuses_conflicts(database):
    admin,url=database;schemas=['copy_source_'+uuid4().hex[:10],'copy_target_'+uuid4().hex[:10]];engines=[]
    metadata=MetaData()
    Table('groups',metadata,Column('id',Integer,primary_key=True),Column('name',String))
    Table('items',metadata,Column('id',Integer,primary_key=True),Column('group_id',Integer,ForeignKey('groups.id')),
        Column('payload',JSON),Column('amount',Numeric(30,8)),Column('observed',DateTime(timezone=True)),Column('note',String))
    try:
        for schema in schemas:
            with admin.begin() as connection:connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            engine=create_engine(url);bind_database_schema(engine,schema);engines.append(engine);metadata.create_all(engine)
        with engines[0].begin() as connection:
            connection.execute(text("INSERT INTO groups(id,name) VALUES (8,'synthetic')"))
            connection.execute(text("INSERT INTO items VALUES (5,8,NULL,1234567890123456.12345678,'2026-01-02T00:00:00Z',:note), (9,8,'null'::json,1.10,'2026-01-03T00:00:00Z','quoted')"),{'note':'comma, quote " and\nnewline'})
        with engines[0].begin() as source,engines[1].begin() as target:
            records=copy_tables(source,target,list(metadata.sorted_tables),*schemas)
            assert records['items']['rows']==2
        with engines[1].begin() as connection:
            rows=connection.execute(text('SELECT payload IS NULL, amount, observed, note FROM items ORDER BY id')).all()
            assert [row[0] for row in rows]==[True,False]
            assert rows[0][1]==Decimal('1234567890123456.12345678') and rows[0][2].tzinfo is not None
            assert rows[0][3]=='comma, quote " and\nnewline'
            assert connection.scalar(text("INSERT INTO items(group_id) VALUES(8) RETURNING id"))==10
        with pytest.raises(ValueError,match='not empty'):
            with engines[0].begin() as source,engines[1].begin() as target:
                copy_tables(source,target,list(metadata.sorted_tables),*schemas)
    finally:
        for engine in engines:engine.dispose()
        with admin.begin() as connection:
            for schema in schemas:connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_private_schema_migrates_all_revisions_and_runtime_role_cannot_bypass_rls(database):
    admin,url=database;schema='migration_'+uuid4().hex[:10];private=create_engine(url);runtime_engine=None;role=None
    try:
        migrate_schema(url,schema);bind_database_schema(private,schema)
        with private.connect() as connection:
            assert connection.scalar(text('SELECT current_schema()'))==schema
            assert inspect_schema(connection)['compatible']
            assert connection.scalar(text('SELECT count(*) FROM adaptive_decisions'))==0
        # The production helper deliberately scopes grants to the fixed analyst schema.
        with admin.begin() as connection:
            connection.execute(text('CREATE SCHEMA IF NOT EXISTS analyst'))
            runtime=provision_runtime(connection,url);role=make_url(runtime).username
        runtime_engine=create_engine(runtime);bind_database_schema(runtime_engine,'analyst')
        with runtime_engine.connect() as connection:
            assert connection.scalar(text('SELECT current_schema()'))=='analyst'
            assert tuple(connection.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')).one())==(False,False)
    finally:
        if runtime_engine:runtime_engine.dispose()
        private.dispose()
        with admin.begin() as connection:
            if role:
                connection.execute(text(f'DROP OWNED BY "{role}"'))
                connection.execute(text(f'DROP ROLE "{role}"'))
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_complete_application_copy_preserves_verified_decisions_and_runtime_scope(database, environment, tmp_path):
    from sqlalchemy.orm import Session
    from backend.tests.test_verified_learning_integration import identity, dataset, spec, run
    from backend.tests.test_adaptive_integration import initialize, drain
    from backend.app.models.adaptive import AdaptiveDecision
    from backend.app.services.learning_supervisor import bind
    env=environment;account=identity(env);initialize(env,account)
    data=dataset(env,account,tmp_path,'region,amount\nx,1.25\nx,2.50\n')
    created=run(env,account,data,spec(account['workspace'],data));drain(env)
    admin,url=database;target=create_engine(url);runtime_engine=None;role=None
    try:
        migrate_schema(url,'analyst');bind_database_schema(target,'analyst')
        with admin.begin() as source,target.begin() as destination:
            copied=copy_tables(source,destination,application_tables())
            assert copied['adaptive_decisions']['rows']>=1
            assert copied['tenant_memberships']['rows']>=1 and copied['dataset_workspace_bindings']['rows']>=1
            runtime=provision_runtime(destination,url);role=make_url(runtime).username
        runtime_engine=create_engine(runtime);bind_database_schema(runtime_engine,'analyst')
        with Session(runtime_engine) as session:
            assert session.query(AdaptiveDecision).count()==0
            bind(session,account['user'],account['workspace'])
            rows=session.query(AdaptiveDecision).filter(AdaptiveDecision.run_id==created['id']).all()
            assert len(rows)==1 and rows[0].content['selected_skill']=='decimal_exact'
            with pytest.raises(Exception,match='Immutable learning evidence'):
                session.execute(text("UPDATE adaptive_decisions SET features='{}' WHERE id=:id"),{'id':rows[0].id})
    finally:
        if runtime_engine:runtime_engine.dispose()
        target.dispose()
        with admin.begin() as connection:
            if role:
                connection.execute(text(f'DROP OWNED BY "{role}"'));connection.execute(text(f'DROP ROLE "{role}"'))
            connection.execute(text('DROP SCHEMA analyst CASCADE'))
