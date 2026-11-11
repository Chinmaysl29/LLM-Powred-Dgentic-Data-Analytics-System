"""Synthetic local-auth browser account and owned data; never reads user data."""
import json
import os
from pathlib import Path
import sys
import time
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def main():
    if make_url(os.environ['DATABASE_URL']).database != 'analyst_setup_test' or os.environ.get('ENVIRONMENT') != 'test':
        raise SystemExit('Dedicated synthetic test database only')
    from backend.app.core.config import Settings, get_settings
    Settings.model_config = {**Settings.model_config, 'env_file': None}; get_settings.cache_clear()
    from backend.app.models import Tenant, Workspace
    from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships
    with httpx.Client(base_url='http://api:8000',timeout=60) as client:
        for _ in range(60):
            try:
                if client.get('/health/ready').status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise SystemExit('Synthetic API not ready')
        email=f'learning-browser-{uuid4().hex[:12]}@example.com'; password=f'Test-{uuid4().hex}-9!'
        response=client.post('/api/v1/auth/register',json={'email':email,'password':password,'full_name':'Synthetic Learning Reviewer'})
        assert response.status_code==201,response.text
        user=UUID(response.json()['id']);workspace=uuid4();tenant=uuid4()
        engine=create_engine(get_settings().postgres_dsn)
        with Session(engine) as db,db.begin():
            db.add(Tenant(id=tenant,tenant_name='Synthetic learning UI',tenant_slug=uuid4().hex,tenant_status='active'));db.flush()
            db.add(Workspace(id=workspace,tenant_id=tenant,workspace_name='Learning verification',workspace_slug='learning-verify',status='active'));db.flush()
            db.execute(tenant_memberships.insert().values(tenant_id=tenant,user_id=user,role='owner',active=True))
            db.execute(workspace_memberships.insert().values(workspace_id=workspace,user_id=user,role='owner',active=True))
        engine.dispose()
        login=client.post('/api/v1/auth/login',json={'email':email,'password':password});assert login.status_code==200
        client.headers['Authorization']='Bearer '+login.json()['access_token']
        uploaded=client.post(f'/api/v1/datasets/upload?workspace_id={workspace}',files={'file':('learning_ui.csv',b'region,amount,status\nNorth,100,paid\nNorth,-20,refund\nSouth,200,paid\nSouth,500,cancelled\nNorth,100,paid\nSouth,300,paid\n','text/csv')})
        assert uploaded.status_code==201,uploaded.text
        dataset=uploaded.json()['dataset_id']
        bound=client.post(f'/api/v1/datasets/{dataset}/workspace',json={'workspace_id':str(workspace)});assert bound.status_code==200
        # Account secrets live only in the isolated volume, never verification artifacts.
        Path('/verification/learning-browser-account.json').write_text(json.dumps({'email':email,'password':password,'workspace_id':str(workspace),'dataset_id':dataset}))
        print('Synthetic browser account and owned CSV ready; no account secrets printed.')


if __name__=='__main__':
    main()
