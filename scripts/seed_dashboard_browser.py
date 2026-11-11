"""Prepare/check only synthetic read-only dashboard browser fixtures."""
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    from sqlalchemy import create_engine, select
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker
    target=make_url(os.environ['DATABASE_URL'])
    assert target.database=='analyst_setup_test' and target.host=='postgres' and os.environ['ENVIRONMENT']=='test'
    from backend.app.core.config import Settings,get_settings
    Settings.model_config={**Settings.model_config,'env_file':None};get_settings.cache_clear()
    from backend.app.models import User,Tenant,Workspace
    from backend.app.core.workspace_authorization import tenant_memberships,workspace_memberships
    from backend.tests.test_perceptron_dashboard import seed
    from backend.app.learning.tables import learner_weights,feedback_events,mistakes
    from backend.app.learning.shadow_table import shadow_predictions
    from backend.app.learning.release_table import router_releases
    from backend.app.learning.column_table import resolver_events
    from backend.app.learning.selection_table import selection_events
    engine=create_engine(target);factory=sessionmaker(engine)
    path=Path('/verification/dashboard-browser-account.json')
    if sys.argv[1]=='seed':
        from scripts.seed_learning_browser import main as create_account
        create_account()
        account=json.loads(Path('/verification/learning-browser-account.json').read_text())
        with factory() as db:
            actor=db.scalar(select(User.id).where(User.email==account['email']))
        tenant=seed({'admin':factory},{'user':actor,'workspace':UUID(account['workspace_id'])},account['dataset_id'])
        empty_tenant,empty_workspace=uuid4(),uuid4()
        with factory() as db,db.begin():
            db.execute(learner_weights.insert(),[dict(id=uuid4(),tenant_id=tenant,learner='intent_router',version=n,
                weights={},is_active=False) for n in range(2,28)])
            db.add(Tenant(id=empty_tenant,tenant_name='Empty synthetic tenant',tenant_slug=uuid4().hex,tenant_status='active'));db.flush()
            db.add(Workspace(id=empty_workspace,tenant_id=empty_tenant,workspace_name='Empty evidence workspace',workspace_slug=uuid4().hex,status='active'));db.flush()
            db.execute(tenant_memberships.insert().values(tenant_id=empty_tenant,user_id=actor,role='owner',active=True))
            db.execute(workspace_memberships.insert().values(workspace_id=empty_workspace,user_id=actor,role='owner',active=True))
        account.update(tenant_id=str(tenant),empty_workspace=str(empty_workspace))
    else:
        assert sys.argv[1]=='check'
        account=json.loads(path.read_text())
    digests={}
    with factory() as db:
        for table in (learner_weights,feedback_events,mistakes,shadow_predictions,router_releases,resolver_events,selection_events):
            rows=[dict(row) for row in db.execute(select(table).where(table.c.tenant_id==UUID(account['tenant_id']))).mappings()]
            encoded=json.dumps(sorted(rows,key=lambda row:str(row['id'])),sort_keys=True,default=str).encode()
            digests[table.name]=hashlib.sha256(encoded).hexdigest()
    if sys.argv[1]=='seed':
        account['digests']=digests;path.write_text(json.dumps(account))
        print('Synthetic dashboard fixtures ready. Account secrets remain in isolated volume.')
    else:
        assert account['digests']==digests,'Dashboard changed learning data'
        print('PASS: all seven learning tables byte-equivalent before/after browser reads for synthetic tenant')
    engine.dispose()


if __name__=='__main__':main()
