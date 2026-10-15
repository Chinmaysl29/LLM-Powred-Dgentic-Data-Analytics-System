"""Enroll browser-verified users only in the isolated acceptance database."""
import json
import sys
from uuid import UUID, uuid5, NAMESPACE_URL

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships
from backend.app.models.tenant import Tenant
from backend.app.models.workspace import Workspace
from backend.app.models.user import User


def main():
    url = make_url(get_settings().postgres_dsn)
    if url.host != 'integration-acceptance-postgres' or url.database != 'acceptance':
        raise SystemExit('Refusing enrollment outside the isolated acceptance database')
    actors = json.load(sys.stdin)
    assert len(actors) == 2 and len({a['actorId'] for a in actors}) == 2
    result = []
    with Session(create_engine(url)) as db, db.begin():
        for actor in actors:
            assert actor['login'] and actor['authStatus'] == 200
            user_id = UUID(actor['actorId'])
            user = db.get(User, user_id)
            assert user is not None and user.is_active, 'User must have authenticated with the real API'
            tenant_id = uuid5(NAMESPACE_URL, f'acceptance/tenant/{user_id}')
            workspace_id = uuid5(NAMESPACE_URL, f'acceptance/workspace/{user_id}')
            if db.get(Tenant, tenant_id) is None:
                db.add(Tenant(id=tenant_id, tenant_name=f'Synthetic acceptance {actor["account"]}',
                              tenant_slug=f'acceptance-{user_id}', tenant_status='active'))
                db.flush()
            if db.get(Workspace, workspace_id) is None:
                db.add(Workspace(id=workspace_id, tenant_id=tenant_id, workspace_name='Synthetic fixtures only',
                                 workspace_slug='synthetic-fixtures', status='active'))
                db.flush()
            for table, key, resource_id in ((tenant_memberships, 'tenant_id', tenant_id),
                                            (workspace_memberships, 'workspace_id', workspace_id)):
                existing = db.execute(select(table).where(table.c[key] == resource_id,
                                                          table.c.user_id == user_id)).first()
                if existing is None:
                    db.execute(table.insert().values(**{key: resource_id, 'user_id': user_id,
                                                        'role': 'owner', 'active': True}))
            result.append({'account': actor['account'], 'actorId': str(user_id),
                           'tenantId': str(tenant_id), 'workspaceId': str(workspace_id)})
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
