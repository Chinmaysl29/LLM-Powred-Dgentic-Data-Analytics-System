"""Disable residual synthetic schedules with immutable history, never production."""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    target = make_url(os.environ['DATABASE_URL'])
    if target.database != 'analyst_setup_test' or target.host != 'postgres' or os.environ.get('ENVIRONMENT') != 'test':
        raise SystemExit('Known isolated synthetic database only')
    from backend.app.core.config import Settings, get_settings
    Settings.model_config = {**Settings.model_config, 'env_file': None}
    get_settings.cache_clear()
    from backend.app.dataplane.records import artifacts, scoped, add_record
    from backend.app.dataplane.company import current_event, lock_artifact
    from backend.app.services.learning_supervisor import audit
    engine = create_engine(get_settings().postgres_dsn)
    count = 0
    with Session(engine) as db:
        rows = db.execute(select(artifacts.c.parent_id, artifacts.c.actor_id, artifacts.c.workspace_id)
            .where(artifacts.c.kind == 'schedule').distinct()).all()
    for identity, actor, workspace in rows:
        with Session(engine) as db, db.begin():
            access = scoped(db, actor, workspace, 'manage')
            state = current_event(db, access, identity, 'schedule')
            if not state.get('enabled'):
                continue
            workflow = lock_artifact(db, access, identity, 'workflow')
            value = {**state, 'enabled': False, 'revision': state['revision']+1,
                     'configured_at': datetime.now(timezone.utc).isoformat()}
            add_record(db, access, 'schedule', value, dataset_id=workflow['dataset_id'], parent_id=identity)
            audit(db, access, 'workflow_schedule', str(identity), enabled=False, revision=value['revision'],
                  reason='Disable residual controlled-clock verification schedule; retain its history')
            count += 1
    engine.dispose()
    print(f'Disabled {count} residual synthetic schedules with retained history.')


if __name__ == '__main__':
    main()
