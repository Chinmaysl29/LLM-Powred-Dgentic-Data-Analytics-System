"""Dataset database model for Phase 2.1 Dataset Foundation."""

import uuid

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class Dataset(Base, TimestampMixin):
    """Dataset ORM model representing uploaded and managed datasets."""

    __tablename__ = "datasets"

    # NULL means quarantined legacy data, never a globally shared dataset.
    owner_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    dataset_id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    dataset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    json_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_active_version_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    status: Mapped[str] = mapped_column(String(50), default="uploaded", nullable=False)

    def __repr__(self) -> str:
        return f"<Dataset dataset_id={self.dataset_id!r} name={self.dataset_name!r} status={self.status!r}>"
