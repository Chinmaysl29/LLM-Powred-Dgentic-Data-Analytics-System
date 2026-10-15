/**
 * Frontend dataset domain types for Enterprise Dataset Management Center.
 */

export type DatasetStatus =
  | 'ready'
  | 'uploaded'
  | 'validating'
  | 'validated'
  | 'processing'
  | 'processed'
  | 'failed'
  | 'Ready'
  | 'Processed';

export type DatasetFileType = 'CSV' | 'Excel' | 'JSON' | 'PDF' | 'Parquet';

export interface Dataset {
  version?: number;
  /** Unique identifier (UUID string from backend). */
  dataset_id: string;
  /** Original filename as uploaded (e.g. "Sales_Data_2025.csv"). */
  filename: string;
  /** Display name */
  name?: string;
  /** Format of dataset file */
  file_type?: DatasetFileType | string;
  /** Number of rows (or undefined if document) */
  row_count?: number;
  /** Number of columns */
  column_count?: number;
  /** Number of pages (for PDF reports) */
  pages?: number;
  /** Overall quality score percentage (0-100) */
  quality_score?: number;
  /** File size in bytes. */
  size_bytes: number;
  /** ISO 8601 UTC timestamp of when the file was uploaded. */
  uploaded_at: string;
  /** ISO 8601 UTC timestamp of last update */
  updated_at?: string;
  /** Current processing status in the data pipeline. */
  status: DatasetStatus;
  /** Raw storage location path */
  raw_path?: string;
  /** Cleaned / Processed Parquet storage path */
  processed_path?: string;
  /** Human-readable description */
  description?: string;
}

export type CellValue = string | number | boolean | null;
export type PreviewRow = Record<string, CellValue>;

export interface DatasetPreview {
  columns: string[];
  rows: PreviewRow[];
  totalRows: number | null;
  previewRows?: number;
  countStatus?: 'exact' | 'unknown';
}

export interface UploadFileEntry {
  key: string;
  file: File;
}

export interface UploadValidationError {
  filename: string;
  reason: string;
}

// ---------------------------------------------------------------------------
// Database Connection Types
// ---------------------------------------------------------------------------

export type DatabaseEngine = 'PostgreSQL' | 'MySQL' | 'MongoDB' | 'SQL Server' | 'Oracle';

export interface DatabaseConnection {
  id: string;
  name: string;
  engine: DatabaseEngine;
  host: string;
  port: number;
  database: string;
  username: string;
  ssl: boolean;
  status: 'connected' | 'error' | 'testing';
  latencyMs?: number;
  tablesCount?: number;
  lastTestedAt: string;
}

// ---------------------------------------------------------------------------
// API Connection Types
// ---------------------------------------------------------------------------

export type ApiType = 'REST API' | 'GraphQL API';
export type ApiAuthType = 'none' | 'bearer' | 'basic' | 'apiKey';

export interface ApiHeader {
  key: string;
  value: string;
}

export interface ApiConnection {
  id: string;
  name: string;
  type: ApiType;
  baseUrl: string;
  endpoint?: string;
  authType: ApiAuthType;
  apiKey?: string;
  apiKeyHeader?: string;
  headers: ApiHeader[];
  status: 'connected' | 'error' | 'testing';
  latencyMs?: number;
  lastTestedAt: string;
}

// ---------------------------------------------------------------------------
// Data Warehouse Types
// ---------------------------------------------------------------------------

export interface WarehouseColumn {
  name: string;
  type: string;
  nullable: boolean;
  isPrimaryKey?: boolean;
  isForeignKey?: boolean;
}

export interface FactTable {
  id: string;
  name: string;
  description: string;
  rowCount: number;
  columnCount: number;
  partitionKey: string;
  sizeBytes: number;
  lastRefreshed: string;
  columns: WarehouseColumn[];
}

export interface DimensionTable {
  id: string;
  name: string;
  description: string;
  rowCount: number;
  columnCount: number;
  primaryKey: string;
  sizeBytes: number;
  lastRefreshed: string;
  columns: WarehouseColumn[];
}

export interface WarehouseView {
  id: string;
  name: string;
  description: string;
  sourceTables: string[];
  lastRefreshed: string;
  query: string;
}

export interface MaterializedView {
  id: string;
  name: string;
  description: string;
  refreshInterval: string;
  lastRefreshed: string;
  rowCount: number;
  sizeBytes: number;
  query: string;
  status: 'ready' | 'refreshing';
}

export interface DataWarehouseCatalog {
  factTables: FactTable[];
  dimensionTables: DimensionTable[];
  views: WarehouseView[];
  materializedViews: MaterializedView[];
}

// ---------------------------------------------------------------------------
// Dataset Deep Detail Types (Metadata, Profile, Quality, Versions, Lineage)
// ---------------------------------------------------------------------------

export interface ColumnMetadata {
  name: string;
  datatype: string;
  uniqueValues: number;
  nullCount: number;
  nullPercentage: number;
  sampleValues: (string | number)[];
  isPrimaryKey?: boolean;
  isTarget?: boolean;
}

export interface ColumnProfileStat {
  count: number;
  mean?: number;
  median?: number;
  stdDev?: number;
  min?: number;
  max?: number;
  q25?: number;
  q75?: number;
  distribution?: { bucket: string; count: number }[];
  boxplot?: { min: number; q1: number; median: number; q3: number; max: number };
}

export interface DatasetProfileData {
  summary: Record<string, ColumnProfileStat>;
  correlation: {
    columns: string[];
    matrix: number[][];
  };
}

export interface QualityRuleResult {
  rule: string;
  description: string;
  status: 'passed' | 'warning' | 'failed';
  score: number;
}

export interface DatasetQualityData {
  qualityScore: number;
  missingValuesCount: number;
  duplicateRowsCount: number;
  outliersCount: number;
  rules: QualityRuleResult[];
}

export interface DatasetVersionItem {
  version_number: number;
  label: string;
  created_at: string;
  author: string;
  changelog: string;
  rows: number;
  columns: number;
  size_bytes: number;
  isActive: boolean;
}

export interface DatasetLineageNode {
  id: string;
  title: string;
  type: 'source' | 'raw_storage' | 'engine' | 'processed_storage' | 'registry' | 'ai_agent';
  description: string;
  path?: string;
  status: 'active' | 'synced' | 'ready';
}
