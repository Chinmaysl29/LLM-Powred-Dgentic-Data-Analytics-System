# Supabase Architecture & Integration Audit — AI Data Analyst OS

**Date:** 2026-10-14  
**Scope:** Client SDK Configuration, Authentication Bridges, Authority Switching, Transport Retries, and Provider Boundaries  
**Readiness Status:** NOT READY (Client integration repaired and verified; cloud RLS policies and multi-tenant live concurrency require production cutover sign-off)

---

## 1. Architectural Overview & System Topography

The **AI Data Analyst OS** employs a hybrid architecture separating high-speed local data transformation from multi-tenant cloud persistence:

```
                      ┌───────────────────────────────────────┐
                      │    React 19 Frontend (Vite :5173)     │
                      └───────────┬───────────────┬───────────┘
                                  │               │
                     FastAPI REST │               │ Supabase PostgREST
                  (Bearer Auth)   │               │ (Anon Key + JWT)
                                  ▼               ▼
        ┌───────────────────────────────┐   ┌───────────────────────────────┐
        │   FastAPI Gateway (:8000)     │   │   Hosted Supabase Backend     │
        │   - JWT Verification Gateway  │   │   - Cloud Auth (GoTrue)       │
        │   - Tenant Authorization      │   │   - PostgREST Multi-Tenant    │
        │   - Analytical Engines        │   │   - Row Level Security (RLS)  │
        │   - RAG / Vector Services     │   │   - Cloud Storage Buckets     │
        └───────────────┬───────────────┘   └───────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────┐
        │   Local PostgreSQL (:5432)    │
        │   - Canonical Datasets        │
        │   - Schema & Profile Meta     │
        │   - Additive Memberships      │
        └───────────────────────────────┘
```

1. **Frontend Client Stack**:
   - `frontend/src/main.tsx` $\to$ `App.tsx` $\to$ `AuthContext` / `RequireAuth` $\to$ `AppLayout`.
   - Built on React 19, TypeScript, Vanilla CSS design tokens (`styles/login-motion.css`), and Motion.
2. **Backend Gateway Stack**:
   - `backend.main:app` $\to$ `app/main.py` $\to$ `app/api/v1/routes/router.py`.
   - Uvicorn / FastAPI on port 8000.
3. **Database Segregation**:
   - Local PostgreSQL database `ai_analyst` manages operational datasets, canonical Parquet conversions, schema profiling, and EDA execution.
   - Hosted Supabase PostgreSQL provides cloud-managed user identities, session persistence, and multi-tenant metadata under RLS.

---

## 2. Authentication Bridge & Identity Resolution

1. **Token Propagation**:
   - The frontend authenticates against Supabase GoTrue, obtaining access and refresh tokens.
   - `AuthContext` copies the active access token into `api/client.ts` as `Authorization: Bearer <token>`.
2. **Server-Side Identity Verification**:
   - `get_current_user` in `backend/app/core/security.py` decodes the token, verifies cryptographic signatures against configured JWT secrets, and resolves a persisted user entity in local PostgreSQL.
   - If the local user record does not exist or database is unavailable, the gateway **fails closed** (HTTP 503 / 401). Synthetic dummy users are never generated.
3. **Dual Token Compatibility**:
   - The gateway supports both Supabase JWTs and local gateway tokens, strictly validating `token_type == 'access'` and rejecting refresh tokens or tokens missing required claims.

---

## 3. Audited Defect Remediations

### A. Elimination of Unsafe Authority Switching (`reportsService.ts`)
- **Vulnerability**: Previously, if a configured hosted Supabase read returned an empty array or an HTTP error, `getStoredReports` switched authority to backend local SQLite/JSON history.
- **Security Impact**: An empty workspace in Supabase caused the client to display unassigned or foreign local report records, breaking tenant boundaries.
- **Fix**: Removed the fallback switch entirely. Empty hosted results truthfully return `[]`; hosted errors propagate as explicit errors.

### B. Error Swallowing in Dashboard Services (`dashboardService.ts`)
- **Vulnerability**: Catch handlers on workspace and visualization queries returned empty arrays and summary counts, masquerading backend failures as empty datasets.
- **Fix**: Catch blocks now propagate typed exceptions to triggering page components, activating existing accessible error banners and retry buttons.

### C. PostgREST SDK Retry Amplification (`lib/supabase/client.ts`)
- **Vulnerability**: The Supabase JS SDK by default executes internal retries on PostgREST requests. Combined with `recovery.ts` transport retries, a single network glitch caused $3 \times 8 = 24$ requests.
- **Fix**: Configured `db: { fetch: customFetch }` with internal SDK retry budget set to 0. A single transport owner (`recovery.ts`) manages all bounded retries with jitter.

### D. Initial Session Race in `AuthContext.tsx`
- **Vulnerability**: `supabase.auth.getSession()` raced with incoming `onAuthStateChange` events; a slow initial read could overwrite a fresh sign-in event or hang indefinitely.
- **Fix**: Implemented a 15-second resolution deadline; subsequent auth events supersede pending initial reads; successful auth events explicitly clear stale session errors.

---

## 4. Realtime Subscriptions & Edge Functions Audit

- **Realtime Channels**: An exhaustive audit of `frontend/src` confirmed that **zero** `.channel()` or WebSocket table subscriptions are actively mounted. `onAuthStateChange` is a local GoTrue auth listener, not a Realtime table stream.
- **Edge Functions**: Confirmed **zero** `supabase.functions.invoke()` calls exist in active frontend pages. All analytical computation is routed through the FastAPI backend gateway.
- **Conclusion**: Provider-level Realtime incidents or Edge Function degradation on `status.supabase.com` do not directly impact core AI Data Analyst OS analytical operations.

---

## 5. Security & Key Governance

1. **Frontend Key Scope**:
   - `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` are the only Supabase parameters exposed to the browser.
   - The anon key grants access only to endpoints protected by PostgreSQL RLS.
2. **Service-Role Key Isolation**:
   - The `SUPABASE_SERVICE_ROLE_KEY` is present only in backend `.env` configurations.
   - Audited production builds confirmed zero bundling of service-role keys.

---

## 6. Remaining Gaps & Final Status

- **Open Gates**: Production cloud RLS policies must be audited against production keys before final cutover.
- **Verdict**: **NOT READY**.
