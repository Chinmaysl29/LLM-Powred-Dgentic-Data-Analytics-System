"""Dataset repository providing CRUD database operations for the Dataset model."""

import logging
from typing import Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.models.dataset import Dataset
from backend.app.core.security import get_current_user

logger = logging.getLogger(__name__)


class DatasetRepository:
    """Repository handling persistence and retrieval of Dataset entities."""

    def __init__(self, db: Session, owner_id: str | None = None) -> None:
        self.db = db
        self.owner_id = owner_id

    @property
    def session(self) -> Session:
        """Backward-compatible alias for the database session."""
        return self.db

    def create(self, dataset: Dataset) -> Dataset:
        """Persist a new Dataset record to the database."""
        if self.owner_id is not None:
            dataset.owner_id = self.owner_id
        self.db.add(dataset)
        self.db.commit()
        self.db.refresh(dataset)
        logger.info(
            "Created dataset record dataset_id=%s dataset_name=%s file_name=%s",
            dataset.dataset_id,
            dataset.dataset_name,
            dataset.file_name,
        )
        return dataset

    def get(self, dataset_id: str) -> Dataset | None:
        """Retrieve a single Dataset record by its unique dataset_id."""
        stmt = select(Dataset).where(Dataset.dataset_id == dataset_id)
        if self.owner_id is not None:
            stmt = stmt.where(Dataset.owner_id == self.owner_id)
        dataset = self.db.scalars(stmt).first()
        if dataset:
            logger.debug("Retrieved dataset record dataset_id=%s", dataset_id)
        else:
            logger.warning("Dataset record not found dataset_id=%s", dataset_id)
        return dataset

    def list(self, skip: int = 0, limit: int = 100) -> list[Dataset]:
        """List Dataset records with pagination ordered by creation time descending."""
        stmt = (
            select(Dataset)
            .where(Dataset.owner_id == self.owner_id if self.owner_id is not None else True)
            .order_by(Dataset.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        results = list(self.db.scalars(stmt).all())
        logger.debug("Listed datasets count=%d skip=%d limit=%d", len(results), skip, limit)
        return results

    def update(self, dataset_id: str, **kwargs: Any) -> Dataset | None:
        """Update fields of an existing Dataset record."""
        dataset = self.get(dataset_id)
        if not dataset:
            logger.warning("Cannot update non-existent dataset dataset_id=%s", dataset_id)
            return None

        if "owner_id" in kwargs or "dataset_id" in kwargs:
            raise ValueError("Ownership and identity require explicit administrative assignment")
        for key, value in kwargs.items():
            if hasattr(dataset, key) and value is not None:
                setattr(dataset, key, value)

        self.db.commit()
        self.db.refresh(dataset)
        logger.info("Updated dataset record dataset_id=%s updated_fields=%s", dataset_id, list(kwargs.keys()))
        return dataset

    def delete(self, dataset_id: str) -> bool:
        """Delete a Dataset record from the database."""
        dataset = self.get(dataset_id)
        if not dataset:
            logger.warning("Cannot delete non-existent dataset dataset_id=%s", dataset_id)
            return False

        self.db.delete(dataset)
        self.db.commit()
        logger.info("Deleted dataset record dataset_id=%s", dataset_id)
        return True


def get_dataset_repository(db: Session = Depends(get_db_session), current_user: Any = Depends(get_current_user)) -> DatasetRepository:
    """FastAPI dependency yielding a DatasetRepository instance."""
    return DatasetRepository(db=db, owner_id=str(current_user.id))
