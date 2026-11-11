"""Additive persistence contract, separate from existing adaptive learning."""
from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Index, Integer,
                        String, Table, Text, Uuid, UniqueConstraint, CheckConstraint, text)
from sqlalchemy.dialects.postgresql import JSONB
from backend.app.models.base import Base


learner_weights = Table(
    "learner_weights", Base.metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, ForeignKey("tenants.id"), nullable=False),
    Column("learner", String(80), nullable=False),
    Column("version", Integer, nullable=False),
    Column("weights", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("is_active", Boolean, nullable=False, server_default=text("false")),
    UniqueConstraint("tenant_id", "learner", "version", name="uq_learner_version"),
    CheckConstraint("version > 0", name="ck_learner_version_positive"),
)
Index("uq_learner_active", learner_weights.c.tenant_id, learner_weights.c.learner,
      unique=True, postgresql_where=learner_weights.c.is_active.is_(True))


def evidence_columns():
    return [
        Column("id", Uuid, primary_key=True),
        Column("tenant_id", Uuid, ForeignKey("tenants.id"), nullable=False),
        Column("workspace_id", Uuid, ForeignKey("workspaces.id"), nullable=False, index=True),
        Column("actor_id", Uuid, ForeignKey("users.id"), nullable=False, index=True),
        Column("dataset_schema_hash", String(64)),
        # Raw questions are deliberately omitted in Phase 1; only their digest is retained.
        Column("question", Text),
        Column("question_hash", String(64), nullable=False),
        Column("features", JSONB, nullable=False),
        Column("predicted", String(80)),
        Column("truth", String(80)),
        Column("signal_type", String(40), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ]


feedback_events = Table("feedback_events", Base.metadata, *evidence_columns())
mistakes = Table("mistakes", Base.metadata, *evidence_columns(),
                 Column("error_type", String(80), nullable=False), Column("corrected_plan", JSONB))
for table in (learner_weights, feedback_events, mistakes):
    Index(f"ix_{table.name}_tenant_created", table.c.tenant_id, table.c.created_at)
