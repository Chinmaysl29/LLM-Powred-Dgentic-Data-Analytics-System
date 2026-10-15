/**
 * Supabase Database TypeScript Definitions
 * Matching the AI Data Analyst OS schema architecture.
 */

export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export interface Database {
  public: {
    Tables: {
      profiles: {
        Row: {
          id: string;
          full_name: string | null;
          avatar_url: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id: string;
          full_name?: string | null;
          avatar_url?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          full_name?: string | null;
          avatar_url?: string | null;
          created_at?: string;
          updated_at?: string;
        };
      };
      workspaces: {
        Row: {
          id: string;
          owner_id: string;
          name: string;
          description: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          owner_id: string;
          name: string;
          description?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          owner_id?: string;
          name?: string;
          description?: string | null;
          created_at?: string;
          updated_at?: string;
        };
      };
      datasets: {
        Row: {
          id: string;
          user_id: string;
          workspace_id: string | null;
          name: string;
          original_filename: string;
          storage_path: string;
          file_type: string;
          file_size: number | null;
          row_count: number | null;
          column_count: number | null;
          processing_status: string;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          workspace_id?: string | null;
          name: string;
          original_filename: string;
          storage_path: string;
          file_type: string;
          file_size?: number | null;
          row_count?: number | null;
          column_count?: number | null;
          processing_status?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          user_id?: string;
          workspace_id?: string | null;
          name?: string;
          original_filename?: string;
          storage_path?: string;
          file_type?: string;
          file_size?: number | null;
          row_count?: number | null;
          column_count?: number | null;
          processing_status?: string;
          created_at?: string;
          updated_at?: string;
        };
      };
      analysis_sessions: {
        Row: {
          id: string;
          user_id: string;
          workspace_id: string | null;
          dataset_id: string | null;
          title: string;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          workspace_id?: string | null;
          dataset_id?: string | null;
          title: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          user_id?: string;
          workspace_id?: string | null;
          dataset_id?: string | null;
          title?: string;
          created_at?: string;
          updated_at?: string;
        };
      };
      analysis_messages: {
        Row: {
          id: string;
          session_id: string;
          role: string;
          content: string;
          metadata: Json | null;
          created_at: string;
        };
        Insert: {
          id?: string;
          session_id: string;
          role: string;
          content: string;
          metadata?: Json | null;
          created_at?: string;
        };
        Update: {
          id?: string;
          session_id?: string;
          role?: string;
          content?: string;
          metadata?: Json | null;
          created_at?: string;
        };
      };
      saved_visualizations: {
        Row: {
          id: string;
          user_id: string;
          workspace_id: string | null;
          dataset_id: string | null;
          title: string;
          chart_type: string;
          chart_config: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          workspace_id?: string | null;
          dataset_id?: string | null;
          title: string;
          chart_type: string;
          chart_config?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          user_id?: string;
          workspace_id?: string | null;
          dataset_id?: string | null;
          title?: string;
          chart_type?: string;
          chart_config?: Json;
          created_at?: string;
          updated_at?: string;
        };
      };
      reports: {
        Row: {
          id: string;
          user_id: string;
          workspace_id: string | null;
          title: string;
          storage_path: string | null;
          status: string;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          user_id: string;
          workspace_id?: string | null;
          title: string;
          storage_path?: string | null;
          status?: string;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          user_id?: string;
          workspace_id?: string | null;
          title?: string;
          storage_path?: string | null;
          status?: string;
          created_at?: string;
          updated_at?: string;
        };
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
  };
}
