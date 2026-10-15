/**
 * Reports Service connected to Supabase Database reports table and enterprise backend.
 */

import { apiClient } from '../api/client';
import { supabase, isSupabaseConfigured } from '../lib/supabase/client';
import type {
  Report,
  ReportFilters,
  ReportSpecification,
  ReportSectionConfig,
  CreateReportParams,
} from '../types/reports';
import type { AnalysisHistoryReportItem } from '../types/analysis';

export interface GeneratedReportResponse {
  id: string;
  title: string;
  status: string;
  format: string;
  report_type: string;
  filename: string;
  created_at: string;
  download_url: string;
  dataset_name?: string;
  query?: string;
  provenance?: Record<string, unknown>;
  summary?: string;
}

export interface StoredReport {
  id: string;
  title: string;
  report_type: string;
  created_at: string;
  workspace_id: string;
  summary?: string;
  markdown?: string;
  metrics?: Record<string, unknown>;
  download_url?: string;
  format?: string;
}

export const DEFAULT_REPORT_SECTIONS: ReportSectionConfig[] = [];

export async function getStoredReports(): Promise<StoredReport[]> {
  if (isSupabaseConfigured()) {
    const { data, error } = await supabase
      .from('reports').select('*').order('created_at', { ascending: false });
    if (error) throw new Error('Report library is unavailable. Please retry.');
    if (!Array.isArray(data)) throw new Error('The report service returned an invalid history.');
    return (data as Array<Record<string, unknown>>).map((r) => ({
      id: String(r.id), title: String(r.title), report_type: 'custom',
      created_at: String(r.created_at), workspace_id: String(r.workspace_id || ''),
      summary: String(r.title),
    }));
  }

  const data = await apiClient.get<StoredReport[]>('/api/v1/os/reports/studio/history');
  if (!Array.isArray(data)) throw new Error('The report service returned an invalid history.');
  return data;
}

export async function getReports(filters?: ReportFilters): Promise<Report[]> {
  const reports = (await getStoredReports()).map(
    (r): Report => ({
      id: r.id,
      title: r.title,
      dataset: 'Source not recorded',
      dateRange: { start: '', end: '', label: 'Period not recorded' },
      reportType: 'custom',
      status: 'generated',
      sections: [],
      outputFormat: 'pdf',
      createdAt: r.created_at,
      updatedAt: r.created_at,
    }),
  );

  return reports.filter(
    (r) =>
      (!filters?.searchQuery ||
        r.title.toLowerCase().includes(filters.searchQuery.toLowerCase())) &&
      (!filters?.status || filters.status === 'all' || r.status === filters.status) &&
      (!filters?.reportType || filters.reportType === 'all' || r.reportType === filters.reportType),
  );
}

export async function getReportById(id: string): Promise<Report | null> {
  return (await getReports()).find((r) => r.id === id) ?? null;
}

export async function getReportSpecification(_id: string): Promise<ReportSpecification | null> {
  return null;
}

export async function createReport(params: CreateReportParams): Promise<Report> {
  if (isSupabaseConfigured()) {
    const { data: { user } } = await supabase.auth.getUser();
    if (user) {
      const { data, error } = await supabase
        .from('reports')
        .insert({
          user_id: user.id,
          title: params.title,
          status: 'generated',
        } as Record<string, unknown>)
        .select()
        .single();

      if (!error && data) {
        const row = data as Record<string, unknown>;
        return {
          id: String(row.id),
          title: String(row.title),
          dataset: params.dataset || 'Uploaded Dataset',
          dateRange: params.dateRange || { start: '', end: '', label: 'Current' },
          reportType: params.reportType || 'custom',
          status: 'generated',
          sections: params.sections || [],
          outputFormat: params.outputFormat || 'pdf',
          createdAt: String(row.created_at || new Date().toISOString()),
          updatedAt: String(row.updated_at || new Date().toISOString()),
        };
      }
    }
  }

  throw new Error('Report creation requires Supabase database connection.');
}

export async function updateReportSections(_id: string, _sections: ReportSectionConfig[]): Promise<Report> {
  throw new Error('Report section update is not supported.');
}

export async function duplicateReport(_id: string): Promise<Report> {
  throw new Error('Report duplication is not supported.');
}

export async function archiveReport(_id: string): Promise<boolean> {
  return true;
}

export async function deleteReport(id: string): Promise<boolean> {
  if (isSupabaseConfigured()) {
    try {
      await supabase.from('reports').delete().eq('id', id);
      return true;
    } catch {
      return false;
    }
  }
  return false;
}

export async function exportReport(_id: string, _format: 'pdf' | 'excel' | 'csv'): Promise<{ success: boolean; filename: string }> {
  throw new Error('Binary export requires dedicated backend worker.');
}

export function downloadStoredReport(report: StoredReport): void {
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = report.id.replace(/[^a-zA-Z0-9_-]/g, '_') + '.json';
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function getReportsAnalysisHistory(
  workspaceId?: string | null,
): Promise<AnalysisHistoryReportItem[]> {
  const query = workspaceId ? `?workspace_id=${workspaceId}` : '';
  return apiClient.get<AnalysisHistoryReportItem[]>(`/api/v1/reports/analysis-history${query}`);
}

export async function generateReportFromAnalysis(payload: {
  run_id: string;
  session_id?: string | null;
  title?: string;
  report_type?: string;
  format_type?: string;
  sections?: string[];
}): Promise<GeneratedReportResponse> {
  return apiClient.post<GeneratedReportResponse>('/api/v1/reports/from-analysis', payload);
}

export async function downloadReportFile(reportId: string, filename?: string): Promise<void> {
  const token = localStorage.getItem('access_token') || localStorage.getItem('token');
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`/api/v1/reports/${reportId}/download`, {
    headers,
  });

  if (!response.ok) {
    throw new Error(`Report download failed with status ${response.status}`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename || `report_${reportId}.pdf`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

