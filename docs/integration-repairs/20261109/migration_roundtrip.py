"""Upgrade/downgrade only the restored review copy; fingerprint original rows."""
import json
import os
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from backend.app.core.config import Settings, get_settings

Settings.model_config = {**Settings.model_config, 'env_file': None}
get_settings.cache_clear()
source = make_url(os.environ['DATABASE_URL'])
assert source.username == 'setup' and source.database == 'analyst_setup_test'
review = source.set(database='integration_repair_copy_20261109')
engine = create_engine(review)
config = Config('/repo/alembic.ini')
config.set_main_option('script_location', '/repo/migrations')
config.attributes['database_url'] = review.render_as_string(hide_password=False)
config.attributes['database_schema'] = 'public'

def fingerprints(names):
    with engine.connect() as connection:
        connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        result = {}
        for name in names:
            quoted = connection.dialect.identifier_preparer.quote(name)
            result[name] = tuple(connection.execute(text(
                "SELECT count(*), md5(coalesce(string_agg(h, '' ORDER BY h), '')) "
                f"FROM (SELECT md5(row_to_json(t)::text) AS h FROM {quoted} t) rows")).one())
        return result

names = [name for name in inspect(engine).get_table_names()
         if name not in {'alembic_version', 'auth_token_revocations'}]
before = fingerprints(names)
for operation, revision in [('upgrade', 'head'), ('downgrade', '019_dataplane'), ('upgrade', 'head')]:
    getattr(command, operation)(config, revision)
    assert fingerprints(names) == before, 'Original table rows changed during migration'
    print(json.dumps({'operation': operation, 'revision': revision,
                      'preserved_tables': len(names), 'preserved_rows': sum(value[0] for value in before.values())}))
engine.dispose()
