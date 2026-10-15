# Confirmed Root Cause & Defect Remediation Register — AI Data Analyst OS

**Date:** 2026-10-14  
**Scope:** Architecture Defects, Authorization Gaps, Transport Failure Modes, and Lifecycle Races  
**Readiness Status:** NOT READY (All identified defect root causes repaired and verified locally; production deployment gated)

---

## 1. Confirmed Integration and Security Defects

| Defect ID | Symptom / Failure Mode | Affected Component / File | Confirmed Root Cause | Engineering Remediation | Verification Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DEF-001** | Empty Supabase report returns local SQLite report history | `frontend/src/services/reportsService.ts` (`getStoredReports`) | Unsafe fallback switch: catch block and empty check diverted authority to local history, leaking unassigned records. | Removed fallback switch completely. Empty hosted results return `[]`; errors propagate as typed exceptions. | `supabase-failure-contract.test.mjs`; signed-in browser 503 check recorded 0 backend fallback requests |
| **DEF-002** | Failed workspace or chart read appears as successful empty state | `frontend/src/services/dashboardService.ts` | Catch handlers swallowed errors, returned empty arrays, and calculated false zero counts. | Catch blocks re-throw typed errors, activating UI error boundaries and retry buttons. | `supabase-failure-contract.test.mjs` |
| **DEF-003** | Upstream 503 results in 24 requests instead of 3 | `frontend/src/api/recovery.ts`, `lib/supabase/client.ts` | Nested retry amplification: PostgREST SDK executed internal retries while transport client also retried. | Disabled internal SDK database retries; delegated single attempt budget ownership to `recovery.ts`. | Browser 503 test dropped from 24 attempts to 6 (2 StrictMode mounts × 3 bounded attempts) |
| **DEF-004** | Network timeout during POST causes duplicate server records | `frontend/src/api/recovery.ts` (`fetchWithRecovery`) | Shared retry handler did not restrict retry logic to idempotent HTTP methods. | Strict GET/HEAD whitelist: POST/PUT/PATCH/DELETE execute exactly once and fail fast on error. | `network-recovery.test.mjs` (POST executed once during simulated network outage) |
| **DEF-005** | Initial session resolution hangs or overwrites fresh login | `frontend/src/context/AuthContext.tsx` | Race condition between initial `getSession()` call and asynchronous `onAuthStateChange` events. | Added 15-second resolution deadline; incoming auth events supersede initial read; successful events clear stale errors. | `network-recovery.test.mjs`; clean manual sign-in and session restoration |
| **DEF-006** | Invalid `DEBUG=release` string silently runs backend in debug mode | `scripts/run_local_backend.py` | Launcher used naive string truthiness, treating any non-empty string as `True`. | Strict boolean validator added; invalid explicit strings reject startup with exit code 1. | `tests/test_local_launcher_config.py` (PASS) |
| **DEF-007** | Body-supplied dataset ID can access other tenant's dataset in chat/DAG | `backend/app/services/orchestrator_service.py`, `data_retrieval_service.py` | Analytical services did not verify dataset ownership before executing file retrieval. | Wired `owned_dataset(db, dataset_id, owner_id)` into retrieval and orchestrator DAG dispatch. | `tests/test_authenticated_dataset_isolation.py` (PASS) |
| **DEF-008** | Background worker executes job even if workspace access was revoked | `backend/jobs/manager.py`, `backend/jobs/authorization.py` | Worker processed enqueued jobs using stale claims without re-checking live database authorization. | Injected `DatabaseJobAuthorizer` to re-verify workspace and dataset ownership prior to every execution and retry. | `tests/test_workspace_authorization_boundary.py` (PASS) |
| **DEF-009** | Missing additive workspace authorization tables | `migrations/proposed/workspace_authorization.sql` | Workspaces lacked relational membership and dataset binding tables in local PostgreSQL. | Authored additive DDL for `tenant_memberships`, `workspace_memberships`, `dataset_workspace_bindings` with indexation. | `test_workspace_authorization_boundary.py` (28 passed in rollback transaction) |
| **DEF-010** | Login page displayed "STATIC PREVIEW" while animation was idle or broken | `frontend/src/components/auth/DataTransformationAnimation.tsx`, `useDataPipelineMotion.ts` | Badge condition fell back to "STATIC PREVIEW" when `isVerifiedRunning` was false; stacked cards caused layout shifts. | Built single stationary viewport; unified modulo 7s active clock; only shows LIVE after verified advancing frames. | `verify-motion-continuity.mjs` (12 loops verified; 0 layout shifts; 0 blank frames) |

---

## 2. Engineering Standards Enforced

1. **Deny-by-Default Authorization**:
   - Absence of identity, revoked role, inactive tenant, or absent membership uniformly returns HTTP 404 (to avoid resource existence leakage) or HTTP 403.
2. **Fail-Closed Gateways**:
   - Database outages during token decoding or user resolution fail closed with HTTP 503; zero synthetic bypass.
3. **Immutability of Dataset Bindings**:
   - Once a dataset is bound to a verified workspace, it cannot be reassigned to a different workspace.
4. **Idempotent Transport Safety**:
   - Mutating operations (`POST`, `PUT`, `DELETE`) are never automatically retried by client transport layers.

---

## 3. Verification & Open Directives

- **Verification Status**: All 10 defects verified through automated unit, integration, and browser tests.
- **Open Directive**: Staging migration deployment and legacy quarantine resolution remain required before production cutover.
