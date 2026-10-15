/**
 * Frontend types for AI Analysis & Chat with persistent sessions and reports.
 * Matches backend POST /api/v1/chat and /api/v1/analysis/sessions contracts.
 */

export interface ChatRequest {
  message: string;
  dataset_id?: string | null;
  dataset_version?: number | null;
  workspace_id?: string | null;
  session_id?: string | null;
}

export interface ChartPoint {
  label: string;
  value: number;
}

export interface ChartSpec {
  chart_type: string;
  x_field: string;
  y_field: string;
  points: ChartPoint[];
  chart_label?: string;
}

export interface KpiMetrics {
  total?: number;
  mean?: number;
  median?: number;
  min?: number;
  max?: number;
  count?: number;
  [key: string]: unknown;
}

export interface RagCitation {
  title?: string;
  doc_id?: string;
  chunk_id?: string;
  snippet?: string;
  page?: number;
  score?: number;
}

export interface ChatResponse {
  session_id?: string | null;
  run_id?: string | null;
  status?: 'complete' | 'clarification_required';
  plan?: {
    operation: string;
    metric_options?: string[];
    dataset_version?: number | null;
    validation_errors?: string[];
    [key: string]: unknown;
  };
  answer: string;
  intent: string;
  confidence: number;
  execution_time: number;
  data: Array<Record<string, unknown>>;
  explanation?: string | null;
  actionable: string[];
  chart?: ChartSpec | null;
  kpis?: KpiMetrics | null;
  citations?: RagCitation[];
}

export interface AnalysisSessionSummary {
  session_id: string;
  title: string;
  status: string;
  workspace_id?: string | null;
  dataset_id?: string | null;
  dataset_name?: string | null;
  dataset_version?: number | null;
  last_question?: string | null;
  latest_status: string;
  last_run_id?: string | null;
  turn_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AnalysisTurn {
  turn_id: string;
  user_message_id?: string | null;
  assistant_message_id?: string | null;
  question: string;
  asked_at?: string | null;
  answered_at?: string | null;
  answer: string;
  intent: string;
  confidence: number;
  execution_time: number;
  status: string;
  data: Array<Record<string, unknown>>;
  explanation?: string | null;
  actionable: string[];
  chart?: ChartSpec | null;
  kpis?: KpiMetrics | null;
  plan?: Record<string, unknown> | null;
  citations?: RagCitation[];
  run_id?: string | null;
  dataset_id?: string | null;
  dataset_version?: number | null;
}

export interface AnalysisSessionDetail {
  session_id: string;
  title: string;
  status: string;
  workspace_id?: string | null;
  dataset_id?: string | null;
  dataset_name?: string | null;
  dataset_version?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  turns: AnalysisTurn[];
}

export interface AnalysisHistoryReportItem {
  session_id: string;
  run_id?: string | null;
  title: string;
  question: string;
  dataset_id?: string | null;
  dataset_name: string;
  dataset_version?: number | null;
  workspace_id?: string | null;
  status: string;
  completed_at?: string | null;
  turn_count: number;
  summary: string;
  kpis: KpiMetrics;
  data_preview: Array<Record<string, unknown>>;
  has_chart: boolean;
  has_citations: boolean;
  report_eligible: boolean;
}
