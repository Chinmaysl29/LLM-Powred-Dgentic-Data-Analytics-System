import { apiClient } from '../api/client';

export interface DictionaryEntry {
  id: string;
  key: string;
  version: number;
  status: string;
  revision: number;
  spec: {
    dataset_id: string;
    description: string;
    domain: string;
    aliases: string[];
    grain: string;
    timezone: string;
    date_basis: string;
    effective_from: string;
    effective_to: string | null;
    definition: {
      owner: string;
      metric: { column: string; aggregation: string; missing: string };
      units: string;
      currency: string | null;
    };
  } | null;
  content: { metric: { column: string; aggregation: string }; units: string };
}
export interface ReviewState {
  status: string;
  revision: number;
}
export interface Incident {
  id: string;
  definition_id: string;
  snapshot_id: string;
  coverage: string;
  checks: { field: string; status: string; observed: unknown; expected: unknown; impact: string }[];
  review: ReviewState;
  affected_outputs: { id: string; kind: string; impact: string; reason: string; path: string[] }[];
  impact_limit: string;
}
export interface Workflow {
  id: string;
  version: number;
  spec: {
    name: string;
    purpose: string;
    require_artifact_review: boolean;
    query: {
      definition_id: string;
      snapshot_id: string;
      business_date: string;
      plan: {
        metric: string;
        dimensions?: string[];
        filters?: { column: string; operator: string; value: unknown }[];
      };
      time_window?: unknown;
    };
    resources?: Record<string, number>;
    source_selection?: string;
    relative_window?: unknown;
  };
  review: ReviewState;
  recent_runs?: {
    id: string;
    status: string;
    attempt: number;
    error_code: string | null;
    schedule_slot: string | null;
    schedule_policy: string | null;
  }[];
  schedule: ReviewState & { enabled?: boolean; timezone?: string; hour?: number; minute?: number };
}
export interface Policy {
  revision: number;
  allow_self_approval: boolean | null;
  role?: string;
}
export interface Comparison {
  id: string;
  comparable: boolean;
  absolute_change_unit: string;
  mismatches: string[];
  percentage_denominator: string;
  contribution_note: string;
  causality: string;
  rows: {
    dimensions: Record<string, unknown>;
    previous: unknown;
    current: unknown;
    entity: string;
    absolute_change: string | null;
    percentage_change: string | null;
  }[];
}
const base = '/api/v1/dataplane/company';
export const companyService = {
  get: <T>(workspace: string, path: string, signal?: AbortSignal) =>
    apiClient.get<T>(base + '/' + path, { params: { workspace_id: workspace }, signal }),
  post: <T>(workspace: string, path: string, body: unknown = {}) =>
    apiClient.post<T>(base + '/' + path, body, { params: { workspace_id: workspace } }),
  put: <T>(workspace: string, path: string, body: unknown) =>
    apiClient.put<T>(base + '/' + path, body, { params: { workspace_id: workspace } }),
  download: (workspace: string, id: string) =>
    apiClient.getBlob(base + '/comparisons/' + id + '/download', {
      params: { workspace_id: workspace },
    }),
};
