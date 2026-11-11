"""Reproducible local/test verification. Never operates on the application DB."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--migration-roundtrip', action='store_true', help='Deletes only supervisor test evidence by downgrading to 010 and re-upgrading.')
    parser.add_argument('--output', default='/verification/learning-evidence')
    parser.add_argument('tests', nargs='*')
    args = parser.parse_args()
    # Tests drive a real worker explicitly under a distinct non-superuser role.
    # Session-scoped legacy TestClients must not race those deterministic claims.
    os.environ['BACKGROUND_WORKER_ENABLED'] = 'false'
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    url = make_url(os.environ.get('DATABASE_URL', ''))
    if url.database != 'analyst_setup_test' or url.username != 'setup' or os.environ.get('ENVIRONMENT') != 'test':
        raise SystemExit('Refusing verification outside the dedicated test database/identity.')
    from backend.app.core.config import Settings, get_settings
    Settings.model_config = {**Settings.model_config, 'env_file': None}
    get_settings.cache_clear()
    for key in ('GROQ_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY','LANGSMITH_API_KEY'):
        os.environ.pop(key, None)
    output = Path(args.output).resolve(); output.mkdir(parents=True, exist_ok=True)
    os.environ['LEARNING_EVIDENCE_DIR'] = str(output)
    from alembic import command
    from alembic.config import Config
    config = Config(str(ROOT/'alembic.ini'))
    config.set_main_option('script_location',str(ROOT/'migrations'))
    command.upgrade(config, 'head')
    if args.migration_roundtrip:
        command.downgrade(config, '010_workspace_authorization_tables')
        command.upgrade(config, 'head')
    command.upgrade(config,'head')
    engine = create_engine(get_settings().postgres_dsn)
    with engine.connect() as conn:
        from backend.app.database.schema_contract import inspect_schema
        schema = inspect_schema(conn)
        assert schema['compatible'], schema
        version = conn.scalar(text('SHOW server_version'))
    inventory = {p:importlib.metadata.version(p) for p in ('fastapi','pydantic','SQLAlchemy','alembic','pandas','redis','chromadb','groq','pytest')}
    (output/'environment.json').write_text(json.dumps({'installed':inventory,'postgresql':version,'schema':schema,
        'migration_roundtrip':args.migration_roundtrip,'database_scope':'isolated synthetic local/test only'},indent=2))
    selected = args.tests or ['tests/test_schema_contract.py','tests/test_authenticated_dataset_isolation.py',
        'backend/tests/test_analysis_history_and_reports.py','backend/tests/test_distribution_chart_recovery.py',
        'backend/tests/test_upload_and_pipeline_recovery.py','backend/tests/test_verified_learning_engine.py',
        'backend/tests/test_verified_learning_integration.py']
    paths = [str(ROOT/p) for p in selected]
    # Writable, disposable storage; no user records or repo datasets are opened.
    with tempfile.TemporaryDirectory(prefix='learning-tests-') as scratch:
        os.chdir(scratch); os.environ['UPLOAD_DIR'] = str(Path(scratch)/'storage'); get_settings.cache_clear()
        import pytest
        result = pytest.main(['-c',str(ROOT/'pytest.ini'),'-o',f'cache_dir={scratch}/cache',
                             f'--junitxml={output}/pytest.xml', *paths])
    engine.dispose()
    (output/'verification.json').write_text(json.dumps({'pytest_exit_code':int(result),
        'baseline_before_changes':'47 passed in 26.32s; existing local/test suite',
        'scope':'Deterministic synthetic fixtures, API integration, PostgreSQL non-superuser application/worker roles',
        'production_accuracy_gain':'not measured','numeric_calibration':'unavailable','weight_training':'not performed'},indent=2))
    return int(result)


if __name__ == '__main__':
    raise SystemExit(main())
