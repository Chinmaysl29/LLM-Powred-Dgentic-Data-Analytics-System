"""Dataset ownership checks shared by HTTP handlers and analytical services."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.exceptions import DatabaseConnectionError, DatasetNotFoundError
from backend.app.models.dataset import Dataset


def owned_dataset(db: Session | None, dataset_id: str, owner_id: str | None) -> Dataset:
    """Fail closed for absent identities and unassigned legacy records."""
    if not owner_id:
        raise DatasetNotFoundError("Dataset not found")
    if db is None:
        raise DatabaseConnectionError("Authorization storage is unavailable")
    dataset = db.scalar(select(Dataset).where(
        Dataset.dataset_id == dataset_id, Dataset.owner_id == str(owner_id),
    ))
    if dataset is None:
        raise DatasetNotFoundError("Dataset not found")
    return dataset
