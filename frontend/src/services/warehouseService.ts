import { apiClient } from '../api/client';
export interface WarehouseColumn { name: string; data_type: string; nullable: boolean; primary_key: boolean }
export interface WarehouseRelationship { source_table: string; source_columns: string[]; target_table: string; target_columns: string[] }
export interface WarehouseTable { table_name: string; schema_name: string | null; columns: WarehouseColumn[]; row_count_estimate: number | null; foreign_keys: WarehouseRelationship[] }
export interface WarehouseSchema { tables: WarehouseTable[]; relationships: WarehouseRelationship[]; metadata: { dialect: string; database_name: string | null; schema_name: string | null; table_count: number; is_cached: boolean } }
export const warehouseService = {
  async schema(signal?: AbortSignal): Promise<WarehouseSchema> {
    const response = await apiClient.get<{ schema_data: WarehouseSchema }>('/api/v1/schema', { signal });
    if (!Array.isArray(response.schema_data?.tables)) throw new Error('The schema service returned an invalid catalog.');
    return response.schema_data;
  },
};
