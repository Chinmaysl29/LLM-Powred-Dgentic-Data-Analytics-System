-- REVIEW REQUIRED. Not an Alembic head; do not run against production without approval.
-- Additive, no legacy backfill. Local PostgreSQL only, not hosted Supabase schema.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
CREATE TABLE tenant_memberships (
 tenant_id uuid NOT NULL REFERENCES tenants(id),
 user_id uuid NOT NULL REFERENCES users(id),
 role varchar(20) NOT NULL CHECK (role IN ('owner','admin','analyst','viewer')),
 active boolean NOT NULL DEFAULT true,
 PRIMARY KEY (tenant_id, user_id)
);
CREATE INDEX ix_tenant_memberships_user ON tenant_memberships(user_id);
CREATE TABLE workspace_memberships (
 workspace_id uuid NOT NULL REFERENCES workspaces(id),
 user_id uuid NOT NULL REFERENCES users(id),
 role varchar(20) NOT NULL CHECK (role IN ('owner','admin','analyst','viewer')),
 active boolean NOT NULL DEFAULT true,
 PRIMARY KEY (workspace_id, user_id)
);
CREATE INDEX ix_workspace_memberships_user ON workspace_memberships(user_id);
CREATE TABLE dataset_workspace_bindings (
 dataset_id varchar(36) PRIMARY KEY REFERENCES datasets(dataset_id),
 workspace_id uuid NOT NULL REFERENCES workspaces(id)
);
CREATE INDEX ix_dataset_workspace_bindings_workspace ON dataset_workspace_bindings(workspace_id);
REVOKE ALL ON tenant_memberships, workspace_memberships, dataset_workspace_bindings FROM PUBLIC;
COMMIT;
-- No membership inserts or bindings are inferred. Enrollment requires separate approval.
-- Rollback before COMMIT is transactional. After commit retain the additive tables;
-- restore only in an isolated environment or use a reviewed forward fix.
