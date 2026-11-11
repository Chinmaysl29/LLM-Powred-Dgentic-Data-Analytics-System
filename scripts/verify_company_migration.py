"""Representative legacy-record roundtrip in a new, isolated test schema only."""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text, MetaData, Table
    from sqlalchemy.engine import make_url
    from backend.app.core.config import Settings, get_settings
    from backend.app.core.database_target import bind_database_schema
    from backend.app.models import User, Tenant, Workspace, Dataset
    from sqlalchemy.orm import Session
    Settings.model_config = {**Settings.model_config, 'env_file': None}
    get_settings.cache_clear()
    target = make_url(os.environ['DATABASE_URL'])
    if (target.database not in {'analyst_setup_test', 'analyst_test', 'analyst_migration_test'}
        or target.host not in {'postgres', '127.0.0.1', 'localhost'} or os.environ.get('ENVIRONMENT') != 'test'):
        raise SystemExit('Known local synthetic test database only')
    schema = 'company_migration_' + uuid4().hex
    admin = create_engine(target)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(target)
    bind_database_schema(engine, schema)
    config = Config(str(ROOT / 'alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'migrations'))
    config.attributes.update(database_url=target.render_as_string(hide_password=False), database_schema=schema)
    try:
        command.upgrade(config, '020_auth_token_revocations')
        user_id, tenant_id, workspace_id, dataset_id, definition_id = [uuid4() for _ in range(5)]
        with Session(engine) as db, db.begin():
            db.add(User(id=user_id, email=f'{user_id}@synthetic.test', hashed_password='', full_name='Synthetic migration', is_active=True))
            db.add(Tenant(id=tenant_id, tenant_name='Synthetic migration', tenant_slug=uuid4().hex, tenant_status='active'))
            db.flush()
            db.add(Workspace(id=workspace_id, tenant_id=tenant_id, workspace_name='Synthetic legacy', workspace_slug=uuid4().hex, status='active'))
            db.flush()
            db.add(Dataset(dataset_id=str(dataset_id), owner_id=str(user_id), dataset_name='Preserved original',
                file_name='synthetic.csv', file_type='csv', file_path='/synthetic/immutable.csv', status='ready'))
            db.flush()
            legacy = Table('learning_definitions', MetaData(), autoload_with=db.connection())
            db.execute(legacy.insert().values(id=str(definition_id), workspace_id=workspace_id, key='legacy_total',
                version=1, actor_id=user_id, content={'historical': 'unknown provenance'}, content_hash='a'*64,
                active=True, created_at=datetime.now(timezone.utc)))
        def snapshot():
            with engine.connect() as connection:
                return connection.execute(text('SELECT id,key,version,actor_id,content::text,content_hash,active,created_at FROM learning_definitions')).all()
        before = snapshot()
        command.upgrade(config, 'head')
        command.upgrade(config, 'head')
        assert snapshot() == before
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT governance::text FROM learning_definitions')) == '{}'
        command.downgrade(config, '020_auth_token_revocations')
        assert 'governance' not in {c['name'] for c in inspect(engine).get_columns('learning_definitions')}
        assert snapshot() == before
        command.upgrade(config, 'head')
        assert snapshot() == before
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO dataplane_artifacts(id,tenant_id,workspace_id,actor_id,kind,payload) "
                "VALUES (:id,:tenant,:workspace,:actor,'policy','{}')"),
                {'id': uuid4(), 'tenant': tenant_id, 'workspace': workspace_id, 'actor': user_id})
        try:
            command.downgrade(config, '020_auth_token_revocations')
        except Exception as error:
            assert 'Archive company review artifacts' in str(error)
        else:
            raise AssertionError('Lossy downgrade was not rejected')
        assert 'governance' in {c['name'] for c in inspect(engine).get_columns('learning_definitions')}
        # Alembic may commit each successful downgrade revision before an older
        # revision refuses. Restore head before checking the grant's own guard.
        command.upgrade(config, 'head')
        reviewer_id = uuid4()
        with Session(engine) as db, db.begin():
            db.add(User(id=reviewer_id, email=f'{reviewer_id}@synthetic.test', hashed_password='',
                        full_name='Synthetic migration reviewer', is_active=True))
            db.flush()
            db.execute(text('INSERT INTO dataset_review_grants '
                '(id,tenant_id,workspace_id,dataset_id,owner_id,reviewer_id,active,expires_at,revision) '
                "VALUES (:id,:tenant,:workspace,:dataset,:owner,:reviewer,true,now()+interval '1 day',1)"),
                {'id': uuid4(), 'tenant': tenant_id, 'workspace': workspace_id, 'dataset': str(dataset_id),
                 'owner': user_id, 'reviewer': reviewer_id})
        try:
            command.downgrade(config, '022_active_version_guard')
        except Exception as error:
            assert 'Archive dataset reviewer grants' in str(error)
        else:
            raise AssertionError('Reviewer history downgrade was not rejected')
        result = {'passed': True, 'legacy_records_preserved': True, 'historical_governance': 'unknown',
            'upgrade_idempotent': True, 'downgrade_upgrade': True, 'lossy_downgrade_rejected': True,
            'reviewer_history_downgrade_rejected': True}
        output = Path(os.environ.get('COMPANY_MIGRATION_RESULT', '/tmp/company-migration.json'))
        output.write_text(json.dumps(result, indent=2))
        print(json.dumps(result))
    finally:
        engine.dispose()
        # Only this exact, freshly generated test schema is removed.
        assert schema.startswith('company_migration_') and len(schema) == 50
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == '__main__':
    main()
