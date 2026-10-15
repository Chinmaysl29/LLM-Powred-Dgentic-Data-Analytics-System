import logging
import warnings
import pandas as pd
import numpy as np
import os
from typing import List, Dict, Any
from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.models.dataset_recommendation import DatasetRecommendation
from backend.app.models.dataset_profile import DatasetProfile
from backend.app.models.dataset_quality import DatasetQuality
from backend.app.repositories.dataset_recommendation_repository import DatasetRecommendationRepository
from backend.app.repositories.dataset_repository import DatasetRepository, get_dataset_repository
from backend.app.repositories.dataset_version_repository import DatasetVersionRepository
from backend.config.cleaning_config import CLEANING_THRESHOLDS, PRIORITY_WEIGHTS, TYPE_STRATEGIES

from backend.app.core.exceptions import CleaningRecommendationError

logger = logging.getLogger(__name__)

class DataCleaningRecommendationService:
    def __init__(
        self,
        recommendation_repo: DatasetRecommendationRepository,
        dataset_repo: DatasetRepository,
        version_repo: DatasetVersionRepository,
        db: Session | None = None,
    ):
        self.recommendation_repo = recommendation_repo
        self.dataset_repo = dataset_repo
        self.version_repo = version_repo
        self.db = db

    def _load_dataframe(self, file_path: str) -> pd.DataFrame:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.csv':
            # Use nrows=100000 to prevent OOM on very large files for recommendations
            return pd.read_csv(file_path, nrows=100000)
        elif ext == '.tsv':
            return pd.read_csv(file_path, sep='\t', nrows=100000)
        elif ext in ['.xlsx', '.xls']:
            return pd.read_excel(file_path, nrows=100000)
        elif ext == '.json':
            return pd.read_json(file_path)
        elif ext in ['.jsonl', '.ndjson']:
            return pd.read_json(file_path, lines=True)
        elif ext in ['.pdf', '.txt', '.text', '.md', '.markdown']:
            return pd.DataFrame()
        elif ext == '.parquet':
            return pd.read_parquet(file_path)
        else:
            raise CleaningRecommendationError(f"Unsupported file extension: {ext}")

    def generate_recommendations(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> List[DatasetRecommendation]:
        """Generate cleaning recommendations. Supports (session, dataset_id, ...) or (dataset_id=..., ...)."""
        # Parse flexible arguments
        if args and isinstance(args[0], Session):
            session = args[0]
            dataset_id = args[1] if len(args) > 1 else kwargs.get("dataset_id", "")
            file_path = args[2] if len(args) > 2 else kwargs.get("file_path", "")
            file_type = args[3] if len(args) > 3 else kwargs.get("file_type", "csv")
            version_id = args[4] if len(args) > 4 else kwargs.get("version_id", "")
            version_number = args[5] if len(args) > 5 else kwargs.get("version_number", 1)
            profile = args[6] if len(args) > 6 else kwargs.get("profile")
            quality = args[7] if len(args) > 7 else kwargs.get("quality")
            created_by = args[8] if len(args) > 8 else kwargs.get("created_by", "system")
        else:
            session = kwargs.get("session") or self.db
            dataset_id = args[0] if len(args) > 0 else kwargs.get("dataset_id", "")
            file_path = args[1] if len(args) > 1 else kwargs.get("file_path", "")
            file_type = args[2] if len(args) > 2 else kwargs.get("file_type", "csv")
            version_id = args[3] if len(args) > 3 else kwargs.get("version_id", "")
            version_number = args[4] if len(args) > 4 else kwargs.get("version_number", 1)
            profile = args[5] if len(args) > 5 else kwargs.get("profile")
            quality = args[6] if len(args) > 6 else kwargs.get("quality")
            created_by = args[7] if len(args) > 7 else kwargs.get("created_by", "system")

        logger.info("Generating recommendations", extra={
            "dataset_id": dataset_id,
            "version_number": version_number,
            "file_path": file_path
        })

        try:
            df = self._load_dataframe(file_path)
        except Exception as e:
            logger.warning("Failed to load dataframe for dataset %s: %s", dataset_id, e)
            return []

        recs = []
        recs.extend(self._check_missing_values(profile, df, dataset_id, version_id, version_number, created_by))
        recs.extend(self._check_duplicates(profile, df, dataset_id, version_id, version_number, created_by))
        recs.extend(self._check_type_conversions(profile, df, dataset_id, version_id, version_number, created_by))
        recs.extend(self._check_outliers(profile, df, dataset_id, version_id, version_number, created_by))
        recs.extend(self._check_consistency(profile, df, dataset_id, version_id, version_number, created_by))
        recs.extend(self._check_quality_improvements(quality, dataset_id, version_id, version_number, created_by))

        if recs:
            self.recommendation_repo.create_many(session, recs)
        
        logger.info("Recommendations generated", extra={
            "dataset_id": dataset_id,
            "version_number": version_number,
            "total_count": len(recs),
            "critical_count": sum(1 for r in recs if r.severity == 'critical')
        })
        
        return recs

    def _infer_semantic_type(self, series: pd.Series, sample_size: int = 100) -> str:
        sample = series.dropna().head(sample_size)
        if sample.empty:
            return "categorical"
            
        if pd.api.types.is_numeric_dtype(sample):
            if set(sample.dropna().unique()).issubset({0, 1, 0.0, 1.0}):
                return "boolean"
            return "numeric"
        
        try:
            pd.to_numeric(sample)
            return "numeric"
        except (ValueError, TypeError):
            pass
            
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pd.to_datetime(sample, format="mixed")
            return "datetime"
        except (ValueError, TypeError):
            pass
            
        return "categorical"

    def _check_missing_values(self, profile: Any, df: pd.DataFrame, dataset_id: str, version_id: str, version_number: int, created_by: str) -> List[DatasetRecommendation]:
        recs = []
        total_rows = len(df)
        if total_rows == 0:
            return recs

        for col_name in df.columns:
            null_count = int(df[col_name].isna().sum())
            if null_count == 0:
                continue

            null_percentage = null_count / total_rows
            series = df[col_name]
            semantic_type = self._infer_semantic_type(series)

            if null_percentage > CLEANING_THRESHOLDS["missing_values"]["critical"]:
                severity = "critical"
            elif null_percentage > CLEANING_THRESHOLDS["missing_values"]["high"]:
                severity = "high"
            elif null_percentage > CLEANING_THRESHOLDS["missing_values"]["medium"]:
                severity = "medium"
            else:
                severity = "low"

            recs.append(DatasetRecommendation(
                dataset_id=dataset_id,
                version_id=version_id,
                version_number=version_number,
                recommendation_type="missing_values",
                severity=severity,
                priority_score=self._calculate_priority(severity, "missing_values"),
                column_name=col_name,
                description=f"Column '{col_name}' has {null_count} missing values ({null_percentage:.1%} of data)",
                suggested_action=f"Impute or handle missing values in '{col_name}'",
                algorithm_metadata={
                    "null_count": null_count,
                    "null_percentage": null_percentage,
                    "semantic_type": semantic_type,
                },
                estimated_quality_gain=15.0 if severity in ['critical', 'high'] else 5.0,
                created_by=created_by
            ))

        return recs

    def _check_duplicates(self, profile: Any, df: pd.DataFrame, dataset_id: str, version_id: str, version_number: int, created_by: str) -> List[DatasetRecommendation]:
        recs = []
        total_rows = len(df)
        if total_rows == 0:
            return recs

        dup_count = int(getattr(profile, "duplicate_rows", df.duplicated().sum()))
        dup_percentage = getattr(profile, "duplicate_percentage", dup_count / total_rows if total_rows > 0 else 0.0)

        if dup_count == 0:
            return recs

        if dup_percentage > CLEANING_THRESHOLDS["duplicates"]["critical"]:
            severity = "critical"
        elif dup_percentage > CLEANING_THRESHOLDS["duplicates"]["high"]:
            severity = "high"
        elif dup_percentage > CLEANING_THRESHOLDS["duplicates"]["medium"]:
            severity = "medium"
        else:
            severity = "low"

        recs.append(DatasetRecommendation(
            dataset_id=dataset_id,
            version_id=version_id,
            version_number=version_number,
            recommendation_type="duplicates",
            severity=severity,
            priority_score=self._calculate_priority(severity, "duplicates"),
            column_name=None,
            description=f"Dataset contains {dup_count} duplicate rows ({dup_percentage:.1%} of data)",
            suggested_action="Remove duplicate rows, keeping first occurrence",
            algorithm_metadata={
                "duplicate_count": dup_count,
                "duplicate_percentage": dup_percentage,
                "total_rows": total_rows,
                "strategy": "keep_first"
            },
            estimated_quality_gain=8.0 if severity in ['critical', 'high'] else 3.0,
            created_by=created_by
        ))
        return recs

    def _check_type_conversions(self, profile: DatasetProfile, df: pd.DataFrame, dataset_id: str, version_id: str, version_number: int, created_by: str) -> List[DatasetRecommendation]:
        recs = []
        for col_name in df.columns:
            series = df[col_name]
            current_dtype = str(series.dtype)
            
            # Skip if it's already explicitly numeric or datetime
            if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
                continue
                
            semantic_type = self._infer_semantic_type(series)
            if semantic_type == "numeric":
                recs.append(DatasetRecommendation(
                    dataset_id=dataset_id,
                    version_id=version_id,
                    version_number=version_number,
                    recommendation_type="type_conversion",
                    severity="medium",
                    priority_score=self._calculate_priority("medium", "type_conversion"),
                    column_name=col_name,
                    description=f"Column '{col_name}' contains numeric values stored as text",
                    suggested_action="Convert column type from string to numeric (float64)",
                    algorithm_metadata={
                        "current_dtype": current_dtype,
                        "detected_semantic_type": semantic_type,
                        "parse_method": "pd.to_numeric()"
                    },
                    estimated_quality_gain=5.0,
                    created_by=created_by
                ))
            elif semantic_type == "datetime":
                recs.append(DatasetRecommendation(
                    dataset_id=dataset_id,
                    version_id=version_id,
                    version_number=version_number,
                    recommendation_type="type_conversion",
                    severity="medium",
                    priority_score=self._calculate_priority("medium", "type_conversion"),
                    column_name=col_name,
                    description=f"Column '{col_name}' contains date values stored as text",
                    suggested_action="Convert column type to datetime",
                    algorithm_metadata={
                        "current_dtype": current_dtype,
                        "detected_semantic_type": semantic_type,
                        "parse_method": "pd.to_datetime()"
                    },
                    estimated_quality_gain=5.0,
                    created_by=created_by
                ))
                
        return recs

    def _check_outliers(self, profile: DatasetProfile, df: pd.DataFrame, dataset_id: str, version_id: str, version_number: int, created_by: str) -> List[DatasetRecommendation]:
        recs = []
        for col_name in df.columns:
            series = df[col_name]
            if not pd.api.types.is_numeric_dtype(series):
                continue
                
            series_clean = series.dropna()
            if series_clean.empty:
                continue
                
            Q1 = series_clean.quantile(0.25)
            Q3 = series_clean.quantile(0.75)
            IQR = Q3 - Q1
            iqr_mult = CLEANING_THRESHOLDS["outliers"]["iqr_multiplier"]
            lower_bound = Q1 - iqr_mult * IQR
            upper_bound = Q3 + iqr_mult * IQR
            
            outliers_mask = (series_clean < lower_bound) | (series_clean > upper_bound)
            outlier_count = outliers_mask.sum()
            total_rows = len(df)
            
            if outlier_count == 0:
                continue
                
            outlier_pct = outlier_count / total_rows
            
            if outlier_pct > CLEANING_THRESHOLDS["outliers"]["critical_percentage"]:
                severity = "critical"
            elif outlier_pct > CLEANING_THRESHOLDS["outliers"]["high_percentage"]:
                severity = "high"
            else:
                severity = "medium"
                
            recs.append(DatasetRecommendation(
                dataset_id=dataset_id,
                version_id=version_id,
                version_number=version_number,
                recommendation_type="outliers",
                severity=severity,
                priority_score=self._calculate_priority(severity, "outliers"),
                column_name=col_name,
                description=f"Column '{col_name}' contains {outlier_count} extreme outliers ({outlier_pct:.1%} of data)",
                suggested_action="Review outliers before analysis (may be legitimate or data errors)",
                algorithm_metadata={
                    "method": "iqr",
                    "iqr_multiplier": iqr_mult,
                    "lower_bound": float(lower_bound),
                    "upper_bound": float(upper_bound),
                    "outlier_count": int(outlier_count),
                    "outlier_percentage": float(outlier_pct)
                },
                estimated_quality_gain=5.0,
                created_by=created_by
            ))
            
        return recs

    def _check_consistency(self, profile: DatasetProfile, df: pd.DataFrame, dataset_id: str, version_id: str, version_number: int, created_by: str) -> List[DatasetRecommendation]:
        recs = []
        for col_name in df.columns:
            series = df[col_name]
            if pd.api.types.is_string_dtype(series):
                series_clean = series.dropna()
                if series_clean.empty:
                    continue
                    
                unique_vals = series_clean.unique()
                if len(unique_vals) > 0 and len(unique_vals) < 50:
                    # Check for casing consistency
                    lower_vals = [str(v).lower() for v in unique_vals]
                    if len(set(lower_vals)) < len(unique_vals):
                        recs.append(DatasetRecommendation(
                            dataset_id=dataset_id,
                            version_id=version_id,
                            version_number=version_number,
                            recommendation_type="consistency",
                            severity="medium",
                            priority_score=self._calculate_priority("medium", "consistency"),
                            column_name=col_name,
                            description=f"Column '{col_name}' contains inconsistent casing in categories",
                            suggested_action="Standardize category values (e.g., to lowercase)",
                            algorithm_metadata={"inconsistency_type": "casing"},
                            estimated_quality_gain=3.0,
                            created_by=created_by
                        ))
        return recs

    def _check_quality_improvements(self, quality: DatasetQuality, dataset_id: str, version_id: str, version_number: int, created_by: str) -> List[DatasetRecommendation]:
        recs = []
        if quality.overall_score < CLEANING_THRESHOLDS["quality_improvement"]["critical_current_score"]:
            recs.append(DatasetRecommendation(
                dataset_id=dataset_id,
                version_id=version_id,
                version_number=version_number,
                recommendation_type="quality_improvement",
                severity="critical",
                priority_score=self._calculate_priority("critical", "quality_improvement"),
                column_name=None,
                description=f"Overall Quality Score is {quality.overall_score:.1f}/100. Dataset needs significant cleaning.",
                suggested_action="Review and apply Critical/High recommendations to improve score.",
                algorithm_metadata={"current_score": quality.overall_score},
                estimated_quality_gain=100.0 - quality.overall_score,
                created_by=created_by
            ))
        return recs

    def _calculate_priority(self, severity: str, rec_type: str) -> int:
        sev_multiplier = {
            "critical": 1.0,
            "high": 0.8,
            "medium": 0.5,
            "low": 0.2
        }.get(severity, 0.5)
        
        weight = PRIORITY_WEIGHTS.get(rec_type, 0.1)
        # Normalize to 0-100 score
        score = int((sev_multiplier * 0.7 + weight * 0.3) * 100)
        return min(max(score, 0), 100)

def get_data_cleaning_recommendation_service(
    db: Session = Depends(get_db_session),
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
) -> DataCleaningRecommendationService:
    from backend.app.repositories.dataset_recommendation_repository import DatasetRecommendationRepository
    from backend.app.repositories.dataset_repository import DatasetRepository
    from backend.app.repositories.dataset_version_repository import DatasetVersionRepository

    return DataCleaningRecommendationService(
        recommendation_repo=DatasetRecommendationRepository(db=db),
        dataset_repo=dataset_repository,
        version_repo=DatasetVersionRepository(db=db),
        db=db,
    )
