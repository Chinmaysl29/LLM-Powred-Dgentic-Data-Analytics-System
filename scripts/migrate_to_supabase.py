"""Explicit, non-overwriting local-to-hosted migration. Preflight is read-only.

The SQL password comes from SUPABASE_DATABASE_URL, never the publishable key.
Stops before cutover: the caller restarts the server only after verification.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import secrets
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from psycopg import sql
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from backend.app.core.database_target import bind_database_schema, hosted_postgres_dsn


def application_tables():
    from backend.app.models import Base
    from backend.app.core.workspace_authorization import authorization_metadata
    # Membership/binding tables intentionally live outside the ORM metadata.
    # Their rows are just as essential as users and workspaces during cutover.
    return [*Base.metadata.sorted_tables, *authorization_metadata.sorted_tables]


def copy_statement(table, schema, direction):
    columns = sql.SQL(', ').join(sql.Identifier(c.name) for c in table.columns)
    qualified = sql.Identifier(schema, table.name)
    if direction == 'out':
        order = sql.SQL(', ').join(sql.Identifier(c.name) for c in table.primary_key.columns)
        return sql.SQL('COPY (SELECT {} FROM {} ORDER BY {}) TO STDOUT WITH (FORMAT CSV)').format(columns, qualified, order)
    return sql.SQL('COPY {} ({}) FROM STDIN WITH (FORMAT CSV)').format(qualified, columns)


def fingerprint(connection, table, schema):
    hasher = sha256()
    with connection.connection.driver_connection.cursor() as cursor:
        with cursor.copy(copy_statement(table, schema, 'out')) as reader:
            for chunk in reader:
                hasher.update(chunk)
        cursor.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(schema, table.name)))
        count = cursor.fetchone()[0]
    return {'rows': count, 'sha256_csv': hasher.hexdigest()}


def copy_tables(source, destination, tables, source_schema='public', destination_schema='analyst'):
    """Caller owns transactions. COPY preserves SQL NULL versus JSON null exactly."""
    with source.connection.driver_connection.cursor() as reader, destination.connection.driver_connection.cursor() as writer:
        for cursor in (reader, writer):
            cursor.execute("SET LOCAL TIME ZONE 'UTC'")
            cursor.execute("SET LOCAL DateStyle = 'ISO, MDY'")
            cursor.execute("SET LOCAL lock_timeout = '5s'")
        # Refuse all conflicts before copying even the first table.
        for table in tables:
            writer.execute(sql.SQL('SELECT EXISTS (SELECT 1 FROM {})').format(sql.Identifier(destination_schema, table.name)))
            if writer.fetchone()[0]:
                raise ValueError(f'Target table {table.name} is not empty; no records were overwritten.')
        records = {}
        for table in tables:
            with reader.copy(copy_statement(table, source_schema, 'out')) as outgoing:
                with writer.copy(copy_statement(table, destination_schema, 'in')) as incoming:
                    for chunk in outgoing:
                        incoming.write(chunk)
            expected = fingerprint(source, table, source_schema)
            if fingerprint(destination, table, destination_schema) != expected:
                raise ValueError(f'Copy verification failed for {table.name}; target transaction will roll back.')
            records[table.name] = expected
            for column in table.columns:
                if column.autoincrement is True or column.primary_key and column.type.python_type is int:
                    writer.execute('SELECT pg_get_serial_sequence(%s, %s)', (f'{destination_schema}.{table.name}', column.name))
                    sequence = writer.fetchone()[0]
                    if sequence:
                        writer.execute(sql.SQL('SELECT COALESCE(max({}), 0) + 1 FROM {}').format(
                            sql.Identifier(column.name), sql.Identifier(destination_schema, table.name)))
                        writer.execute('SELECT setval(%s::regclass, %s, false)', (sequence, writer.fetchone()[0]))
    return records


def migrate_schema(url, schema):
    from alembic import command
    from alembic.config import Config
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}',schema):
        raise ValueError('Invalid database schema identifier')
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            connection.execute(text(f'REVOKE ALL ON SCHEMA "{schema}" FROM PUBLIC'))
        cfg = Config(str(ROOT / 'alembic.ini'))
        cfg.set_main_option('script_location', str(ROOT / 'migrations'))
        cfg.attributes.update(database_url=url, database_schema=schema)
        command.upgrade(cfg, 'head')
    finally:
        engine.dispose()


def provision_runtime(connection, admin_url):
    role = 'analyst_app_' + uuid4().hex[:12]
    password = secrets.token_urlsafe(40)
    with connection.connection.driver_connection.cursor() as cursor:
        cursor.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {}').format(
            sql.Identifier(role), sql.Literal(password)))
        cursor.execute(sql.SQL('GRANT USAGE ON SCHEMA analyst TO {}').format(sql.Identifier(role)))
        cursor.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA analyst TO {}').format(sql.Identifier(role)))
        cursor.execute(sql.SQL('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA analyst TO {}').format(sql.Identifier(role)))
    admin = make_url(admin_url)
    suffix = '.' + admin.username.split('.', 1)[1] if '.pooler.supabase.com' in admin.host else ''
    return admin.set(username=role + suffix, password=password).render_as_string(hide_password=False)


def save_runtime(path, value):
    contents = path.read_text(encoding='utf-8')
    line = 'SUPABASE_RUNTIME_DATABASE_URL=' + value
    if re.search(r'^SUPABASE_RUNTIME_DATABASE_URL=.*$', contents, re.M):
        contents = re.sub(r'^SUPABASE_RUNTIME_DATABASE_URL=.*$', lambda _: line, contents, flags=re.M)
    else:
        contents = contents.rstrip() + '\n' + line + '\n'
    path.write_text(contents, encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Apply migrations and copy into empty analyst tables')
    parser.add_argument('--source-stopped', action='store_true', help='Confirm the source API and all workers are stopped')
    parser.add_argument('--runtime-env-file', type=Path, help='Private existing .env file to receive generated runtime credentials')
    parser.add_argument('--initialize-ui', action='store_true', help='Initialize the supplied hosted public UI/Storage schema on a fresh project')
    args = parser.parse_args()
    from backend.app.core.config import Settings
    from backend.app.database.schema_contract import inspect_schema
    settings = Settings(database_target='local')
    if not settings.supabase_database_url:
        print(json.dumps({'state':'needs_database_credentials', 'configured_auth_project':settings.supabase_url,
            'required':'Add SUPABASE_DATABASE_URL from Connect > Session pooler to the backend .env. The publishable key cannot migrate PostgreSQL.'}))
        return 2
    target_url = hosted_postgres_dsn(settings.supabase_database_url.get_secret_value(), settings.supabase_url)
    if args.apply and (not args.source_stopped or not args.runtime_env_file or not args.runtime_env_file.is_file()):
        raise ValueError('Stop the source API/workers and provide --source-stopped and an existing private --runtime-env-file before applying.')
    source_engine = create_engine(settings.postgres_dsn, hide_parameters=True, pool_pre_ping=True)
    target_admin = create_engine(target_url, hide_parameters=True, pool_pre_ping=True, pool_size=2, max_overflow=0)
    try:
        with source_engine.connect() as source, target_admin.connect() as target:
            if not inspect_schema(source)['compatible']:
                raise ValueError('Source schema must be current before migration.')
            with target.connection.driver_connection.cursor() as cursor:
                cursor.execute('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user')
                if not cursor.fetchone()[0]:
                    raise ValueError('A database migration-owner connection is required to copy immutable scoped evidence.')
            tables = application_tables()
            counts = {table.name:source.scalar(text(f'SELECT count(*) FROM "{table.name}"')) for table in tables}
            existing=set(inspect(target).get_table_names(schema='analyst'))
            if existing-({table.name for table in tables}|{'alembic_version'}):
                raise ValueError('The hosted analyst schema contains unknown tables; inspect it before migrating.')
            for table in tables:
                if table.name in existing and target.scalar(text(f'SELECT EXISTS(SELECT 1 FROM analyst."{table.name}")')):
                    raise ValueError('Hosted analyst tables contain data; migration will not overwrite an existing target.')
            print(json.dumps({'state':'preflight_ok', 'target_schema':'analyst', 'source_table_counts':counts, 'apply':args.apply}))
        if not args.apply:
            return 0
        if args.initialize_ui:
            with target_admin.begin() as target:
                existing=set(inspect(target).get_table_names(schema='public'))
                if existing & {'profiles','workspaces','datasets','analysis_sessions','reports','saved_visualizations'}:
                    raise ValueError('Hosted UI tables already exist; inspect their schema before applying UI initialization.')
                target.exec_driver_sql((ROOT/'supabase/migrations/20261012000000_supabase_initial_schema.sql').read_text(encoding='utf-8'))
                target.exec_driver_sql((ROOT/'infrastructure/supabase_public_grants.sql').read_text(encoding='utf-8'))
        migrate_schema(target_url, 'analyst')
        target_engine = create_engine(target_url, hide_parameters=True)
        bind_database_schema(target_engine, 'analyst')
        try:
            with source_engine.connect().execution_options(isolation_level='REPEATABLE READ') as source, source.begin(), target_engine.begin() as target:
                source.execute(text("SET LOCAL lock_timeout='5s'"))
                source.execute(text('LOCK TABLE '+', '.join(f'"{t.name}"' for t in tables)+' IN SHARE MODE'))
                if not inspect_schema(target)['compatible']:
                    raise ValueError('Hosted schema compatibility check failed.')
                records = copy_tables(source, target, tables)
                runtime = provision_runtime(target, target_url)
                # Save the credential before committing the role and copied rows.
                # DATABASE_TARGET remains local even if later verification fails.
                save_runtime(args.runtime_env_file, runtime)
            runtime_engine = create_engine(runtime, hide_parameters=True)
            bind_database_schema(runtime_engine, 'analyst')
            try:
                with runtime_engine.connect() as connection:
                    flags=connection.execute(text('SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user')).one()
                    if any(flags) or not inspect_schema(connection)['compatible']:
                        raise ValueError('Runtime role or schema verification failed; leave DATABASE_TARGET=local.')
            finally:
                runtime_engine.dispose()
            print(json.dumps({'state':'copy_verified', 'records':records, 'runtime_credentials_saved':True,
                'cutover':'Set DATABASE_TARGET=supabase in .env and recreate backend; keep the source database and storage volumes.'}))
        finally:
            target_engine.dispose()
    finally:
        source_engine.dispose(); target_admin.dispose()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Driver/DDL exceptions can include connection or role-password values.
        print(json.dumps({'state':'not_switched', 'error_category':type(exc).__name__,
            'message':str(exc) if isinstance(exc, ValueError) else 'Migration failed; keep local mode. Inspect credentials/connectivity privately.'}))
        raise SystemExit(1)
