"""REST API routes for Enterprise Workspace Management."""

from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.core.security import get_current_user
from backend.app.core.workspace_authorization import authorize_tenant, authorize_workspace
from backend.app.repositories.workspace_repository import WorkspaceRepository, get_workspace_repository
from backend.app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from backend.app.services.workspace_service import (
    DuplicateWorkspaceException,
    WorkspaceNotFoundException,
    WorkspaceService,
    WorkspaceValidationException,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces", tags=["Enterprise Workspace Management"])


def get_workspace_service(
    repo: WorkspaceRepository = Depends(get_workspace_repository),
) -> WorkspaceService:
    """Dependency provider for WorkspaceService."""
    return WorkspaceService(repository=repo)


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreate,
    service: WorkspaceService = Depends(get_workspace_service),
    user=Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Any:
    """Create a new workspace within an enterprise tenant."""
    authorize_tenant(db, user.id, payload.tenant_id, 'manage')
    try:
        return service.create_workspace(
            tenant_id=payload.tenant_id,
            workspace_name=payload.workspace_name,
            workspace_slug=payload.workspace_slug,
            description=payload.description or "",
            status=payload.status,
        )
    except DuplicateWorkspaceException as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except WorkspaceValidationException as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("", response_model=WorkspaceListResponse)
def list_workspaces(
    tenant_id: uuid.UUID = Query(..., description="Parent tenant UUID to list workspaces for"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    status: str | None = Query(default=None),
    service: WorkspaceService = Depends(get_workspace_service),
    user=Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Any:
    """List all workspaces for a given tenant."""
    authorize_tenant(db, user.id, tenant_id)
    candidates = service.list_workspaces(tenant_id=tenant_id, skip=skip, limit=limit, status=status)
    items = []
    for item in candidates:
        try:
            authorize_workspace(db, user.id, item.id)
            items.append(item)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    return {
        "items": items,
        "total": len(items),
        "skip": skip,
        "limit": limit,
    }


@router.get('/mine')
def my_workspaces(db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    from sqlalchemy import select
    from backend.app.models.workspace import Workspace
    from backend.app.core.workspace_authorization import workspace_memberships
    candidates = db.scalars(select(Workspace).join(workspace_memberships,
        workspace_memberships.c.workspace_id == Workspace.id).where(workspace_memberships.c.user_id == user.id,
        workspace_memberships.c.active.is_(True))).all()
    result = []
    for item in candidates:
        try:
            authorize_workspace(db, user.id, item.id)
            result.append({'id': str(item.id), 'workspace_name': item.workspace_name, 'tenant_id': str(item.tenant_id)})
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    return result


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: uuid.UUID,
    service: WorkspaceService = Depends(get_workspace_service),
    user=Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Any:
    """Retrieve details of a single workspace by ID."""
    authorize_workspace(db, user.id, workspace_id)
    try:
        return service.get_workspace(workspace_id)
    except WorkspaceNotFoundException as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.put("/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdate,
    repo: WorkspaceRepository = Depends(get_workspace_repository),
    user=Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> Any:
    """Update metadata or status of an existing workspace."""
    authorize_workspace(db, user.id, workspace_id, 'manage')
    updated = repo.update_workspace(
        workspace_id=workspace_id,
        workspace_name=payload.workspace_name,
        description=payload.description,
        status=payload.status,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{workspace_id}' not found",
        )
    return updated


@router.delete("/{workspace_id}", status_code=status.HTTP_200_OK)
def delete_workspace(
    workspace_id: uuid.UUID,
    repo: WorkspaceRepository = Depends(get_workspace_repository),
    user=Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Delete a workspace and all nested departmental/project assets."""
    authorize_workspace(db, user.id, workspace_id, 'manage')
    # Cascades may contain retained customer assets; use status=archived instead.
    raise HTTPException(409, 'Archive the workspace; permanent deletion requires a reviewed retention operation')
