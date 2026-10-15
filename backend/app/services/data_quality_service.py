"""Service for assessing and computing dataset quality scores."""

import logging
from typing import Any
import pandas as pd
from fastapi import Depends

from backend.app.schemas.dataset_quality import DatasetQualityCreate
from backend.app.models.dataset_quality import DatasetQuality
from backend.app.repositories.dataset_repository import DatasetRepository, get_dataset_repository
from backend.app.repositories.dataset_profile_repository import DatasetProfileRepository, get_dataset_profile_repository
from backend.app.services.metadata_extraction_service import MetadataExtractionService, get_metadata_extraction_service

logger = logging.getLogger(__name__)


from backend.app.core.exceptions import DataQualityError, QualityAssessmentError


class DataQualityService:
    """Service to compute overall data quality and specific metric scores."""

    @classmethod
    def evaluate_dataframe_quality(cls, df: pd.DataFrame, profile: Any = None) -> dict[str, Any]:
        """Compute standalone quality assessment directly on DataFrame."""
        total_cells = df.shape[0] * df.shape[1]
        null_count = int(df.isna().sum().sum())
        completeness = round(1.0 - (null_count / total_cells if total_cells > 0 else 0.0), 4)
        duplicate_rows = int(df.duplicated().sum())
        uniqueness = round(1.0 - (duplicate_rows / df.shape[0] if df.shape[0] > 0 else 0.0), 4)
        overall = round((completeness * 0.6) + (uniqueness * 0.4), 4)
        return {
            "overall_score": overall,
            "completeness_score": completeness,
            "uniqueness_score": uniqueness,
            "null_count": null_count,
            "duplicate_rows": duplicate_rows,
        }

    def __init__(
        self, 
        dataset_repository: DatasetRepository,
        dataset_profile_repository: DatasetProfileRepository,
        metadata_service: MetadataExtractionService
    ) -> None:
        self.dataset_repository = dataset_repository
        self.dataset_profile_repository = dataset_profile_repository
        self.metadata_service = metadata_service

    def _calculate_completeness(self, df: pd.DataFrame, profile: Any) -> float:
        """Calculate completeness score based on null percentage."""
        # Ensure we have a profile to extract from
        if isinstance(profile, dict):
            # Fetch from raw dict if it's not an ORM model
            null_percentage = profile.get("missing_data_profile", {}).get("null_percentage", 0.0)
        else:
            # Assumes it's an ORM or Schema model
            null_percentage = profile.missing_data_profile.get("null_percentage", 0.0) if isinstance(profile.missing_data_profile, dict) else profile.missing_data_profile.null_percentage

        # null_percentage is typically 0.0 - 1.0 based on earlier phases, so we multiply by 100
        null_percent_value = null_percentage * 100

        completeness = 100.0 - null_percent_value
        completeness = max(0.0, min(100.0, completeness))

        if null_percent_value > 50.0:
            return min(49.9, completeness)
            
        return completeness

    def _calculate_uniqueness(self, df: pd.DataFrame, profile: Any) -> float:
        """Calculate uniqueness score based on duplicate rows."""
        if isinstance(profile, dict):
            duplicate_percentage = profile.get("duplicate_percentage", 0.0)
        else:
            duplicate_percentage = profile.duplicate_percentage

        duplicate_percent_value = duplicate_percentage * 100

        uniqueness = 100.0 - duplicate_percent_value
        uniqueness = max(0.0, min(100.0, uniqueness))

        if duplicate_percent_value > 30.0:
            return min(69.9, uniqueness)
        if duplicate_percent_value >= 50.0:
            return min(49.9, uniqueness)

        return uniqueness

    def _calculate_consistency(self, df: pd.DataFrame) -> float:
        """Detect inconsistent data types and formatting across columns."""
        if df.empty:
            return 100.0
            
        total_cols = len(df.columns)
        if total_cols == 0:
            return 100.0

        inconsistency_ratios = []

        for col in df.columns:
            series = df[col].dropna()
            total_non_null = len(series)
            
            if total_non_null == 0:
                inconsistency_ratios.append(0.0)
                continue

            # Infer types per element to find mixed types (e.g., strings in a numeric column)
            types = series.apply(type)
            type_counts = types.value_counts()
            
            # If all are same type, ratio is 0
            if len(type_counts) <= 1:
                inconsistency_ratios.append(0.0)
                continue
                
            # The most common type is considered the "intended" type
            dominant_type_count = type_counts.iloc[0]
            unusual_count = total_non_null - dominant_type_count
            ratio = unusual_count / total_non_null
            inconsistency_ratios.append(ratio)
            
            if ratio > 0:
                logger.debug("Column %s has inconsistency ratio %f", col, ratio)

        avg_inconsistency_ratio = sum(inconsistency_ratios) / total_cols
        consistency = 100.0 * (1.0 - avg_inconsistency_ratio)
        
        # Apply penalties based on prompt
        if avg_inconsistency_ratio >= 0.25:
            return min(75.0, consistency)
            
        return max(0.0, min(100.0, consistency))

    def _calculate_validity(self, df: pd.DataFrame) -> float:
        """Detect invalid values using heuristics (outliers, extreme strings, unparseable dates)."""
        if df.empty:
            return 100.0
            
        total_cols = len(df.columns)
        if total_cols == 0:
            return 100.0

        total_penalty = 0.0

        for col in df.columns:
            series = df[col].dropna()
            total_values = len(series)
            if total_values == 0:
                continue

            # Check if column is numeric
            if pd.api.types.is_numeric_dtype(series):
                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                
                outliers = series[(series < lower_bound) | (series > upper_bound)]
                outlier_count = len(outliers)
                
                if (outlier_count / total_values) > 0.10:
                    penalty = (outlier_count / total_values) * 20.0
                    total_penalty += penalty
                    
            # Check if column is string/object
            elif pd.api.types.is_string_dtype(series):
                str_lens = series.astype(str).str.len()
                suspicious = str_lens[(str_lens < 1) | (str_lens > 1000)]
                suspicious_count = len(suspicious)
                
                if suspicious_count > 0:
                    penalty = (suspicious_count / total_values) * 10.0
                    total_penalty += penalty
                    
            # Date attempt could be implemented here by checking for "date" in col name 
            # and attempting to parse, but skipped for brevity to avoid excessive slow conversions.
            elif "date" in col.lower() or "time" in col.lower():
                # Attempt to parse
                parsed = pd.to_datetime(series, errors='coerce')
                failed_count = parsed.isna().sum()
                if failed_count > 0:
                    penalty = (failed_count / total_values) * 15.0
                    total_penalty += penalty

        # Average penalty per column roughly applied to a base score of 100
        # Normalizing penalty by column count so a large dataset doesn't easily go to 0
        avg_penalty = total_penalty / total_cols
        validity = 100.0 - avg_penalty
        return max(0.0, min(100.0, validity))

    def _calculate_integrity(self, df: pd.DataFrame) -> float:
        """Detect structural and referential integrity (e.g. missing required headers, unnamed cols)."""
        score = 100.0
        
        if df.empty:
            return score
            
        # Check for unnamed/empty headers
        unnamed_cols = [c for c in df.columns if str(c).startswith("Unnamed:") or str(c).strip() == ""]
        if unnamed_cols:
            score -= len(unnamed_cols) * 5.0

        # Check for completely empty columns
        empty_cols = df.columns[df.isna().all()].tolist()
        if empty_cols:
            score -= len(empty_cols) * 5.0
            
        return max(0.0, min(100.0, score))

    def assess_quality(
        self, dataset_id: str, file_path: str, file_type: str, profile: Any
    ) -> DatasetQualityCreate:
        """Calculate overall quality and persist."""
        logger.info("Starting quality assessment", extra={"dataset_id": dataset_id})

        if not profile:
            raise QualityAssessmentError(f"Profile is required for dataset {dataset_id}")

        if file_type.lower() in {"pdf", "txt", "text", "md", "markdown"}:
            return DatasetQualityCreate(
                dataset_id=dataset_id,
                completeness_score=100.0,
                uniqueness_score=100.0,
                consistency_score=100.0,
                validity_score=100.0,
                integrity_score=100.0,
                overall_score=100.0,
                quality_classification="Good",
            )

        try:
            df = self.metadata_service._load_dataframe(file_path, file_type)
        except Exception as e:
            logger.warning("File unreadable during quality assessment for dataset %s: %s", dataset_id, str(e))
            return DatasetQualityCreate(
                dataset_id=dataset_id,
                completeness_score=50.0,
                uniqueness_score=50.0,
                consistency_score=50.0,
                validity_score=50.0,
                integrity_score=50.0,
                overall_score=50.0,
                quality_classification="Poor"
            )

        if df.empty:
            logger.info("Dataframe is empty for dataset %s", dataset_id)
            return DatasetQualityCreate(
                dataset_id=dataset_id,
                completeness_score=0.0,
                uniqueness_score=100.0,
                consistency_score=100.0,
                validity_score=100.0,
                integrity_score=0.0,
                overall_score=0.0,
                quality_classification="Poor"
            )

        completeness = self._calculate_completeness(df, profile)
        logger.debug("Completeness: %f", completeness, extra={"dataset_id": dataset_id})

        uniqueness = self._calculate_uniqueness(df, profile)
        consistency = self._calculate_consistency(df)
        validity = self._calculate_validity(df)
        integrity = self._calculate_integrity(df)

        # Weighted calculation
        overall_score = (
            (completeness * 0.30) +
            (consistency * 0.25) +
            (validity * 0.25) +
            (uniqueness * 0.20)
        )
        # Integrity acts as a small multiplier/penalty rather than a core weight in this default formula
        if integrity < 100.0:
            overall_score = overall_score * (integrity / 100.0)
            
        overall_score = max(0.0, min(100.0, overall_score))

        if overall_score >= 90:
            classification = "Excellent"
        elif overall_score >= 80:
            classification = "Good"
        elif overall_score >= 70:
            classification = "Fair"
        else:
            classification = "Poor"

        logger.info("Quality assessment complete", extra={"dataset_id": dataset_id, "score": overall_score})

        return DatasetQualityCreate(
            dataset_id=dataset_id,
            completeness_score=round(completeness, 2),
            uniqueness_score=round(uniqueness, 2),
            consistency_score=round(consistency, 2),
            validity_score=round(validity, 2),
            integrity_score=round(integrity, 2),
            overall_score=round(overall_score, 2),
            quality_classification=classification
        )


def get_data_quality_service(
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    dataset_profile_repository: DatasetProfileRepository = Depends(get_dataset_profile_repository),
    metadata_service: MetadataExtractionService = Depends(get_metadata_extraction_service),
) -> DataQualityService:
    """FastAPI dependency yielding a DataQualityService instance."""
    return DataQualityService(
        dataset_repository=dataset_repository,
        dataset_profile_repository=dataset_profile_repository,
        metadata_service=metadata_service,
    )
