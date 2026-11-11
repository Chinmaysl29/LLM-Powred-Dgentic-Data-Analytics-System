-- Run with reviewed service role names after migration 023. No end-user DB access.
-- psql -v app_role=existing_app -v worker_role=existing_worker -f infrastructure/company_review_role_grants.sql
BEGIN;
GRANT SELECT, INSERT, UPDATE ON dataset_review_grants TO :"app_role";
GRANT SELECT ON dataset_review_grants TO :"worker_role";
GRANT EXECUTE ON FUNCTION company_review_artifact(uuid,text) TO :"app_role", :"worker_role";
GRANT EXECUTE ON FUNCTION company_review_queue(integer) TO :"app_role";
-- The narrow SECURITY DEFINER function must retain its trusted migration owner,
-- fixed pg_catalog search path and canonical scope checks. No raw artifact grant
-- or general source privilege is added. Existing application grants still apply.
COMMIT;
