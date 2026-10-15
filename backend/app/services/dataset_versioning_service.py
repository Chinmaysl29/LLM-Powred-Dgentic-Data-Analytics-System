"""Service for managing dataset versions, snapshots, and rollbacks."""

import logging
from typing import Any

from fastapi import Depends

from backend.app.schemas.dataset_version import DatasetVersionComparisonResponse, DatasetVersionResponse
from backend.app.models.dataset_version import DatasetVersion
from backend.app.repositories.dataset_repository import DatasetRepository, get_dataset_repository
from backend.app.repositories.dataset_version_repository import DatasetVersionRepository, get_dataset_version_repository

logger = logging.getLogger(__name__)


from backend.app.core.exceptions import (
    DuplicateVersionError,
    VersioningError,
    VersionNotFoundError,
)


class DatasetVersioningService:
    """Service to handle dataset versions, comparisons, and rollbacks."""

    def __init__(
        self,
        dataset_repository: DatasetRepository,
        dataset_version_repository: DatasetVersionRepository,
    ) -> None:
        self.dataset_repository = dataset_repository
        self.dataset_version_repository = dataset_version_repository

    def create_initial_version(
        self,
        dataset_id: str,
        file_path: str,
        metadata: Any,
        quality: Any,
        created_by: str,
    ) -> DatasetVersion:
        """Create the first version of a dataset during initial upload."""
        logger.info("Creating initial version for dataset %s", dataset_id)
        
        # Validate dataset exists
        dataset = self.dataset_repository.get(dataset_id)
        if not dataset:
            raise VersionNotFoundError("Dataset not found")
            
        if dataset.file_type.lower() not in {'pdf', 'txt', 'text', 'md', 'markdown'} and (not metadata or not quality):
            raise ValueError("Metadata and quality are required")

        metadata_snapshot = {
            "row_count": getattr(metadata, "row_count", 0),
            "column_count": getattr(metadata, "column_count", 0),
            "columns": getattr(metadata, "column_names", []),
            "dtypes": getattr(metadata, "column_types", {}),
            "null_counts": {}, # Not natively stored in metadata top-level currently, could extract if needed
        } if metadata else {'kind': 'document', 'status': 'not_extracted'}
        
        quality_snapshot = {
            "completeness_score": getattr(quality, "completeness_score", 0.0),
            "uniqueness_score": getattr(quality, "uniqueness_score", 0.0),
            "consistency_score": getattr(quality, "consistency_score", 0.0),
            "validity_score": getattr(quality, "validity_score", 0.0),
            "integrity_score": getattr(quality, "integrity_score", 0.0),
            "overall_score": getattr(quality, "overall_score", 0.0),
            "classification": getattr(quality, "quality_classification", "Poor")
        } if quality else {'status': 'not_assessed'}
        
        version = DatasetVersion(
            dataset_id=dataset_id,
            version_number=1,
            parent_version_id=None,
            change_type="initial_upload",
            storage_path=file_path,
            metadata_snapshot=metadata_snapshot,
            quality_snapshot=quality_snapshot,
            is_active=True,
            created_by=created_by
        )
        
        try:
            return self.dataset_version_repository.create(version)
        except ValueError as e:
            if "Duplicate version number" in str(e):
                logger.warning("Duplicate version 1 for dataset_id=%s. Attempting to fetch existing.", dataset_id)
                return self.dataset_version_repository.get_version(dataset_id, 1)
            raise VersioningError(str(e))

    def create_new_version(
        self,
        dataset_id: str,
        parent_version_number: int,
        file_path: str,
        change_type: str,
        transformation_metadata: dict,
        metadata: Any,
        quality: Any,
        created_by: str,
    ) -> DatasetVersion:
        """Create a new version (>= 2) based on a parent version."""
        try:
            parent_version = self.dataset_version_repository.get_version(dataset_id, parent_version_number)
        except ValueError as e:
            raise VersionNotFoundError(f"Parent version not found: {e}")
            
        versions, total = self.dataset_version_repository.get_versions(dataset_id, limit=1)
        next_version_number = versions[0].version_number + 1 if versions else 2
        
        metadata_snapshot = {
            "row_count": getattr(metadata, "row_count", 0),
            "column_count": getattr(metadata, "column_count", 0),
            "columns": getattr(metadata, "column_names", []),
            "dtypes": getattr(metadata, "column_types", {}),
        }
        
        quality_snapshot = {
            "completeness_score": getattr(quality, "completeness_score", 0.0),
            "uniqueness_score": getattr(quality, "uniqueness_score", 0.0),
            "overall_score": getattr(quality, "overall_score", 0.0),
            "classification": getattr(quality, "quality_classification", "Poor")
        }
        
        version = DatasetVersion(
            dataset_id=dataset_id,
            version_number=next_version_number,
            parent_version_id=parent_version.version_id,
            change_type=change_type,
            transformation_metadata=transformation_metadata,
            storage_path=file_path,
            metadata_snapshot=metadata_snapshot,
            quality_snapshot=quality_snapshot,
            is_active=False,
            created_by=created_by
        )
        
        try:
            return self.dataset_version_repository.create(version)
        except Exception as e:
            raise VersioningError(str(e))

    def rollback_version(self, dataset_id: str, target_version_number: int) -> DatasetVersion:
        """Rollback to a previous version."""
        logger.info("Rollback requested", extra={"dataset_id": dataset_id, "target_version": target_version_number})
        try:
            return self.dataset_version_repository.set_active_version(dataset_id, target_version_number)
        except ValueError as e:
            raise VersionNotFoundError(str(e))
        except Exception as e:
            raise VersioningError(str(e))

    def compare_versions(
        self, dataset_id: str, version_number_1: int, version_number_2: int
    ) -> DatasetVersionComparisonResponse:
        """Structurally compare two versions by reading their snapshots."""
        try:
            v1 = self.dataset_version_repository.get_version(dataset_id, version_number_1)
            v2 = self.dataset_version_repository.get_version(dataset_id, version_number_2)
        except ValueError as e:
            raise VersionNotFoundError(str(e))
            
        snap1 = v1.metadata_snapshot
        snap2 = v2.metadata_snapshot
        
        r1 = snap1.get("row_count", 0)
        r2 = snap2.get("row_count", 0)
        
        rows_added = max(0, r2 - r1)
        rows_removed = max(0, r1 - r2)
        
        cols1 = set(snap1.get("columns", []))
        cols2 = set(snap2.get("columns", []))
        
        columns_added = list(cols2 - cols1)
        columns_removed = list(cols1 - cols2)
        
        return DatasetVersionComparisonResponse(
            version_number_1=version_number_1,
            version_number_2=version_number_2,
            rows_added=rows_added,
            rows_removed=rows_removed,
            columns_added=columns_added,
            columns_removed=columns_removed,
            new_columns=columns_added,
            deleted_columns=columns_removed
        )
        
    def get_version_lineage(self, dataset_id: str, version_number: int) -> list[DatasetVersionResponse]:
        """Get lineage from the given version upwards."""
        try:
            version = self.dataset_version_repository.get_version(dataset_id, version_number)
        except ValueError as e:
            raise VersionNotFoundError(str(e))
            
        chain = self.dataset_version_repository.get_lineage_chain(version.version_id)
        return [DatasetVersionResponse.model_validate(v) for v in chain]


def get_dataset_versioning_service(
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    dataset_version_repository: DatasetVersionRepository = Depends(get_dataset_version_repository),
) -> DatasetVersioningService:
    """FastAPI dependency yielding a DatasetVersioningService instance."""
    return DatasetVersioningService(
        dataset_repository=dataset_repository,
        dataset_version_repository=dataset_version_repository,
    )
