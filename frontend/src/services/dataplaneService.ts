import { apiClient } from '../api/client';

export function requestKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return [
    hex.slice(0, 8),
    hex.slice(8, 12),
    hex.slice(12, 16),
    hex.slice(16, 20),
    hex.slice(20),
  ].join('-');
}

export interface PlaneRecord {
  id: string;
  kind: string;
  dataset_id: string | null;
  parent_id: string | null;
  created_at: string;
  payload: {
    schema?: Record<string, string>;
    row_count?: number;
    snapshot_hash?: string;
    result_rows?: number;
    elapsed_ms?: number;
    rows?: Record<string, string | number | null>[];
    definition?: { name: string; column: string | null; aggregation: string; description: string };
    sample?: { before: number; after: number; removed: number };
    preview_rows?: {
      before: Record<string, unknown>[];
      after: Record<string, unknown>[];
      coverage: string;
    };
    plan?: { operation?: string; reason?: string };
    volume?: { status: string; message?: string };
    duplicate_rows?: number;
    snapshot_age_seconds?: number;
    distribution_warnings?: { column: string; mean_shift_stddevs: number }[];
    columns?: { column: string; nulls: number; missing_fraction: number }[];
    reconciliation?: { before: number; after: number; quarantined: number };
    engine?: string;
    query_hash?: string;
    name?: string;
    status?: string;
  };
}
export interface PlaneJob {
  id: string;
  kind: string;
  status: string;
  attempt: number;
  error_code?: string;
  result?: { artifact_id: string };
}
export interface PlaneDashboard {
  records: PlaneRecord[];
  jobs: PlaneJob[];
  next_offset: number | null;
  limits: { memory_mb: number; timeout_s: number };
}
const base = '/api/v1/dataplane';
const scope = (workspace: string) => ({ workspace_id: workspace });
export const dataplaneService = {
  status: (signal: AbortSignal) =>
    apiClient.get<{ enabled: boolean; upload_mb: number }>(base + '/status', { signal }),
  workspaces: (signal: AbortSignal) =>
    apiClient.get<{ id: string; workspace_name: string }[]>('/api/v1/workspaces/mine', { signal }),
  dashboard: (workspace: string, offset: number, signal: AbortSignal) =>
    apiClient.get<PlaneDashboard>(base + '/dashboard', {
      params: { ...scope(workspace), offset: String(offset) },
      signal,
    }),
  upload: (workspace: string, file: File) => {
    const body = new FormData();
    body.append('workspace_id', workspace);
    body.append('idempotency_key', requestKey());
    body.append('file', file);
    return apiClient.post<PlaneJob>(base + '/upload', body);
  },
  post: (workspace: string, path: string, body: unknown = {}) =>
    apiClient.post<{ id?: string; status?: string }>(base + '/' + path, body, {
      params: scope(workspace),
    }),
  report: (workspace: string, id: string) =>
    apiClient.getBlob(base + '/evidence/' + id + '/report', { params: scope(workspace) }),
};
