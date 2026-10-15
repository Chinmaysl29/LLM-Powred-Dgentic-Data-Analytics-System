"""Validate proposed DDL and real PostgreSQL isolation in an existing test clone.

Only accepts explicitly named stabilization_verify_* databases; customer ai_analyst
is never a valid target. DDL and pytest fixtures are rolled back. No secrets print.
"""
from pathlib import Path
import argparse
import os
import subprocess
import sys

from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', required=True)
    args = parser.parse_args()
    if not args.database.startswith('stabilization_verify_'):
        raise SystemExit('Only an isolated stabilization_verify_* database is permitted')
    root = Path(__file__).resolve().parents[1]
    config = {**dotenv_values(root / '.env'), **os.environ}
    url = make_url(config['DATABASE_URL']).set(database=args.database)
    if url.host == 'postgres':
        url = url.set(host='127.0.0.1', port=int(config.get('POSTGRES_HOST_PORT', '5433')))
    engine = create_engine(url, connect_args={'connect_timeout': 5})
    expected = {'tenant_memberships', 'workspace_memberships', 'dataset_workspace_bindings'}
    try:
        with engine.connect() as connection:
            assert not expected.intersection(inspect(connection).get_table_names()), 'Test clone already has proposed tables'
            connection.rollback()
            transaction = connection.begin()
            try:
                sql = (root / 'migrations/proposed/workspace_authorization.sql').read_text(encoding='utf-8')
                sql = '\n'.join(line for line in sql.splitlines() if not line.strip().startswith('--') and line.strip() not in {'BEGIN;', 'COMMIT;'})
                for statement in sql.split(';'):
                    if statement.strip():
                        connection.exec_driver_sql(statement)
                assert expected.issubset(inspect(connection).get_table_names())
                assert len(inspect(connection).get_foreign_keys('dataset_workspace_bindings')) == 2
            finally:
                transaction.rollback()
            assert not expected.intersection(inspect(connection).get_table_names())
        print('PASS proposed DDL, foreign keys and rollback in isolated PostgreSQL clone', flush=True)
    except Exception as error:
        print('Migration validation failed:', type(error).__name__, flush=True)
        return 1
    finally:
        engine.dispose()
    env = {**os.environ, 'DEBUG': 'false', 'ISOLATION_TEST_DATABASE_URL': url.render_as_string(hide_password=False)}
    return subprocess.call([sys.executable, '-m', 'pytest', 'tests/test_workspace_authorization_boundary.py',
        'tests/test_authenticated_dataset_isolation.py', '-q', '--junitxml=reports/postgres-workspace-isolation.xml'], cwd=root, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
