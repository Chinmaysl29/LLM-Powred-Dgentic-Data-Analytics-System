import { apiClient } from '../api/client';
export interface SourceDataset { dataset_id: string; dataset_name: string; file_type?: string; row_count?: number | null }
export interface SourcePreview { columns: string[]; rows: Record<string, unknown>[]; total_rows: number | null; preview_rows?: number; count_status?: 'exact' | 'unknown'; column_types?: Record<string, string>; dataset_version?: number | null }
export interface ForecastResult {
  model_type: string; target: string; frequency: string; generated_at: string;
  horizon: number; confidence_level: number; dates: string[]; forecast: number[];
  lower_bound: number[]; upper_bound: number[]; diagnostics: Record<string, unknown>;
}
export interface ChartDataQuery {
  chart_type: string;
  x_axis?: string;
  y_axis?: string;
  aggregation?: string;
  group_by?: string;
  filter_field?: string;
  filter_value?: string;
  date_field?: string;
  start_date?: string;
  end_date?: string;
  version?: number | null;
  limit_categories?: number;
  max_scatter_points?: number;
}

export interface BackendChartDataResponse {
  dataset_id: string;
  dataset_version: number | null;
  chart_type: string;
  metric: string;
  dimension: string;
  aggregation: string;
  unit: string;
  is_valid: boolean;
  validation_message?: string | null;
  total_records: number;
  eligible_records: number;
  computed_records: number;
  is_sampled: boolean;
  sampling_disclosure?: string | null;
  points: { categoryKey: string; seriesKey?: string; label: string; value: number; group?: string }[];
  scatter_points?: { x: number; y: number; label: string }[] | null;
  scatter_bounds?: { minX: number; maxX: number; minY: number; maxY: number } | null;
  histogram_bins?: { bin_start: number; bin_end: number; count: number; percentage: number }[] | null;
  summary_metrics?: Record<string, number>;
}

export const workbenchService = {
  async datasets(signal?: AbortSignal) {
    const all: SourceDataset[] = [];
    for (let skip = 0; ; skip += 100) {
      const page = await apiClient.get<SourceDataset[]>('/api/v1/datasets', { signal, params: { skip: String(skip), limit: '100' } });
      if (!Array.isArray(page)) throw new Error('The dataset service returned an invalid response.');
      all.push(...page);
      if (page.length < 100) return all;
    }
  },
  preview(id: string, signal?: AbortSignal) {
    return apiClient.get<SourcePreview>(`/api/v1/datasets/${encodeURIComponent(id)}/preview`, { signal, params: { limit: '100' } });
  },
  chartData(id: string, query: ChartDataQuery, signal?: AbortSignal) {
    return apiClient.post<BackendChartDataResponse>(`/api/v1/datasets/${encodeURIComponent(id)}/chart-data`, query, { signal });
  },
};
export function downloadWorkbenchJson(value: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function forecastSeries(rows: Record<string, unknown>[], dateColumn: string, valueColumn: string) {
  const seen = new Set<string>();
  const series = rows.map((row, index) => {
    const date = row[dateColumn]; const value = row[valueColumn];
    if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}/.test(date) || !Number.isFinite(Date.parse(date))) throw new Error(`Row ${index + 1} needs a valid ISO date in ${dateColumn}.`);
    if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`Row ${index + 1} needs a numeric value in ${valueColumn}.`);
    const normalized = new Date(date).toISOString();
    if (seen.has(normalized)) throw new Error('Duplicate timestamps need aggregation before forecasting.');
    seen.add(normalized); return { date: normalized, value };
  });
  if (series.length < 3) throw new Error('At least three valid observations are required. Models may require more history.');
  return series.sort((a, b) => a.date.localeCompare(b.date));
}
