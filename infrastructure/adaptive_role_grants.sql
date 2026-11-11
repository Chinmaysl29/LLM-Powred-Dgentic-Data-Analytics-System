-- Additive grants after migration 012; roles must already be reviewed app roles.
-- psql -v app_role=existing_app -v worker_role=existing_worker -f infrastructure/adaptive_role_grants.sql
BEGIN;
ALTER ROLE :"app_role" NOSUPERUSER NOBYPASSRLS;
ALTER ROLE :"worker_role" NOSUPERUSER NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO :"app_role", :"worker_role";
GRANT SELECT, INSERT, UPDATE ON adaptive_skills, adaptive_skill_revisions,
  adaptive_cases, adaptive_work, adaptive_models, adaptive_contexts,
  adaptive_decisions, adaptive_outcomes, adaptive_label_revisions, adaptive_controls
  TO :"app_role", :"worker_role";
-- Existing learning/base-table privileges remain necessary. FORCE RLS and
-- immutable-evidence triggers apply to both roles; no DELETE or bypass grants.
COMMIT;
