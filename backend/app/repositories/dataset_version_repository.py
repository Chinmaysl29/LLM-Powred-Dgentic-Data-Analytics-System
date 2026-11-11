"""Dataset version repository providing CRUD and version management operations."""

import logging
from typing import Any
from datetime import datetime, timezone
import os

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func

from backend.app.database.postgres import get_db_session
from backend.app.models.dataset_version import DatasetVersion
from backend.app.models.dataset import Dataset

logger = logging.getLogger(__name__)


class DatasetVersionRepository:
    """Repository handling persistence and retrieval of DatasetVersion entities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @property
    def session(self) -> Session:
        """Backward-compatible alias for the database session."""
        return self.db

    def _validate_storage_path(self, path: str) -> bool:
        """Validate that the storage path exists on the filesystem."""
        if not path or not os.path.exists(path):
            raise ValueError(f"Storage path does not exist or is unreadable: {path}")
        return True

    def create(self, version: DatasetVersion) -> DatasetVersion:
        """Persist a new DatasetVersion record."""
        self._validate_storage_path(version.storage_path)

        if version.version_number == 1 and version.parent_version_id is not None:
            raise ValueError("Version 1 cannot have a parent version")
        if version.version_number > 1 and version.parent_version_id is None:
            raise ValueError("Versions > 1 must have a parent version")

        try:
            # Serialize with reviewed activation/undo, and update the old pointer
            # before an autoflush can insert another active version.
            with self.db.no_autoflush:
                self.db.scalar(select(Dataset).where(Dataset.dataset_id == version.dataset_id).with_for_update())
                if version.is_active:
                    self.db.query(DatasetVersion).filter(
                        DatasetVersion.dataset_id == version.dataset_id,
                        DatasetVersion.is_active == True
                    ).update({"is_active": False, "deactivated_at": func.now()})
            self.db.add(version)

            self.db.flush()
            self.db.commit()
            self.db.refresh(version)
            logger.info("Created version %d for dataset %s", version.version_number, version.dataset_id)
            return version
        except IntegrityError as exc:
            self.db.rollback()
            err_msg = str(exc)
            if "uq_dataset_version" in err_msg or "unique constraint" in err_msg.lower():
                logger.error("Failed to create version: Duplicate version_number for dataset_id=%s", version.dataset_id)
                raise ValueError("Duplicate version number") from exc
            elif "fk_dataset_id" in err_msg or "foreign key" in err_msg.lower():
                logger.error("Failed to create version: Dataset not found for dataset_id=%s", version.dataset_id)
                raise ValueError("Dataset not found") from exc
            else:
                logger.error("Failed to create version due to integrity error: %s", err_msg)
                raise ValueError("Invalid version state") from exc
        except Exception as exc:
            self.db.rollback()
            logger.error("Create version failed", extra={"error": str(exc)})
            raise exc

    def get_versions(self, dataset_id: str, limit: int = 50, offset: int = 0) -> tuple[list[DatasetVersion], int]:
        """Retrieve paginated list of versions for a dataset."""
        stmt = (
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number.desc(), DatasetVersion.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        versions = list(self.db.scalars(stmt).all())
        
        count_stmt = select(func.count()).select_from(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
        total_count = self.db.scalar(count_stmt) or 0
        
        logger.debug("Retrieved versions", extra={"dataset_id": dataset_id, "count": len(versions)})
        return versions, total_count

    def get_active_version(self, dataset_id: str) -> DatasetVersion | None:
        """Retrieve the currently active version for a dataset."""
        stmt = (
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .where(DatasetVersion.is_active == True)
            .limit(1)
        )
        version = self.db.scalars(stmt).first()
        if not version:
            logger.warning("No active version found", extra={"dataset_id": dataset_id})
        return version

    def get_version(self, dataset_id: str, version_number: int) -> DatasetVersion:
        """Retrieve a specific version by its number."""
        stmt = (
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .where(DatasetVersion.version_number == version_number)
        )
        version = self.db.scalars(stmt).first()
        if not version:
            raise ValueError(f"Version {version_number} not found for dataset {dataset_id}")
        return version

    def get_version_by_id(self, version_id: str) -> DatasetVersion:
        """Retrieve a specific version by its UUID."""
        stmt = select(DatasetVersion).where(DatasetVersion.version_id == version_id)
        version = self.db.scalars(stmt).first()
        if not version:
            raise ValueError(f"Version {version_id} not found")
        return version

    def set_active_version(self, dataset_id: str, target_version_number: int) -> DatasetVersion:
        """Rollback or set a specific version as active."""
        self.db.scalar(select(Dataset).where(Dataset.dataset_id == dataset_id).with_for_update())
        target_version = self.get_version(dataset_id, target_version_number)
        
        if target_version.is_active:
            return target_version
            
        try:
            current_active = self.get_active_version(dataset_id)
            now = datetime.now(timezone.utc)
            
            if current_active:
                current_active.is_active = False
                current_active.deactivated_at = now
                self.db.add(current_active)
                self.db.flush()  # Enforce the partial unique index before activating the target.
                
            target_version.is_active = True
            target_version.activated_at = now
            self.db.add(target_version)
            
            # Update main Dataset record
            dataset = self.db.scalars(select(Dataset).where(Dataset.dataset_id == dataset_id)).first()
            if dataset:
                dataset.last_active_version_id = target_version.version_id
                dataset.updated_at = now
                self.db.add(dataset)
                
            self.db.commit()
            logger.info("Activated version %d for dataset %s", target_version_number, dataset_id)
            
            self.db.refresh(target_version)
            return target_version
        except Exception as exc:
            self.db.rollback()
            logger.error("Failed to set active version", extra={"error": str(exc)})
            raise exc

    def get_lineage_chain(self, version_id: str) -> list[DatasetVersion]:
        """Walk backwards via parent_version_id chain and return ordered newest-to-oldest."""
        chain = []
        current_id = version_id
        
        while current_id:
            try:
                version = self.get_version_by_id(current_id)
                chain.append(version)
                current_id = version.parent_version_id
            except ValueError:
                break
                
        logger.debug("Retrieved lineage chain", extra={"version_id": version_id, "chain_length": len(chain)})
        return chain


def get_dataset_version_repository(db: Session = Depends(get_db_session)) -> DatasetVersionRepository:
    """FastAPI dependency yielding a DatasetVersionRepository instance."""
    return DatasetVersionRepository(db=db)
