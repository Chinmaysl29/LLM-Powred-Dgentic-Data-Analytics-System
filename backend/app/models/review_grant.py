"""Scoped reviewer permission, separate from raw-source and execution rights."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import (Uuid, String, Boolean, Integer, DateTime, ForeignKey,
                        UniqueConstraint, CheckConstraint, Index, func)
from sqlalchemy.orm import Mapped, mapped_column
from backend.app.models.base import Base


class DatasetReviewGrant(Base):
    __tablename__ = 'dataset_review_grants'
    __table_args__ = (
        UniqueConstraint('dataset_id', 'owner_id', 'reviewer_id', name='uq_dataset_reviewer_owner'),
        CheckConstraint('owner_id <> reviewer_id', name='ck_review_grant_no_self'),
        CheckConstraint('revision >= 1', name='ck_review_grant_revision'),
        Index('ix_review_grant_reviewer_scope', 'reviewer_id', 'workspace_id', 'active'),
        Index('ix_review_grant_owner_scope', 'owner_id', 'workspace_id'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('tenants.id'))
    workspace_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('workspaces.id'))
    dataset_id: Mapped[str] = mapped_column(String(36), ForeignKey('datasets.dataset_id'))
    owner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'))
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('users.id'))
    active: Mapped[bool] = mapped_column(Boolean)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
