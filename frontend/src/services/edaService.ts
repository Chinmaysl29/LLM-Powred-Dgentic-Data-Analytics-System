/**
 * edaService.ts
 *
 * Connects the EDA Visualization Studio to the backend EDA API.
 * Endpoint: GET /api/v1/eda/{dataset_id}
 * No mock data — all results come from backend computation.
 */

import { apiClient } from '../api/client';
import type { EDAResponse, EDAResults } from '../types/eda';

export interface EDARequestOptions {
  version?: number;
  filters?: Record<string, unknown>;
  sampleSize?: number;
  signal?: AbortSignal;
}

export const edaService = {
  /**
   * Run the full EDA pipeline for a dataset and return structured results.
   * The backend computes statistics, distributions, correlations, trends,
   * anomalies, and business insights — no fabrication on the frontend.
   */
  async analyze(datasetId: string, opts: EDARequestOptions = {}): Promise<EDAResults> {
    const params: Record<string, string> = {};
    if (opts.filters) params['filters'] = JSON.stringify(opts.filters);
    if (opts.version != null) params['version'] = String(opts.version);
    if (opts.sampleSize != null) params['sample_size'] = String(opts.sampleSize);

    const response = await apiClient.get<EDAResponse>(
      `/api/v1/eda/${encodeURIComponent(datasetId)}`,
      { params, signal: opts.signal, timeout: 120_000 },
    );

    if (!response || !response.eda_results) {
      throw new Error('EDA service returned an invalid or empty response.');
    }

    return response.eda_results;
  },
};
