"""Tenant-local skill, decision, label and learned-weight authority."""
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.models.base import Base
from backend.app.models.background_job import utcnow
from backend.app.models.learning import Scoped


class AdaptiveSkill(Scoped, Base):
    __tablename__='adaptive_skills'
    __table_args__=(UniqueConstraint('workspace_id','skill_id','version'),UniqueConstraint('id','workspace_id'))
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    skill_id: Mapped[str]=mapped_column(String(80))
    version: Mapped[int]=mapped_column(Integer)
    state: Mapped[str]=mapped_column(String(20))
    manifest: Mapped[dict]=mapped_column(JSON)
    content_hash: Mapped[str]=mapped_column(String(64))
    test_result: Mapped[dict | None]=mapped_column(JSON)
    actor_id: Mapped[UUID]=mapped_column(Uuid,ForeignKey('users.id'))
    created_at: Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow)
    activated_at: Mapped[object | None]=mapped_column(DateTime(timezone=True))


class AdaptiveSkillRevision(Scoped, Base):
    __tablename__='adaptive_skill_revisions'
    __table_args__=(ForeignKeyConstraint(['skill_id','workspace_id'],['adaptive_skills.id','adaptive_skills.workspace_id']),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    skill_id: Mapped[str]=mapped_column(String(36))
    state: Mapped[str]=mapped_column(String(20))
    actor_id: Mapped[UUID]=mapped_column(Uuid,ForeignKey('users.id'))
    evidence: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow)


class AdaptiveCase(Scoped, Base):
    __tablename__='adaptive_cases'
    __table_args__=(UniqueConstraint('id','workspace_id'),UniqueConstraint('workspace_id','content_hash'))
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    actor_id: Mapped[UUID]=mapped_column(Uuid,ForeignKey('users.id'))
    scenario_group: Mapped[str]=mapped_column(String(100),index=True)
    split: Mapped[str]=mapped_column(String(20))
    content: Mapped[dict]=mapped_column(JSON)
    content_hash: Mapped[str]=mapped_column(String(64))
    input_hashes: Mapped[dict]=mapped_column(JSON)
    available: Mapped[bool]=mapped_column(default=True)
    created_at: Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow)


class AdaptiveWork(Scoped, Base):
    __tablename__='adaptive_work'
    __table_args__=(UniqueConstraint('workspace_id','kind','idempotency_key'),UniqueConstraint('id','workspace_id'))
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    owner_id: Mapped[UUID]=mapped_column(Uuid,ForeignKey('users.id'))
    job_id: Mapped[UUID]=mapped_column(Uuid,ForeignKey('background_jobs.id'),unique=True)
    kind: Mapped[str]=mapped_column(String(25))
    idempotency_key: Mapped[str]=mapped_column(String(128))
    manifest: Mapped[dict]=mapped_column(JSON)
    state: Mapped[str]=mapped_column(String(30),default='queued')
    result: Mapped[dict | None]=mapped_column(JSON)
    created_at: Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow)


class AdaptiveModel(Scoped, Base):
    __tablename__='adaptive_models'
    __table_args__=(UniqueConstraint('workspace_id','work_id','kind'),UniqueConstraint('id','workspace_id'))
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    work_id: Mapped[str]=mapped_column(String(36),ForeignKey('adaptive_work.id'))
    kind: Mapped[str]=mapped_column(String(20))
    state: Mapped[str]=mapped_column(String(20),default='candidate')
    bundle: Mapped[dict]=mapped_column(JSON)
    content_hash: Mapped[str]=mapped_column(String(64))
    invalid_reason: Mapped[str | None]=mapped_column(String(200))
    created_at: Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow)


class AdaptiveContext(Scoped, Base):
    __tablename__='adaptive_contexts'
    __table_args__=(ForeignKeyConstraint(['run_id','workspace_id'],['learning_runs.id','learning_runs.workspace_id']),)
    run_id: Mapped[str]=mapped_column(String(36),primary_key=True)
    content: Mapped[dict]=mapped_column(JSON)
    input_hashes: Mapped[dict]=mapped_column(JSON)
    skill_snapshot: Mapped[list]=mapped_column(JSON)
    model_id: Mapped[str | None]=mapped_column(String(36),ForeignKey('adaptive_models.id'))
    selector_mode: Mapped[str]=mapped_column(String(20))
    generation: Mapped[int]=mapped_column(Integer)
    created_at: Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow)


class AdaptiveDecision(Scoped, Base):
    __tablename__='adaptive_decisions'
    __table_args__=(UniqueConstraint('workspace_id','dedup_key'),UniqueConstraint('id','workspace_id'),
        ForeignKeyConstraint(['run_id','workspace_id'],['learning_runs.id','learning_runs.workspace_id']),
        ForeignKeyConstraint(['case_id','workspace_id'],['adaptive_cases.id','adaptive_cases.workspace_id']))
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    owner_id: Mapped[UUID]=mapped_column(Uuid,ForeignKey('users.id'))
    run_id: Mapped[str | None]=mapped_column(String(36))
    case_id: Mapped[str | None]=mapped_column(String(36))
    dedup_key: Mapped[str]=mapped_column(String(64))
    content: Mapped[dict]=mapped_column(JSON)
    features: Mapped[dict]=mapped_column(JSON)
    input_hash: Mapped[str]=mapped_column(String(64))
    created_at: Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow)


class AdaptiveOutcome(Scoped, Base):
    __tablename__='adaptive_outcomes'
    __table_args__=(ForeignKeyConstraint(['decision_id','workspace_id'],['adaptive_decisions.id','adaptive_decisions.workspace_id']),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    decision_id: Mapped[str]=mapped_column(String(36),unique=True)
    content: Mapped[dict]=mapped_column(JSON)
    label_status: Mapped[str]=mapped_column(String(20))
    revision: Mapped[int]=mapped_column(Integer,default=1)
    created_at: Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow)


class AdaptiveLabelRevision(Scoped, Base):
    __tablename__='adaptive_label_revisions'
    __table_args__=(UniqueConstraint('outcome_id','number'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    outcome_id: Mapped[str]=mapped_column(String(36),ForeignKey('adaptive_outcomes.id'))
    number: Mapped[int]=mapped_column(Integer)
    actor_id: Mapped[UUID]=mapped_column(Uuid,ForeignKey('users.id'))
    content: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow)


class AdaptiveControl(Scoped, Base):
    __tablename__='adaptive_controls'
    workspace_id: Mapped[UUID]=mapped_column(Uuid,ForeignKey('workspaces.id'),primary_key=True)
    mode: Mapped[str]=mapped_column(String(20),default='disabled')
    active_model_id: Mapped[str | None]=mapped_column(String(36),ForeignKey('adaptive_models.id'))
    previous_model_id: Mapped[str | None]=mapped_column(String(36),ForeignKey('adaptive_models.id'))
    generation: Mapped[int]=mapped_column(Integer,default=0)
    actor_id: Mapped[UUID]=mapped_column(Uuid,ForeignKey('users.id'))
    updated_at: Mapped[object]=mapped_column(DateTime(timezone=True),default=utcnow)


TABLES=[AdaptiveSkill,AdaptiveSkillRevision,AdaptiveCase,AdaptiveWork,AdaptiveModel,AdaptiveContext,
    AdaptiveDecision,AdaptiveOutcome,AdaptiveLabelRevision,AdaptiveControl]
