-- ============================================================================
-- AI DATA ANALYST OS — SUPABASE INITIAL DATABASE & STORAGE MIGRATION
-- Migration: 20261012000000_supabase_initial_schema.sql
-- Description: Creates profiles, workspaces, datasets, analysis sessions/messages,
--              saved visualizations, reports, RLS policies, trigger on auth.users,
--              and private user-datasets storage bucket with security policies.
-- ============================================================================

-- Ensure uuid-ossp / pgcrypto are available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- 1. TABLE: profiles
-- Store application-specific account information linked to auth.users.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT,
    avatar_url TEXT,
    preferences JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_profiles_created_at ON public.profiles(created_at DESC);

-- ============================================================================
-- 2. TABLE: workspaces
-- Workspaces owned by users for organizing datasets and analytics.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workspaces_owner_id ON public.workspaces(owner_id);

-- ============================================================================
-- 3. TABLE: datasets
-- Structured datasets uploaded by users, tracking file details and status.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size BIGINT,
    row_count BIGINT,
    column_count INTEGER,
    processing_status TEXT NOT NULL DEFAULT 'uploaded',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_datasets_user_id ON public.datasets(user_id);
CREATE INDEX IF NOT EXISTS idx_datasets_workspace_id ON public.datasets(workspace_id);
CREATE INDEX IF NOT EXISTS idx_datasets_created_at ON public.datasets(created_at DESC);

-- ============================================================================
-- 4. TABLE: analysis_sessions
-- Multi-turn analytical conversations and agent sessions.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.analysis_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    dataset_id UUID REFERENCES public.datasets(id) ON DELETE SET NULL,
    title TEXT NOT NULL DEFAULT 'New Analysis',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analysis_sessions_user_id ON public.analysis_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_analysis_sessions_dataset_id ON public.analysis_sessions(dataset_id);
CREATE INDEX IF NOT EXISTS idx_analysis_sessions_created_at ON public.analysis_sessions(created_at DESC);

-- ============================================================================
-- 5. TABLE: analysis_messages
-- Messages exchanged between user and AI analytical agents within a session.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.analysis_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.analysis_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analysis_messages_session_id ON public.analysis_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_analysis_messages_created_at ON public.analysis_messages(created_at ASC);

-- ============================================================================
-- 6. TABLE: saved_visualizations
-- Generated charts, plots, and visual dashboards configured by users.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.saved_visualizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    dataset_id UUID REFERENCES public.datasets(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    chart_type TEXT NOT NULL,
    chart_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_saved_visualizations_user_id ON public.saved_visualizations(user_id);
CREATE INDEX IF NOT EXISTS idx_saved_visualizations_dataset_id ON public.saved_visualizations(dataset_id);

-- ============================================================================
-- 7. TABLE: reports
-- Formatted reports, analytical briefs, and executive summaries.
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES public.workspaces(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    storage_path TEXT,
    status TEXT NOT NULL DEFAULT 'generated',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_reports_user_id ON public.reports(user_id);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON public.reports(created_at DESC);

-- ============================================================================
-- 8. TRIGGER: Automatic Profile Provisioning
-- When a user registers via Supabase Auth, automatically insert a profile row.
-- ============================================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
    INSERT INTO public.profiles (id, full_name, avatar_url, created_at, updated_at)
    VALUES (
        new.id,
        COALESCE(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name', ''),
        COALESCE(new.raw_user_meta_data->>'avatar_url', ''),
        now(),
        now()
    )
    ON CONFLICT (id) DO UPDATE
    SET full_name = COALESCE(EXCLUDED.full_name, public.profiles.full_name),
        updated_at = now();
    RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================================
-- 9. ROW LEVEL SECURITY (RLS) POLICIES
-- Strict least-privilege policies.
-- ============================================================================

-- A. PROFILES
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view their own profile" ON public.profiles;
CREATE POLICY "Users can view their own profile"
    ON public.profiles FOR SELECT TO authenticated
    USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update their own profile" ON public.profiles;
CREATE POLICY "Users can update their own profile"
    ON public.profiles FOR UPDATE TO authenticated
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

DROP POLICY IF EXISTS "Users can insert their own profile" ON public.profiles;
CREATE POLICY "Users can insert their own profile"
    ON public.profiles FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = id);

-- B. WORKSPACES
ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view their own workspaces" ON public.workspaces;
CREATE POLICY "Users can view their own workspaces"
    ON public.workspaces FOR SELECT TO authenticated
    USING (auth.uid() = owner_id);

DROP POLICY IF EXISTS "Users can create their own workspaces" ON public.workspaces;
CREATE POLICY "Users can create their own workspaces"
    ON public.workspaces FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = owner_id);

DROP POLICY IF EXISTS "Users can update their own workspaces" ON public.workspaces;
CREATE POLICY "Users can update their own workspaces"
    ON public.workspaces FOR UPDATE TO authenticated
    USING (auth.uid() = owner_id)
    WITH CHECK (auth.uid() = owner_id);

DROP POLICY IF EXISTS "Users can delete their own workspaces" ON public.workspaces;
CREATE POLICY "Users can delete their own workspaces"
    ON public.workspaces FOR DELETE TO authenticated
    USING (auth.uid() = owner_id);

-- C. DATASETS
ALTER TABLE public.datasets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view their own datasets" ON public.datasets;
CREATE POLICY "Users can view their own datasets"
    ON public.datasets FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can create their own datasets" ON public.datasets;
CREATE POLICY "Users can create their own datasets"
    ON public.datasets FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own datasets" ON public.datasets;
CREATE POLICY "Users can update their own datasets"
    ON public.datasets FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own datasets" ON public.datasets;
CREATE POLICY "Users can delete their own datasets"
    ON public.datasets FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

-- D. ANALYSIS SESSIONS
ALTER TABLE public.analysis_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view their own analysis sessions" ON public.analysis_sessions;
CREATE POLICY "Users can view their own analysis sessions"
    ON public.analysis_sessions FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can create their own analysis sessions" ON public.analysis_sessions;
CREATE POLICY "Users can create their own analysis sessions"
    ON public.analysis_sessions FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own analysis sessions" ON public.analysis_sessions;
CREATE POLICY "Users can update their own analysis sessions"
    ON public.analysis_sessions FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own analysis sessions" ON public.analysis_sessions;
CREATE POLICY "Users can delete their own analysis sessions"
    ON public.analysis_sessions FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

-- E. ANALYSIS MESSAGES (Inherited session authorization)
ALTER TABLE public.analysis_messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view messages from their analysis sessions" ON public.analysis_messages;
CREATE POLICY "Users can view messages from their analysis sessions"
    ON public.analysis_messages FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.analysis_sessions s
            WHERE s.id = analysis_messages.session_id
              AND s.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "Users can insert messages into their analysis sessions" ON public.analysis_messages;
CREATE POLICY "Users can insert messages into their analysis sessions"
    ON public.analysis_messages FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.analysis_sessions s
            WHERE s.id = analysis_messages.session_id
              AND s.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "Users can delete messages from their analysis sessions" ON public.analysis_messages;
CREATE POLICY "Users can delete messages from their analysis sessions"
    ON public.analysis_messages FOR DELETE TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.analysis_sessions s
            WHERE s.id = analysis_messages.session_id
              AND s.user_id = auth.uid()
        )
    );

-- F. SAVED VISUALIZATIONS
ALTER TABLE public.saved_visualizations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view their own saved visualizations" ON public.saved_visualizations;
CREATE POLICY "Users can view their own saved visualizations"
    ON public.saved_visualizations FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can create their own saved visualizations" ON public.saved_visualizations;
CREATE POLICY "Users can create their own saved visualizations"
    ON public.saved_visualizations FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own saved visualizations" ON public.saved_visualizations;
CREATE POLICY "Users can update their own saved visualizations"
    ON public.saved_visualizations FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own saved visualizations" ON public.saved_visualizations;
CREATE POLICY "Users can delete their own saved visualizations"
    ON public.saved_visualizations FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

-- G. REPORTS
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view their own reports" ON public.reports;
CREATE POLICY "Users can view their own reports"
    ON public.reports FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can create their own reports" ON public.reports;
CREATE POLICY "Users can create their own reports"
    ON public.reports FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own reports" ON public.reports;
CREATE POLICY "Users can update their own reports"
    ON public.reports FOR UPDATE TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete their own reports" ON public.reports;
CREATE POLICY "Users can delete their own reports"
    ON public.reports FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

-- ============================================================================
-- 10. STORAGE BUCKET & POLICIES: user-datasets
-- Dedicated private bucket for uploaded CSV, Excel, and structured files.
-- ============================================================================

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'user-datasets',
    'user-datasets',
    false,
    104857600, -- 100 MB
    ARRAY[
        'text/csv',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/json',
        'application/pdf',
        'application/octet-stream'
    ]
)
ON CONFLICT (id) DO UPDATE
SET public = false,
    file_size_limit = 104857600;

-- Storage RLS: Users can only read objects in their own user folder: <user_id>/*
DROP POLICY IF EXISTS "Users can read own dataset files" ON storage.objects;
CREATE POLICY "Users can read own dataset files"
    ON storage.objects FOR SELECT TO authenticated
    USING (
        bucket_id = 'user-datasets'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

-- Storage RLS: Users can upload files into their own user folder: <user_id>/*
DROP POLICY IF EXISTS "Users can upload own dataset files" ON storage.objects;
CREATE POLICY "Users can upload own dataset files"
    ON storage.objects FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id = 'user-datasets'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

-- Storage RLS: Users can update/overwrite their own files
DROP POLICY IF EXISTS "Users can update own dataset files" ON storage.objects;
CREATE POLICY "Users can update own dataset files"
    ON storage.objects FOR UPDATE TO authenticated
    USING (
        bucket_id = 'user-datasets'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );

-- Storage RLS: Users can delete their own files
DROP POLICY IF EXISTS "Users can delete own dataset files" ON storage.objects;
CREATE POLICY "Users can delete own dataset files"
    ON storage.objects FOR DELETE TO authenticated
    USING (
        bucket_id = 'user-datasets'
        AND (storage.foldername(name))[1] = auth.uid()::text
    );
