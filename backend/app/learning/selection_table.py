"""Append-only selection shadow observations and privileged lifecycle audit."""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Identity, Index, Integer, String, Table, Uuid, CheckConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from backend.app.models.base import Base

selection_events = Table('selection_events', Base.metadata,
    Column('id', BigInteger, Identity(), primary_key=True),
    Column('tenant_id', Uuid, ForeignKey('tenants.id'), nullable=False),
    Column('workspace_id', Uuid, ForeignKey('workspaces.id'), nullable=False, index=True),
    Column('actor_id', Uuid, ForeignKey('users.id'), nullable=False, index=True),
    Column('reviewer_id', Uuid, ForeignKey('users.id'), index=True),
    Column('dataset_id', String(36), ForeignKey('datasets.dataset_id'), nullable=False, index=True),
    Column('dataset_version', Integer, nullable=False),
    Column('schema_hash', String(64), nullable=False),
    Column('kind', String(20), nullable=False),
    Column('action', String(20), nullable=False),
    Column('version', Integer, nullable=False),
    Column('previous_version', Integer, nullable=False),
    Column('model_digest', String(64)),
    Column('runtime_digest', String(64), nullable=False),
    Column('detail', JSONB, nullable=False),
    Column('created_at', DateTime(timezone=True), server_default=text('now()'), nullable=False),
    CheckConstraint("kind IN ('chart','provider')", name='ck_selection_kind'),
    CheckConstraint('version >= 0 AND previous_version >= 0 AND dataset_version > 0', name='ck_selection_versions'),
    CheckConstraint("action IN ('stage','shadow','promote','rollback','disable')", name='ck_selection_action'))
Index('ix_selection_events_tenant_version', selection_events.c.tenant_id, selection_events.c.kind, selection_events.c.version, selection_events.c.action)
