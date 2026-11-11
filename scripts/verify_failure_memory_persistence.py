"""Seed/check synthetic memory across a separate verification Chroma restart."""
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from sqlalchemy import create_engine, update
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker
    target = make_url(os.environ['DATABASE_URL'])
    assert target.database == 'analyst_setup_test' and target.username == 'setup' and target.host == 'postgres'
    assert os.environ.get('ENVIRONMENT') == 'test'
    from backend.app.core.config import Settings, get_settings
    Settings.model_config = {**Settings.model_config, 'env_file': None}
    get_settings.cache_clear()
    get_settings().learning_enabled = True
    from backend.app.learning import evidence, failure_memory, memory_review
    from backend.app.models import DatasetVersion
    from backend.tests.test_verified_learning_integration import identity, dataset
    engine = create_engine(str(target.render_as_string(hide_password=False)))
    env = {'admin': sessionmaker(engine, expire_on_commit=False), 'actors': set()}
    state_path = Path('/verification/phase5-persistence.json')
    question = 'Explore the dataset schema and inspect missing values across all columns'
    plan = {'format': 1, 'intent': 'dataset_overview', 'add_steps': ['validation']}
    if sys.argv[1] == 'seed':
        account = identity(env)
        ds = dataset(env, account, Path('/verification'))
        with env['admin']() as db, db.begin():
            db.execute(update(DatasetVersion).where(DatasetVersion.dataset_id == ds).values(
                metadata_snapshot={'columns': ['region', 'amount', 'status'],
                    'dtypes': {'region': 'object', 'amount': 'int64', 'status': 'object'}}))
        event = uuid4()
        assert evidence.record_failure(actor_id=str(account['user']), dataset_id=ds,
            question=question, error_type='validator_rejection', event_id=event)
        result = memory_review.approve(env['admin'], account['user'], event, ds, 1, question, plan)
        assert result['indexed'], result
        state_path.write_text(json.dumps({'actor': str(account['user']), 'dataset': ds}))
    else:
        assert sys.argv[1] == 'check'
    state = json.loads(state_path.read_text())
    assert failure_memory.retrieve_sync(state['actor'], state['dataset'], question, plan['intent']) == [plan]
    engine.dispose()
    print('PASS: synthetic reviewed memory retrieved in a fresh process (' + sys.argv[1] + ')')


if __name__ == '__main__':
    main()
