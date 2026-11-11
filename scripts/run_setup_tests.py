"""Run existing integration tests in a separate database and disposable storage."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from sqlalchemy.engine import make_url
    url = make_url(os.environ.get("DATABASE_URL", ""))
    if url.database != "analyst_setup_test" or url.username != "setup":
        raise SystemExit("Refusing tests outside the dedicated setup database")
    for key in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY"):
        os.environ.pop(key, None)
    from backend.app.core.config import Settings, get_settings
    Settings.model_config = {**Settings.model_config, "env_file": None}
    get_settings.cache_clear()
    from alembic import command
    from alembic.config import Config
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")  # Repeated setup must be a no-op.
    selected = sys.argv[1:] or [
        "tests/test_schema_contract.py",
        "tests/test_authenticated_dataset_isolation.py",
        "backend/tests/test_analysis_history_and_reports.py",
        "backend/tests/test_distribution_chart_recovery.py",
        "backend/tests/test_upload_and_pipeline_recovery.py",
    ]
    paths = []
    for value in selected:
        filename, separator, node = value.partition('::')
        candidate = ROOT / filename
        paths.append(str(candidate) + separator + node if candidate.exists() else value)
    with tempfile.TemporaryDirectory(prefix="setup-tests-") as scratch:
        os.chdir(scratch)
        os.environ["UPLOAD_DIR"] = str(Path(scratch) / "storage")
        get_settings.cache_clear()
        import pytest
        return pytest.main(["-c", str(ROOT / "pytest.ini"), "-o", f"cache_dir={scratch}/cache", *paths])


if __name__ == "__main__":
    raise SystemExit(main())
