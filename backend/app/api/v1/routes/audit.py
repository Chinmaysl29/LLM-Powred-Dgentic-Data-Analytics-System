"""Query and record audit events for Phase 16.5."""

import csv
import io
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.core.security import get_current_user
from backend.app.services.audit_trail_service import audit_trail_service


router = APIRouter(prefix="/audit", tags=["Audit Trail"])


class AuditRecordRequest(BaseModel):
    actor: str = Field(..., min_length=1, max_length=255)
    action: str = Field(..., min_length=1, max_length=100)
    resource_type: str = Field(..., min_length=1, max_length=100)
    resource_id: str | None = Field(default=None, max_length=255)
    details: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    actor_type: str = Field(default="user", max_length=50)
    status: str = Field(default="success", max_length=32)


@router.post("", status_code=status.HTTP_201_CREATED)
def record_audit_event(
    payload: AuditRecordRequest,
    request: Request,
    session: Session | None = Depends(get_db_session),
    user=Depends(get_current_user),
) -> dict[str, Any]:
    return audit_trail_service.record(
        **{**payload.model_dump(), 'actor': str(user.id), 'actor_type': 'user'},
        request_id=getattr(request.state, "request_id", request.headers.get("X-Request-ID")),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        session=session,
    )


def _filters(
    actor: str | None, action: str | None, resource_type: str | None, resource_id: str | None,
    event_status: str | None, search: str | None, start_at: datetime | None, end_at: datetime | None,
) -> dict[str, Any]:
    return {"actor": actor, "action": action, "resource_type": resource_type, "resource_id": resource_id,
            "status": event_status, "search": search, "start_at": start_at, "end_at": end_at}


@router.get("/search")
def search_audit_events(
    actor: str | None = None, action: str | None = None, resource_type: str | None = None,
    resource_id: str | None = None, event_status: str | None = Query(default=None, alias="status"),
    search: str | None = None, start_at: datetime | None = None, end_at: datetime | None = None,
    offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500),
    session: Session | None = Depends(get_db_session),
    user=Depends(get_current_user),
) -> list[dict[str, Any]]:
    return audit_trail_service.query(session=session, offset=offset, limit=limit,
        **_filters(str(user.id), action, resource_type, resource_id, event_status, search, start_at, end_at))


@router.get("/export")
def export_audit_events(
    format: str = Query(default="json", pattern="^(json|csv)$"), actor: str | None = None,
    action: str | None = None, resource_type: str | None = None, resource_id: str | None = None,
    event_status: str | None = Query(default=None, alias="status"), search: str | None = None,
    start_at: datetime | None = None, end_at: datetime | None = None,
    session: Session | None = Depends(get_db_session),
    user=Depends(get_current_user),
) -> Response:
    events = audit_trail_service.export(session=session, format=format,
        **_filters(str(user.id), action, resource_type, resource_id, event_status, search, start_at, end_at))
    if format == "json":
        return Response(content=__import__("json").dumps(events, default=str), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=audit-events.json"})
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=(events[0].keys() if events else ["id", "event_id", "actor_id", "action", "resource_type", "resource_id", "status", "occurred_at"]))
    writer.writeheader()
    writer.writerows(events)
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=audit-events.csv"})


@router.get("/{audit_id}")
def get_audit_event(audit_id: str, session: Session | None = Depends(get_db_session), user=Depends(get_current_user)) -> dict[str, Any]:
    event = audit_trail_service.get(audit_id, session)
    if event is None or str(event.get('actor_id', event.get('actor'))) != str(user.id):
        raise HTTPException(status_code=404, detail="Audit event not found")
    return event


@router.get("")
def query_audit_events(
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    event_status: str | None = Query(default=None, alias="status"),
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session | None = Depends(get_db_session),
    user=Depends(get_current_user),
) -> list[dict[str, Any]]:
    return audit_trail_service.query(
        session=session,
        actor=str(user.id),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=event_status,
        start_at=start_at,
        end_at=end_at,
        offset=offset,
        limit=limit,
    )
