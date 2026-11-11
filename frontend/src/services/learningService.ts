import { apiClient } from '../api/client';

export interface Page<T> {
  items: T[];
  next_offset: number | null;
}
export interface Workspace {
  id: string;
  workspace_name: string;
}
export interface Metric {
  column: string;
  aggregation: 'sum' | 'mean' | 'min' | 'max' | 'count';
  missing: 'reject' | 'exclude';
  definition_ref: string | null;
}
export interface Filter {
  column: string;
  operator: 'eq' | 'ne' | 'in' | 'not_in';
  value: string | number | Array<string | number>;
}
export interface TaskSpec {
  workspace_id: string;
  objective: string;
  task_type: 'descriptive';
  datasets: { dataset_id: string; version: number }[];
  metrics: Metric[];
  dimensions: string[];
  grain: string;
  filters: Filter[];
  date_range: { column: string; format: string; start: string; end: string } | null;
  timezone: string;
  units: string;
  currency: string | null;
  output: 'table' | 'chart' | 'report';
  definition_refs: string[];
  assumptions: string[];
  ambiguity: string[];
  success_criteria: string[];
  relationships?: {
    left_dataset_id: string;
    right_dataset_id: string;
    left_key: string;
    right_key: string;
    order_amount: string;
    refund_amount: string;
    purpose: 'order_net_revenue' | 'refund_event_count';
    cardinality: 'one_to_many';
    missing_refund_policy: 'no_event_means_no_refund';
  }[];
}
export interface Check {
  validator: string;
  version: string;
  invariant: string;
  severity: string;
  outcome: 'pass' | 'fail' | 'unknown';
  limitations: string[];
  evidence_refs: string[];
}
export interface Answer {
  rows: Record<string, string | number | null>[];
  claims: { text: string; value: string | number | null; evidence_ref: string }[];
  chart: { label: string; value: string | number | null; evidence_ref: string }[];
}
export interface Outcome {
  status: 'verified' | 'insufficient_evidence';
  error_code: string | null;
  validations: Check[];
  answer: Answer | null;
  result_hash: string | null;
  applied_lessons: string[];
  profile: {
    row_count: number;
    duplicate_looking_rows: number;
    columns: Record<string, { dtype: string; missing: number; unique: number }>;
  };
  limitations: string[];
}
export interface RunSummary {
  id: string;
  state: string;
  mode: string;
  task: TaskSpec | null;
  error_code: string | null;
}
export interface RunStatus {
  run_id: string;
  state: string;
  mode: string;
  bundle_id: string | null;
  task: TaskSpec | null;
  outcome: Outcome | null;
  repairs: number;
  budget: { max_repairs: number; deadline_seconds: number };
  error_code: string | null;
  memory_cutoff: string;
  attempts: {
    attempt_id: string;
    stage_id: string;
    status: string;
    validations: Check[];
    error_category: string | null;
  }[];
}
export interface Lesson {
  id: string;
  state: string;
  revision: number;
  content_hash: string;
  expires_at: string;
  invalid_reason: string | null;
  content: {
    type: string;
    conditions: string[];
    correction: { type: 'exact_decimal_parse'; column: string };
    exceptions: string[];
    provenance: string[];
    scope: { schema_hash: string; definition_refs: string[]; workspace_id: string };
    invalidation_rules: string[];
  };
  verification_records?: {
    id: string;
    passed: boolean;
    evidence: {
      positive_cases: number;
      counterexamples: number;
      limitations: string[];
      scope: string;
    };
  }[];
  revisions?: { number: number; state: string; reason: string }[];
}
export interface Controls {
  mode: 'disabled' | 'collection' | 'shadow' | 'limited';
  active_bundle_id: string | null;
  previous_bundle_id: string | null;
  generation: number;
  rollout_percent: number;
  engine_version: string;
  can_review?: boolean;
}
export interface Definition {
  id: string;
  reference: string;
  active: boolean;
  content: {
    key: string;
    version: number;
    owner: string;
    source: string;
    metric: Metric;
    filters: Filter[];
    units: string;
    currency: string | null;
  };
}
export interface Bundle {
  id: string;
  content_hash: string;
  content: { memory_cutoff: string; lessons: { id: string }[] };
}
export interface EvaluationCase {
  id: string;
  split: string;
  scenario_group: string;
  label_source: string;
  dataset_version: { dataset_id: string; version: number };
}
export interface EvaluationMetrics {
  correct: number;
  total: number;
  correctness: number;
  repeated_error_rate: number;
  completed: number;
  abstained: number;
  unknown: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  cost_usd: number;
}
export interface Evaluation {
  id: string;
  state: string;
  job_status: string;
  error_code: string | null;
  result: null | {
    sample_size: number;
    independent_scenario_groups: number;
    correctness_delta: number;
    metrics: { baseline: EvaluationMetrics; candidate: EvaluationMetrics };
    applications: number;
    useful_applications: number;
    harmful_applications: number;
    gates: Record<string, boolean>;
    release_eligible: boolean;
    limitations: string[];
    paired_bootstrap_95_interval: number[] | null;
  };
}
export interface Monitor {
  items: { id: string; action: string; at: string }[];
  failed_jobs: { id: string; kind: string; error_code: string }[];
}
export type FeedbackCategory =
  'interpretation' | 'calculation' | 'business_definition' | 'presentation_preference' | 'other';
export interface DefinitionInput {
  key: string;
  version: number;
  owner: string;
  source: string;
  metric: Metric;
  filters: Filter[];
  units: string;
  currency: string | null;
  examples: { description: string }[];
}
export interface CaseInput {
  task: TaskSpec;
  scenario_group: string;
  split: 'development' | 'calibration' | 'final';
  dataset_version: { dataset_id: string; version: number };
  label_source: 'synthetic' | 'domain_reviewed';
  reference: string;
  expected_status: 'verified' | 'insufficient_evidence';
  expected_rows: Record<string, string | number | null>[];
}
const scoped = (w: string, path: string, offset = 0) =>
  `/api/v1/learning/${path}?workspace_id=${encodeURIComponent(w)}&offset=${offset}`;
// getRandomValues is available on local HTTP origins where randomUUID is not.
const requestKey = () =>
  typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : [...crypto.getRandomValues(new Uint8Array(16))]
        .map((v) => v.toString(16).padStart(2, '0'))
        .join('');

export const learningService = {
  workspaces: () => apiClient.get<Workspace[]>('/api/v1/workspaces/mine'),
  controls: (w: string) => apiClient.get<Controls>(scoped(w, 'controls')),
  setMode: (w: string, mode: 'disabled' | 'collection' | 'shadow', generation: number) =>
    apiClient.put<Controls>(scoped(w, 'controls'), { mode, expected_generation: generation }),
  runs: (w: string, offset = 0) => apiClient.get<Page<RunSummary>>(scoped(w, 'runs', offset)),
  run: (id: string, signal?: AbortSignal) =>
    apiClient.get<RunStatus>(`/api/v1/learning/runs/${encodeURIComponent(id)}`, { signal }),
  start: (task: TaskSpec) =>
    apiClient.post<{ id: string }>('/api/v1/orchestrator/runs', {
      workspace_id: task.workspace_id,
      dataset_id: task.datasets[0].dataset_id,
      version_number: task.datasets[0].version,
      query: task.objective,
      task_spec: task,
      idempotency_key: requestKey(),
    }),
  cancel: (id: string) =>
    apiClient.post(`/api/v1/orchestrator/runs/${encodeURIComponent(id)}/cancel`),
  feedback: (id: string, category: FeedbackCategory, comment: string, correctionColumn: string) =>
    apiClient.post(`/api/v1/learning/runs/${encodeURIComponent(id)}/feedback`, {
      idempotency_key: requestKey(),
      category,
      sentiment: 'neutral',
      comment,
      correction: correctionColumn
        ? { type: 'exact_decimal_parse', column: correctionColumn }
        : null,
    }),
  lessons: (w: string, offset = 0) => apiClient.get<Page<Lesson>>(scoped(w, 'lessons', offset)),
  lesson: (w: string, id: string) =>
    apiClient.get<Lesson>(scoped(w, `lessons/${encodeURIComponent(id)}`)),
  review: (w: string, lesson: Lesson, action: string, reason: string) =>
    apiClient.post<Lesson>(scoped(w, `lessons/${encodeURIComponent(lesson.id)}/review`), {
      expected_state: lesson.state,
      action,
      reason,
    }),
  definitions: (w: string) => apiClient.get<Definition[]>(scoped(w, 'definitions')),
  createDefinition: (w: string, body: DefinitionInput) =>
    apiClient.post(scoped(w, 'definitions'), body),
  invalidateDefinition: (w: string, id: string) =>
    apiClient.post(scoped(w, `definitions/${encodeURIComponent(id)}/invalidate`)),
  freeze: (w: string) => apiClient.post<Bundle>(scoped(w, 'bundles')),
  bundles: (w: string, offset = 0) => apiClient.get<Page<Bundle>>(scoped(w, 'bundles', offset)),
  cases: (w: string, offset = 0) => apiClient.get<Page<EvaluationCase>>(scoped(w, 'cases', offset)),
  addCase: (w: string, body: CaseInput) => apiClient.post(scoped(w, 'cases'), body),
  evaluate: (w: string, bundle: Bundle, cases: EvaluationCase[], minCases: number) =>
    apiClient.post<Evaluation>(scoped(w, 'evaluations'), {
      idempotency_key: requestKey(),
      manifest: {
        case_ids: cases.map((c) => c.id),
        split_version: 'workspace-final-v1',
        dataset_versions: cases.map((c) => c.dataset_version),
        baseline_bundle: 'validated-baseline-v1',
        candidate_bundle: bundle.id,
        memory_cutoff: bundle.content.memory_cutoff,
        model_configuration: 'deterministic-supervisor-v1',
        graders: 'exact-decimal-reference-v1',
        metrics: 'paired-correctness-cost-latency-v1',
        budget: {},
        gates: {
          min_cases: minCases,
          max_correctness_regression: 0,
          max_p95_ratio: 1.5,
          max_cost_delta_usd: 0,
          require_measured_benefit: true,
        },
      },
    }),
  evaluations: (w: string, offset = 0) =>
    apiClient.get<Page<Evaluation>>(scoped(w, 'evaluations', offset)),
  evaluation: (w: string, id: string) =>
    apiClient.get<Evaluation>(scoped(w, `evaluations/${encodeURIComponent(id)}`)),
  release: (w: string, id: string, generation: number) =>
    apiClient.post<Controls>(scoped(w, 'release'), {
      evaluation_id: id,
      expected_generation: generation,
      rollout_percent: 10,
    }),
  rollback: (w: string, generation: number) =>
    apiClient.post<Controls>(scoped(w, 'rollback'), { expected_generation: generation }),
  monitor: (w: string) => apiClient.get<Monitor>(scoped(w, 'monitor')),
  report: (id: string) =>
    apiClient.getBlob(`/api/v1/learning/runs/${encodeURIComponent(id)}/report`),
};
