# API and Dependency Reliability Matrix — AI Data Analyst OS

**Date:** 2026-10-14  
**Scope:** Transport Deadlines, Retry Policies, Auth-State Contract, Idempotency, and Job Recovery  
**Readiness Status:** NOT READY (Foundational contracts verified; full 13-route degraded matrix and end-to-end token rotation require live environment certification)

---

## 1. Boundary-by-Boundary Reliability Specification

| Integration Boundary | Transport & Retry Policy | Deadline & Timeout Policy | Error Classification & Handling |
| :--- | :--- | :--- | :--- |
| **FastAPI Client (`api/client.ts`, `recovery.ts`)** | GET/HEAD only: bounded retry (max 2 additional attempts with exponential backoff & jitter). Writes (POST/PUT/PATCH/DELETE) are **never** automatically retried. | Outer request deadline: **30 seconds** covering connection, header arrival, body streaming, and JSON parsing. | 429/502/503/504 trigger safe read retry up to budget. 401/403/404/422 fail fast without retry. Respects `Retry-After` header. |
| **Supabase PostgREST SDK (`lib/supabase/client.ts`)** | SDK internal database retries disabled (`db: { fetch: customFetch }`). Single-point retry ownership delegated to `recovery.ts`. | Transport deadline: **15 seconds** for response headers; body read deadline: **15 seconds**. | Errors propagate truthfully; empty arrays do not switch authority to alternative local fallback stores. |
| **Authentication Lifecycle (`AuthContext.tsx`)** | 6-state explicit contract. Auth events supersede pending async reads. Single in-flight token refresh to prevent concurrency storms. | Initial session resolution deadline: **15 seconds**. Stale errors cleared on successful token receipt. | Expired token triggers refresh; 401 on refresh triggers `EXPIRED` state; remote logout failure cleanly resets client state. |
| **Database Sessions (`postgres.py`)** | Connection pool with bounded acquisition timeout (5.0s). Deadlock detection and rollback handlers. | Query statement timeout: **30 seconds**; lock acquisition timeout: **5 seconds**. | Connection loss raises `DatabaseConnectionError`; schema drift triggers fail-closed gateway abort. |
| **External LLM Providers (`provider.py`)** | Fallback chain: `Groq → Gemini → OpenAI`. Provider-specific backoff on 429 rate limit. | Per-provider API timeout: **10 to 15 seconds** bounded deadline. | OpenAI `insufficient_quota` is trapped gracefully, falling back to secondary providers without pipeline crashes. |
| **ChromaDB Vector Store (`chromadb_store.py`)** | Persistent collection connections only. Refuses silent degradation to in-memory non-persistent stores. | Vector similarity query deadline: **10 seconds**. | Unreachable store raises `ChromaConnectionError`; zero documents returned on failure is treated as dependency failure, not empty dataset. |
| **Redis Background Jobs (`jobs/manager.py`)** | Durable queue (`ai-analyst:jobs:queue`), persistent job state (`ai-analyst:jobs:item`). Safe retry only when `retry_safe = True`. | Handler execution bounded; lock TTL: **30 seconds**. | Authorization re-verified by `DatabaseJobAuthorizer` prior to enqueue, execution, and manual retry. |

---

## 2. Explicit Authentication-State Contract (Phase 3)

The authentication system operates under a formalized six-state finite-state contract:

```
                  ┌─────────────────┐
                  │   SIGNED_OUT    │ ◄────────────────────────┐
                  └────────┬────────┘                          │
                           │ Sign-in / Restore                 │
                           ▼                                   │
                  ┌─────────────────┐                          │
            ┌───► │  AUTHENTICATED  │                          │
            │     └────────┬────────┘                          │
            │              │ Token Expiry / 401                │ Logout /
Token Valid │              ▼                                   │ Refresh Failed
            │     ┌─────────────────┐                          │
            └──── │   REFRESHING    │ ─────────────────────────┤
                  └────────┬────────┘                          │
                           │ Network / 503 Outage              │
                           ▼                                   │
                  ┌─────────────────┐                          │
                  │   TEMPORARILY   │                          │
                  │   UNAVAILABLE   │                          │
                  └────────┬────────┘                          │
                           │ Expiry Deadline Exceeded          │
                           ▼                                   │
                  ┌─────────────────┐                          │
                  │     EXPIRED     │ ─────────────────────────┘
                  └─────────────────┘
```

1. **`AUTHENTICATED`**: Principal verified via Supabase JWT or local access token. Token passed in `Authorization: Bearer <token>`.
2. **`REFRESHING`**: Single-flight token rotation in progress. Duplicate requests queue on a shared promise to prevent refresh races across tabs.
3. **`TEMPORARILY_UNAVAILABLE`**: Network or Supabase outage during refresh attempt; preserved user state without premature logout for up to 60s.
4. **`EXPIRED`**: Refresh token rejected or expired; session terminates safely, prompting re-authentication.
5. **`SIGNED_OUT`**: Local session tokens cleared, storage purged, active background jobs detached.
6. **`AUTHORIZATION_DENIED`**: Valid token, but workspace or dataset membership is absent or revoked (HTTP 403/404). Fails safely.

---

## 3. Network and Dependency Deadlines (Phase 4)

- **Response Headers Deadline**: All outbound HTTP requests enforce an explicit 15-second header deadline via `AbortController`.
- **Response Body Read Deadline**: Streaming and JSON body reading is wrapped with a bounded deadline (15s). Hung response streams cannot leak connection handles.
- **Client Lock Acquisition**: Mutex locks for cross-tab session synchronization enforce a 5-second acquisition timeout.
- **Backend Dependency Calls**: Database queries enforce `statement_timeout = 30s`; vector lookups enforce `timeout = 10s`; LLM inference enforces `timeout = 15s`. Total end-to-end request budget is strictly bounded ($\le 35\text{s}$).
- **Idempotency**: All mutating operations (`POST`, `PUT`, `DELETE`) require unique request tokens or entity IDs; transport layers never blindly replay writes.

---

## 4. Durable Job Recovery (Phase 5)

1. **Persistence & Lifecycle**:
   - Background jobs are registered as `BackgroundJob` records serialized in Redis with 7-day TTL (`ai-analyst:jobs:item:{job_id}`).
   - States: `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`.
2. **Independent Ownership Re-Verification**:
   - `DatabaseJobAuthorizer` executes before every job step:
     - Re-verifies actor workspace membership (`authorize_workspace`).
     - Verifies tenant matching (`job.tenant_id == access.tenant_id`).
     - Verifies dataset binding (`authorize_bound_dataset`).
   - If membership was revoked between enqueue and execution, the job immediately transitions to `FAILED` with terminal authorization error; it is **never** retried.
3. **Worker Crash Recovery**:
   - Stalled or interrupted jobs retain their attempt counter. Only jobs explicitly tagged `retry_safe = True` are eligible for retry; non-idempotent operations fail closed.

---

## 5. Verification Matrix

| Reliability Property | Test Suite | Result | Evidence |
| :--- | :--- | :--- | :--- |
| GET/HEAD Safe Retry Bounded | `network-recovery.test.mjs` | **PASS** | Recovers on 3rd attempt; 4th attempt returns failure |
| Write Replay Prevention | `network-recovery.test.mjs` | **PASS** | POST request executed exactly once during network errors |
| Cancellation Handling | `network-recovery.test.mjs` | **PASS** | Aborted request cancels pending backoff; pre-aborted never starts |
| 429 Retry-After Compliance | `network-recovery.test.mjs` | **PASS** | Fails immediately when `Retry-After` exceeds remaining budget |
| SDK Retry Multiplication | `network-recovery.test.mjs` | **PASS** | Verified zero double-retry amplification in PostgREST SDK |
| Auth Fail-Closed Gateway | `test_auth_fail_closed.py` | **PASS** | Missing secrets, expired claims, or DB outage fail closed |
| Worker Job Authorization | `test_workspace_authorization_boundary.py` | **PASS** | Revoked membership prevents worker execution |

---

## 6. Remaining Gaps & Verdict

- **Gaps**: Full multi-browser concurrent tab refresh tests and long-term background worker crash-restart simulation require live multi-node staging.
- **Verdict**: **NOT READY**.
