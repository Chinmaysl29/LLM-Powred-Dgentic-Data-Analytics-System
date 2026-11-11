"""Create only a synthetic coworker in the existing isolated browser workspace."""
import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid4
import httpx
from sqlalchemy import create_engine
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
    from backend.app.models import Workspace
    from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships
    path = Path('/verification/learning-browser-account.json')
    account = json.loads(path.read_text())
    email, password = f'company-review-{uuid4().hex[:12]}@example.com', f'Test-{uuid4().hex}-9!'
    with httpx.Client(base_url='http://api:8000', timeout=60) as client:
        response = client.post('/api/v1/auth/register', json={'email': email, 'password': password,
            'full_name': 'Synthetic assigned company reviewer'})
        assert response.status_code == 201, response.status_code
        user_id = UUID(response.json()['id'])
    engine = create_engine(get_settings().postgres_dsn)
    with Session(engine) as db, db.begin():
        workspace = db.get(Workspace, UUID(account['workspace_id']))
        assert workspace is not None and workspace.workspace_name == 'Learning verification'
        db.execute(tenant_memberships.insert().values(tenant_id=workspace.tenant_id, user_id=user_id, role='viewer', active=True))
        db.execute(workspace_memberships.insert().values(workspace_id=workspace.id, user_id=user_id, role='viewer', active=True))
    engine.dispose()
    account['reviewer'] = {'id': str(user_id), 'email': email, 'password': password}
    path.write_text(json.dumps(account))
    print('Synthetic coworker created; credentials retained only in the isolated volume.')


if __name__ == '__main__':
    main()
