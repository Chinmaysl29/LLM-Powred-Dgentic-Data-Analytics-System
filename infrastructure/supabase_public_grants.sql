-- Apply only with the hosted UI schema, separate from private analyst tables.
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.profiles, public.workspaces,
  public.datasets, public.analysis_sessions, public.analysis_messages,
  public.saved_visualizations, public.reports TO authenticated;
REVOKE ALL ON public.profiles, public.workspaces, public.datasets,
  public.analysis_sessions, public.analysis_messages, public.saved_visualizations,
  public.reports FROM anon;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
-- All seven tables have explicit owner/session RLS policies in the initial schema.
