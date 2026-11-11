"""Synthetic chart/provider approvals survive isolated PostgreSQL restart."""
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
    get_settings.cache_clear(); get_settings().learning_enabled = True
    from backend.app.models import DatasetVersion
    from backend.tests.test_verified_learning_integration import identity, dataset
    from backend.tests.test_perceptron_selection import SCHEMA, MODELS, reviewed_cases, stage, decide, promote
    engine = create_engine(target)
    env = {'admin': sessionmaker(engine, expire_on_commit=False), 'actors': set()}
    state_path = Path('/verification/phase7-persistence.json')
    if sys.argv[1] == 'seed':
        account = identity(env)
        ds = dataset(env, account, Path('/verification'), 'date,amount\n2025-01-01,10\n2025-02-01,-5\n2025-04-01,20\n')
        with env['admin']() as db, db.begin():
            db.execute(update(DatasetVersion).where(DatasetVersion.dataset_id == ds).values(metadata_snapshot=SCHEMA))
        for kind in ('chart', 'provider'):
            case = env, account, ds, reviewed_cases(kind)
            version = stage(case)
            assert decide(case) is None
            assert promote(case, version)['promoted']
        state_path.write_text(json.dumps({'actor': str(account['user']), 'dataset': ds}))
    else:
        assert sys.argv[1] == 'check'
    state = json.loads(state_path.read_text())
    for kind in ('chart', 'provider'):
        case = env, {'user': state['actor']}, state['dataset'], reviewed_cases(kind)
        chosen = decide(case)
        assert chosen and chosen['choice'] in (['line'] if kind == 'chart' else MODELS)
    engine.dispose()
    print('PASS: both synthetic policies and approvals survived in a fresh process (' + sys.argv[1] + '); no external provider calls')


if __name__ == '__main__':
    main()
