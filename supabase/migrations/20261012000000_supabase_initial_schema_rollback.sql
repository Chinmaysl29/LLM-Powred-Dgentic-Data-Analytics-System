-- ============================================================================
-- AI DATA ANALYST OS — SUPABASE INITIAL MIGRATION ROLLBACK SCRIPT
-- Migration: 20261012000000_supabase_initial_schema_rollback.sql
-- ============================================================================

-- Drop storage policies
DROP POLICY IF EXISTS "Users can delete own dataset files" ON storage.objects;
DROP POLICY IF EXISTS "Users can update own dataset files" ON storage.objects;
DROP POLICY IF EXISTS "Users can upload own dataset files" ON storage.objects;
DROP POLICY IF EXISTS "Users can read own dataset files" ON storage.objects;

-- Drop trigger & function
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user();

-- Drop application tables in reverse foreign-key order
DROP TABLE IF EXISTS public.reports CASCADE;
DROP TABLE IF EXISTS public.saved_visualizations CASCADE;
DROP TABLE IF EXISTS public.analysis_messages CASCADE;
DROP TABLE IF EXISTS public.analysis_sessions CASCADE;
DROP TABLE IF EXISTS public.datasets CASCADE;
DROP TABLE IF EXISTS public.workspaces CASCADE;
DROP TABLE IF EXISTS public.profiles CASCADE;
