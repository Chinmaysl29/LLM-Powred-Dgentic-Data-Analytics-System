"""Durable analysis evidence, separate from disposable execution leases."""
from uuid import uuid4
from sqlalchemy import String, Integer, JSON, DateTime, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.models.base import Base
from backend.app.models.background_job import utcnow

class AnalysisRun(Base):
    __tablename__ = 'analysis_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[object] = mapped_column(Uuid, ForeignKey('background_jobs.id'), unique=True)
    workspace_id: Mapped[object] = mapped_column(Uuid, ForeignKey('workspaces.id'), index=True)
    owner_id: Mapped[object] = mapped_column(Uuid, ForeignKey('users.id'))
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey('datasets.dataset_id'))
    version_number: Mapped[int] = mapped_column(Integer)
    query: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(20), default='PENDING')
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)

class AnalysisStage(Base):
    __tablename__ = 'analysis_stages'
    __table_args__ = (UniqueConstraint('run_id', 'number'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey('analysis_runs.id'))
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default='PENDING')
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(200))

class AnalysisArtifact(Base):
    __tablename__ = 'analysis_artifacts'
    __table_args__ = (UniqueConstraint('run_id', 'stage_number'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey('analysis_runs.id'))
    stage_number: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)

class AnalysisEvent(Base):
    __tablename__ = 'analysis_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey('analysis_runs.id'))
    stage_number: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
