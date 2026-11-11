/**
 * reports.ts
 *
 * Strongly-typed data contracts for Phase 7: Reports module.
 * Represents report management, section structure, specifications,
 * and export payloads.
 */

import type {
  Insight,
  Risk,
  Opportunity,
  Recommendation,
  BusinessHealthMetric,
  ScenarioProjection,
  ScenarioInputVariables,
} from './insights';
import type { ChartPoint } from '../lib/chartDataTransforms';

export type ReportStatus = 'draft' | 'generating' | 'generated' | 'failed' | 'archived';

export type ReportType =
  'business_performance' | 'sales_analysis' | 'customer_analysis' | 'marketing_analysis' | 'custom';

export type ReportSectionType =
  | 'cover'
  | 'summary'
  | 'kpis'
  | 'visualizations'
  | 'insights'
  | 'risks'
  | 'opportunities'
  | 'recommendations'
  | 'what_if';

export interface ReportSectionConfig {
  id: string;
  type: ReportSectionType;
  title: string;
  description?: string;
  enabled: boolean;
  order: number;
}

export interface ReportDateRange {
  start: string;
  end: string;
  label?: string;
}

export interface Report {
  id: string;
  title: string;
  description?: string;
  dataset: string;
  dateRange: ReportDateRange;
  reportType: ReportType;
  status: ReportStatus;
  sections: ReportSectionConfig[];
  outputFormat: 'pdf' | 'excel' | 'csv';
  createdAt: string;
  updatedAt: string;
  generatedAt?: string;
  author?: string;
}

export interface ReportVisualizationItem {
  id: string;
  title: string;
  chartType: 'Line' | 'Bar' | 'Area' | 'Pie';
  description?: string;
  dataPoints: ChartPoint[];
  xAxisLabel?: string;
  yAxisLabel?: string;
}

export interface ReportSpecification {
  reportId: string;
  title: string;
  dataset: string;
  dateRange: ReportDateRange;
  reportType: ReportType;
  generatedAt: string;
  author: string;
  sections: ReportSectionConfig[];

  // Section Payload Content
  cover: {
    title: string;
    subtitle: string;
    organization: string;
    datasetName: string;
    periodLabel: string;
    generatedDate: string;
    confidentialityNotice: string;
  };
  summary: {
    narrative: string;
    keyHighlights: string[];
  };
  kpis: BusinessHealthMetric[];
  visualizations: ReportVisualizationItem[];
  insights: Insight[];
  risks: Risk[];
  opportunities: Opportunity[];
  recommendations: Recommendation[];
  scenario?: {
    scenarioName: string;
    narrative: string;
    inputs: ScenarioInputVariables;
    projection: ScenarioProjection;
  };
}

export interface ReportFilters {
  searchQuery?: string;
  dataset?: string;
  reportType?: ReportType | 'all';
  status?: ReportStatus | 'all';
  dateFilter?: string;
}

export interface CreateReportParams {
  title: string;
  dataset: string;
  dateRange: ReportDateRange;
  reportType: ReportType;
  sections: ReportSectionConfig[];
  outputFormat: 'pdf' | 'excel' | 'csv';
}

export interface ExportRequest {
  reportId: string;
  format: 'pdf' | 'excel' | 'csv';
}
