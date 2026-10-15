/**
 * EDA Type Definitions — mirrors backend app/schemas/eda.py exactly.
 * All fields optional-safe for graceful frontend rendering.
 */

export interface NumericColumnStatistics {
  count: number;
  mean: number;
  median: number;
  mode?: number | null;
  std: number;
  variance: number;
  min: number;
  max: number;
  q25: number;
  q75: number;
}

export interface ColumnMissingDetail {
  missing_count: number;
  missing_percentage: number;
}

export interface MissingValuesAnalysis {
  total_missing_cells: number;
  missing_percentage: number;
  affected_columns_count: number;
  affected_columns: string[];
  column_details: Record<string, ColumnMissingDetail>;
}

export interface ColumnDistribution {
  distribution_type: 'normal' | 'skewed' | 'uniform';
  skewness: number;
  kurtosis: number;
  is_symmetric: boolean;
  description: string;
}

export interface OutlierDetectionDetail {
  method: string;
  outlier_count: number;
  outlier_percentage: number;
  lower_bound?: number | null;
  upper_bound?: number | null;
  sample_outliers: number[];
}

export interface ColumnOutliers {
  iqr: OutlierDetectionDetail;
  z_score: OutlierDetectionDetail;
}

export interface CorrelationPair {
  column_a: string;
  column_b: string;
  correlation: number;
  strength: string;
}

export interface CorrelationAnalysis {
  correlation_matrix: Record<string, Record<string, number>>;
  strongest_correlations: CorrelationPair[];
  top_positive?: CorrelationPair | null;
  top_negative?: CorrelationPair | null;
}

export interface TrendPattern {
  metric_column: string;
  date_column: string;
  trend_type: 'growth' | 'decline' | 'stable' | 'fluctuating';
  growth_rate_pct: number;
  seasonality_detected: boolean;
  description: string;
}

export interface TrendAnalysis {
  has_time_series: boolean;
  date_columns: string[];
  trends: TrendPattern[];
}

export interface CategoryDetail {
  unique_count: number;
  cardinality_level: 'low' | 'medium' | 'high';
  top_categories: Record<string, number>;
  frequency_distribution: Record<string, number>;
}

export interface BusinessInsight {
  category: string;
  title: string;
  insight: string;
  impact: 'low' | 'medium' | 'high';
}

export interface DatasetSummary {
  dataset_id?: string | null;
  dataset_type: string;
  business_domain: string;
  row_count: number;
  column_count: number;
  column_names: string[];
  numeric_columns: string[];
  categorical_columns: string[];
  datetime_columns: string[];
  data_categories: string[];
  memory_usage_mb: number;
  is_sampled: boolean;
}

export interface EDAResults {
  chart_manifest?: ChartManifest[];
  dataset_summary: DatasetSummary;
  statistics: Record<string, NumericColumnStatistics>;
  missing_values: MissingValuesAnalysis;
  distributions: Record<string, ColumnDistribution>;
  outliers: Record<string, ColumnOutliers>;
  correlations: CorrelationAnalysis;
  trends: TrendAnalysis;
  categorical_analysis: Record<string, CategoryDetail>;
  business_insights: BusinessInsight[];
}

export interface EDAResponse {
  dataset_id: string;
  status: string;
  execution_time_ms: number;
  eda_results: EDAResults;
}
export interface ChartManifest {
  chart_id: string; chart_type: 'histogram' | 'scatter' | 'time_series' | 'grouped_bar';
  dataset_id: string | null; version: number | null; source_checksum: string | null;
  source_data_reference: string | null; analysis_run_id: string | null;
  metric: string; dimension: string; aggregation: string; applied_filters: Record<string, unknown>;
  total_source_rows: number; rendered_rows: number; sampling_method: string;
  coordinate_data: Record<string, string | number>[]; units: string; null_handling: string;
  computation_metadata: Record<string, unknown>; warnings: string[];
}
