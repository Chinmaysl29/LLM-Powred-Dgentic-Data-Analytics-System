"""Pydantic schemas for Phase 3.5 EDA Agent."""

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


DatasetType = Literal[
    "sales",
    "marketing",
    "finance",
    "inventory",
    "customer",
    "operations",
    "general",
]

DistributionType = Literal["normal", "skewed", "uniform"]
TrendDirection = Literal["growth", "decline", "stable", "fluctuating"]
CardinalityLevel = Literal["low", "medium", "high"]


class DatasetSummary(BaseModel):
    """Overall dataset understanding and summary."""

    model_config = ConfigDict(from_attributes=True)

    dataset_id: str | None = Field(None, description="Dataset ID")
    dataset_type: str = Field(..., description="Inferred dataset type (sales, customer, etc.)")
    business_domain: str = Field(..., description="Detected business domain")
    row_count: int = Field(..., description="Total row count evaluated")
    column_count: int = Field(..., description="Total column count evaluated")
    column_names: list[str] = Field(default_factory=list, description="List of columns")
    numeric_columns: list[str] = Field(default_factory=list, description="List of numeric columns")
    categorical_columns: list[str] = Field(default_factory=list, description="List of categorical columns")
    datetime_columns: list[str] = Field(default_factory=list, description="List of datetime/time-series columns")
    data_categories: list[str] = Field(default_factory=list, description="Data categories detected")
    memory_usage_mb: float = Field(..., description="Estimated memory usage in MB")
    is_sampled: bool = Field(False, description="Whether EDA was performed on a sample")


class NumericColumnStatistics(BaseModel):
    """Detailed descriptive statistical summary for a single numeric column."""

    count: int = Field(..., description="Count of non-null elements")
    mean: float = Field(..., description="Mean value")
    median: float = Field(..., description="Median (50th percentile)")
    mode: float | None = Field(None, description="Primary mode value")
    std: float = Field(..., description="Standard deviation")
    variance: float = Field(..., description="Variance")
    min: float = Field(..., description="Minimum value")
    max: float = Field(..., description="Maximum value")
    q25: float = Field(..., description="25th percentile")
    q75: float = Field(..., description="75th percentile")


class ColumnMissingDetail(BaseModel):
    """Missing value details for a single column."""

    missing_count: int = Field(..., description="Number of missing values")
    missing_percentage: float = Field(..., description="Percentage of missing values (0.0 - 100.0)")


class MissingValuesAnalysis(BaseModel):
    """Missing value analysis across the dataset."""

    total_missing_cells: int = Field(..., description="Total missing cells across all columns")
    missing_percentage: float = Field(..., description="Overall missing percentage across all cells")
    affected_columns_count: int = Field(..., description="Number of columns with missing data")
    affected_columns: list[str] = Field(default_factory=list, description="Names of columns with missing values")
    column_details: dict[str, ColumnMissingDetail] = Field(
        default_factory=dict, description="Missing metrics per affected column"
    )


class ColumnDistribution(BaseModel):
    """Distribution analysis for a numeric column."""

    distribution_type: DistributionType = Field(..., description="Inferred distribution: normal, skewed, uniform")
    skewness: float = Field(..., description="Skewness coefficient")
    kurtosis: float = Field(..., description="Kurtosis coefficient")
    is_symmetric: bool = Field(..., description="Whether distribution is roughly symmetric")
    description: str = Field(..., description="Human-readable distribution assessment")


class OutlierDetectionDetail(BaseModel):
    """Outlier detection results using a specific method (IQR or Z-score)."""

    method: str = Field(..., description="Detection method (IQR or Z-score)")
    outlier_count: int = Field(..., description="Number of detected outliers")
    outlier_percentage: float = Field(..., description="Percentage of values identified as outliers")
    lower_bound: float | None = Field(None, description="Lower cutoff threshold")
    upper_bound: float | None = Field(None, description="Upper cutoff threshold")
    sample_outliers: list[float] = Field(default_factory=list, description="Sample of detected outlier values")


class ColumnOutliers(BaseModel):
    """Outlier results for a numeric column across detection methods."""

    iqr: OutlierDetectionDetail = Field(..., description="IQR-based outlier detection")
    z_score: OutlierDetectionDetail = Field(..., description="Z-score-based outlier detection")


class CorrelationPair(BaseModel):
    """A pair of columns with significant correlation."""

    column_a: str = Field(..., description="First column")
    column_b: str = Field(..., description="Second column")
    correlation: float = Field(..., description="Pearson correlation coefficient (-1.0 to 1.0)")
    strength: str = Field(..., description="Qualitative strength (strong_positive, moderate, etc.)")


class CorrelationAnalysis(BaseModel):
    """Correlation analysis among numeric columns."""

    correlation_matrix: dict[str, dict[str, float]] = Field(
        default_factory=dict, description="Pairwise Pearson correlation matrix"
    )
    strongest_correlations: list[CorrelationPair] = Field(
        default_factory=list, description="Top absolute correlation pairs (|r| >= 0.5)"
    )
    top_positive: CorrelationPair | None = Field(None, description="Strongest positive correlation")
    top_negative: CorrelationPair | None = Field(None, description="Strongest negative correlation")


class TrendPattern(BaseModel):
    """Time-series trend pattern for a metric column."""

    metric_column: str = Field(..., description="Numeric metric being analyzed")
    date_column: str = Field(..., description="Date/timestamp column")
    trend_type: TrendDirection = Field(..., description="Growth, decline, stable, or fluctuating")
    growth_rate_pct: float = Field(..., description="Estimated percentage change over the period")
    seasonality_detected: bool = Field(..., description="Whether cyclical/seasonal pattern was identified")
    description: str = Field(..., description="Summary of the trend (e.g. Revenue increasing 7.5% monthly)")


class TrendAnalysis(BaseModel):
    """Time-series and trend detection results."""

    has_time_series: bool = Field(..., description="Whether time-series data was detected")
    date_columns: list[str] = Field(default_factory=list, description="Identified date/time columns")
    trends: list[TrendPattern] = Field(default_factory=list, description="Detected trends per metric")


class CategoryDetail(BaseModel):
    """Analysis for a categorical column."""

    unique_count: int = Field(..., description="Total distinct categories")
    cardinality_level: CardinalityLevel = Field(..., description="Cardinality classification (low, medium, high)")
    top_categories: dict[str, int] = Field(default_factory=dict, description="Top categories with counts")
    frequency_distribution: dict[str, float] = Field(
        default_factory=dict, description="Top categories with relative frequency percentage"
    )


class BusinessInsight(BaseModel):
    """Business-level actionable insight derived from statistical findings."""

    category: str = Field(..., description="Category (distribution, correlation, trend, anomaly, etc.)")
    title: str = Field(..., description="Concise insight title")
    insight: str = Field(..., description="Business readable insight sentence")
    impact: str = Field("medium", description="Business impact level: low, medium, high")


class ChartManifest(BaseModel):
    chart_id: str
    chart_type: Literal["histogram", "scatter", "time_series", "grouped_bar"]
    dataset_id: str | None = None
    version: int | None = None
    analysis_run_id: str | None = None
    source_data_reference: str | None = None
    source_checksum: str | None = None
    metric: str
    dimension: str
    aggregation: str
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    total_source_rows: int
    rendered_rows: int
    sampling_method: str = "none"
    coordinate_data: list[dict[str, Any]] = Field(default_factory=list)
    units: str = "source units"
    null_handling: str = "Exclude null and non-finite coordinates"
    computation_metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class EDAResults(BaseModel):
    """Standardized output structure for the EDA Agent."""

    chart_manifest: list[ChartManifest] = Field(default_factory=list)
    dataset_summary: DatasetSummary = Field(..., description="High-level understanding and metadata")
    statistics: dict[str, NumericColumnStatistics] = Field(
        default_factory=dict, description="Statistical summary for numeric columns"
    )
    missing_values: MissingValuesAnalysis = Field(..., description="Missing value analysis")
    distributions: dict[str, ColumnDistribution] = Field(
        default_factory=dict, description="Distribution analysis per numeric column"
    )
    outliers: dict[str, ColumnOutliers] = Field(
        default_factory=dict, description="Outlier detection per numeric column"
    )
    correlations: CorrelationAnalysis = Field(..., description="Correlation matrix and top pairs")
    trends: TrendAnalysis = Field(..., description="Trend and seasonality analysis")
    categorical_analysis: dict[str, CategoryDetail] = Field(
        default_factory=dict, description="Category distributions and cardinality"
    )
    business_insights: list[BusinessInsight] = Field(
        default_factory=list, description="Human-readable business insights"
    )


class EDAResponse(BaseModel):
    """API response envelope for EDA operations."""

    dataset_id: str = Field(..., description="Dataset ID analyzed")
    status: str = Field("success", description="Execution status")
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")
    eda_results: EDAResults = Field(..., description="Complete EDA analysis results")
