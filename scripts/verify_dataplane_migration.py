"""Verify Dataplane upgrade/downgrade/upgrade in the isolated database only."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.engine import make_url
    from alembic import command
    from alembic.config import Config
    from backend.app.core.config import Settings, get_settings
    Settings.model_config = {**Settings.model_config, "env_file": None}
    get_settings.cache_clear()
    target = make_url(os.environ["DATABASE_URL"])
    if (target.database != "analyst_setup_test" or target.username != "setup"
            or target.host != "postgres" or os.environ.get("ENVIRONMENT") != "test"):
        raise SystemExit("Refusing migration roundtrip outside isolated setup database")
    engine = create_engine(target)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))

    def snapshot():
        with engine.connect() as db:
            inspector = inspect(db)
            result = {}
            for name in inspector.get_table_names():
                if name in {"dataplane_artifacts", "alembic_version"}:
                    continue
                quoted = engine.dialect.identifier_preparer.quote(name)
                result[name] = {
                    "columns": [(col["name"], str(col["type"]), col["nullable"]) for col in inspector.get_columns(name)],
                    "pk": inspector.get_pk_constraint(name), "fk": inspector.get_foreign_keys(name),
                    "indexes": inspector.get_indexes(name),
                    "count": db.scalar(text(f"SELECT count(*) FROM {quoted}")),
                    "policies": db.execute(text("SELECT policyname, cmd, qual, with_check FROM pg_policies WHERE schemaname=current_schema() AND tablename=:name ORDER BY policyname"), {"name": name}).all(),
                }
            return result

    before = snapshot()
    command.upgrade(config, "019_dataplane")
    assert "dataplane_artifacts" in inspect(engine).get_table_names()
    assert snapshot() == before
    command.downgrade(config, "018_selection_policies")
    assert "dataplane_artifacts" not in inspect(engine).get_table_names()
    assert snapshot() == before
    command.upgrade(config, "019_dataplane")
    assert "dataplane_artifacts" in inspect(engine).get_table_names()
    assert snapshot() == before
    engine.dispose()
    print(f"PASS: upgrade / downgrade / upgrade; {len(before)} existing tables unchanged, including policies and row counts")


if __name__ == "__main__":
    main()
