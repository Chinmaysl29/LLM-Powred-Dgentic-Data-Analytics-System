"""Operator-written release history; runtime roles have read access only."""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Identity, Index, Integer, String, Table, Uuid, CheckConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from backend.app.models.base import Base

router_releases = Table(
    "router_releases", Base.metadata,
    Column("id", BigInteger, Identity(), primary_key=True),
    Column("tenant_id", Uuid, ForeignKey("tenants.id"), nullable=False),
    Column("actor_id", Uuid, ForeignKey("users.id"), nullable=False, index=True),
    Column("action", String(20), nullable=False),
    Column("version", Integer, nullable=False),
    Column("previous_version", Integer, nullable=False),
    Column("model_digest", String(64)),
    Column("runtime_digest", String(64), nullable=False),
    Column("evidence", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), server_default=text("now()"), nullable=False),
    CheckConstraint("version >= 0 AND previous_version >= 0", name="ck_router_release_versions"),
    CheckConstraint("action IN ('stage','promote','rollback','disable')", name="ck_router_release_action"),
)
Index("ix_router_releases_tenant_id", router_releases.c.tenant_id, router_releases.c.id)
