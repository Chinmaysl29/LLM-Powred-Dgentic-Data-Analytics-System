"""Repository for indexed audit-event persistence and retrieval."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from backend.app.models.audit_entry import AuditEntry


class AuditRepository:
    def create(self, session: Session, entry: AuditEntry) -> AuditEntry:
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry

    def get(self, session: Session, audit_id: str | Any) -> AuditEntry | None:
        import uuid
        parsed_id = audit_id
        if isinstance(audit_id, str):
            try:
                parsed_id = uuid.UUID(audit_id)
            except Exception:
                pass
        return session.get(AuditEntry, parsed_id)


    def query(
        self,
        session: Session,
        *,
        actor_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        status: str | None = None,
        search: str | None = None,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[AuditEntry]:
        statement: Select[tuple[AuditEntry]] = select(AuditEntry).order_by(AuditEntry.occurred_at.desc())
        if actor_id:
            statement = statement.where(AuditEntry.actor == actor_id)
        if action:
            statement = statement.where(AuditEntry.action == action)
        if resource_type:
            statement = statement.where(AuditEntry.resource_type == resource_type)
        if resource_id:
            statement = statement.where(AuditEntry.resource_id == resource_id)
        if status:
            statement = statement.where(AuditEntry.status == status)
        if start_at:
            statement = statement.where(AuditEntry.occurred_at >= start_at)
        if end_at:
            statement = statement.where(AuditEntry.occurred_at <= end_at)
        if search:
            pattern = f"%{search.strip()}%"
            statement = statement.where(or_(AuditEntry.action.ilike(pattern), AuditEntry.resource_type.ilike(pattern), AuditEntry.actor.ilike(pattern)))
        return list(session.scalars(statement.offset(max(offset, 0)).limit(max(1, min(limit, 500)))).all())
