import { apiClient, ApiError } from '../api/client';
export interface WarehouseIndex {
  name: string | null;
  columns: string[];
  unique: boolean;
  keys?: {
    position: number;
    kind: 'column' | 'expression' | 'unknown';
    column_name: string | null;
    expression: string | null;
    sorting: string[];
  }[];
  include_columns?: string[];
  predicate?: string | null;
  dialect_options?: Record<string, unknown>;
  warnings?: string[];
}

export function warehouseErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Please sign in again to view the database schema.';
    if (error.status === 403) return 'You do not have permission to inspect this database schema.';
    if (error.status === 503) return 'The database is temporarily unavailable. Please retry.';
    if (error.status === 504 || error.code === 'TIMEOUT')
      return 'Loading the database schema timed out. Please retry.';
    if (error.status === 0)
      return 'The schema service could not be reached. Check your connection and retry.';
  }
  return 'The database schema could not be loaded. Please retry or contact support.';
}
export interface WarehouseColumn {
  name: string;
  data_type: string;
  nullable: boolean;
  primary_key: boolean;
}
export interface WarehouseRelationship {
  source_table: string;
  source_columns: string[];
  target_table: string;
  target_columns: string[];
}
export interface WarehouseTable {
  table_name: string;
  schema_name: string | null;
  columns: WarehouseColumn[];
  row_count_estimate: number | null;
  foreign_keys: WarehouseRelationship[];
  indexes?: WarehouseIndex[];
  unique_constraints?: { name: string | null; columns: string[] }[];
  warnings?: string[];
}
export interface WarehouseSchema {
  tables: WarehouseTable[];
  relationships: WarehouseRelationship[];
  metadata: {
    dialect: string;
    database_name: string | null;
    schema_name: string | null;
    table_count: number;
    is_cached: boolean;
  };
}
export const warehouseService = {
  async schema(signal?: AbortSignal, refresh = false): Promise<WarehouseSchema> {
    const response = await apiClient.get<{ schema_data: WarehouseSchema }>('/api/v1/schema', {
      signal,
      params: refresh ? { refresh: 'true' } : undefined,
    });
    if (!Array.isArray(response.schema_data?.tables))
      throw new Error('The schema service returned an invalid catalog.');
    return response.schema_data;
  },
};
