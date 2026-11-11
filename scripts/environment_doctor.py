"""Read-only container diagnostics. Output contains no configuration secrets."""
from __future__ import annotations

import ctypes
from importlib import metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path.cwd() if __file__ == "<stdin>" else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from packaging.requirements import Requirement
    checks = []

    def record(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    record("python", sys.version_info[:2] == (3, 11), f"{sys.version.split()[0]} at {sys.executable}")
    mismatches = []
    count = 0
    for line in (ROOT / "backend/requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        req = Requirement(line)
        if req.marker and not req.marker.evaluate():
            continue
        count += 1
        try:
            installed = metadata.version(req.name)
            if installed not in req.specifier:
                mismatches.append(req.name)
        except metadata.PackageNotFoundError:
            mismatches.append(req.name)
    record("declared_packages", not mismatches, {"checked": count, "missing_or_incompatible": mismatches})
    result = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
    record("dependency_consistency", result.returncode == 0,
           "No broken requirements" if result.returncode == 0 else "Run python -m pip check inside the container")
    from backend.app.core.config import get_settings
    settings = get_settings()
    record("jwt_configuration", bool(settings.jwt_secret_key and settings.jwt_secret_key.get_secret_value()),
           "present" if settings.jwt_secret_key else "missing")
    from sqlalchemy import create_engine
    from backend.app.database.schema_contract import inspect_schema
    engine = None
    try:
        engine = create_engine(settings.postgres_dsn, connect_args={"connect_timeout": 5})
        with engine.connect() as connection:
            schema = inspect_schema(connection)
        record("schema", schema["compatible"], schema)
    except Exception:
        record("schema", False, "Cannot verify schema; check database availability and credentials")
    finally:
        if engine is not None:
            engine.dispose()
    for endpoint in ("health/ready", "health/rag"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:8000/{endpoint}", timeout=15) as response:
                data = json.load(response)
            record(endpoint, data.get("success", data.get("ready", False)), "reachable and compatible")
        except Exception:
            record(endpoint, False, "API probe failed; inspect service status and sanitized application logs")
    storage = Path(settings.upload_dir)
    record("upload_storage", storage.is_dir() and os.access(storage, os.W_OK), "present and writable")
    report_dir = storage / "reports"
    # A not-yet-used report directory is normal; its parent must be writable.
    record("report_storage", os.access(report_dir if report_dir.exists() else storage, os.W_OK),
           "parent writable; renderer creates report directories on use")
    try:
        ctypes.CDLL("libgomp.so.1")
        record("native_openmp", True, "libgomp available")
    except OSError:
        record("native_openmp", False, "libgomp missing")
    dist = metadata.distribution("matplotlib")
    font = dist.locate_file("matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf")
    record("report_font", Path(font).is_file(), "Matplotlib DejaVuSans.ttf")
    integrations = {name: bool(getattr(settings, name)) for name in
                    ("groq_api_key", "gemini_api_key", "openai_api_key")}
    versions = {name: metadata.version(name) for name in
                ("fastapi", "uvicorn", "sqlalchemy", "psycopg", "redis", "chromadb", "torch", "reportlab")}
    print(json.dumps({"checks": checks, "versions": versions,
                      "optional_provider_configured": integrations,
                      "worker": "In-process durable worker; check startup log and isolated job execution test",
                      "ready": all(check["ok"] for check in checks)}, indent=2))
    return 0 if all(check["ok"] for check in checks) else 1


if __name__ == "__main__":
    try:
        result = main()
    except Exception:
        # Validation and driver exceptions can contain secret-bearing inputs.
        print(json.dumps({"ready": False, "error": "Doctor could not complete; inspect configuration and installed dependencies privately"}))
        result = 1
    raise SystemExit(result)
