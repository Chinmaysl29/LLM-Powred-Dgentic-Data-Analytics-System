"""Durable supervisor authority. JSON stores versioned validated contracts, not prompts."""
from uuid import UUID, uuid4

from sqlalchemy import (DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON,
                        String, UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base
from backend.app.models.background_job import utcnow


class Scoped:
    workspace_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('workspaces.id'), index=True)


class LearningRun(Scoped, Base):
    __tablename__ = 'learning_runs'
    __table_args__ = (UniqueConstraint('id', 'workspace_id'),)
    id: Mapped[str] = mapped_column(String(36), ForeignKey('analysis_runs.id'), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'))
    state: Mapped[str] = mapped_column(String(30), default='queued')
    mode: Mapped[str] = mapped_column(String(20), default='disabled')
    task: Mapped[dict | None] = mapped_column(JSON)
    budget: Mapped[dict] = mapped_column(JSON)
    schema_hash: Mapped[str | None] = mapped_column(String(64))
    source_hash: Mapped[str | None] = mapped_column(String(64))
    memory_cutoff: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    lesson_snapshot: Mapped[list] = mapped_column(JSON, default=list)
    applied_lessons: Mapped[list] = mapped_column(JSON, default=list)
    bundle_id: Mapped[str | None] = mapped_column(String(36))
    repairs: Mapped[int] = mapped_column(Integer, default=0)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    repair_reservations: Mapped[list] = mapped_column(JSON, default=list)
    plan: Mapped[dict | None] = mapped_column(JSON)
    outcome: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))


class LearningAttempt(Scoped, Base):
    __tablename__ = 'learning_attempts'
    __table_args__ = (
        UniqueConstraint('run_id', 'stage', 'number'),
        ForeignKeyConstraint(['run_id', 'workspace_id'], ['learning_runs.id', 'learning_runs.workspace_id']),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36))
    stage: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    evidence: Mapped[dict] = mapped_column(JSON)


class LearningFeedback(Scoped, Base):
    __tablename__ = 'learning_feedback'
    __table_args__ = (
        UniqueConstraint('workspace_id', 'actor_id', 'idempotency_key'),
        ForeignKeyConstraint(['run_id', 'workspace_id'], ['learning_runs.id', 'learning_runs.workspace_id']),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36))
    actor_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningLesson(Scoped, Base):
    __tablename__ = 'learning_lessons'
    __table_args__ = (
        UniqueConstraint('id', 'workspace_id'), UniqueConstraint('workspace_id', 'dedup_key'),
        ForeignKeyConstraint(['source_run_id', 'workspace_id'], ['learning_runs.id', 'learning_runs.workspace_id']),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_run_id: Mapped[str] = mapped_column(String(36))
    source_dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey('datasets.dataset_id'))
    dedup_key: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(20), default='candidate')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    schema_hash: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    verified_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    invalid_reason: Mapped[str | None] = mapped_column(String(200))


class LearningRevision(Scoped, Base):
    __tablename__ = 'learning_revisions'
    __table_args__ = (
        UniqueConstraint('lesson_id', 'number'),
        ForeignKeyConstraint(['lesson_id', 'workspace_id'], ['learning_lessons.id', 'learning_lessons.workspace_id']),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lesson_id: Mapped[str] = mapped_column(String(36))
    number: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20))
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'))
    reason: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningVerification(Scoped, Base):
    __tablename__ = 'learning_verifications'
    __table_args__ = (
        UniqueConstraint('lesson_id', 'content_hash', 'verifier_version'),
        ForeignKeyConstraint(['lesson_id', 'workspace_id'], ['learning_lessons.id', 'learning_lessons.workspace_id']),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lesson_id: Mapped[str] = mapped_column(String(36))
    content_hash: Mapped[str] = mapped_column(String(64))
    verifier_version: Mapped[str] = mapped_column(String(80))
    evidence: Mapped[dict] = mapped_column(JSON)
    passed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class BusinessDefinition(Scoped, Base):
    __tablename__ = 'learning_definitions'
    __table_args__ = (UniqueConstraint('workspace_id', 'key', 'version'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    key: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'))
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(default=True)
    governance: Mapped[dict] = mapped_column(JSON, default=dict, server_default='{}')
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningCase(Scoped, Base):
    __tablename__ = 'learning_cases'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'))
    scenario_group: Mapped[str] = mapped_column(String(100), index=True)
    split: Mapped[str] = mapped_column(String(20))
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningBundle(Scoped, Base):
    __tablename__ = 'learning_bundles'
    __table_args__ = (UniqueConstraint('workspace_id', 'content_hash'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    content: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningEvaluation(Scoped, Base):
    __tablename__ = 'learning_evaluations'
    __table_args__ = (UniqueConstraint('workspace_id', 'idempotency_key'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'))
    job_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('background_jobs.id'), unique=True)
    bundle_id: Mapped[str] = mapped_column(String(36), ForeignKey('learning_bundles.id'))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    manifest: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default='queued')
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningControl(Scoped, Base):
    __tablename__ = 'learning_controls'
    workspace_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('workspaces.id'), primary_key=True)
    mode: Mapped[str] = mapped_column(String(20), default='disabled')
    active_bundle_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('learning_bundles.id'))
    previous_bundle_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('learning_bundles.id'))
    rollout_percent: Mapped[int] = mapped_column(Integer, default=0)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    actor_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class LearningAudit(Scoped, Base):
    __tablename__ = 'learning_audit'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(36))
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


TABLES = [LearningRun, LearningAttempt, LearningFeedback, LearningLesson, LearningRevision,
          LearningVerification, BusinessDefinition, LearningCase, LearningBundle,
          LearningEvaluation, LearningControl, LearningAudit]
