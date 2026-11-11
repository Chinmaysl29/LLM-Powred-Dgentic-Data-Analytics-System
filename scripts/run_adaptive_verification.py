"""Reproducible adaptive migration, regression and real trained-candidate pilot."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--migration-roundtrip',action='store_true')
    parser.add_argument('--output',default='/verification/adaptive-evidence')
    parser.add_argument('tests',nargs='*')
    args=parser.parse_args()
    from sqlalchemy import create_engine,text
    from sqlalchemy.engine import make_url
    url=make_url(os.environ.get('DATABASE_URL',''))
    if url.database!='analyst_setup_test' or url.username!='setup' or os.environ.get('ENVIRONMENT')!='test':
        raise SystemExit('Refusing adaptive verification outside the dedicated local/test database.')
    from backend.app.core.config import Settings,get_settings
    Settings.model_config={**Settings.model_config,'env_file':None}
    os.environ['BACKGROUND_WORKER_ENABLED']='false'
    for key in ('GROQ_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY','LANGSMITH_API_KEY'):
        os.environ.pop(key,None)
    get_settings.cache_clear()
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    os.environ['ADAPTIVE_EVIDENCE_DIR']=str(output)
    from alembic import command
    from alembic.config import Config
    cfg=Config(str(ROOT/'alembic.ini'));cfg.set_main_option('script_location',str(ROOT/'migrations'))
    command.upgrade(cfg,'head')
    engine=create_engine(get_settings().postgres_dsn)
    old_tables=['learning_runs','learning_feedback','learning_lessons','learning_definitions']
    if args.migration_roundtrip:
        with engine.connect() as conn:
            before={table:conn.scalar(text(f'SELECT count(*) FROM {table}')) for table in old_tables}
        command.downgrade(cfg,'011_verified_learning');command.upgrade(cfg,'head')
        with engine.connect() as conn:
            after={table:conn.scalar(text(f'SELECT count(*) FROM {table}')) for table in old_tables}
        assert before==after,'Adaptive downgrade/upgrade changed earlier learning records'
    command.upgrade(cfg,'head')
    from backend.app.database.schema_contract import inspect_schema
    with engine.connect() as conn:
        schema=inspect_schema(conn);assert schema['compatible'],schema
        postgres=conn.scalar(text('SHOW server_version'))
    inventory={name:importlib.metadata.version(name) for name in ('fastapi','pydantic','SQLAlchemy','pandas','numpy','scikit-learn','groq','sentence-transformers','pytest')}
    (output/'environment.json').write_text(json.dumps({'packages':inventory,'postgresql':postgres,'schema':schema,
        'migration_roundtrip_preserved_previous_learning':args.migration_roundtrip,
        'provider_calls':'No live provider configured; interpretation tested using explicitly mocked provider and deterministic fallback.'},indent=2))
    paths=args.tests or ['tests/test_schema_contract.py','tests/test_authenticated_dataset_isolation.py',
        'backend/tests/test_analysis_history_and_reports.py','backend/tests/test_distribution_chart_recovery.py',
        'backend/tests/test_upload_and_pipeline_recovery.py','backend/tests/test_verified_learning_engine.py',
        'backend/tests/test_verified_learning_integration.py','backend/tests/test_adaptive_skills.py','backend/tests/test_adaptive_integration.py']
    with tempfile.TemporaryDirectory(prefix='adaptive-verification-') as scratch:
        os.chdir(scratch);os.environ['UPLOAD_DIR']=str(Path(scratch)/'storage');get_settings.cache_clear()
        import pytest
        result=pytest.main(['-c',str(ROOT/'pytest.ini'),'-o',f'cache_dir={scratch}/cache',
            f'--junitxml={output}/pytest.xml',*[str(ROOT/path) for path in paths]])
    (output/'verification.json').write_text(json.dumps({'pytest_exit_code':int(result),'pre_change_baseline':'75 passed in 37.70s',
        'main_llm_and_embeddings':'frozen','selector_weights':'real CPU logistic/MLP candidates when evidence thresholds pass',
        'production_activation':'not performed; baseline retained unless declared gates pass','production_improvement':'not established'},indent=2))
    engine.dispose();return int(result)


if __name__=='__main__':
    raise SystemExit(main())
