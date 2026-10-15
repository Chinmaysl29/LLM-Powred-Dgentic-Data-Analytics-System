"""Run selected backend tests with disposable relative storage and test credentials.

Usage: .venv/Scripts/python.exe scripts/validate_backend.py tests/test_api_health.py
All pytest arguments are passed through; test paths are resolved before changing
directory. Existing repository datasets and application credentials are not used.
"""

from __future__ import annotations

import os
import faulthandler
from contextlib import chdir
from pathlib import Path
import sys
import tempfile


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    args = sys.argv[1:]
    if not args:
        raise SystemExit("Pass explicit test paths to avoid running live mutation tests.")
    resolved_args = []
    for arg in args:
        path, separator, node = arg.partition("::")
        candidate = root / path
        resolved_args.append(str(candidate) + separator + node if candidate.exists() else arg)
    sys.path.insert(0, str(root))
    with tempfile.TemporaryDirectory(prefix="analytics-backend-tests-") as scratch, chdir(scratch):
        os.environ.update({
            "ENVIRONMENT": "test",
            "DEBUG": "false",
            "JWT_SECRET_KEY": "isolated-test-secret-not-for-deployment-123456789",
            "DATABASE_URL": "postgresql+psycopg://test:test@127.0.0.1:1/test",
            "POSTGRES_HOST": "127.0.0.1",
            "POSTGRES_PORT": "1",
            "REDIS_URL": "redis://127.0.0.1:1/15",
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": "1",
            "CHROMA_HOST": "127.0.0.1",
            "CHROMA_PORT": "1",
            "UPLOAD_DIR": str(Path(scratch) / "storage"),
            "LANGCHAIN_TRACING_V2": "false",
        })
        from backend.app.core.config import Settings

        # Prevent implicit production .env loading. Explicit fixture settings
        # and explicitly supplied env_file arguments remain available to tests.
        Settings.model_config = {**Settings.model_config, "env_file": None}
        import pytest

        faulthandler.dump_traceback_later(60, repeat=True)
        try:
            return pytest.main(["-c", str(root / "pytest.ini"), "-o", f"cache_dir={scratch}/pytest-cache", *resolved_args])
        finally:
            faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    raise SystemExit(main())
