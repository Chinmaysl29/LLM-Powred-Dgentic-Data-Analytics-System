import { apiClient } from '../api/client';
import type { Page, TaskSpec } from './learningService';

export interface SelectorControls {
  mode: 'disabled' | 'collection' | 'shadow' | 'active';
  active_model_id: string | null;
  previous_model_id: string | null;
  generation: number;
  effective_selector?: string;
  can_review?: boolean;
  can_write?: boolean;
  numeric_confidence: null;
  routing_calibration: string;
}
export interface Diagnosis {
  observed_failure: string;
  category: string;
  evidence: Record<string, unknown>[];
  proposed_causes: string[];
  distinguishing_checks: string[];
  established: boolean;
}
export interface ProblemContext {
  version: string;
  task: TaskSpec;
  schema_versions: Record<string, string>;
  grain: string;
  entities: string[];
  quality_findings: Record<string, unknown>;
  constraints: string[];
  acceptance_checks: string[];
  interpretation_source: string;
  limitations: string[];
}
export interface Interpretation {
  problem_context: ProblemContext;
  diagnosis: Diagnosis;
  interpretation_status: string;
  requires_confirmation: boolean;
  usage: { logical_calls: number; provider: string | null; cost_usd: number | null };
}
export interface AdaptiveContext {
  run_id: string;
  context: { problem: ProblemContext; diagnosis: Diagnosis } | null;
  skill_snapshot: { skill_id: string; version: number }[];
  selector_mode: string;
  model_id: string | null;
}
export type SkillState =
  'candidate' | 'testing' | 'verified' | 'active' | 'rejected' | 'superseded' | 'revoked';
export interface Skill {
  id: string;
  skill_id: string;
  version: number;
  state: SkillState;
  content_hash: string;
  manifest: {
    implementation: string;
    implementation_hash: string;
    preconditions: string[];
    permitted_tools: string[];
    resource_limits: Record<string, number>;
    stages: number[];
    source: string;
    recipe: string[];
    inputs: string;
    outputs: string;
  };
  test_result: {
    passed: boolean;
    checks: number;
    results: boolean[];
    source: string;
    limitations: string[];
  } | null;
  revisions?: { state: string; evidence: Record<string, unknown>; at: string }[];
}
export interface Decision {
  id: string;
  run_id: string | null;
  case_id: string | null;
  decision: {
    selected_skill: string;
    selected_version: number;
    selector: string;
    model_id: string | null;
    scores: Record<string, number>;
    shadow_scores: Record<string, number>;
    fallback_reason: string | null;
    remaining_repairs: number;
    context_version: string;
    feature_version: string;
    diagnosis: Diagnosis;
    eligible_candidates: { skill_id: string; version: number; implementation_hash: string }[];
  };
  outcome: {
    id: string;
    revision: number;
    label_status: string;
    record: {
      result: string;
      label_policy: string;
      evidence: { invariant: string; outcome: string }[];
      usage: { latency_ms: number };
      source_kind: string;
    };
  } | null;
}
export interface AdaptiveCase {
  id: string;
  split: 'train' | 'development' | 'calibration' | 'final';
  source_kind: 'synthetic' | 'domain_reviewed' | 'verified_run';
  scenario_group: string;
  task: TaskSpec;
  available: boolean;
}
export interface CaseInput {
  task: TaskSpec;
  scenario_group: string;
  split: AdaptiveCase['split'];
  source_kind: AdaptiveCase['source_kind'];
  reference: string;
  source_run_id?: string | null;
  expected_status: 'verified' | 'insufficient_evidence';
  expected_rows: Record<string, string | number | null>[];
}
export interface PolicyMetrics {
  cases: number;
  first_attempt_correct: number;
  final_correct: number;
  verified_repair_success: number;
  attempted_repairs: number;
  verified_repair_rate: number;
  failed_repair_attempts: number;
  repeated_errors: number;
  harmful_repairs: number;
  abstained: number;
  unknown: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  provider_cost_usd: number;
}
export interface PolicyComparison {
  sample_size: number;
  scenario_groups: number;
  trusted_final_groups: number;
  metrics: Record<'baseline' | 'linear' | 'mlp', PolicyMetrics>;
  limits: string[];
  denominators: Record<string, string>;
}
export interface AdaptiveJob {
  id: string;
  kind: string;
  state: string;
  job_status: string;
  attempt: number;
  max_attempts: number;
  error_code: string | null;
  retry_eligible: boolean;
  result: {
    trained?: boolean;
    reason?: string;
    active_model?: string;
    models?: Record<string, string>;
    release_eligible?: boolean;
    comparison?: PolicyComparison;
    train_examples?: number;
    measurements?: {
      training_seconds: number;
      rss_peak_observed_bytes: number;
      rss_increase_bytes: number;
      cpu_threads: number;
    };
    lifecycle?: string;
    note?: string;
  } | null;
}
export interface SelectorModel {
  id: string;
  kind: 'linear' | 'mlp';
  state: string;
  content_hash: string;
  invalid_reason: string | null;
  feature_version: string;
  embedding_version: string;
  calibration_status: string;
  evaluation: {
    release_eligible: boolean;
    gates: Record<string, boolean>;
    parameter_count: number;
    train_action_log_loss: number;
    development_action_log_loss: number;
    inference_p50_ms: number;
    inference_p95_ms: number;
    hidden_layers?: number[];
    policy_comparison: PolicyComparison;
    paired_correctness_delta: number;
    paired_scenario_bootstrap_95_interval: number[] | null;
  };
}
export interface TrainingInput {
  train_case_ids: string[];
  development_case_ids: string[];
  final_case_ids: string[];
  min_examples: number;
  min_groups: number;
  min_per_class: number;
  max_epochs: number;
  idempotency_key: string;
}
const key = () =>
  typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : [...crypto.getRandomValues(new Uint8Array(16))]
        .map((v) => v.toString(16).padStart(2, '0'))
        .join('');
const route = (w: string, part: string, offset = 0) =>
  `/api/v1/adaptive/${part}?workspace_id=${encodeURIComponent(w)}&offset=${offset}`;

export const adaptiveService = {
  key,
  controls: (w: string) => apiClient.get<SelectorControls>(route(w, 'controls')),
  configure: (
    w: string,
    mode: SelectorControls['mode'],
    generation: number,
    model: string | null = null,
  ) =>
    apiClient.put<SelectorControls>(route(w, 'controls'), {
      mode,
      expected_generation: generation,
      model_id: model,
    }),
  rollback: (w: string, generation: number) =>
    apiClient.post<SelectorControls>(route(w, 'rollback'), {
      mode: 'collection',
      expected_generation: generation,
    }),
  interpret: (w: string, task: TaskSpec, provider: boolean) =>
    apiClient.post<Interpretation>(
      route(w, 'interpret'),
      { task, use_provider: provider },
      { timeout: 30000 },
    ),
  context: (run: string) =>
    apiClient.get<AdaptiveContext>(`/api/v1/adaptive/runs/${encodeURIComponent(run)}/context`),
  bootstrap: (w: string) => apiClient.post<Page<Skill>>(route(w, 'skills/bootstrap')),
  skills: (w: string, offset = 0) => apiClient.get<Page<Skill>>(route(w, 'skills', offset)),
  skill: (w: string, id: string) =>
    apiClient.get<Skill>(route(w, `skills/${encodeURIComponent(id)}`)),
  reviewSkill: (
    w: string,
    skill: Skill,
    action: 'test' | 'activate' | 'reject' | 'revoke' | 'supersede',
    reason: string,
  ) =>
    apiClient.post<Skill>(route(w, `skills/${encodeURIComponent(skill.id)}/review`), {
      action,
      expected_state: skill.state,
      reason,
    }),
  scan: (w: string) => apiClient.post(route(w, 'skills/detect-gaps/scan')),
  decisions: (w: string, offset = 0) =>
    apiClient.get<Page<Decision>>(route(w, 'decisions', offset)),
  reviewOutcome: (
    w: string,
    id: string,
    revision: number,
    label: 'unknown' | 'disputed',
    reason: string,
  ) =>
    apiClient.post(route(w, `outcomes/${encodeURIComponent(id)}/review`), {
      expected_revision: revision,
      label_status: label,
      reason,
    }),
  cases: (w: string, offset = 0) => apiClient.get<Page<AdaptiveCase>>(route(w, 'cases', offset)),
  registerCase: (w: string, input: CaseInput) => apiClient.post(route(w, 'cases'), input),
  replay: (w: string, ids: string[]) =>
    apiClient.post<AdaptiveJob>(route(w, 'replays'), { case_ids: ids, idempotency_key: key() }),
  train: (w: string, input: TrainingInput) =>
    apiClient.post<AdaptiveJob>(route(w, 'training'), input),
  jobs: (w: string, offset = 0) => apiClient.get<Page<AdaptiveJob>>(route(w, 'jobs', offset)),
  retry: (w: string, id: string) =>
    apiClient.post<AdaptiveJob>(route(w, `jobs/${encodeURIComponent(id)}/retry`)),
  models: (w: string, offset = 0) => apiClient.get<Page<SelectorModel>>(route(w, 'models', offset)),
  download: (w: string, id: string) =>
    apiClient.getBlob(route(w, `models/${encodeURIComponent(id)}/download`)),
};
