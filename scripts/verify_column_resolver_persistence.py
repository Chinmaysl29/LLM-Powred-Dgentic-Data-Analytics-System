"""Synthetic resolver release survives isolated PostgreSQL restart; no live writes."""
import json
import os
from pathlib import Path
import sys

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
    from backend.app.models import DatasetVersion
    from backend.tests.test_verified_learning_integration import identity, dataset
    from backend.tests.test_perceptron_columns import SCHEMA, QUESTION, reviewed_cases, stage, resolve, promote
    engine = create_engine(target)
    env = {'admin': sessionmaker(engine, expire_on_commit=False), 'actors': set()}
    state_path = Path('/verification/phase6-persistence.json')
    if sys.argv[1] == 'seed':
        account = identity(env)
        ds = dataset(env, account, Path('/verification'), 'region,amount,cost\na,100,10\na,1000,100\na,-20,2\na,100,10\n')
        with env['admin']() as db, db.begin():
            db.execute(update(DatasetVersion).where(DatasetVersion.dataset_id == ds).values(metadata_snapshot=SCHEMA))
        case = (env, account, ds, reviewed_cases())
        version = stage(case)
        assert resolve(case).clarification_required
        result = promote(case, version)
        assert result['promoted'], result
        state_path.write_text(json.dumps({'actor': str(account['user']), 'dataset': ds, 'version': version}))
    else:
        assert sys.argv[1] == 'check'
    state = json.loads(state_path.read_text())
    case = (env, {'user': state['actor']}, state['dataset'], reviewed_cases())
    assert resolve(case).metric == 'amount'
    engine.dispose()
    print('PASS: approved resolver selected amount in a fresh process (' + sys.argv[1] + ')')


if __name__ == '__main__':
    main()
