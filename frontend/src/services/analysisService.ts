/**
 * Analysis service for natural-language analytics, persistent sessions, and chat.
 * Connects directly to backend /api/v1/chat and /api/v1/analysis/sessions.
 */

import { apiClient } from '../api/client';
import type {
  AnalysisSessionDetail,
  AnalysisSessionSummary,
  ChatRequest,
  ChatResponse,
} from '../types/analysis';

export interface AskParams {
  message: string;
  datasetId?: string | null;
  sessionId?: string | null;
  workspaceId?: string | null;
  datasetVersion?: number | null;
  signal?: AbortSignal;
}

export const analysisService = {
  /**
   * Submit an analytical question or follow-up query to the backend agent orchestrator.
   * Can be called with (params: AskParams) or legacy (message: string, datasetId?: string, signal?: AbortSignal).
   */
  async ask(
    paramOrMessage: string | AskParams,
    legacyDatasetId?: string | null,
    legacySignal?: AbortSignal,
  ): Promise<ChatResponse> {
    let payload: ChatRequest;
    let signal: AbortSignal | undefined;

    if (typeof paramOrMessage === 'string') {
      payload = {
        message: paramOrMessage.trim(),
        dataset_id: legacyDatasetId || null,
      };
      signal = legacySignal;
    } else {
      payload = {
        message: paramOrMessage.message.trim(),
        dataset_id: paramOrMessage.datasetId || null,
        session_id: paramOrMessage.sessionId || null,
        workspace_id: paramOrMessage.workspaceId || null,
        dataset_version: paramOrMessage.datasetVersion || null,
      };
      signal = paramOrMessage.signal;
    }

    return apiClient.post<ChatResponse>('/api/v1/chat', payload, {
      signal,
      timeout: 120_000,
    });
  },

  /**
   * Create a new persistent analysis session in PostgreSQL.
   */
  async createSession(data: {
    title?: string;
    workspace_id?: string | null;
    dataset_id?: string | null;
    dataset_version?: number | null;
  }): Promise<{ session_id: string; title: string; status: string; created_at: string }> {
    return apiClient.post('/api/v1/analysis/sessions', data);
  },

  /**
   * List all analysis sessions for the current user.
   */
  async listSessions(
    workspaceId?: string | null,
    search?: string | null,
    limit: number = 50,
    offset: number = 0,
  ): Promise<AnalysisSessionSummary[]> {
    const params = new URLSearchParams();
    if (workspaceId) params.append('workspace_id', workspaceId);
    if (search && search.trim()) params.append('search', search.trim());
    params.append('limit', String(limit));
    params.append('offset', String(offset));

    const query = params.toString() ? `?${params.toString()}` : '';
    return apiClient.get<AnalysisSessionSummary[]>(`/api/v1/analysis/sessions${query}`);
  },

  /**
   * Fetch full details for a session including all chronological turns and artifacts.
   */
  async getSession(sessionId: string): Promise<AnalysisSessionDetail> {
    return apiClient.get<AnalysisSessionDetail>(`/api/v1/analysis/sessions/${sessionId}`);
  },

  /**
   * Rename or change status of a session.
   */
  async updateSession(
    sessionId: string,
    updates: { title?: string; status?: string },
  ): Promise<{ status: string; session_id: string }> {
    return apiClient.patch(`/api/v1/analysis/sessions/${sessionId}`, updates);
  },

  /**
   * Soft-delete an analysis session.
   */
  async deleteSession(sessionId: string): Promise<{ status: string; session_id: string }> {
    return apiClient.delete(`/api/v1/analysis/sessions/${sessionId}`);
  },
};
