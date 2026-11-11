/**
 * enterpriseOsService.ts
 *
 * Frontend service layer for Phase 20: Enterprise AI Analytics Operating System.
 * Connects to /api/v1/os/* backend endpoints:
 * - 20.1 Workspace Management
 * - 20.2 AI Memory Layer
 * - 20.3 Natural Language Dashboard Builder
 * - 20.4 Executive Report Studio
 * - 20.5 Data Storytelling Engine
 * - 20.6 Dashboard Marketplace
 * - 20.7 Dataset Relationship Engine
 * - 20.8 Semantic Business Layer
 * - 20.9 KPI Knowledge Engine
 * - 20.10 Autonomous AI Analyst Mode
 */

import { apiClient } from '../api/client';

export interface WorkspaceMember {
  user_id: string;
  email: string;
  role: string;
}

export interface WorkspaceResources {
  datasets: Record<string, unknown>[];
  dashboards: Record<string, unknown>[];
  reports: Record<string, unknown>[];
  forecasts: Record<string, unknown>[];
  insights: Record<string, unknown>[];
}

export interface WorkspaceItem {
  id: string;
  name: string;
  slug: string;
  description: string;
  status: string;
  members: WorkspaceMember[];
  resources: WorkspaceResources;
}

export interface MarketplaceTemplate {
  id: string;
  name: string;
  category: string;
  description: string;
  icon: string;
  default_kpis: string[];
}

export interface KpiItem {
  id: string;
  name: string;
  category: string;
  formula: string;
  unit: string;
  benchmark: string;
  description: string;
  value?: number;
  formatted?: string;
  status?: string;
}

export interface StoryRisk {
  risk: string;
  severity: string;
  impact: string;
}

export interface StoryOpportunity {
  opportunity: string;
  potential_gain: string;
  strategy: string;
}

export interface StoryRecommendation {
  priority: number;
  action: string;
  roi: string;
  effort: string;
  timeline: string;
}

export interface AutonomousAnalystResponse {
  query: string;
  executive_answer: string;
  plan: Record<string, unknown>;
  kpis: KpiItem[];
  visualizations: Record<string, unknown>[];
  story: {
    executive_summary: string;
    key_findings: string[];
    risks: StoryRisk[];
    opportunities: StoryOpportunity[];
    recommendations: StoryRecommendation[];
    confidence_score: number;
  };
  forecast?: Record<string, unknown>;
  execution_metadata: {
    rows_analyzed: number;
    columns_analyzed: number;
    execution_time_seconds: number;
    confidence_score: number;
  };
}

export const enterpriseOsService = {
  // 20.1 Workspaces
  async listWorkspaces(): Promise<WorkspaceItem[]> {
    return apiClient.get<WorkspaceItem[]>('/api/v1/os/workspaces');
  },

  async createWorkspace(name: string, description = ''): Promise<WorkspaceItem> {
    return apiClient.post<WorkspaceItem>('/api/v1/os/workspaces', { name, description });
  },

  async getWorkspaceResources(workspaceId: string): Promise<WorkspaceResources> {
    return apiClient.get<WorkspaceResources>(`/api/v1/os/workspaces/${workspaceId}/resources`);
  },

  // 20.3 Dashboards
  async generateDashboard(
    prompt: string,
    workspaceId = 'default-ws',
    title?: string,
  ): Promise<Record<string, unknown>> {
    return apiClient.post<Record<string, unknown>>('/api/v1/os/dashboards/generate', {
      prompt,
      workspace_id: workspaceId,
      title,
    });
  },

  // 20.4 Report Studio
  async generateReport(
    title: string,
    reportType = 'Executive Report',
    workspaceId = 'default-ws',
  ): Promise<Record<string, unknown>> {
    return apiClient.post<Record<string, unknown>>('/api/v1/os/reports/studio/generate', {
      title,
      report_type: reportType,
      workspace_id: workspaceId,
    });
  },

  async getReportHistory(workspaceId?: string): Promise<Record<string, unknown>[]> {
    return apiClient.get<Record<string, unknown>[]>('/api/v1/os/reports/studio/history', {
      params: workspaceId ? { workspace_id: workspaceId } : undefined,
    });
  },

  // 20.5 Storytelling
  async generateStory(
    query: string,
    dataRecords: Record<string, unknown>[] = [],
  ): Promise<Record<string, unknown>> {
    return apiClient.post<Record<string, unknown>>('/api/v1/os/storytelling/generate', {
      query,
      data_records: dataRecords,
    });
  },

  // 20.6 Marketplace
  async listTemplates(): Promise<MarketplaceTemplate[]> {
    return apiClient.get<MarketplaceTemplate[]>('/api/v1/os/marketplace/templates');
  },

  async applyTemplate(
    templateId: string,
    workspaceId = 'default-ws',
    dataRecords: Record<string, unknown>[] = [],
  ): Promise<Record<string, unknown>> {
    return apiClient.post<Record<string, unknown>>(
      `/api/v1/os/marketplace/templates/${templateId}/apply`,
      {
        workspace_id: workspaceId,
        data_records: dataRecords,
      },
    );
  },

  // 20.7 Dataset Relationships
  async discoverRelationships(
    datasets: Record<string, Record<string, unknown>[]>,
  ): Promise<Record<string, unknown>> {
    return apiClient.post<Record<string, unknown>>('/api/v1/os/relationships/discover', {
      datasets,
    });
  },

  // 20.8 Semantic Layer
  async getSemanticGlossary(): Promise<Record<string, unknown>> {
    return apiClient.get<Record<string, unknown>>('/api/v1/os/semantic/glossary');
  },

  // 20.9 KPIs
  async getKpiCatalog(): Promise<KpiItem[]> {
    return apiClient.get<KpiItem[]>('/api/v1/os/kpis/catalog');
  },

  // 20.10 Autonomous AI Analyst
  async executeAnalyst(
    query: string,
    workspaceId = 'default-ws',
    sessionId = 'session-main',
  ): Promise<AutonomousAnalystResponse> {
    return apiClient.post<AutonomousAnalystResponse>('/api/v1/os/analyst/execute', {
      query,
      workspace_id: workspaceId,
      session_id: sessionId,
    });
  },

  // 21.2 & 21.3 Portfolio Mode & Demo Datasets
  async initPortfolioMode(): Promise<Record<string, unknown>> {
    return apiClient.post<Record<string, unknown>>('/api/v1/os/portfolio/init');
  },

  async listDemoDatasets(): Promise<Record<string, unknown>[]> {
    return apiClient.get<Record<string, unknown>[]>('/api/v1/os/demo/datasets');
  },

  // 21.4 Telemetry & Usage Analytics
  async getTelemetrySummary(): Promise<Record<string, unknown>> {
    return apiClient.get<Record<string, unknown>>('/api/v1/os/telemetry/summary');
  },

  async trackTelemetryEvent(
    eventType: string,
    metadata: Record<string, unknown> = {},
    latencyMs = 0,
  ): Promise<Record<string, unknown>> {
    return apiClient.post<Record<string, unknown>>('/api/v1/os/telemetry/event', {
      event_type: eventType,
      metadata,
      latency_ms: latencyMs,
    });
  },
};
