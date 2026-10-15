"""Authoritative execution state; Redis notifications are never the source of truth."""
from datetime import datetime, timezone
from uuid import uuid4, UUID
from sqlalchemy import String, Integer, DateTime, JSON, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.models.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class DurableJob(Base):
    __tablename__ = 'background_jobs'
    __table_args__ = (UniqueConstraint('workspace_id', 'kind', 'idempotency_key', name='uq_background_job_request'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('workspaces.id'), nullable=False, index=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default='QUEUED', nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_eligible: Mapped[bool] = mapped_column(default=True, nullable=False)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
