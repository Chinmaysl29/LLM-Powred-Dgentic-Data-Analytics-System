"""Pydantic request and response schemas for Dataset foundation operations."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DatasetResponse(BaseModel):
    """Schema representing a persisted dataset entity."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: str = Field(..., description="Unique dataset identifier")
    dataset_name: str = Field(..., description="Human-readable name of the dataset")
    file_name: str = Field(..., description="Original filename of the uploaded file")
    file_type: str = Field(..., description="Extension/format type (csv, xlsx, json)")
    file_path: str = Field(..., description="Storage file path on disk")
    original_path: str | None = Field(None, description="Immutable source file path")
    json_path: str | None = Field(None, description="JSON preview or document artifact path")
    canonical_path: str | None = Field(None, description="Canonical tabular artifact path")
    canonical_format: str | None = Field(None, description="Canonical storage format")
    content_hash: str | None = Field(None, description="SHA-256 of the original file")
    size_bytes: int | None = Field(None, description="Source file size in bytes")
    row_count: int | None = Field(None, description="Parsed tabular row count")
    column_count: int | None = Field(None, description="Parsed tabular column count")
    version: int = Field(default=1, description="Dataset version number")
    last_active_version_id: str | None = Field(None, description="UUID of the current active version")
    status: str = Field(default="uploaded", description="Current lifecycle status")
    created_at: datetime = Field(..., description="Timestamp of dataset creation")
    updated_at: datetime = Field(..., description="Timestamp of last update")


class DatasetUploadResponse(DatasetResponse):
    """Schema representing upload response including pipeline summary."""

    message: str = Field(default="Dataset uploaded successfully")
    indexing_status: str = Field(default='NOT_APPLICABLE', description='Storage success is separate from searchable readiness')
    version_info: dict | None = Field(None, description="Initial version information")
    quality_score: float | None = Field(None, description="Overall data quality score")
    classification: str | None = Field(None, description="Quality classification")
    recommendations_summary: str | None = Field(None, description="Summary of generated cleaning recommendations")


class DatasetUpdate(BaseModel):
    """Schema for partial updates to a dataset record."""

    dataset_name: str | None = Field(None, min_length=1, max_length=255)
    status: str | None = Field(None, min_length=1, max_length=50)


class DatasetListResponse(BaseModel):
    """Paginated list response of datasets."""

    items: list[DatasetResponse]
    total: int
    skip: int
    limit: int


class DatasetPreviewResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    preview_rows: int
    total_rows: int | None
    count_status: Literal["exact", "unknown"]
    dataset_version: int | None = None
    column_types: dict[str, str] = Field(default_factory=dict)
    source_type: str = Field(default="tabular", description="Source classification type, e.g. tabular")


class ChartQueryRequest(BaseModel):
    chart_type: str = Field(default="Bar", description="Bar, Line, Area, Pie, Scatter, Histogram, Table, Heatmap, Treemap")
    x_axis: str = Field(default="", description="Category or date field")
    y_axis: str = Field(default="", description="Numeric measure field")
    aggregation: str = Field(default="sum", description="sum, mean, count, min, max, median")
    group_by: str = Field(default="", description="Secondary grouping field")
    filter_field: str = Field(default="", description="Field to filter on")
    filter_value: str = Field(default="", description="Value to match")
    date_field: str = Field(default="", description="Date field for range filter")
    start_date: str = Field(default="", description="Start date ISO string")
    end_date: str = Field(default="", description="End date ISO string")
    version: int | None = Field(default=None, description="Dataset version number")
    limit_categories: int = Field(default=30, description="Max categories to return in chart")
    max_scatter_points: int = Field(default=1000, description="Max points to sample for scatter plot")


class ChartQueryResponse(BaseModel):
    dataset_id: str
    dataset_version: int | None = None
    chart_type: str
    metric: str
    dimension: str
    aggregation: str
    unit: str = "source units"
    is_valid: bool = True
    validation_message: str | None = None
    total_records: int
    eligible_records: int
    computed_records: int
    is_sampled: bool = False
    sampling_disclosure: str | None = None
    points: list[dict[str, Any]] = Field(default_factory=list)
    scatter_points: list[dict[str, Any]] | None = None
    scatter_bounds: dict[str, float] | None = None
    histogram_bins: list[dict[str, Any]] | None = None
    summary_metrics: dict[str, Any] = Field(default_factory=dict)
