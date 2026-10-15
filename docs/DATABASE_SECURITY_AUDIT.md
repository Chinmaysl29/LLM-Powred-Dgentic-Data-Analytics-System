# Database and Security Audit — AI Data Analyst OS

**Date:** 2026-10-14  
**Audit Scope:** Local PostgreSQL (`ai_analyst`), Hosted Supabase PostgreSQL, Storage Buckets, and Tenant Isolation  
**Readiness Status:** NOT READY (Production migration staged and gated; quarantined legacy data unassigned)

---

## 1. Architecture and Store Segregation

1. **Dual Database Tier**:
   - **Local PostgreSQL (`ai_analyst`, port 5432/5433)**: Primary relational store for operational analytical datasets, dataset metadata, quality profiles, cleaning recommendations, schema history, and local workspace authorizations.
   - **Hosted Supabase PostgreSQL**: Dedicated multi-tenant persistence layer accessed by the frontend via the Supabase client using configured publishable anon keys and JWT-bound RLS policies.
   - **Integrity Boundary**: The frontend never bypasses the FastAPI gateway to execute unauthenticated writes. Hosted Supabase and local PostgreSQL stores maintain strict separation of concerns; failures in one store do not cause unauthenticated fallback switching to another store.

2. **Server-Side Service-Role Usage**:
   - The Supabase `service_role` key is strictly restricted to server-side administrative background tasks and backend environment configurations.
   - Verified that client bundles (`frontend/dist/assets/*`) contain zero references to service-role keys or privileged secrets. Only the public anon key (`VITE_SUPABASE_ANON_KEY`) is bundled.

---

## 2. Row Level Security (RLS) & Role Grants

1. **Tenant and Workspace Access Control**:
   - All workspace access enforces server-side identity validation via `get_current_user` and `authorize_workspace(db, user_id, workspace_id, permission)`.
   - Access is **deny-by-default**: missing memberships, inactive users, or inactive tenants raise HTTP 404 (preventing resource existence enumeration) or HTTP 403 (for permission mismatches such as viewer attempting writes).
   - In Supabase PostgreSQL, RLS policies on `workspaces` enforce:
     - `SELECT`: Restricted to authenticated users where `auth.uid() = owner_id` or membership exists.
     - `INSERT`: Restricted to authenticated principals; `owner_id` is bound to `auth.uid()`.
     - `UPDATE` / `DELETE`: Restricted to workspace owners/admins. Verified cross-account update denial in browser SDK tests.

2. **Storage Bucket Policies**:
   - **Local Storage (`storage/`)**:
     - `storage/raw/`: Raw CSV, XLSX, JSON, and PDF files are stored with UUID-prefixed file paths. File access requires `DataRetrievalService` checking `owned_dataset(db, dataset_id, owner_id)`.
     - `storage/authorized_workspaces/{workspace_id}/`: Workspace reports, dashboards, and memory files are isolated by workspace UUID. Directory traversal is blocked by UUID validation (`identifier()`).
   - **Supabase Storage**:
     - Public bucket policies are revoked for private analytical artifacts.
     - Authenticated uploads require valid session tokens; cross-tenant reads return HTTP 403/404.

---

## 3. Legacy-Data Quarantine

1. **Quarantine State**:
   - 38 legacy datasets in local PostgreSQL have `owner_id IS NULL`.
   - **Policy**: In accordance with the non-negotiable directive, all quarantined legacy records remain **strictly unassigned and inaccessible** to tenant queries.
   - **Enforcement**:
     - `owned_dataset(db, dataset_id, owner_id)` in `backend/app/core/authorization.py` explicitly rejects `owner_id IS None` and filters queries by `Dataset.owner_id == str(owner_id)`.
     - Legacy records return HTTP 404 on preview, profiling, recommendations, metadata, versions, and quality endpoints.
     - RAG vector search explicitly isolates collections by owner (`rag_owner_{hex}`); legacy chunks are completely excluded from retrieval.
   - **Assignment Gate**: No backfill or automated assignment will be performed without explicit user review and written approval.

---

## 4. Foreign-Key Integrity and Additive Authorization Tables

1. **Proposed Additive Migration (`migrations/proposed/workspace_authorization.sql`)**:
   - Tables staged:
     - `tenant_memberships` (`tenant_id` FK to `tenants.id`, `user_id` FK to `users.id`, role check, composite PK).
     - `workspace_memberships` (`workspace_id` FK to `workspaces.id`, `user_id` FK to `users.id`, role check, composite PK).
     - `dataset_workspace_bindings` (`dataset_id` FK to `datasets.dataset_id`, `workspace_id` FK to `workspaces.id`, PK on dataset_id).
   - Revocation: `REVOKE ALL ON tenant_memberships, workspace_memberships, dataset_workspace_bindings FROM PUBLIC;`
   - Indexes: Indexed on `user_id` and `workspace_id` for fast query resolution without full table scans.

2. **Dataset-to-Workspace Binding Integrity**:
   - Handled via `POST /api/v1/datasets/{dataset_id}/workspace`.
   - Requires that the calling user owns the dataset AND holds write permissions on the target workspace.
   - Binding is **immutable** once set; attempts to rebind to an unauthorized or different workspace fail with HTTP 404 or HTTP 409.

---

## 5. Migration Execution & Rollback Strategy

1. **Execution Safeguards**:
   - All DDL scripts must execute within explicit transactions:
     ```sql
     BEGIN;
     SET LOCAL lock_timeout = '5s';
     SET LOCAL statement_timeout = '30s';
     -- DDL statements
     COMMIT;
     ```
   - Lock timeout (5s) prevents table lock queues from blocking active production traffic.
   - Statement timeout (30s) prevents hung catalog locks.
2. **Rollback Strategy**:
   - If any statement fails, the transaction automatically rolls back cleanly without partial schema states.
   - Verified pre-reconciliation backup is maintained in `logs/recovery/` with verifiable SHA-256 digest.
   - Forward-only remediation: In case of post-commit regression, rollback consists of forward migration patches rather than dropping tables or wiping customer records.
3. **Approval Status**:
   - Production execution remains **GATED AND PENDING EXPLICIT USER APPROVAL**. No production schema changes were applied in this batch.

---

## 6. Verification and Test Results

| Test Suite / Inspection | Tests Executed | Passed | Failed | Status | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `test_workspace_authorization_boundary.py` | 28 | 28 | 0 | **PASS** | Two-account workspace, reports, memory, dataset binding isolation |
| `test_authenticated_dataset_isolation.py` | 19 | 19 | 0 | **PASS** | Quarantined legacy datasets, cross-tenant preview/metadata denial |
| `test_dataset_ownership_security.py` | 15 | 15 | 0 | **PASS** | Ownership preceding route handlers, anonymous rejection |
| `test_auth_fail_closed.py` | 5 | 5 | 0 | **PASS** | DB outage fails closed, secret absence never defaults |
| `test_rag_owner_isolation.py` | 8 | 8 | 0 | **PASS** | Vector collections partitioned by owner, legacy chunks quarantined |
| **Total Database Security Checks** | **75** | **75** | **0** | **PASS** | **All automated test boundary assertions pass** |

---

## 7. Remaining Blockers

1. **Production Migration Execution**: `workspace_authorization.sql` is fully verified in isolated transactions but requires explicit production sign-off.
2. **Quarantined Data Resolution**: 38 legacy datasets remain unassigned. Production readiness requires user validation of legacy dataset provenance.
3. **Verdict**: **NOT READY** until production migration is approved and executed in staging/prod.
