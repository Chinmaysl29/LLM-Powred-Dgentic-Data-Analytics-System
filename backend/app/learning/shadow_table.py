"""Append-only shadow comparisons, separate from trusted teacher feedback."""
from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index,
                        Integer, String, Table, Uuid, text)
from sqlalchemy.dialects.postgresql import JSONB
from backend.app.models.base import Base

shadow_predictions = Table(
    "shadow_predictions", Base.metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, ForeignKey("tenants.id"), nullable=False),
    Column("workspace_id", Uuid, ForeignKey("workspaces.id"), nullable=False, index=True),
    Column("actor_id", Uuid, ForeignKey("users.id"), nullable=False, index=True),
    Column("dataset_id", String(36), ForeignKey("datasets.dataset_id"), nullable=False, index=True),
    Column("dataset_version", Integer, nullable=False),
    Column("dataset_schema_hash", String(64)),
    Column("question_hash", String(64), nullable=False),
    Column("feature_version", String(64), nullable=False),
    Column("features", JSONB, nullable=False),
    Column("source", String(20), nullable=False),
    Column("live_route", String(20), nullable=False),
    Column("live_intent", String(80)),
    Column("live_operation", String(30)),
    Column("shadow_intent", String(80), nullable=False),
    Column("candidate_intent", String(80), nullable=False),
    Column("margin", Float, nullable=False),
    Column("abstained", Boolean, nullable=False),
    Column("model_source", String(30), nullable=False),
    Column("model_version", Integer),
    Column("rejected_version", Integer),
    Column("model_digest", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    CheckConstraint("dataset_version > 0", name="ck_shadow_dataset_version"),
    CheckConstraint("margin >= 0 AND margin < 'Infinity'::float8", name="ck_shadow_finite_margin"),
)
Index("ix_shadow_predictions_tenant_created", shadow_predictions.c.tenant_id, shadow_predictions.c.created_at)
