"""Dataset API routes for Phase 2.1 Dataset Foundation."""

import json
import logging
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import numpy as np
import pandas as pd
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status, Query

from backend.app.models.dataset import Dataset
from backend.app.models.dataset_metadata import DatasetMetadata
from backend.app.models.dataset_profile import DatasetProfile
from backend.app.models.dataset_quality import DatasetQuality
from backend.app.repositories.dataset_repository import (
    DatasetRepository,
    get_dataset_repository,
)
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
from backend.app.schemas.dataset import (
    ChartQueryRequest,
    ChartQueryResponse,
    DatasetListResponse,
    DatasetPreviewResponse,
    DatasetResponse,
    DatasetUpdate,
    DatasetUploadResponse,
)
from backend.app.schemas.dataset_metadata import DatasetMetadataResponse
from backend.app.schemas.dataset_profile import DatasetProfileResponse
from backend.app.schemas.dataset_quality import DatasetQualityResponse
from backend.app.services.storage_service import StorageService, get_storage_service
from backend.app.services.metadata_extraction_service import (
    MetadataExtractionService,
    get_metadata_extraction_service,
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
    VersioningError,
)
from backend.app.schemas.dataset_version import (
    DatasetVersionResponse,
    DatasetVersionComparisonResponse,
    DatasetVersionListResponse,
)
from backend.app.services.data_cleaning_recommendation_service import (
    DataCleaningRecommendationService,
    get_data_cleaning_recommendation_service,
)
from backend.app.services.dataset_upload_service import (
    DatasetUploadService,
    get_dataset_upload_service,
)
from backend.app.schemas.dataset_recommendation import (
    DatasetRecommendationListResponse,
    DatasetRecommendationResponse,
)

logger = logging.getLogger(__name__)

from backend.app.core.security import get_current_user
from backend.app.database.postgres import get_db_session
from backend.app.core.workspace_authorization import authorize_workspace, dataset_workspace_bindings

router = APIRouter(prefix="/datasets", tags=["datasets"])


class DatasetWorkspaceBinding(BaseModel):
    workspace_id: UUID


@router.post('/{dataset_id}/workspace')
def bind_dataset_workspace(dataset_id: str, payload: DatasetWorkspaceBinding,
                           user=Depends(get_current_user), db: Session = Depends(get_db_session)):
    """Bind an already owned dataset to a verified workspace; never reassign it.

    Gateway dataset ownership is required in addition to workspace membership.
    Legacy NULL owners cannot reach this handler. No client tenant/owner is used.
    """
    from backend.app.core.authorization import owned_dataset
    owned_dataset(db, dataset_id, str(user.id))
    access = authorize_workspace(db, user.id, payload.workspace_id, 'write')
    try:
        existing = db.scalar(select(dataset_workspace_bindings.c.workspace_id).where(
            dataset_workspace_bindings.c.dataset_id == dataset_id))
        if existing is not None and existing != access.workspace_id:
            raise HTTPException(409, 'Dataset workspace binding is immutable')
        if existing is None:
            db.execute(dataset_workspace_bindings.insert().values(dataset_id=dataset_id, workspace_id=access.workspace_id))
            db.commit()
        from sqlalchemy.orm import sessionmaker
        from backend.app.services.document_indexing_service import DocumentIndexingService
        indexing = DocumentIndexingService(sessionmaker(bind=db.get_bind(), expire_on_commit=False))
        job = indexing.enqueue(dataset_id, user.id)
        return {'dataset_id': dataset_id, 'workspace_id': str(access.workspace_id),
                'indexing_status': job['status'] if job else 'NOT_APPLICABLE'}
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Dataset binding changed; reload before retrying') from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, 'Workspace binding storage is unavailable') from None


@router.post(
    "/upload",
    response_model=DatasetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new dataset file",
    description="Upload a CSV, XLSX, or JSON file, store it, create a dataset record, and return the dataset entity.",
)
async def upload_dataset(
    file: Annotated[UploadFile, File(description="CSV, XLSX, or JSON dataset file")],
    dataset_name: Annotated[str | None, Form(description="Optional custom dataset name")] = None,
    upload_service: DatasetUploadService = Depends(get_dataset_upload_service),
) -> Any:
    """Execute upload flow via dedicated DatasetUploadService."""
    logger.info("Received dataset upload request filename=%s", file.filename)
    return await upload_service.process_upload(file=file, dataset_name=dataset_name)


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    summary="Get dataset metadata by ID",
)
async def get_dataset(
    dataset_id: str,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
) -> DatasetResponse:
    """Retrieve metadata for a specific dataset."""
    dataset = dataset_repository.get(dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID '{dataset_id}' not found",
        )
    return DatasetResponse.model_validate(dataset)
@router.get(
    "/{dataset_id}/metadata",
    response_model=DatasetMetadataResponse,
    summary="Get dataset metadata by ID",
)
async def get_dataset_metadata(
    dataset_id: str,
    metadata_repository: DatasetMetadataRepository = Depends(get_dataset_metadata_repository),
) -> DatasetMetadataResponse:
    """Retrieve extracted metadata for a specific dataset."""
    metadata = metadata_repository.get(dataset_id)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metadata for dataset with ID '{dataset_id}' not found",
        )
    
    # We must convert the dictionary classifications to a structured response, since our model returns dict
    # but Pydantic expects DatasetClassification schema.
    # The dictionary matches exactly the DatasetClassification schema fields.
    return DatasetMetadataResponse.model_validate(metadata)


@router.get(
    "/{dataset_id}/profile",
    response_model=DatasetProfileResponse,
    summary="Get dataset profile by ID",
)
async def get_dataset_profile(
    dataset_id: str,
    profile_repository: DatasetProfileRepository = Depends(get_dataset_profile_repository),
) -> DatasetProfileResponse:
    """Retrieve statistical profile for a specific dataset."""
    profile = profile_repository.get(dataset_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile for dataset with ID '{dataset_id}' not found",
        )
    return DatasetProfileResponse.model_validate(profile)


@router.get(
    "/{dataset_id}/quality",
    response_model=DatasetQualityResponse,
    summary="Get dataset quality by ID",
)
async def get_dataset_quality(
    dataset_id: str,
    quality_repository: DatasetQualityRepository = Depends(get_dataset_quality_repository),
) -> DatasetQualityResponse:
    """Retrieve quality assessment for a specific dataset."""
    quality = quality_repository.get(dataset_id)
    if not quality:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quality record for dataset with ID '{dataset_id}' not found",
        )
    return DatasetQualityResponse.model_validate(quality)


@router.get(
    "/{dataset_id}/preview",
    summary="Get preview records for a dataset",
    response_model=DatasetPreviewResponse,
)
async def get_dataset_preview(
    dataset_id: str,
    request: Request = None,
    version: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    storage_service: StorageService = Depends(get_storage_service),
) -> dict[str, Any]:
    """A bounded preview is not a dataset count. Failures are never empty success."""
    import pandas as pd
    from backend.app.models.dataset_version import DatasetVersion
    from backend.app.core.exceptions import StorageFileNotFoundError

    dataset = dataset_repository.get(dataset_id)
    if not dataset:
        raise HTTPException(404, detail={"code": "dataset_not_found", "message": "Dataset not found."})
    resolved_version = None
    db = getattr(dataset_repository, "session", None)
    if db is not None:
        query = db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset_id)
        resolved_version = query.filter(DatasetVersion.version_number == version).first() if version is not None else query.filter(DatasetVersion.is_active == True).first()
    if version is not None and resolved_version is None:
        raise HTTPException(404, detail={"code": "version_not_found", "message": "Dataset version not found."})
    total = (resolved_version.metadata_snapshot or {}).get("row_count") if resolved_version else getattr(dataset, "row_count", None)
    total = total if isinstance(total, int) and total >= 0 else None
    current_version = resolved_version.version_number if resolved_version else getattr(dataset, "version", None)
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    try:
        # A registered version is authoritative, including rollback snapshots.
        artifact = (
            resolved_version.storage_path
            if resolved_version
            else getattr(dataset, "canonical_path", None)
            or getattr(dataset, "file_path", None)
            or getattr(dataset, "json_path", None)
        )
        if not artifact:
            raise FileNotFoundError()
        path = storage_service.retrieve_file(artifact)
        kind = path.suffix.lower().lstrip(".")
        if kind in {"pdf", "txt", "text", "md", "markdown"}:
            raise HTTPException(400, detail={
                "code": "unstructured_document_source",
                "message": f"This source is an unstructured document ({kind.upper()}) configured for Document RAG analysis, not tabular charting.",
                "source_type": "document",
                "dataset_id": dataset_id,
            })
        elif kind in {"csv", "tsv", "xlsx", "xls", "json", "jsonl", "ndjson", "parquet"}:
            from backend.app.services.tabular_loader import load_tabular_dataframe
            # Load with smart headers and financial numeric parsing
            df = load_tabular_dataframe(path, kind, nrows=limit + 1)
            if len(df) <= limit:
                total = len(df)
            elif total is not None and total < len(df):
                total = None
        else:
            raise HTTPException(422, detail={"code": "unsupported_preview_format", "message": "This format has no supported tabular preview."})
        rows = json.loads(df.head(limit).to_json(orient="records", date_format="iso"))
        return {"columns": list(df.columns), "rows": rows, "preview_rows": len(rows), "total_rows": total,
                "count_status": "exact" if total is not None else "unknown", "dataset_version": current_version,
                "column_types": {str(column): str(dtype) for column, dtype in df.dtypes.items()},
                "source_type": "tabular"}
    except HTTPException:
        raise
    except (FileNotFoundError, StorageFileNotFoundError):
        code, error, message = 404, "preview_artifact_missing", "The dataset source is unavailable."
    except PermissionError:
        code, error, message = 403, "preview_access_denied", "Access to the dataset source was denied."
    except (ValueError, UnicodeError, pd.errors.ParserError, pd.errors.EmptyDataError):
        code, error, message = 422, "preview_parse_failed", "The dataset source could not be parsed."
    except OSError:
        code, error, message = 503, "preview_storage_unavailable", "Dataset storage is temporarily unavailable. Retry later."
    except Exception:
        logger.exception("Unexpected preview error dataset=%s request_id=%s", dataset_id, request_id)
        raise HTTPException(500, detail={"code": "preview_failed", "message": "Preview generation failed.", "request_id": request_id})
    logger.warning("Preview failed dataset=%s code=%s request_id=%s", dataset_id, error, request_id)
    raise HTTPException(code, detail={"code": error, "message": message, "request_id": request_id})


@router.post(
    "/{dataset_id}/chart-data",
    summary="Compute full-population analytical chart data",
    response_model=ChartQueryResponse,
)
async def post_chart_data(
    dataset_id: str,
    payload: ChartQueryRequest,
    current_user=Depends(get_current_user),
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    storage_service: StorageService = Depends(get_storage_service),
) -> ChartQueryResponse:
    """Execute analytical calculations over the full authorized dataset population.
    
    A 100-row preview must never be the source of truth for full analytical calculations.
    Computes exact aggregations, genuine scatter points (with disclosed sampling if > 1000),
    histograms, and KPIs directly from the authoritative source artifact.
    """
    import numpy as np
    from backend.app.core.authorization import owned_dataset
    from backend.app.models.dataset_version import DatasetVersion
    from backend.app.services.tabular_loader import load_tabular_dataframe, IDENTIFIER_PATTERN

    db = getattr(dataset_repository, "session", None)
    if db is not None:
        owned_dataset(db, dataset_id, str(current_user.id))

    dataset = dataset_repository.get(dataset_id)
    if not dataset:
        raise HTTPException(404, detail={"code": "dataset_not_found", "message": "Dataset not found."})

    resolved_version = None
    if db is not None:
        query = db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset_id)
        resolved_version = (
            query.filter(DatasetVersion.version_number == payload.version).first()
            if payload.version is not None
            else query.filter(DatasetVersion.is_active == True).first()
        )

    current_version = resolved_version.version_number if resolved_version else getattr(dataset, "version", None)
    artifact = (
        resolved_version.storage_path
        if resolved_version
        else getattr(dataset, "canonical_path", None)
        or getattr(dataset, "json_path", None)
        or getattr(dataset, "file_path", None)
    )
    if not artifact:
        raise HTTPException(404, detail={"code": "source_artifact_missing", "message": "The dataset source is unavailable."})

    path = storage_service.retrieve_file(artifact)
    kind = path.suffix.lower().lstrip(".")
    if kind in {"pdf", "txt", "text", "md", "markdown"}:
        raise HTTPException(400, detail={
            "code": "unstructured_document_source",
            "message": f"This source is an unstructured document ({kind.upper()}) configured for Document RAG analysis, not tabular charting.",
            "source_type": "document",
            "dataset_id": dataset_id,
        })

    try:
        df = load_tabular_dataframe(path, kind)
    except Exception as exc:
        logger.exception("Failed to load tabular data for chart query: %s", exc)
        raise HTTPException(422, detail={"code": "parse_failed", "message": f"Failed to parse dataset: {exc}"})

    total_records = len(df)
    if total_records == 0:
        return ChartQueryResponse(
            dataset_id=dataset_id,
            dataset_version=current_version,
            chart_type=payload.chart_type,
            metric=payload.y_axis,
            dimension=payload.x_axis,
            aggregation=payload.aggregation,
            is_valid=False,
            validation_message="Dataset contains no observations.",
            total_records=0,
            eligible_records=0,
            computed_records=0,
        )

    # 1. Apply user filters across full population
    if payload.filter_field and payload.filter_field in df.columns and payload.filter_value:
        df = df[df[payload.filter_field].astype(str).str.contains(payload.filter_value, case=False, na=False)]

    if payload.date_field and payload.date_field in df.columns and (payload.start_date or payload.end_date):
        try:
            date_s = pd.to_datetime(df[payload.date_field], errors="coerce")
            if payload.start_date:
                df = df[date_s >= pd.to_datetime(payload.start_date)]
            if payload.end_date:
                df = df[date_s <= (pd.to_datetime(payload.end_date) + pd.Timedelta(days=1))]
        except Exception:
            pass

    eligible_records = len(df)
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c]) and not IDENTIFIER_PATTERN.search(c)]
    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c]) or "date" in c.lower() or "year" in c.lower()]
    cat_cols = [c for c in df.columns if c not in numeric_cols]

    # Dynamic fallback: never assume 'revenue' or hardcoded demo columns!
    metric = payload.y_axis if payload.y_axis in df.columns else (numeric_cols[0] if numeric_cols else "")
    dimension = payload.x_axis if payload.x_axis in df.columns else (cat_cols[0] if cat_cols else (df.columns[0] if len(df.columns) else ""))
    agg = payload.aggregation.lower() if payload.aggregation else "sum"

    chart_type = payload.chart_type
    points: list[dict[str, Any]] = []
    scatter_points: list[dict[str, Any]] | None = None
    scatter_bounds: dict[str, float] | None = None
    histogram_bins: list[dict[str, Any]] | None = None
    summary_metrics: dict[str, Any] = {}
    is_valid = True
    validation_message: str | None = None
    is_sampled = False
    sampling_disclosure = "Full population: 100% of eligible records computed."

    # Compute summary metrics over full eligible records
    if metric and metric in numeric_cols and eligible_records > 0:
        val_series = df[metric].dropna()
        if len(val_series):
            summary_metrics = {
                "count": int(len(val_series)),
                "sum": round(float(val_series.sum()), 4),
                "mean": round(float(val_series.mean()), 4),
                "min": round(float(val_series.min()), 4),
                "max": round(float(val_series.max()), 4),
                "median": round(float(val_series.median()), 4),
            }

    if chart_type == "Scatter":
        if len(numeric_cols) < 2:
            is_valid = False
            validation_message = "Scatter plot requires at least two numeric fields in the dataset."
        else:
            x_num = dimension if dimension in numeric_cols else numeric_cols[0]
            avail_y = [c for c in numeric_cols if c != x_num]
            y_num = metric if metric in numeric_cols and metric != x_num else (avail_y[0] if avail_y else numeric_cols[0])
            pair_df = df[[x_num, y_num]].dropna()
            total_valid = len(pair_df)
            if total_valid == 0:
                is_valid = False
                validation_message = "No paired numeric observations available after filtering."
            else:
                if total_valid > payload.max_scatter_points:
                    sampled = pair_df.sample(n=payload.max_scatter_points, random_state=42)
                    is_sampled = True
                    sampling_disclosure = f"Sampled {payload.max_scatter_points} of {total_valid} valid observations for chart responsiveness."
                else:
                    sampled = pair_df
                    is_sampled = False
                    sampling_disclosure = f"All {total_valid} valid observations displayed."
                scatter_points = [
                    {"x": round(float(row[x_num]), 4), "y": round(float(row[y_num]), 4), "label": f"{x_num}: {row[x_num]}, {y_num}: {row[y_num]}"}
                    for _, row in sampled.iterrows()
                ]
                scatter_bounds = {
                    "minX": float(pair_df[x_num].min()),
                    "maxX": float(pair_df[x_num].max()),
                    "minY": float(pair_df[y_num].min()),
                    "maxY": float(pair_df[y_num].max()),
                }
    elif chart_type == "Histogram":
        hist_metric = metric if metric in numeric_cols else (payload.x_axis if payload.x_axis in numeric_cols else (numeric_cols[0] if numeric_cols else ""))
        if not hist_metric:
            is_valid = False
            validation_message = "No numerical field is available for a distribution chart in this dataset."
        else:
            metric = hist_metric
            dimension = hist_metric
            agg = "frequency"
            unit = "observations"
            val_series = pd.to_numeric(df[hist_metric], errors="coerce").dropna()
            total_observations = len(val_series)
            if total_observations == 0:
                is_valid = False
                validation_message = "No numeric observations available after filtering."
            else:
                summary_metrics = {
                    "count": int(total_observations),
                    "sum": round(float(val_series.sum()), 4),
                    "mean": round(float(val_series.mean()), 4),
                    "min": round(float(val_series.min()), 4),
                    "max": round(float(val_series.max()), 4),
                    "median": round(float(val_series.median()), 4),
                    "excluded_count": int(len(df) - total_observations),
                }
                vals = val_series.values.astype(float)
                v_min = float(np.min(vals))
                v_max = float(np.max(vals))
                if v_min == v_max:
                    counts = np.array([len(vals)])
                    bin_edges = np.array([v_min - 0.5, v_max + 0.5])
                else:
                    q75, q25 = np.percentile(vals, [75, 25])
                    iqr = q75 - q25
                    if iqr > 0 and len(vals) > 10:
                        bin_width = 2 * iqr * (len(vals) ** (-1/3))
                        num_bins = int(np.clip(np.ceil((v_max - v_min) / max(bin_width, 1e-6)), 5, 20))
                    else:
                        num_bins = int(np.clip(np.ceil(np.log2(len(vals)) + 1), 5, 15))
                    counts, bin_edges = np.histogram(vals, bins=num_bins)

                histogram_bins = []
                for i in range(len(counts)):
                    b_start = round(float(bin_edges[i]), 2)
                    b_end = round(float(bin_edges[i+1]), 2)
                    c = int(counts[i])
                    pct = round(float(c / total_observations * 100), 1)
                    bin_label = f"{b_start:g} to {b_end:g}"
                    histogram_bins.append({
                        "bin_start": b_start,
                        "bin_end": b_end,
                        "count": c,
                        "percentage": pct,
                        "label": bin_label,
                    })
                    points.append({
                        "categoryKey": bin_label,
                        "label": bin_label,
                        "value": c,
                    })
    else:
        # Categorical / Aggregate charts: Bar, Line, Area, Pie, Treemap
        if eligible_records == 0:
            is_valid = False
            validation_message = "No records match the current filter."
        elif dimension not in df.columns:
            is_valid = False
            validation_message = "Select fields available in the current dataset."
        else:
            group_col = payload.group_by if payload.group_by in df.columns and payload.group_by != dimension else None
            group_cols = [dimension, group_col] if group_col else [dimension]

            if metric in numeric_cols and agg != "count":
                if agg == "mean":
                    grouped = df.groupby(group_cols)[metric].mean()
                elif agg == "min":
                    grouped = df.groupby(group_cols)[metric].min()
                elif agg == "max":
                    grouped = df.groupby(group_cols)[metric].max()
                elif agg == "median":
                    grouped = df.groupby(group_cols)[metric].median()
                else:
                    grouped = df.groupby(group_cols)[metric].sum()
            else:
                grouped = df.groupby(group_cols).size()
                agg = "count"
                metric = dimension

            if group_col:
                unstacked = grouped.reset_index(name="val")
                for _, row in unstacked.head(payload.limit_categories * 4).iterrows():
                    points.append({
                        "categoryKey": str(row[dimension]),
                        "seriesKey": str(row[group_col]),
                        "label": str(row[dimension]),
                        "value": round(float(row["val"]), 4) if pd.notna(row["val"]) else 0.0,
                        "group": str(row[group_col]),
                    })
            else:
                if dimension in date_cols:
                    grouped = grouped.sort_index()
                else:
                    grouped = grouped.sort_values(ascending=False)
                for cat_val, num_val in grouped.head(payload.limit_categories).items():
                    points.append({
                        "categoryKey": str(cat_val),
                        "label": str(cat_val) if pd.notna(cat_val) and str(cat_val).strip() else "Unknown",
                        "value": round(float(num_val), 4) if pd.notna(num_val) else 0.0,
                    })

    return ChartQueryResponse(
        dataset_id=dataset_id,
        dataset_version=current_version,
        chart_type=chart_type,
        metric=metric,
        dimension=dimension,
        aggregation=agg,
        unit="observations" if chart_type == "Histogram" else ("count" if agg == "count" else "source units"),
        is_valid=is_valid,
        validation_message=validation_message,
        total_records=total_records,
        eligible_records=eligible_records,
        computed_records=eligible_records,
        is_sampled=is_sampled,
        sampling_disclosure=sampling_disclosure,
        points=points,
        scatter_points=scatter_points,
        scatter_bounds=scatter_bounds,
        histogram_bins=histogram_bins,
        summary_metrics=summary_metrics,
    )


@router.get(
    "/{dataset_id}/versions",
    response_model=DatasetVersionListResponse,
    summary="List dataset versions",
)
async def list_dataset_versions(
    dataset_id: str,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    versioning_service: DatasetVersioningService = Depends(get_dataset_versioning_service),
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
) -> dict:
    """Retrieve all versions of a dataset."""
    if not dataset_repository.get(dataset_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID '{dataset_id}' not found",
        )
    versions, total = versioning_service.dataset_version_repository.get_versions(dataset_id, limit, offset)
    active = versioning_service.dataset_version_repository.get_active_version(dataset_id)
    return {
        "versions": [DatasetVersionResponse.model_validate(v) for v in versions],
        "total_count": total,
        "current_active_version": active.version_number if active else None
    }


@router.get(
    "/{dataset_id}/versions/compare",
    response_model=DatasetVersionComparisonResponse,
    summary="Compare two dataset versions",
)
async def compare_dataset_versions(
    dataset_id: str,
    v1: Annotated[int, Query(description="First version number")],
    v2: Annotated[int, Query(description="Second version number")],
    versioning_service: DatasetVersioningService = Depends(get_dataset_versioning_service),
) -> DatasetVersionComparisonResponse:
    """Compare rows and columns between two versions."""
    try:
        return versioning_service.compare_versions(dataset_id, v1, v2)
    except VersioningError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{dataset_id}/versions/{version_number}",
    response_model=DatasetVersionResponse,
    summary="Get a specific dataset version",
)
async def get_dataset_version(
    dataset_id: str,
    version_number: int,
    versioning_service: DatasetVersioningService = Depends(get_dataset_versioning_service),
) -> DatasetVersionResponse:
    """Retrieve details for a specific version."""
    try:
        v = versioning_service.dataset_version_repository.get_version(dataset_id, version_number)
        return DatasetVersionResponse.model_validate(v)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{dataset_id}/versions/{version_number}/rollback",
    summary="Rollback dataset to a specific version",
)
async def rollback_dataset_version(
    dataset_id: str,
    version_number: int,
    versioning_service: DatasetVersioningService = Depends(get_dataset_versioning_service),
) -> dict:
    """Set the specified version as active."""
    try:
        active = versioning_service.rollback_version(dataset_id, version_number)
        return {
            "message": "Rollback successful",
            "dataset_id": dataset_id,
            "rolled_back_to_version": active.version_number,
            "version_details": DatasetVersionResponse.model_validate(active).model_dump()
        }
    except VersioningError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if "not found" in str(e).lower() else status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/{dataset_id}/versions/{version_number}/lineage",
    summary="Get version lineage chain",
)
async def get_dataset_version_lineage(
    dataset_id: str,
    version_number: int,
    versioning_service: DatasetVersioningService = Depends(get_dataset_versioning_service),
) -> dict:
    """Retrieve the ancestry chain of a version."""
    try:
        chain = versioning_service.get_version_lineage(dataset_id, version_number)
        return {
            "dataset_id": dataset_id,
            "version_number": version_number,
            "lineage_chain": [c.model_dump() for c in chain]
        }
    except VersioningError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{dataset_id}/recommendations",
    response_model=DatasetRecommendationListResponse,
    summary="List data cleaning recommendations",
)
async def list_dataset_recommendations(
    dataset_id: str,
    recommendation_repository: DatasetRecommendationRepository = Depends(get_dataset_recommendation_repository),
) -> DatasetRecommendationListResponse:
    """Retrieve active cleaning recommendations for the dataset."""
    recs = recommendation_repository.get_active_recommendations_for_dataset(dataset_id)

    total = len(recs)
    critical = sum(1 for r in recs if r.severity == 'critical')
    return DatasetRecommendationListResponse(
        dataset_id=dataset_id,
        version_id=recs[0].version_id if recs else "",
        total_count=total,
        active_count=total,
        critical_count=critical,
        recommendations=[DatasetRecommendationResponse.model_validate(r) for r in recs],
        estimated_quality_after_all_fixes=sum(r.estimated_quality_gain for r in recs),
        summary=f"{critical} critical, {total - critical} other recommendations",
    )


@router.post(
    "/{dataset_id}/recommendations/{recommendation_id}/resolve",
    response_model=DatasetRecommendationResponse,
    summary="Mark recommendation as resolved",
)
async def resolve_dataset_recommendation(
    dataset_id: str,
    recommendation_id: str,
    recommendation_repository: DatasetRecommendationRepository = Depends(get_dataset_recommendation_repository),
) -> DatasetRecommendationResponse:
    """Mark a recommendation as resolved after acting on it."""
    try:
        rec = recommendation_repository.mark_resolved(recommendation_id, dataset_id=dataset_id)
        return DatasetRecommendationResponse.model_validate(rec)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get(
    "",
    response_model=list[DatasetResponse],
    summary="List all datasets",
)
async def list_datasets(
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Max records to return")] = 50,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
) -> list[DatasetResponse]:
    """List datasets ordered by creation time descending."""
    datasets = dataset_repository.list(skip=skip, limit=limit)
    return [DatasetResponse.model_validate(d) for d in datasets]


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete a dataset",
)
async def delete_dataset(
    dataset_id: str,
    dataset_repository: DatasetRepository = Depends(get_dataset_repository),
    storage_service: StorageService = Depends(get_storage_service),
) -> dict[str, str | bool]:
    """Delete dataset record and its backing storage file."""
    dataset = dataset_repository.get(dataset_id)
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID '{dataset_id}' not found",
        )

    # Delete the isolated source plus canonical artifacts.
    if not storage_service.delete_dataset(dataset_id):
        # Datasets uploaded before Phase 17.11 used a flat source-file layout.
        storage_service.delete_file(dataset.file_path)

    # Delete database record
    dataset_repository.delete(dataset_id)

    # Delete any associated vector embeddings from ChromaDB
    try:
        from backend.app.services.rag_service import get_pipeline
        pipeline = get_pipeline()
        pipeline._store.delete(document_id=dataset_id)
        logger.info("Deleted vector embeddings for dataset_id=%s from Chroma", dataset_id)
    except Exception as exc:
        logger.debug("No Chroma vector embeddings to delete for dataset_id=%s (%s)", dataset_id, exc)

    logger.info("Dataset deleted successfully dataset_id=%s", dataset_id)

    return {"success": True, "message": f"Dataset '{dataset_id}' deleted successfully"}
