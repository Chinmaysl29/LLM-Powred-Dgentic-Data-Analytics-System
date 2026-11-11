-- Additional privileges for existing reviewed roles; run by a migration owner.
-- psql -v app_role=existing_app -v worker_role=existing_worker -f infrastructure/learning_role_grants.sql
-- This is an operator example, not an automatic deployment or password script.
BEGIN;
ALTER ROLE :"app_role" NOSUPERUSER NOBYPASSRLS;
ALTER ROLE :"worker_role" NOSUPERUSER NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO :"app_role", :"worker_role";
GRANT SELECT, INSERT, UPDATE ON learning_runs, learning_attempts, learning_feedback,
  learning_lessons, learning_revisions, learning_verifications, learning_definitions,
  learning_cases, learning_bundles, learning_evaluations, learning_controls, learning_audit
  TO :"app_role", :"worker_role";
GRANT SELECT ON tenant_memberships, workspace_memberships, dataset_workspace_bindings,
  workspaces, tenants TO :"app_role", :"worker_role";
-- Workers also need existing approved run/job/data privileges. Keep inherited
-- privileges for ordinary app endpoints under their existing least-privilege policy.
GRANT SELECT (id, is_active) ON users TO :"worker_role";
GRANT SELECT, INSERT, UPDATE ON background_jobs TO :"worker_role";
GRANT SELECT, UPDATE ON analysis_runs, analysis_stages TO :"worker_role";
GRANT SELECT, INSERT ON analysis_events, analysis_artifacts TO :"worker_role";
GRANT SELECT ON datasets, dataset_versions, dataset_metadata, dataset_profiles, dataset_quality TO :"worker_role";
COMMIT;
