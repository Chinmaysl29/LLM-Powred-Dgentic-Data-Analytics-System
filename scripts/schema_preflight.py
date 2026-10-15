"""Read-only deployment preflight. Never applies or stamps migrations."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from backend.app.core.config import get_settings
from backend.app.database.schema_contract import inspect_schema


def main() -> int:
    engine = None
    try:
        engine = create_engine(get_settings().postgres_dsn)
        with engine.connect() as connection:
            result = inspect_schema(connection)
        print(json.dumps(result, indent=2))
        return 0 if result['compatible'] else 1
    except Exception:
        # Connection/configuration exceptions can contain credentials or URLs.
        print(json.dumps({'compatible': False, 'error': 'Schema preflight failed; check configuration and database availability'}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
