/**
 * Dashboard & Workspace Service for Supabase Database Persistence
 *
 * Provides real data aggregation, workspace management, visualization saving,
 * and session tracking backed by Supabase PostgreSQL and Row Level Security.
 */

import { supabase, isSupabaseConfigured } from '../lib/supabase/client';
import { datasetService } from './datasetService';
import type { Dataset } from '../types/datasets';

export interface WorkspaceItem {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface SavedVisualizationItem {
  id: string;
  user_id: string;
  workspace_id: string | null;
  dataset_id: string | null;
  title: string;
  chart_type: string;
  chart_config: Record<string, unknown>;
  created_at: string;
}

export interface DashboardSummary {
  datasetCount: number;
  recentDatasets: Dataset[];
  workspaceCount: number;
  savedVisualizationCount: number;
  reportCount: number;
}

export const dashboardService = {
  /**
   * Fetch authenticated user's workspaces from Supabase.
   */
  async getWorkspaces(): Promise<WorkspaceItem[]> {
    if (!isSupabaseConfigured()) return [];

    const { data, error } = await supabase.from('workspaces').select('*').order('created_at', { ascending: false });
    if (error) throw new Error('Workspace service is unavailable. Please retry.');
    if (!Array.isArray(data)) throw new Error('Workspace service returned invalid data.');
    return data as WorkspaceItem[];
  },

  /**
   * Create a new workspace under the current authenticated user.
   */
  async createWorkspace(name: string, description?: string): Promise<WorkspaceItem | null> {
    if (!isSupabaseConfigured()) return null;

    const { data: { user } } = await supabase.auth.getUser();
    if (!user) throw new Error('Must be authenticated to create a workspace.');

    const { data, error } = await supabase
      .from('workspaces')
      .insert({
        owner_id: user.id,
        name,
        description: description || null,
      } as Record<string, unknown>)
      .select()
      .single();

    if (error) throw new Error(error.message);
    return data as WorkspaceItem;
  },

  /**
   * Fetch saved chart visualizations from Supabase.
   */
  async getSavedVisualizations(): Promise<SavedVisualizationItem[]> {
    if (!isSupabaseConfigured()) return [];

    const { data, error } = await supabase.from('saved_visualizations').select('*').order('created_at', { ascending: false });
    if (error) throw new Error('Saved visualization service is unavailable. Please retry.');
    if (!Array.isArray(data)) throw new Error('Saved visualization service returned invalid data.');
    return data as SavedVisualizationItem[];
  },

  /**
   * Save an analytical visualization configuration to Supabase.
   */
  async saveVisualization(
    title: string,
    chartType: string,
    chartConfig: Record<string, unknown>,
    datasetId?: string,
    workspaceId?: string,
  ): Promise<SavedVisualizationItem | null> {
    if (!isSupabaseConfigured()) return null;

    const { data: { user } } = await supabase.auth.getUser();
    if (!user) throw new Error('Must be authenticated to save visualizations.');

    const { data, error } = await supabase
      .from('saved_visualizations')
      .insert({
        user_id: user.id,
        workspace_id: workspaceId || null,
        dataset_id: datasetId || null,
        title,
        chart_type: chartType,
        chart_config: chartConfig,
      } as Record<string, unknown>)
      .select()
      .single();

    if (error) throw new Error(error.message);
    return data as SavedVisualizationItem;
  },

  /**
   * Fetch live dashboard statistics combining Supabase tables and datasets.
   */
  async getDashboardSummary(): Promise<DashboardSummary> {
    const [datasets, workspaces, visualisations] = await Promise.all([
      datasetService.list(0, 5),
      this.getWorkspaces(),
      this.getSavedVisualizations(),
    ]);

    let reportCount = 0;
    if (isSupabaseConfigured()) {
      const { count, error } = await supabase.from('reports').select('*', { count: 'exact', head: true });
      if (error || count == null) throw new Error('Report count is unavailable. Please retry.');
      reportCount = count;
    }

    return {
      datasetCount: datasets.length,
      recentDatasets: datasets,
      workspaceCount: workspaces.length,
      savedVisualizationCount: visualisations.length,
      reportCount,
    };
  },
};
