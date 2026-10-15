import { apiClient } from '../api/client';

export interface DatabaseConnection {
  id: string;
  connector_name: string;
  connector_type: string;
  connector_subtype: string;
  status: string;
  config: {
    host: string;
    port: number;
    database: string;
    username: string;
    schema_name?: string;
    workspace_id?: string;
  };
  created_at: string;
}

export interface ConnectionTestPayload {
  connector_type: 'postgresql' | 'mysql';
  host: string;
  port: number;
  database: string;
  username: string;
  password?: string;
  schema_name?: string;
}

export interface ConnectionTestResult {
  success: boolean;
  status: string;
  connector_type: string;
  latency_ms: number;
  tables: string[];
  total_tables: number;
  message: string;
}

export interface SaveConnectionPayload extends ConnectionTestPayload {
  workspace_id: string;
  connector_name: string;
}

export const connectionService = {
  testConnection(payload: ConnectionTestPayload, signal?: AbortSignal): Promise<ConnectionTestResult> {
    return apiClient.post<ConnectionTestResult>('/api/v1/connections/test', payload, { signal });
  },
  saveConnection(payload: SaveConnectionPayload, signal?: AbortSignal): Promise<DatabaseConnection> {
    return apiClient.post<DatabaseConnection>('/api/v1/connections', payload, { signal });
  },
  listConnections(workspaceId: string, signal?: AbortSignal): Promise<DatabaseConnection[]> {
    return apiClient.get<DatabaseConnection[]>('/api/v1/connections', {
      signal,
      params: { workspace_id: workspaceId },
    });
  },
  deleteConnection(connectionId: string, workspaceId: string, signal?: AbortSignal): Promise<{ success: boolean; message: string }> {
    return apiClient.delete<{ success: boolean; message: string }>(`/api/v1/connections/${encodeURIComponent(connectionId)}`, {
      signal,
      params: { workspace_id: workspaceId },
    });
  },
};
