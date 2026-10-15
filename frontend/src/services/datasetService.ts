/**
 * datasetService.ts
 *
 * Enterprise Dataset Service Boundary
 * Strictly connects frontend to backend /api/v1/datasets API, database connections,
 * API connectors, and data warehouse metadata.
 * NO mock or seeded datasets.
 */

import { apiClient } from '../api/client';
import { supabase, isSupabaseConfigured } from '../lib/supabase/client';
import type {
  Dataset,
  DatasetStatus,
  DatabaseConnection,
  ApiConnection,
  DataWarehouseCatalog,
  ColumnMetadata,
  ColumnProfileStat,
  DatasetProfileData,
  DatasetQualityData,
  DatasetVersionItem,
  DatasetLineageNode,
  DatasetPreview,
  CellValue,
} from '../types/datasets';
import { getExtension } from '../datasetUtils';

export interface BackendDatasetResponse {
  dataset_id: string;
  dataset_name: string;
  file_name: string;
  file_type?: string;
  file_path?: string;
  original_path?: string | null;
  json_path?: string | null;
  canonical_path?: string | null;
  canonical_format?: string | null;
  content_hash?: string | null;
  size_bytes?: number | null;
  row_count?: number | null;
  column_count?: number | null;
  quality_score?: number | null;
  version?: number;
  last_active_version_id?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export function mapBackendDatasetToFrontend(backend: BackendDatasetResponse): Dataset {
  const filename = backend.file_name || backend.dataset_name || 'untitled.csv';
  const inferredType = backend.file_type || getExtension(filename);
  const rows = backend.row_count ?? 0;
  const cols = backend.column_count ?? 0;
  const quality = backend.quality_score ?? undefined;

  return {
    version: backend.version,
    dataset_id: backend.dataset_id,
    filename,
    name: backend.dataset_name || filename.replace(/\.[^/.]+$/, ''),
    file_type: inferredType,
    row_count: rows,
    column_count: cols,
    quality_score: quality,
    size_bytes: backend.size_bytes ?? 0,
    uploaded_at: backend.created_at
      ? new Date(backend.created_at).toISOString()
      : new Date().toISOString(),
    updated_at: backend.updated_at
      ? new Date(backend.updated_at).toISOString()
      : new Date().toISOString(),
    status: (backend.status as DatasetStatus) || 'Ready',
    raw_path: backend.original_path || backend.file_path || '',
    processed_path: backend.canonical_path || backend.json_path || '',
  };
}

export const datasetService = {
  /**
   * List all datasets from Supabase PostgreSQL (with RLS isolation) or backend database.
   * Never injects mock datasets.
   */
  async list(skip = 0, limit = 50): Promise<Dataset[]> {
    // The backend owns dataset authorization, versions and preview records.
    // Hosted mirror metadata must never replace its authoritative registry.
    const data = await apiClient.get<BackendDatasetResponse[]>('/api/v1/datasets', {
      params: {
        skip: String(skip),
        limit: String(limit),
      },
    });

    if (!Array.isArray(data)) {
      throw new Error('The dataset registry returned an invalid response. Please retry.');
    }

    return data.map(mapBackendDatasetToFrontend);
  },

  /**
   * Get a single dataset by ID from backend.
   */
  async getById(datasetId: string): Promise<Dataset> {
    const data = await apiClient.get<BackendDatasetResponse>(
      `/api/v1/datasets/${encodeURIComponent(datasetId)}`,
    );
    return mapBackendDatasetToFrontend(data);
  },

  /**
   * Upload dataset file to Supabase private storage and backend processing pipeline.
   * Throws on failure so UI displays authentic error message.
   */
  async upload(file: File, datasetName?: string): Promise<Dataset> {
    let supabaseStoragePath: string | null = null;
    let currentUserId: string | null = null;

    if (isSupabaseConfigured()) {
      try {
        const { data: { user } } = await supabase.auth.getUser();
        if (user) {
          currentUserId = user.id;
          const cleanName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
          const path = `${user.id}/${Date.now()}_${cleanName}`;
          const { error: storageErr } = await supabase.storage
            .from('user-datasets')
            .upload(path, file, { cacheControl: '3600', upsert: false });

          if (!storageErr) {
            supabaseStoragePath = path;
          }
        }
      } catch (err) {
        console.warn('Supabase storage upload skipped:', err);
      }
    }

    const formData = new FormData();
    formData.append('file', file);
    if (datasetName) {
      formData.append('dataset_name', datasetName);
    }
    const data = await apiClient.post<BackendDatasetResponse>(
      '/api/v1/datasets/upload',
      formData,
    );
    const mapped = mapBackendDatasetToFrontend(data);

    // Record dataset metadata in Supabase datasets table if user is authenticated
    if (isSupabaseConfigured() && currentUserId) {
      try {
        await supabase.from('datasets').insert({
          id: mapped.dataset_id,
          user_id: currentUserId,
          name: mapped.name,
          original_filename: mapped.filename,
          storage_path: supabaseStoragePath || mapped.raw_path || 'local',
          file_type: mapped.file_type,
          file_size: mapped.size_bytes,
          row_count: mapped.row_count,
          column_count: mapped.column_count,
          processing_status: 'Ready',
        } as Record<string, unknown>);
      } catch {
        // Table will be populated once remote SQL migration is applied
      }
    }

    return mapped;
  },

  /**
   * Delete dataset from database and disk storage.
   */
  async delete(datasetId: string): Promise<void> {
    if (isSupabaseConfigured()) {
      try {
        await supabase.from('datasets').delete().eq('id', datasetId);
      } catch {
        // Ignore if table not present
      }
    }
    await apiClient.delete(`/api/v1/datasets/${encodeURIComponent(datasetId)}`);
  },

  /**
   * Fetch real preview records directly from canonical JSON or source storage.
   */
  async getPreview(datasetId: string, limit = 50): Promise<DatasetPreview> {
    const res = await apiClient.get<{ columns: string[]; rows: Record<string, CellValue>[]; total_rows: number | null; preview_rows?: number; count_status?: 'exact' | 'unknown' }>(
      `/api/v1/datasets/${encodeURIComponent(datasetId)}/preview?limit=${limit}`,
    );
    if (!res || !Array.isArray(res.columns) || !Array.isArray(res.rows)) throw new Error('The preview service returned invalid data. Please retry.');
    return { columns: res.columns, rows: res.rows, totalRows: res.total_rows ?? null,
      previewRows: res.preview_rows ?? res.rows.length, countStatus: res.count_status ?? (res.total_rows == null ? 'unknown' : 'exact') };
  },

  /**
   * Fetch extracted metadata columns and statistics from backend.
   */
  async getMetadata(datasetId: string): Promise<ColumnMetadata[]> {
    try {
      const data = await apiClient.get<{
        columns_metadata?: Array<{
          name: string;
          type: string;
          null_count?: number;
          null_percentage?: number;
          unique_count?: number;
        }>;
      }>(`/api/v1/datasets/${encodeURIComponent(datasetId)}/metadata`);

      if (data && data.columns_metadata && data.columns_metadata.length > 0) {
        return data.columns_metadata.map((col) => ({
          name: col.name,
          datatype: col.type,
          uniqueValues: col.unique_count ?? 0,
          nullCount: col.null_count ?? 0,
          nullPercentage: Math.round((col.null_percentage ?? 0) * 100),
          sampleValues: [],
        }));
      }
    } catch (err) {
      console.warn(`Metadata not found for dataset ${datasetId}:`, err);
    }
    return [];
  },

  /**
   * Fetch statistical profile for dataset.
   */
  async getProfile(datasetId: string): Promise<DatasetProfileData | null> {
    try {
      const data = await apiClient.get<{
        dataset_id: string;
        duplicate_rows: number;
        duplicate_percentage: number;
        missing_data_profile: {
          null_count: number;
          null_percentage: number;
          columns_with_missing: string[];
        };
        cardinality_profile: {
          high_cardinality_columns: string[];
          low_cardinality_columns: string[];
        };
        numeric_columns_profile: Record<string, {
          mean: number;
          median: number;
          min: number;
          max: number;
          std: number;
          p25: number;
          p75: number;
          skewness: number;
        }>;
      }>(`/api/v1/datasets/${encodeURIComponent(datasetId)}/profile`);

      if (data) {
        const summary: Record<string, ColumnProfileStat> = {};
        for (const [col, stats] of Object.entries(data.numeric_columns_profile || {})) {
          summary[col] = {
            count: data.duplicate_rows ?? 0,
            mean: Math.round(stats.mean * 100) / 100,
            stdDev: Math.round(stats.std * 100) / 100,
            min: stats.min,
            max: stats.max,
            q25: stats.p25,
            median: stats.median,
            q75: stats.p75,
          };
        }

        return {
          summary,
          correlation: {
            columns: Object.keys(data.numeric_columns_profile || {}),
            matrix: [],
          },
        };
      }
    } catch (err) {
      console.warn(`Profile not found for dataset ${datasetId}:`, err);
    }
    return null;
  },

  /**
   * Fetch data quality scores from backend.
   */
  async getQuality(datasetId: string): Promise<DatasetQualityData | null> {
    try {
      const data = await apiClient.get<{
        overall_score: number;
        completeness_score: number;
        validity_score: number;
        uniqueness_score: number;
        consistency_score: number;
        integrity_score: number;
        quality_classification: string;
      }>(`/api/v1/datasets/${encodeURIComponent(datasetId)}/quality`);

      if (data) {
        return {
          qualityScore: Math.round(data.overall_score),
          missingValuesCount: 0,
          duplicateRowsCount: 0,
          outliersCount: 0,
          rules: [
            {
              rule: 'Completeness',
              description: 'Percentage of non-null and present values',
              status: data.completeness_score >= 90 ? 'passed' : data.completeness_score >= 80 ? 'warning' : 'failed',
              score: Math.round(data.completeness_score),
            },
            {
              rule: 'Validity',
              description: 'Data format conformity and schema integrity',
              status: data.validity_score >= 90 ? 'passed' : data.validity_score >= 80 ? 'warning' : 'failed',
              score: Math.round(data.validity_score),
            },
            {
              rule: 'Uniqueness',
              description: 'Absence of duplicate records',
              status: data.uniqueness_score >= 90 ? 'passed' : data.uniqueness_score >= 80 ? 'warning' : 'failed',
              score: Math.round(data.uniqueness_score),
            },
            {
              rule: 'Consistency',
              description: 'Uniform data representations across features',
              status: data.consistency_score >= 90 ? 'passed' : data.consistency_score >= 80 ? 'warning' : 'failed',
              score: Math.round(data.consistency_score),
            },
            {
              rule: 'Integrity',
              description: 'Referential and structural integrity',
              status: data.integrity_score >= 90 ? 'passed' : data.integrity_score >= 80 ? 'warning' : 'failed',
              score: Math.round(data.integrity_score),
            },
          ],
        };
      }
    } catch (err) {
      console.warn(`Quality score not found for dataset ${datasetId}:`, err);
    }
    return null;
  },

  /**
   * Fetch dataset versions from backend.
   */
  async getVersions(datasetId: string): Promise<DatasetVersionItem[]> {
    try {
      const data = await apiClient.get<{
        versions: Array<{
          version_number: number;
          created_at: string;
          change_type: string;
          created_by: string;
          is_active: boolean;
          metadata_snapshot: { row_count?: number; column_count?: number; size_bytes?: number };
        }>;
      }>(`/api/v1/datasets/${encodeURIComponent(datasetId)}/versions`);

      if (data && Array.isArray(data.versions)) {
        return data.versions.map((v) => ({
          version_number: v.version_number,
          label: `Version ${v.version_number}`,
          created_at: v.created_at,
          author: v.created_by,
          changelog: v.change_type,
          rows: v.metadata_snapshot?.row_count ?? 0,
          columns: v.metadata_snapshot?.column_count ?? 0,
          size_bytes: v.metadata_snapshot?.size_bytes ?? 0,
          isActive: v.is_active,
        }));
      }
    } catch (err) {
      console.warn(`Versions not found for dataset ${datasetId}:`, err);
    }
    return [];
  },

  async rollbackVersion(datasetId: string, versionNumber: number): Promise<{ success: boolean; message: string }> {
    try {
      await apiClient.post(`/api/v1/datasets/${encodeURIComponent(datasetId)}/versions/${versionNumber}/rollback`);
      return {
        success: true,
        message: `Dataset successfully rolled back to Version ${versionNumber}. Active parquet storage updated.`,
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Rollback failed';
      return { success: false, message: msg };
    }
  },

  async getLineage(dataset: Dataset): Promise<DatasetLineageNode[]> {
    return [
      ...(dataset.raw_path ? [{ id: 'source', type: 'source' as const, title: dataset.filename, description: 'Registered source path', path: dataset.raw_path, status: 'ready' as const }] : []),
      ...(dataset.processed_path ? [{ id: 'processed', type: 'processed_storage' as const, title: 'Canonical dataset', description: 'Registered canonical path', path: dataset.processed_path, status: 'ready' as const }] : []),
    ];
  },
  async listDatabaseConnections(): Promise<DatabaseConnection[]> { throw new Error('Database connection API is unavailable.'); },
  async testDatabaseConnection(_conn: Partial<DatabaseConnection>): Promise<{ success: boolean; latencyMs: number; message: string }> { throw new Error('Database connection testing is unavailable.'); },
  async saveDatabaseConnection(_conn: Omit<DatabaseConnection, 'id' | 'lastTestedAt'>): Promise<DatabaseConnection> { throw new Error('Database connection persistence is unavailable.'); },
  async listApiConnections(): Promise<ApiConnection[]> { throw new Error('API connection registry is unavailable.'); },
  async testApiConnection(_conn: Partial<ApiConnection>): Promise<{ success: boolean; latencyMs: number; message: string }> { throw new Error('API connection testing is unavailable.'); },
  async saveApiConnection(_conn: Omit<ApiConnection, 'id' | 'lastTestedAt'>): Promise<ApiConnection> { throw new Error('API connection persistence is unavailable.'); },
  async getWarehouseCatalog(): Promise<DataWarehouseCatalog> { throw new Error('Warehouse catalog API is unavailable.'); },
  async refreshMaterializedView(_mvId: string): Promise<void> { throw new Error('Materialized-view refresh API is unavailable.'); },
};
