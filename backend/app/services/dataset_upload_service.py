"""Dataset upload orchestration service for executing the multi-stage ingestion pipeline."""

import logging
import hashlib
from pathlib import Path
from typing import Any

from fastapi import Depends, UploadFile
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.models.dataset import Dataset
from backend.app.models.dataset_metadata import DatasetMetadata
from backend.app.models.dataset_profile import DatasetProfile
from backend.app.models.dataset_quality import DatasetQuality
from backend.app.repositories.dataset_metadata_repository import (
    DatasetMetadataRepository,
    get_dataset_metadata_repository,
)
from backend.app.repositories.dataset_profile_repository import (
    DatasetProfileRepository,
    get_dataset_profile_repository,
)
from backend.app.repositories.dataset_quality_repository import (
    DatasetQualityRepository,
    get_dataset_quality_repository,
)
from backend.app.repositories.dataset_recommendation_repository import (
    DatasetRecommendationRepository,
    get_dataset_recommendation_repository,
)
from backend.app.repositories.dataset_repository import (
    DatasetRepository,
    get_dataset_repository,
)
from backend.app.repositories.dataset_version_repository import (
    DatasetVersionRepository,
    get_dataset_version_repository,
)
from backend.app.services.data_cleaning_recommendation_service import (
    DataCleaningRecommendationService,
    get_data_cleaning_recommendation_service,
)
from backend.app.services.data_profiling_service import (
    DataProfilingService,
    get_data_profiling_service,
)
from backend.app.services.data_quality_service import (
    DataQualityService,
    get_data_quality_service,
)
from backend.app.services.dataset_versioning_service import (
    DatasetVersioningService,
    get_dataset_versioning_service,
)
from backend.app.services.metadata_extraction_service import (
    MetadataExtractionService,
    get_metadata_extraction_service,
)
from backend.app.services.storage_service import StorageService, get_storage_service
from backend.app.services.dataset_json_service import DatasetJsonService

logger = logging.getLogger(__name__)


class DatasetUploadService:
    """Orchestrates the multi-stage ingestion pipeline for uploaded datasets."""

    def __init__(
        self,
        storage_service: StorageService,
        dataset_repository: DatasetRepository,
        metadata_service: MetadataExtractionService,
        metadata_repository: DatasetMetadataRepository,
        profiling_service: DataProfilingService,
        profile_repository: DatasetProfileRepository,
        quality_service: DataQualityService,
        quality_repository: DatasetQualityRepository,
        versioning_service: DatasetVersioningService,
        version_repository: DatasetVersionRepository,
        recommendation_service: DataCleaningRecommendationService,
        recommendation_repository: DatasetRecommendationRepository,
        db: Session,
        canonical_service: DatasetJsonService | None = None,
    ) -> None:
        self.storage_service = storage_service
        self.dataset_repository = dataset_repository
        self.metadata_service = metadata_service
        self.metadata_repository = metadata_repository
        self.profiling_service = profiling_service
        self.profile_repository = profile_repository
        self.quality_service = quality_service
        self.quality_repository = quality_repository
        self.versioning_service = versioning_service
        self.version_repository = version_repository
        self.recommendation_service = recommendation_service
        self.recommendation_repository = recommendation_repository
        self.db = db
        self.canonical_service = canonical_service or DatasetJsonService(storage_service)

    async def process_upload(
        self,
        file: UploadFile,
        dataset_name: str | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        """Execute the full dataset upload and downstream processing pipeline."""
        logger.info("Starting dataset upload pipeline for filename=%s", file.filename)

        # Stage 1: File validation and storage
        dataset_id, file_name, file_type, file_path, size_bytes = await self.storage_service.save_file(
            upload=file
        )

        resolved_name = dataset_name.strip() if dataset_name and dataset_name.strip() else Path(file_name).stem

        # Stage 2: Create base Dataset record
        dataset = Dataset(
            owner_id=self.dataset_repository.owner_id,
            dataset_id=dataset_id,
            dataset_name=resolved_name,
            file_name=file_name,
            file_type=file_type,
            file_path=file_path,
            version=1,
            status="uploaded",
        )

        try:
            created_record = self.dataset_repository.create(dataset)
        except Exception as exc:
            self.storage_service.delete_file(file_path)
            logger.exception("Failed to persist dataset record: %s", exc)
            raise

        if file_type.lower() in ('pdf', 'txt', 'text', 'md', 'markdown'):
            # Document extraction belongs to the durable worker. Even malformed
            # documents retain a recoverable source and a truthful UPLOADED state.
            checksum = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
            created_record = self.dataset_repository.update(dataset_id, original_path=file_path,
                canonical_path=file_path, canonical_format='document_source', size_bytes=size_bytes,
                content_hash=checksum, status='uploaded') or created_record
            version_record = self.versioning_service.create_initial_version(dataset_id=dataset_id,
                file_path=file_path, metadata=None, quality=None, created_by=str(self.dataset_repository.owner_id))
            created_record = self.dataset_repository.update(dataset_id, last_active_version_id=version_record.version_id) or created_record
            from backend.app.schemas.dataset import DatasetResponse
            return {**DatasetResponse.model_validate(created_record).model_dump(),
                    'message': 'Document stored. Select an authorized workspace to queue indexing.',
                    'indexing_status': 'UPLOADED',
                    'version_info': {'version_number': version_record.version_number, 'version_id': version_record.version_id}}

        # Stage 2b: preserve the source and materialize a canonical artifact
        # before downstream agents can consume the dataset.
        try:
            canonical = self.canonical_service.materialize(
                dataset_id=created_record.dataset_id,
                dataset_name=created_record.dataset_name,
                original_path=created_record.file_path,
                file_type=created_record.file_type,
            )
            created_record = self.dataset_repository.update(
                created_record.dataset_id,
                original_path=created_record.file_path,
                size_bytes=size_bytes,
                **canonical,
                status="parsed",
            ) or created_record
        except Exception as exc:
            self.dataset_repository.update(created_record.dataset_id, status="parse_failed")
            logger.exception("Canonical dataset materialization failed dataset_id=%s", dataset_id)
            raise

        # Indexing is queued only after an authorized workspace binding exists.
        # It runs under a durable worker lease, not inside the upload request.

        metadata_create = None
        profile_create = None
        quality_create = None
        version_record = None
        recommendations = []

        # Stage 3: Metadata Extraction & Persistence
        try:
            metadata_create = self.metadata_service.extract_metadata(
                dataset_id=created_record.dataset_id,
                file_path=created_record.file_path,
                file_type=created_record.file_type,
            )
            metadata_record = DatasetMetadata(
                dataset_id=metadata_create.dataset_id,
                row_count=metadata_create.row_count,
                column_count=metadata_create.column_count,
                column_names=metadata_create.column_names,
                column_types=metadata_create.column_types,
                columns_metadata=[m.model_dump() for m in metadata_create.columns_metadata],
                classifications=metadata_create.classifications.model_dump(),
            )
            self.metadata_repository.create(metadata_record)
            root_dir = self.storage_service.dataset_directory(dataset_id)
            metadata_path = root_dir / "metadata.json"
            self.canonical_service.write_artifact(metadata_path, metadata_create)
            self.canonical_service.write_artifact(root_dir / "artifacts" / "metadata.json", metadata_create)
            self.dataset_repository.update(dataset_id, metadata_path=str(metadata_path))
            logger.info("Persisted metadata for dataset_id=%s", dataset_id)
        except Exception as exc:
            logger.error("Metadata extraction failed for dataset_id=%s: %s", dataset_id, exc)

        # Stage 4: Data Profiling & Persistence
        try:
            profile_create = self.profiling_service.generate_profile(
                dataset_id=created_record.dataset_id,
                file_path=created_record.file_path,
                file_type=created_record.file_type,
            )
            profile_record = DatasetProfile(
                dataset_id=profile_create.dataset_id,
                duplicate_rows=profile_create.duplicate_rows,
                duplicate_percentage=profile_create.duplicate_percentage,
                missing_data_profile=profile_create.missing_data_profile.model_dump(),
                cardinality_profile=profile_create.cardinality_profile.model_dump(),
                numeric_columns_profile={
                    k: v.model_dump() for k, v in profile_create.numeric_columns_profile.items()
                },
            )
            self.profile_repository.create(profile_record)
            root_dir = self.storage_service.dataset_directory(dataset_id)
            profile_path = root_dir / "profile.json"
            self.canonical_service.write_artifact(profile_path, profile_create)
            self.canonical_service.write_artifact(root_dir / "artifacts" / "profile.json", profile_create)
            # Enterprise Lake: storage/profiles/
            self.storage_service.save_profile(dataset_id, profile_create.model_dump())
            self.dataset_repository.update(dataset_id, profile_path=str(profile_path))
            logger.info("Persisted profile for dataset_id=%s", dataset_id)
        except Exception as exc:
            logger.error("Data profiling failed for dataset_id=%s: %s", dataset_id, exc)

        # Stage 5: Data Quality Assessment & Persistence
        try:
            quality_create = self.quality_service.assess_quality(
                dataset_id=created_record.dataset_id,
                file_path=created_record.file_path,
                file_type=created_record.file_type,
                profile=profile_create,
            )
            quality_record = DatasetQuality(
                dataset_id=quality_create.dataset_id,
                completeness_score=quality_create.completeness_score,
                uniqueness_score=quality_create.uniqueness_score,
                consistency_score=quality_create.consistency_score,
                validity_score=quality_create.validity_score,
                integrity_score=quality_create.integrity_score,
                overall_score=quality_create.overall_score,
                quality_classification=quality_create.quality_classification,
            )
            self.quality_repository.create(quality_record)
            root_dir = self.storage_service.dataset_directory(dataset_id)
            quality_path = root_dir / "quality.json"
            self.canonical_service.write_artifact(quality_path, quality_create)
            self.canonical_service.write_artifact(root_dir / "artifacts" / "quality.json", quality_create)
            # Enterprise Lake: storage/quality/
            self.storage_service.save_quality(dataset_id, quality_create.model_dump())
            self.dataset_repository.update(dataset_id, quality_path=str(quality_path), status="ready")
            logger.info("Persisted quality assessment for dataset_id=%s", dataset_id)
        except Exception as exc:
            logger.error("Quality assessment failed for dataset_id=%s: %s", dataset_id, exc)

        # Stage 6: Dataset Versioning (v1)
        try:
            version_record = self.versioning_service.create_initial_version(
                dataset_id=created_record.dataset_id,
                file_path=created_record.file_path,
                metadata=metadata_create,
                quality=quality_create,
                created_by=created_by,
            )
            self.dataset_repository.update(
                created_record.dataset_id,
                last_active_version_id=version_record.version_id,
            )

            # Write versions.json and lineage.json to registry root: storage/datasets/{dataset_id}/
            root_dir = self.storage_service.dataset_directory(dataset_id)
            versions_payload = {
                "dataset_id": dataset_id,
                "total_versions": 1,
                "active_version": 1,
                "versions": [
                    {
                        "version_id": version_record.version_id,
                        "version_number": 1,
                        "change_type": version_record.change_type,
                        "storage_path": version_record.storage_path,
                        "created_by": version_record.created_by,
                        "created_at": str(version_record.created_at),
                        "is_active": True,
                    }
                ],
            }
            lineage_payload = {
                "dataset_id": dataset_id,
                "current_version": 1,
                "lineage": [
                    {
                        "version_id": version_record.version_id,
                        "version_number": 1,
                        "parent_version_id": None,
                        "change_type": "initial_upload",
                        "timestamp": str(version_record.created_at),
                        "author": created_by,
                        "description": f"Initial ingestion of {file_name}",
                    }
                ],
            }
            self.canonical_service.write_artifact(root_dir / "versions.json", versions_payload)
            self.canonical_service.write_artifact(root_dir / "lineage.json", lineage_payload)
            # Enterprise Lake: storage/lineage/
            self.storage_service.save_lineage(dataset_id, lineage_payload)
            logger.info("Created initial version for dataset_id=%s version_id=%s", dataset_id, version_record.version_id)
        except Exception as exc:
            logger.error("Versioning failed for dataset_id=%s: %s", dataset_id, exc)

        # Stage 7: Cleaning Recommendations
        try:
            v_id = version_record.version_id if version_record else ""
            v_num = version_record.version_number if version_record else 1
            recommendations = self.recommendation_service.generate_recommendations(
                dataset_id=created_record.dataset_id,
                file_path=created_record.file_path,
                file_type=created_record.file_type,
                version_id=v_id,
                version_number=v_num,
                profile=profile_create,
                quality=quality_create,
                created_by=created_by,
                session=self.db,
            )
            logger.info("Generated %d cleaning recommendations for dataset_id=%s", len(recommendations), dataset_id)
        except Exception as exc:
            logger.error("Cleaning recommendations failed for dataset_id=%s: %s", dataset_id, exc)

        logger.info(
            "Completed upload pipeline dataset_id=%s name=%s size_bytes=%d",
            created_record.dataset_id,
            created_record.dataset_name,
            size_bytes,
        )

        return {
            "dataset_id": created_record.dataset_id,
            "dataset_name": created_record.dataset_name,
            "file_name": created_record.file_name,
            "file_type": created_record.file_type,
            "file_path": created_record.file_path,
            "original_path": created_record.original_path,
            "json_path": created_record.json_path,
            "canonical_path": created_record.canonical_path,
            "canonical_format": created_record.canonical_format,
            "content_hash": created_record.content_hash,
            "size_bytes": created_record.size_bytes,
            "row_count": created_record.row_count,
            "column_count": created_record.column_count,
            "version": created_record.version,
            "last_active_version_id": version_record.version_id if version_record else created_record.last_active_version_id,
            "status": created_record.status,
            "created_at": created_record.created_at,
            "updated_at": created_record.updated_at,
            "message": "Dataset uploaded successfully",
            "indexing_status": "UPLOADED" if file_type == "pdf" else "NOT_APPLICABLE",
            "version_info": {
                "version_number": version_record.version_number if version_record else 1,
                "version_id": version_record.version_id if version_record else None,
                "is_active": version_record.is_active if version_record else True,
                "created_at": str(version_record.created_at) if version_record else None,
            } if version_record else None,
            "quality_score": quality_create.overall_score if quality_create else 0.0,
            "classification": quality_create.quality_classification if quality_create else "Unknown",
            "recommendations_summary": f"Generated {len(recommendations)} recommendations",
        }


def get_dataset_upload_service(
    db: Session = Depends(get_db_session),
    storage_service: StorageService = Depends(get_storage_service),
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    metadata_service: MetadataExtractionService = Depends(get_metadata_extraction_service),
    metadata_repository: DatasetMetadataRepository = Depends(get_dataset_metadata_repository),
    profiling_service: DataProfilingService = Depends(get_data_profiling_service),
    profile_repository: DatasetProfileRepository = Depends(get_dataset_profile_repository),
    quality_service: DataQualityService = Depends(get_data_quality_service),
    quality_repository: DatasetQualityRepository = Depends(get_dataset_quality_repository),
    versioning_service: DatasetVersioningService = Depends(get_dataset_versioning_service),
    version_repository: DatasetVersionRepository = Depends(get_dataset_version_repository),
    recommendation_service: DataCleaningRecommendationService = Depends(get_data_cleaning_recommendation_service),
        recommendation_repository: DatasetRecommendationRepository = Depends(get_dataset_recommendation_repository),
) -> DatasetUploadService:
    """FastAPI dependency yielding a configured DatasetUploadService."""
    return DatasetUploadService(
        storage_service=storage_service,
        dataset_repository=dataset_repository,
        metadata_service=metadata_service,
        metadata_repository=metadata_repository,
        profiling_service=profiling_service,
        profile_repository=profile_repository,
        quality_service=quality_service,
        quality_repository=quality_repository,
        versioning_service=versioning_service,
        version_repository=version_repository,
        recommendation_service=recommendation_service,
        recommendation_repository=recommendation_repository,
        db=db,
    )
