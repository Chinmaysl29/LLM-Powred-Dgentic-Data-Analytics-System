"""Reviewed failure provenance and revocation; no runtime writes."""
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Table, Uuid, UniqueConstraint, text
from backend.app.models.base import Base

failure_memory_links = Table(
    "failure_memory_links", Base.metadata,
    Column("mistake_id", Uuid, ForeignKey("mistakes.id"), primary_key=True),
    Column("feedback_id", Uuid, ForeignKey("feedback_events.id"), nullable=False),
    Column("tenant_id", Uuid, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Uuid, ForeignKey("workspaces.id"), nullable=False, index=True),
    Column("actor_id", Uuid, ForeignKey("users.id"), nullable=False, index=True),
    Column("reviewer_id", Uuid, ForeignKey("users.id"), nullable=False, index=True),
    Column("dataset_id", String(36), ForeignKey("datasets.dataset_id"), nullable=False, index=True),
    Column("dataset_version", Integer, nullable=False),
    Column("schema_hash", String(64), nullable=False),
    Column("payload_digest", String(64), nullable=False),
    Column("active", Boolean, nullable=False, server_default=text("true")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("revoked_at", DateTime(timezone=True)),
    Column("revoked_by", Uuid, ForeignKey("users.id"), index=True),
    UniqueConstraint("feedback_id", name="uq_failure_memory_feedback"),
    CheckConstraint("dataset_version > 0", name="ck_failure_memory_version"),
)
Index("ix_failure_memory_scope", failure_memory_links.c.tenant_id, failure_memory_links.c.actor_id,
      failure_memory_links.c.dataset_id, failure_memory_links.c.dataset_version)
