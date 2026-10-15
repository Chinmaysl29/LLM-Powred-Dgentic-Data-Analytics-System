"""Persisted, deny-by-default workspace authorization.

The additive tables are deliberately separate from the deployed model metadata.
Their reviewed migration is staged under migrations/proposed; absent tables deny
requests with 503, never fall back to client claims or filesystem membership.
"""
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Boolean, Column, ForeignKey, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import UUID as UUIDType
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.core.security import get_current_user
from backend.app.database.postgres import get_db_session
from backend.app.models.dataset import Dataset
from backend.app.models.tenant import Tenant
from backend.app.models.user import User
from backend.app.models.workspace import Workspace

authorization_metadata = MetaData()
tenant_memberships = Table(
    'tenant_memberships', authorization_metadata,
    Column('tenant_id', UUIDType(as_uuid=True), ForeignKey(Tenant.id), primary_key=True),
    Column('user_id', UUIDType(as_uuid=True), ForeignKey(User.id), primary_key=True),
    Column('role', String(20), nullable=False),
    Column('active', Boolean, nullable=False, default=True),
)
workspace_memberships = Table(
    'workspace_memberships', authorization_metadata,
    Column('workspace_id', UUIDType(as_uuid=True), ForeignKey(Workspace.id), primary_key=True),
    Column('user_id', UUIDType(as_uuid=True), ForeignKey(User.id), primary_key=True),
    Column('role', String(20), nullable=False),
    Column('active', Boolean, nullable=False, default=True),
)
dataset_workspace_bindings = Table(
    'dataset_workspace_bindings', authorization_metadata,
    Column('dataset_id', String(36), ForeignKey(Dataset.dataset_id), primary_key=True),
    Column('workspace_id', UUIDType(as_uuid=True), ForeignKey(Workspace.id), nullable=False),
)

ROLES = {'read': {'viewer', 'analyst', 'admin', 'owner'},
         'write': {'analyst', 'admin', 'owner'}, 'manage': {'admin', 'owner'}}


def identifier(value) -> UUID:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(404, 'Resource not found') from None


def rows(db, statement):
    if db is None:
        raise HTTPException(503, 'Authorization storage is unavailable')
    try:
        return db.execute(statement).all()
    except SQLAlchemyError:
        # Do not leak SQL, credentials or membership existence.
        raise HTTPException(503, 'Authorization storage is unavailable') from None


def authorize_tenant(db, actor_id, tenant_id, permission='read'):
    actor, tenant = identifier(actor_id), identifier(tenant_id)
    records = rows(db, select(tenant_memberships.c.role).join(
        Tenant, Tenant.id == tenant_memberships.c.tenant_id).join(
        User, User.id == tenant_memberships.c.user_id).where(
        tenant_memberships.c.tenant_id == tenant, tenant_memberships.c.user_id == actor,
        tenant_memberships.c.active.is_(True), User.is_active.is_(True),
        Tenant.tenant_status == 'active'))
    if not records:
        raise HTTPException(404, 'Resource not found')
    if records[0][0] not in ROLES[permission]:
        raise HTTPException(403, 'Permission denied')
    return tenant


@dataclass(frozen=True)
class WorkspaceAccess:
    actor_id: UUID
    workspace_id: UUID
    tenant_id: UUID
    role: str


def authorize_workspace(db, actor_id, workspace_id, permission='read') -> WorkspaceAccess:
    actor, workspace = identifier(actor_id), identifier(workspace_id)
    wm, tm = workspace_memberships.c, tenant_memberships.c
    records = rows(db, select(Workspace.tenant_id, tm.role, wm.role).select_from(Workspace)
        .join(Tenant, Tenant.id == Workspace.tenant_id)
        .join(tenant_memberships, (tm.tenant_id == Workspace.tenant_id) & (tm.user_id == actor) & tm.active.is_(True))
        .join(User, (User.id == actor) & User.is_active.is_(True))
        .outerjoin(workspace_memberships, (wm.workspace_id == Workspace.id) & (wm.user_id == actor) & wm.active.is_(True))
        .where(Workspace.id == workspace, Workspace.status == 'active', Tenant.tenant_status == 'active'))
    if not records:
        raise HTTPException(404, 'Resource not found')
    tenant, tenant_role, workspace_role = records[0]
    role = tenant_role if tenant_role in {'owner', 'admin'} else workspace_role
    if tenant_role not in ROLES['read'] or role not in ROLES['read']:
        raise HTTPException(404, 'Resource not found')
    if role not in ROLES[permission]:
        raise HTTPException(403, 'Permission denied')
    return WorkspaceAccess(actor, workspace, tenant, role)


def authorize_bound_dataset(db, access: WorkspaceAccess, dataset_id: str):
    # Account ownership remains required; membership alone never widens dataset access.
    records = rows(db, select(Dataset.dataset_id).join(dataset_workspace_bindings,
        dataset_workspace_bindings.c.dataset_id == Dataset.dataset_id).where(
        Dataset.dataset_id == dataset_id, Dataset.owner_id == str(access.actor_id),
        dataset_workspace_bindings.c.workspace_id == access.workspace_id))
    if not records:
        raise HTTPException(404, 'Resource not found')


async def require_os_workspace(request: Request, user=Depends(get_current_user),
                               db: Session = Depends(get_db_session)):
    """Authorize scoped OS routes before a service can open any artifact."""
    path = request.url.path.removeprefix('/api/v1/os')
    if request.method == 'GET' and path in {'/marketplace/templates', '/semantic/glossary', '/kpis/catalog'}:
        return
    # These legacy operations write global state or accept self-asserted owners.
    if path.startswith(('/workspaces', '/portfolio', '/demo', '/telemetry', '/analyst', '/marketplace/templates/')):
        raise HTTPException(503, 'This operation requires verified workspace persistence')
    body = {}
    if request.method in {'POST', 'PUT', 'PATCH'}:
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(422, 'Invalid JSON request') from None
        if not isinstance(body, dict):
            raise HTTPException(422, 'Invalid JSON request')
    values = [v for v in (request.path_params.get('workspace_id'),
        request.query_params.get('workspace_id'), body.get('workspace_id')) if v is not None]
    if not values or len({str(identifier(v)) for v in values}) != 1:
        raise HTTPException(404, 'Resource not found')
    access = authorize_workspace(db, user.id, values[0], 'read' if request.method in {'GET', 'HEAD'} else 'write')
    if body.get('dataset_id'):
        authorize_bound_dataset(db, access, str(body['dataset_id']))
    request.state.workspace_access = access


async def deny_unverified_enterprise(user=Depends(get_current_user)):
    """In-memory enterprise identities are not an authorization authority."""
    raise HTTPException(503, 'Enterprise authorization persistence is not configured')
