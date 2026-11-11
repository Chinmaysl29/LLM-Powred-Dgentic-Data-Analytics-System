"""Explicit local operator commands; no HTTP promotion surface or golden training."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("stage", "promote", "rollback", "status"))
    parser.add_argument("--actor-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--version", type=int)
    parser.add_argument("--expected-version", type=int)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.command == "stage" and not args.candidate:
        parser.error("stage requires --candidate")
    if args.command in {"promote", "rollback"} and (args.version is None or args.expected_version is None):
        parser.error("promote/rollback require --version and --expected-version (0 means baseline)")
    if args.command == "promote" and (not args.manifest or not args.manifest_sha256):
        parser.error("promote requires --manifest and --manifest-sha256")
    engine = None
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import NullPool
        from backend.app.core.config import get_settings
        from backend.app.core.database_target import bind_database_schema
        from backend.app.learning import lifecycle
        settings = get_settings()
        engine = create_engine(settings.postgres_dsn, poolclass=NullPool, hide_parameters=True,
                               connect_args={"connect_timeout": 2})
        bind_database_schema(engine, settings.database_schema)
        factory = sessionmaker(engine)
        common = (factory, args.actor_id, args.tenant_id)
        if args.command == "stage":
            if args.candidate.stat().st_size > 1_000_000:
                raise ValueError("Oversized candidate")
            result = lifecycle.stage(*common, json.loads(args.candidate.read_bytes()))
        elif args.command == "promote":
            result = asyncio.run(lifecycle.promote(*common, args.version, args.expected_version,
                args.root, args.manifest, args.manifest_sha256))
        elif args.command == "rollback":
            result = lifecycle.rollback(*common, args.version, args.expected_version)
        else:
            result = lifecycle.status(*common)
        print(json.dumps(result, allow_nan=False))
        return 1 if result.get("promoted") is False else 0
    except Exception:
        print("Router command refused: check operator authorization, version, shadow evidence and golden integrity.", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
