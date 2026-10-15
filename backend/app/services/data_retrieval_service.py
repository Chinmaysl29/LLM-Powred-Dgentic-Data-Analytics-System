"""Centralized enterprise-grade data access layer for all analytical agents."""

import logging
from typing import Any

import pandas as pd
from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session as get_db
from backend.app.core.security import get_current_user
from backend.app.core.authorization import owned_dataset
from backend.app.core.exceptions import (
    CorruptedFileError,
    DataRetrievalError,
    DatasetNotFoundError,
    VersionNotFoundError,
)
from backend.app.schemas.retrieval import (
    DataRetrievalFilter,
    DatasetSchemaResponse,
    PackagedDatasetContext,
)
from backend.app.services.storage_service import StorageService, get_storage_service
from backend.app.services.dataset_loader import DatasetLoader
from backend.app.models.dataset import Dataset
from backend.app.models.dataset_version import DatasetVersion
from backend.app.models.dataset_metadata import DatasetMetadata
from backend.app.models.dataset_profile import DatasetProfile
from backend.app.models.dataset_quality import DatasetQuality
from backend.app.schemas.dataset import DatasetResponse
from backend.app.schemas.dataset_metadata import DatasetMetadataResponse
from backend.app.schemas.dataset_profile import DatasetProfileResponse
from backend.app.schemas.dataset_quality import DatasetQualityResponse
from backend.app.schemas.dataset_version import DatasetVersionResponse

logger = logging.getLogger(__name__)


class DataRetrievalService:
    """Service providing single-source-of-truth access to datasets and their contexts."""

    def __init__(self, db: Session, storage_service: StorageService, *, owner_id: str | None = None):
        self.db = db
        self.owner_id = owner_id
        self.storage_service = storage_service
        self.dataset_loader = DatasetLoader()

    def discover(
        self, dataset_id: str, version_number: int | None = None
    ) -> tuple[Dataset, DatasetVersion, DatasetMetadata | None, DatasetProfile | None, DatasetQuality | None]:
        """Gather dataset records and version from database."""
        dataset = owned_dataset(self.db, dataset_id, self.owner_id)

        # Resolve version
        query = self.db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset_id)
        if version_number is not None:
            version = query.filter(DatasetVersion.version_number == version_number).first()
            if not version:
                raise VersionNotFoundError(f"Version {version_number} for dataset {dataset_id} not found.")
        else:
            version = query.filter(DatasetVersion.is_active == True).first()
            if not version:
                # Fallback to latest version if no active version flag (shouldn't happen in healthy DB)
                version = query.order_by(DatasetVersion.version_number.desc()).first()
                if not version:
                    raise VersionNotFoundError(f"No active version found for dataset {dataset_id}.")

        # Retrieve related context records for this version.
        # Since metadata, profile, quality might be stored at dataset level or version level depending on schema,
        # we check by dataset_id (assuming 1:1 or related to latest active in phase 2).
        metadata = self.db.query(DatasetMetadata).filter(DatasetMetadata.dataset_id == dataset_id).first()
        profile = self.db.query(DatasetProfile).filter(DatasetProfile.dataset_id == dataset_id).first()
        quality = self.db.query(DatasetQuality).filter(DatasetQuality.dataset_id == dataset_id).first()

        # Dataset-level summaries describe the latest materialization, not an
        # arbitrary historical/rolled-back version. Never attach them to it.
        if version.version_number != dataset.version or not version.is_active:
            metadata = profile = quality = None
        return dataset, version, metadata, profile, quality

    def get_schema(self, dataset_id: str, version_number: int | None = None) -> DatasetSchemaResponse:
        """Fast schema lookup without loading full dataset into memory."""
        dataset, version, metadata, _, _ = self.discover(dataset_id, version_number)
        
        # If we have extracted metadata, use it
        if metadata and metadata.column_names and metadata.column_types:
            return DatasetSchemaResponse(
                columns=metadata.column_names,
                data_types=metadata.column_types,
                row_count=metadata.row_count
            )

        # Otherwise read a preview using pandas
        try:
            file_path = self.storage_service.retrieve_file(version.storage_path)
            file_type = file_path.suffix.lower().lstrip(".")
            
            from backend.app.services.tabular_loader import load_tabular_dataframe
            df_preview = load_tabular_dataframe(file_path, file_type, nrows=5)
                
            dtypes = {col: str(dtype) for col, dtype in df_preview.dtypes.items()}
            return DatasetSchemaResponse(
                columns=df_preview.columns.tolist(),
                data_types=dtypes,
                row_count=None # Unknown without full load
            )
        except Exception as e:
            logger.error("Failed to read schema from file for dataset %s: %s", dataset_id, e)
            raise CorruptedFileError(f"Failed to parse dataset file: {str(e)}")

    def _apply_filters(self, df: pd.DataFrame, filters: DataRetrievalFilter) -> pd.DataFrame:
        """Apply standardized filters to a DataFrame."""
        if filters.columns:
            # Check if columns exist
            missing = [c for c in filters.columns if c not in df.columns]
            if missing:
                raise DataRetrievalError(f"Requested columns not found in dataset: {missing}")
            df = df[filters.columns]

        if filters.conditions:
            for cond in filters.conditions:
                if cond.column not in df.columns:
                    raise DataRetrievalError(f"Condition column not found: {cond.column}")
                
                col = df[cond.column]
                val = cond.value
                
                try:
                    if cond.operator == "eq":
                        df = df[col == val]
                    elif cond.operator == "neq":
                        df = df[col != val]
                    elif cond.operator == "gt":
                        df = df[col > val]
                    elif cond.operator == "gte":
                        df = df[col >= val]
                    elif cond.operator == "lt":
                        df = df[col < val]
                    elif cond.operator == "lte":
                        df = df[col <= val]
                    elif cond.operator == "in":
                        if not isinstance(val, (list, tuple)):
                            val = [val]
                        df = df[col.isin(val)]
                    elif cond.operator == "contains":
                        df = df[col.astype(str).str.contains(str(val), na=False)]
                except Exception as e:
                    raise DataRetrievalError(f"Failed to apply filter condition on {cond.column}: {e}")

        if filters.date_range:
            col_name = filters.date_range.column
            if col_name not in df.columns:
                raise DataRetrievalError(f"Date range column not found: {col_name}")
            
            try:
                # Convert to datetime if it's not already
                if not pd.api.types.is_datetime64_any_dtype(df[col_name]):
                    date_series = pd.to_datetime(df[col_name])
                else:
                    date_series = df[col_name]
                    
                mask = pd.Series(True, index=df.index)
                if filters.date_range.start_date:
                    start = pd.to_datetime(filters.date_range.start_date)
                    mask &= (date_series >= start)
                if filters.date_range.end_date:
                    end = pd.to_datetime(filters.date_range.end_date)
                    mask &= (date_series <= end)
                df = df[mask]
            except Exception as e:
                raise DataRetrievalError(f"Failed to apply date filter on {col_name}: {e}")
                
        return df

    def load_dataframe(
        self,
        dataset_id: str,
        version_number: int | None = None,
        filters: DataRetrievalFilter | None = None,
        sample_size: int | None = None
    ) -> tuple[pd.DataFrame, bool]:
        """Load dataset into a pandas DataFrame.
        
        Returns:
            Tuple of (DataFrame, is_sampled)
        """
        dataset, version, metadata, _, _ = self.discover(dataset_id, version_number)
        
        try:
            # Canonical artifacts are the source of truth for agents. The
            # legacy source-file branch supports datasets uploaded before the
            # Phase 17.11 migration.
            # discover() resolves the active version even without an explicit
            # version argument. A dataset-level canonical pointer can still
            # reference a newer version after rollback.
            if version:
                file_path = self.storage_service.retrieve_file(version.storage_path)
                file_type = file_path.suffix.lower().lstrip(".")
                from backend.app.services.tabular_loader import load_tabular_dataframe
                df = load_tabular_dataframe(file_path, file_type)
        except Exception as e:
            logger.error("Failed to load DataFrame for dataset %s: %s", dataset_id, e)
            raise CorruptedFileError(f"Failed to read dataset file: {str(e)}")

        # Apply filters before sampling
        if filters:
            df = self._apply_filters(df, filters)

        is_sampled = False
        total_rows = len(df)
        
        # Multi-tiered Sampling Engine
        # If user explicitly requested a sample size, use it
        target_sample_size = sample_size
        
        if target_sample_size is None:
            # Auto-sampling based on size rules
            if total_rows > 1_000_000:
                target_sample_size = 100_000
            elif total_rows > 100_000:
                # Up to 1M, we allow full load, but if requested we could sample. We'll default to full load here.
                pass
                
        if target_sample_size and total_rows > target_sample_size:
            df = df.sample(n=target_sample_size, random_state=42)
            is_sampled = True

        return df, is_sampled

    def get_packaged_context(
        self,
        dataset_id: str,
        version_number: int | None = None,
        filters: DataRetrievalFilter | None = None
    ) -> PackagedDatasetContext:
        """Create the standardized packaged context for downstream agents."""
        dataset, version, metadata, profile, quality = self.discover(dataset_id, version_number)
        
        # We need the row/col count based on actual loaded data (especially if filtered)
        # If no filters, we can just use metadata if available to save a load.
        if filters:
            df, _ = self.load_dataframe(dataset_id, version_number, filters=filters, sample_size=0)
            rows, columns = df.shape
        else:
            if metadata and metadata.row_count is not None and metadata.column_count is not None:
                rows = metadata.row_count
                columns = metadata.column_count
            else:
                schema = self.get_schema(dataset_id, version_number)
                if schema.row_count is not None:
                    rows = schema.row_count
                    columns = len(schema.columns)
                else:
                    df, _ = self.load_dataframe(dataset_id, version_number, sample_size=0)
                    rows, columns = df.shape
                    
        return PackagedDatasetContext(
            dataset_id=dataset.dataset_id,
            rows=rows,
            columns=columns,
            quality_score=quality.overall_score if quality else None,
            active_version=version.version_number,
            dataset=DatasetResponse.model_validate(dataset) if dataset else None,
            metadata=DatasetMetadataResponse.model_validate(metadata) if metadata else None,
            profile=DatasetProfileResponse.model_validate(profile) if profile else None,
            quality=DatasetQualityResponse.model_validate(quality) if quality else None,
            version=DatasetVersionResponse.model_validate(version) if version else None,
        )


def get_data_retrieval_service(
    db: Session = Depends(get_db),
    storage_service: StorageService = Depends(get_storage_service),
    current_user: Any = Depends(get_current_user),
) -> DataRetrievalService:
    return DataRetrievalService(db=db, storage_service=storage_service, owner_id=str(current_user.id))
