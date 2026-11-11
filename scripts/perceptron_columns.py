"""Operator-only column resolver training, evaluation, promotion and rollback."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('stage', 'evaluate', 'promote', 'rollback', 'status'))
    parser.add_argument('--reviewer-id', required=True)
    parser.add_argument('--dataset-id', required=True)
    parser.add_argument('--dataset-version', required=True, type=int)
    parser.add_argument('--version', type=int)
    parser.add_argument('--expected-version', type=int)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--reviewed', action='store_true')
    args = parser.parse_args()
    if args.command in ('stage', 'evaluate', 'promote') and not (args.manifest and args.manifest_sha256 and args.reviewed):
        parser.error('Reviewed manifest and its canonical SHA-256 are required')
    if args.command in ('evaluate', 'promote', 'rollback') and args.version is None:
        parser.error('Version required')
    if args.command in ('promote', 'rollback') and args.expected_version is None:
        parser.error('Expected active version required (0 means baseline)')
    engine = None
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import NullPool
        from backend.app.core.config import get_settings
        from backend.app.core.database_target import bind_database_schema
        from backend.app.learning import column_lifecycle as lifecycle, column_store as store
        from backend.app.learning.column_contract import evaluate
        from backend.app.learning.column_ranker import ColumnRanker
        settings = get_settings()
        engine = create_engine(settings.postgres_dsn, poolclass=NullPool, hide_parameters=True, connect_args={'connect_timeout': 2})
        bind_database_schema(engine, settings.database_schema)
        factory = sessionmaker(engine)
        common = (factory, args.reviewer_id, args.dataset_id, args.dataset_version)
        value = None
        if args.manifest:
            if args.manifest.stat().st_size > 1_000_000:
                raise ValueError('Manifest too large')
            value = lifecycle.checked_manifest(json.loads(args.manifest.read_bytes()), args.manifest_sha256)
        if args.command == 'stage':
            result = lifecycle.stage(*common, value, args.manifest_sha256)
        elif args.command == 'promote':
            result = lifecycle.promote(*common, args.version, args.expected_version, value, args.manifest_sha256)
        elif args.command == 'rollback':
            result = lifecycle.rollback(*common, args.version, args.expected_version)
        else:
            with factory() as db, db.begin():
                current = lifecycle.access(db, args.reviewer_id, args.dataset_id, args.dataset_version)
                if args.command == 'status':
                    result = {'active_version': store.active(db, current.tenant_id), 'versions': [dict(row) for row in db.execute(
                        select(store.weights.c.version, store.weights.c.is_active).where(store.condition(current.tenant_id))
                        .order_by(store.weights.c.version)).mappings()]}
                else:
                    payload = store.read(db, current.tenant_id, args.version)
                    if payload['scope'] != store.scope_dict(current) or payload['manifest_digest'] != args.manifest_sha256:
                        raise ValueError('Scope/manifest mismatch')
            if args.command == 'evaluate':
                result = evaluate(value, ColumnRanker(payload['weights'], payload['vocabulary']))
        print(json.dumps(result, allow_nan=False))
        return 1 if result.get('promoted') is False or result.get('passed') is False else 0
    except Exception:
        print('Resolver command refused: check authorization, reviewed splits, schema, version and shadow evidence.', file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
