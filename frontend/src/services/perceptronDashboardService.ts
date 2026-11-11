import { apiClient } from '../api/client';

export type Learner =
  'intent_router' | 'column_metric_resolver' | 'chart_selector' | 'provider_bandit';
export interface DashboardEvaluation {
  learner: Learner;
  version: number;
  created_at: string;
  cases: number;
  correct: number;
  accuracy: number;
  mean_reward: number | null;
  manifest_digest: string;
}
export interface LearningDashboard {
  enabled: boolean;
  workspace_id: string;
  days: number;
  since: string;
  as_of: string;
  top_mistakes: { error_type: string; count: number }[];
  shadow: {
    observations: number;
    abstentions: number;
    compared: number;
    agreements: number;
    agreement_rate: number | null;
  };
  evaluations: DashboardEvaluation[];
  evaluations_truncated: boolean;
  omitted_evaluations: number;
  versions: { learner: Learner; version: number; selected: boolean; created_at: string }[];
  next_offset: number | null;
}
export interface DashboardWorkspace {
  id: string;
  workspace_name: string;
}
export const perceptronDashboardService = {
  workspaces: (signal: AbortSignal) =>
    apiClient.get<DashboardWorkspace[]>('/api/v1/workspaces/mine', { signal }),
  read: (workspace: string, days: number, offset: number, signal: AbortSignal) =>
    apiClient.get<LearningDashboard>('/api/v1/perceptron/dashboard', {
      params: { workspace_id: workspace, days: String(days), offset: String(offset), limit: '25' },
      signal,
    }),
};
