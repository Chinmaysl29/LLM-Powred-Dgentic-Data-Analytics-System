"""One-time, explicitly approved local additive migration with preservation checks.

Requires a verified private pg_dump archive path. Never enrolls identities or
assigns datasets. Does not connect to hosted Supabase.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--backup', required=True)
    parser.add_argument('--approved-local-additive', action='store_true', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    backup = Path(args.backup).resolve()
    if not backup.is_file() or backup.read_bytes()[:5] != b'PGDMP':
        raise SystemExit('A verified custom-format PostgreSQL backup is required')
    config = {**dotenv_values(root / '.env'), **os.environ}
    url = make_url(config['DATABASE_URL'])
    if url.host == 'postgres':
        url = url.set(host='127.0.0.1', port=int(config.get('POSTGRES_HOST_PORT', '5433')))
    if url.database != 'ai_analyst' or url.host not in {'127.0.0.1', 'localhost'}:
        raise SystemExit('Only the approved local ai_analyst database is permitted')
    engine = create_engine(url, isolation_level='REPEATABLE READ', connect_args={'connect_timeout': 5})
    added = {'tenant_memberships', 'workspace_memberships', 'dataset_workspace_bindings'}
    def snapshot(connection, tables):
        result = {}
        for table in tables:
            quoted = connection.dialect.identifier_preparer.quote(table)
            result[table] = list(connection.execute(text(
                f"SELECT count(*), md5(coalesce(string_agg(h, '' ORDER BY h), '')) FROM "
                f"(SELECT md5(row_to_json(t)::text) h FROM public.{quoted} t) s"
            )).one())
        return result
    with engine.begin() as connection:
        tables = inspect(connection).get_table_names(schema='public')
        if added.intersection(tables):
            raise SystemExit('Proposed tables already exist; inspect before retrying')
        before = snapshot(connection, tables)
        sql = (root / 'migrations/proposed/workspace_authorization.sql').read_text(encoding='utf-8')
        sql = '\n'.join(line for line in sql.splitlines() if not line.strip().startswith('--') and line.strip() not in {'BEGIN;', 'COMMIT;'})
        for statement in sql.split(';'):
            if statement.strip():
                connection.exec_driver_sql(statement)
        assert before == snapshot(connection, tables), 'Existing rows changed; rolling back'
        for table in added:
            assert connection.execute(text(f'SELECT count(*) FROM {table}')).scalar_one() == 0
    evidence = {'time': datetime.now(timezone.utc).isoformat(), 'database': 'local ai_analyst',
                'backup_sha256': hashlib.sha256(backup.read_bytes()).hexdigest(),
                'added_empty_tables': sorted(added), 'preserved_table_count': len(before),
                'existing_rows_preserved': True, 'legacy_assignments': 0}
    (root / 'logs/recovery/workspace-authorization-apply.json').write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence))
    engine.dispose()


if __name__ == '__main__':
    main()
