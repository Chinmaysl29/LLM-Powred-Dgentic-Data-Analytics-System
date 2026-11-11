# Optimization engineering report — 10 November 2026

The user subsequently requested completion of the remaining Redis and audit
findings. Both are now **VERIFIED**, including a complete **437 passed, 1 skipped**
backend run and live browser acceptance. See [the continuation report](OPTIMIZATION_FOLLOWUP.md)
for changes and measurements. The results below retain
the original pass's evidence and scope.

## Outcome and scope

The company dashboard, workflow list and incident list now perform bounded batch
reads while retaining their response contracts and authorization. Dictionary
typing sends one request per settled search instead of reloading four panels on
every keystroke. Synchronous identity lookup runs outside the API event loop.

This completes a measured optimization pass over the existing implementation.
It does not claim to finish feature gaps from the earlier eight-feature prompt.
The pre-existing dirty tree was preserved. No credentials, production database,
deployment configuration, dependencies or database schema were changed.

The prioritized pre-change findings are in [OPTIMIZATION_AUDIT.md](OPTIMIZATION_AUDIT.md).
Raw timing samples, source hashes, response hashes, browser counts and sanitized
query-plan structure are in [OPTIMIZATION_METRICS.json](OPTIMIZATION_METRICS.json).

## Architecture and decisions

React/TypeScript/Vite calls FastAPI. SQLAlchemy/PostgreSQL is authoritative for
workspace access, immutable artifacts, definitions and durable jobs. Redis is
optional cache infrastructure. Chroma candidates are checked against canonical
records. Heavy dataplane work stays in bounded, killable DuckDB child processes;
the existing worker, queue, process limits, precision and analytical calculations
are retained. Route code splitting already exists.

No new shared authorization cache, concurrent SQL fan-out, microservice, index,
materialized view or storage format was introduced. Request-local batches remove
redundant work without a cache invalidation policy. Window functions retain ten
runs per workflow and 100 assessed outputs per dataset, rather than applying a
global limit across the page. Incident reads project lineage and manifests rather
than repeatedly hydrating aggregate result rows. The maximum list page remains 50.

The auth dependency uses FastAPI's existing worker pool because its database and
JWKS calls are synchronous. This follows the framework's documented
[dependency execution behavior](https://fastapi.tiangolo.com/async/#dependencies).
JWT verification, issuer/key rules, revocations, active users and persisted roles
are unchanged. The current Supabase changelog was checked; no SDK, hosted Auth or
Supabase configuration change was needed.

## Implementation and files

| File | Change |
|---|---|
| `backend/app/core/workspace_authorization.py` | One fresh dataset-access query for a page; single-dataset callers use the same predicates |
| `backend/app/dataplane/api.py` | Batch dataset authorization for dashboard records; preserve skipped inaccessible records and raw-page pagination |
| `backend/app/dataplane/read_models.py` | Latest scoped events, per-workflow top-ten runs, per-dataset top-100 lineage and batched definitions |
| `backend/app/dataplane/company_api.py` | Replace nested repeated reads in workflows and incidents with the bounded read models |
| `backend/app/core/security.py` | Synchronous identity dependency off the event loop |
| `frontend/src/components/CompanyWorkbench.tsx` | Independent panel loading, 250 ms dictionary debounce, cancellation and separate recoverable load errors |
| `backend/tests/test_company_read_batches.py` | Six real database regression tests for bounds, response semantics, scope, lifecycle, revision ordering and missing definitions |
| `backend/tests/test_auth_concurrency.py` | Held identity lookup does not block an unrelated async request |
| `backend/tests/test_dataset_review_grants.py` | Workflow run status retains a peer's approval, including after grant revocation |
| `backend/tests/test_company_review.py` | Schedule test follows the actual registry pagination instead of assuming fewer than 100 workflows |
| `scripts/benchmark_company_reads.py` | Guarded synthetic API benchmark and restricted-role EXPLAIN plans |
| `scripts/summarize_optimization.py` | Complete response comparison and export of non-secret evidence |
| `frontend/scripts/benchmark-company-browser.mjs` | Real browser request counts, refresh and error-recovery acceptance |
| `scripts/pause_company_verification_schedules.py` | Skip already-disabled schedules before checking their possibly archived source |
| `docs/OPTIMIZATION_AUDIT.md`, `docs/OPTIMIZATION_METRICS.json`, this report | Findings, measurements and verification record |

These are the files touched by this optimization task, not the full list of
pre-existing repository changes.

## Before and after

**Conditions:** same persisted synthetic account/workspace/dataset, 20 workflows,
three completed runs each, ten incidents, 80 workflow/evidence outputs. Five
warm-ups and 25 sequential measured requests per endpoint in separate Python
processes. Every request checks expected statuses, lineage and redaction. The
complete returned JSON objects match before and after for all three endpoints.

FastAPI TestClient executes real ASGI routes against real PostgreSQL with a
NOSUPERUSER/NOBYPASSRLS application role. Timings include auth, database calls,
serialization and client-side assertions; they exclude network latency. Tests
drive synthetic metadata, not a dataset-compute throughput workload.

Docker Desktop on this Windows machine exposed 12 logical CPUs and
5,084,327,936 bytes of VM memory. API and PostgreSQL containers had no separate
CPU/memory limit. Python 3.11.18, FastAPI 0.162.0, SQLAlchemy 2.1.6, psycopg 3.3.7,
PostgreSQL 16; Node 22.23.4, Vite 8.3.6 and Chromium 156.0.8078.79. Other local
services share the VM. The verification worker was stopped during API measurement
and backend tests. Additional synthetic records were added by regression tests
between baseline and final runs; the measured fixture and its responses stayed
identical. Results are local observations, not production capacity estimates.

| Endpoint | SQL round trips/request | p50 ms before → after | p95 ms before → after | p95 reduction | p99 ms before → after |
|---|---:|---:|---:|---:|---:|
| Dashboard | 60 → 11 | 137.13 → 61.94 | 164.19 → 76.45 | 53.4% | 192.97 → 77.47 |
| Workflows | 129 → 12 | 354.27 → 65.64 | 433.86 → 75.91 | 82.5% | 690.76 → 79.43 |
| Incidents | 249 → 13 | 689.91 → 78.56 | 878.26 → 97.50 | 88.9% | 1,027.43 → 105.63 |

Counts are application SQL round trips, not internal statements executed by RLS
functions. With 25 samples, p99 is effectively the slowest observation; this is
not a statistically established production tail-latency estimate.

| Metric | Dashboard before → after | Workflows before → after | Incidents before → after |
|---|---:|---:|---:|
| Median summed SQL call duration, ms/request | 52.785 → 16.669 | 209.132 → 27.000 | 407.865 → 28.541 |
| Client/API process CPU, seconds for 25 requests | 2.859 → 1.323 | 5.662 → 1.150 | 10.957 → 1.504 |
| Sampled process peak RSS, MiB | 652.55 → 651.10 | 653.36 → 651.20 | 659.21 → 653.10 |
| Sequential requests/second | 7.07 → 15.69 | 2.66 → 15.05 | 1.40 → 12.25 |

SQL duration reductions are 68.4%, 87.1% and 93.0%; CPU reductions are 53.7%,
79.7% and 86.3%. RSS reductions are only 0.22%, 0.33% and 0.93%; no substantial
memory improvement is claimed. RSS was sampled every 10 ms for the Python process
hosting both API and test client, not PostgreSQL or total container memory.
Sequential requests/second is the reciprocal of observed request time, not a
concurrent load-test result.

Five final `EXPLAIN (ANALYZE, BUFFERS)` plans under the same restricted role took
0.161–2.152 ms execution time, with memory sorts and zero temporary-block writes.
Existing scope/parent/job indexes were used. This small workload does not justify
adding a production index or predict behavior with millions of historical rows.

**Browser:** one warm-up and five seven-character searches at 75 ms between keys.
All five baseline samples sent dictionary/workflow/policy/incident counts of
7/7/7/7. All five final samples sent 1/0/0/0: **28 → 1 requests, 96.4% fewer**.
Both samples used the corrected auth backend to isolate the frontend comparison.
Latest search, manual refresh, visible failure, successful retry and absence of
uncaught browser errors were verified. The debounce adds up to 250 ms before a
settled search starts.

Production Data Health JS grew from 41,943 to 42,244 bytes; default gzip grew
11,222 → 11,312 bytes (+90). Total JS gzip grew 347,680 → 347,776 bytes (+96).
There is no bundle-size win; the small code increase buys lower request volume
and independent error recovery.

**NOT MEASURED:** React render duration, production page-load/Web Vitals, maximum
concurrent throughput, database/server CPU and total system peak memory, large
dataset processing time, background-job speed, live-provider latency/token cost,
Redis invalidation memory and production-scale history growth. No gains are
claimed for these areas.

## Verification record

Commands below run inside the existing isolated containers, with `/repo` for
Python and `/app` for Node. Backend pytest commands use
`DATAPLANE_ENABLED=false BACKGROUND_WORKER_ENABLED=false`; tests explicitly enable
features within their fixtures. The guarded runner disables local `.env` loading,
removes provider keys, accepts only the synthetic database and migrates head twice.

| Status | Command / check | Result |
|---|---|---|
| PASS | `python scripts/benchmark_company_reads.py --output /verification/optimization-before.json --samples 25` | Baseline with full response fixtures |
| PASS | `python scripts/benchmark_company_reads.py --output /verification/optimization-final.json --samples 25 --explain` | Final timings and restricted-role plans |
| PASS | `python scripts/summarize_optimization.py` | Every full response equal; all benchmark assertions pass |
| FAIL, corrected test assertion | `python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/optimization-full.xml` | 425 passed, 1 failed, 1 skipped; five existing forecasting warnings; 395.95 s. The new missing-definition test incorrectly expected `detail`; actual application error envelope uses `message`. The API correctly returned 404. |
| PASS | `python scripts/run_setup_tests.py backend/tests/test_company_read_batches.py --junitxml=/verification/optimization-batches-final.xml` | All six tests pass after correcting that assertion; 38.19 s. No runtime change followed the full run. |
| PASS | `python scripts/run_setup_tests.py backend/tests/test_auth_concurrency.py --junitxml=/verification/optimization-auth.xml` | Held identity lookup and responsive async request; also passes in the full run |
| PASS | `python scripts/run_setup_tests.py backend/tests/test_company_review.py::test_workflow_manual_review_binary_download_idempotency_and_schedule` | Earlier single-page test assumption corrected; actual pagination and deduplication pass, including in the full run |
| PASS | `npm run lint`, `npm run format:check`, `npm run build` | ESLint, formatting, TypeScript and production build |
| PASS | `node scripts/benchmark-company-browser.mjs before` and `after` | Five samples each; final retry and refresh checks pass |
| PASS | `node scripts/verify-company-browser.mjs` | Two users, explicit dataset grants, independent definition/workflow/output approvals, computed total 35, exported zero delta, owner PDF download, revocation, desktop/mobile and no browser errors |
| NOT RUN / skipped | Optional TLS PostgreSQL fixture | Required fixture is not configured; no TLS verification claimed |

The final status across the full suite and corrective six-test rerun is **426
unique passing tests, one skipped**. This is a consolidated result, not a claim
that a second complete suite invocation ran. The first targeted company run also
had a scheduling test failure caused by its single-page assumption; that is
recorded above and was resolved without changing scheduler behavior.

Local evidence: [full run XML](../reports/repository-maintenance-local/optimization-evidence/full.xml),
[corrective run XML](../reports/repository-maintenance-local/optimization-evidence/batches-final.xml),
[auth concurrency XML](../reports/repository-maintenance-local/optimization-evidence/auth.xml),
and [browser journey](../reports/repository-maintenance-local/optimization-evidence/browser-journey.json).
The XML consolidation was checked programmatically: 426 PASS, one SKIP, zero
unresolved failures. Final backend hashes match the benchmark artifact, and
`git diff --check` passed (existing CRLF conversion notices only).

## Security, compatibility and remaining work

Dataset ownership, active lifecycle and workspace binding are checked explicitly
even on privileged connections. Tenant/workspace/actor predicates and database
RLS remain in place. Reviews intentionally include decisions authored by granted
peers; schedule events remain actor-scoped. Revoked grants do not erase historical
approvals. No mutable permission or approval decision is cached across requests.
Error sanitization, output redaction, immutable versions, download permissions,
job bounds and analytical formulas remain unchanged.

The full regression includes independently expected calculations, forecasts,
lease/retry/cancellation behavior, tenant isolation, revocation and report flows.
The list benchmark is metadata-only and cannot establish new analytical accuracy;
it verifies compatibility of existing list responses. Live hosted Supabase and
paid providers were not exercised.

Remaining limitations: batch query costs still grow with qualifying history;
large-tenant concurrent load needs a representative staging dataset. The audit
middleware and Redis key-collection findings deferred by this first pass are
addressed in [OPTIMIZATION_FOLLOWUP.md](OPTIMIZATION_FOLLOWUP.md). Existing
forecasting warnings and missing TLS fixture remain.
The earlier feature checklist's remaining authoring gaps are unchanged.

**Separate approval before deployment:** production rollout/restart, changes to
database indexes or RLS, pool/worker/resource sizing, shared caches, dependency
upgrades and paid-provider load tests. None is necessary for this source change.
No architecture migration is proposed. Rollback requires reverting only these
task's code hunks; no database rollback is needed. Do not reset the existing dirty
tree. The original three list/UI source files were saved under
`reports/repository-maintenance-local/optimization-baseline/`.

Docker Desktop's VM connection failed during baseline setup and was restarted
using its documented local recovery command. Volumes and configuration were
retained. Application containers recovered automatically; only the relevant
isolated verification stack was explicitly resumed. The test worker was restored
after tests, and three residual synthetic schedules were disabled with immutable
history before the browser journey.
The final isolated API/worker and local application backend/worker/frontend
health checks are healthy; the isolated Vite frontend is running.

## Readiness verdict

**VERIFIED** for this optimization scope: relevant backend regressions, complete
response comparisons, measured performance gains, frontend checks and the real
two-person browser journey passed. The optional TLS fixture and the explicitly
unmeasured workloads remain outside this verdict. Source changes have not been
deployed to production.
