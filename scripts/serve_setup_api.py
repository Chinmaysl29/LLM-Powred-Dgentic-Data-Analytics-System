"""Serve only the isolated synthetic acceptance application."""
import os
from sqlalchemy.engine import make_url
from backend.app.core.config import Settings, get_settings

if make_url(os.environ["DATABASE_URL"]).database != "analyst_setup_test":
    raise SystemExit("Refusing to serve a non-test database")
Settings.model_config = {**Settings.model_config, "env_file": None}
# Tests drive the shared durable queue explicitly; this HTTP fixture must not
# compete with them for analysis jobs. The dataplane has its separate worker.
os.environ['BACKGROUND_WORKER_ENABLED'] = 'false'
get_settings.cache_clear()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000)
