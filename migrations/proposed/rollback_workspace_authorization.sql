-- ROLLBACK SCRIPT FOR workspace_authorization.sql
-- Restores database to exact pre-migration state.
-- Safe, additive-only reversal: does not modify or drop core tenants, workspaces, users, or datasets tables.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

-- Drop the three proposed authorization tables in reverse dependency order
DROP TABLE IF EXISTS dataset_workspace_bindings CASCADE;
DROP TABLE IF EXISTS workspace_memberships CASCADE;
DROP TABLE IF EXISTS tenant_memberships CASCADE;

COMMIT;
