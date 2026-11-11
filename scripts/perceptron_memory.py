"""Operator review/reindex/revoke commands for tenant-local failure memory."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("approve", "reindex", "revoke"))
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--feedback-id")
    parser.add_argument("--mistake-id")
    parser.add_argument("--dataset-id")
    parser.add_argument("--dataset-version", type=int)
    parser.add_argument("--question-file", type=Path)
    parser.add_argument("--correction-file", type=Path)
    parser.add_argument("--reviewed", action="store_true", help="Attest that the supplied correction has been reviewed")
    args = parser.parse_args()
    if args.command == "approve" and not all((args.feedback_id, args.dataset_id, args.dataset_version,
            args.question_file, args.correction_file, args.reviewed)):
        parser.error("approve requires reviewed failure, dataset/version, exact question file and correction JSON")
    if args.command != "approve" and not args.mistake_id:
        parser.error("reindex/revoke require --mistake-id")
    engine = None
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import NullPool
        from backend.app.core.config import get_settings
        from backend.app.core.database_target import bind_database_schema
        from backend.app.learning import memory_review
        settings = get_settings()
        engine = create_engine(settings.postgres_dsn, poolclass=NullPool, hide_parameters=True,
                               connect_args={"connect_timeout": 2})
        bind_database_schema(engine, settings.database_schema)
        factory = sessionmaker(engine)
        if args.command == "approve":
            if args.question_file.stat().st_size > 8000 or args.correction_file.stat().st_size > 4096:
                raise ValueError("Review input too large")
            result = memory_review.approve(factory, args.reviewer_id, args.feedback_id, args.dataset_id,
                args.dataset_version, args.question_file.read_text(encoding="utf-8"),
                json.loads(args.correction_file.read_bytes()))
        elif args.command == "reindex":
            result = {"mistake_id": args.mistake_id,
                      "indexed": memory_review.reindex(factory, args.reviewer_id, args.mistake_id)}
        else:
            result = memory_review.revoke(factory, args.reviewer_id, args.mistake_id)
        print(json.dumps(result))
        return 1 if result.get("indexed") is False else 0
    except Exception:
        print("Memory command refused: check operator authorization, failure provenance and correction contract.", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
