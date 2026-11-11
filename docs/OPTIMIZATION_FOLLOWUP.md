# Remaining optimization findings — 10 November 2026

The user selected **Finish remaining optimization findings** after the first
optimization pass. This continuation addresses the two documented code findings:
unbounded Redis key accumulation and synchronous audit persistence. The earlier
eight-feature authoring backlog and production deployment are outside this scope.

## Findings, changes and architecture

The audit middleware previously requested its own SQLAlchemy connection before
the request's yield-based database dependency had released its connection. A
deliberately constrained one-connection pool reproduced successful responses with
zero persisted audit events. Audit writes also executed synchronously on the
event loop. This was a correctness and responsiveness problem, not merely an
opportunity to reduce query time.

`backend/app/middleware/audit.py` now uses a small ASGI wrapper. It forwards
response messages unchanged, waits for the inner application and dependency
cleanup, and awaits audit persistence through Starlette's existing bounded worker
pool. The audit session is created, used and closed on that worker. No separate
queue, detached tasks, new connection pool or resource-limit changes are added.
Streaming responses and existing background tasks are retained. The approach
uses Starlette's documented [ASGI middleware](https://starlette.dev/middleware/)
and [thread-pool execution](https://starlette.dev/threadpool/).

`backend/app/database/redis.py` now sends at most 200 keys in each DELETE rather
than retaining the entire matching namespace. It sums actual deletion counts,
including when SCAN repeats keys, and retains visible RedisConnectionError
failures. SCAN's count remains a hint, not a strict page-size bound, as documented
by [Redis](https://redis.io/docs/latest/commands/scan/). The application accumulator
and each DELETE are bounded to 200 keys; no absolute server/client memory ceiling
is claimed for unusually large keys or Redis scan pages.

The existing FastAPI/PostgreSQL/Redis architecture, authentication, RLS, owner
checks, analytical formulas, durable jobs and frontend are unchanged. No schema,
index, dependency, credentials, production configuration or production database
changes were made.

## Measurements

[Raw samples and source hashes](OPTIMIZATION_FOLLOWUP_METRICS.json) contain the
before/final results. All data is synthetic in the existing isolated test stack.
The environment remains Docker Desktop with 12 logical CPUs and approximately
4.74 GiB VM RAM, Python 3.11.18, PostgreSQL 16 and Redis 7. Other local services
share this machine; these are bounded reproduction results, not production SLAs.

Redis uses 10,000 keys under a fresh random benchmark-only prefix, two warm-ups
and ten measured iterations. Each iteration asserts exactly 10,000 deletions,
zero remaining matching keys, and an unchanged neighboring key. TTLs bound
fixture lifetime and the script cleans only its own prefix. Allocation is measured
with Python tracemalloc around deletion, excluding seeding; this is not Redis
server memory, process RSS or whole-system peak memory.

| Metric | Before | After | Change |
|---|---:|---:|---:|
| Median traced peak Python allocation | 2,968,588 bytes | 300,767 bytes | 89.87% lower |
| Median invalidation duration | 457.87 ms | 490.35 ms | 7.09% slower |
| Maximum keys accumulated/passed per DELETE on this workload | 10,000 | 200 | Bounded independently of namespace cardinality |

The time tradeoff is explicit: a 10,000-key namespace now needs 50 small DELETEs
instead of one large DELETE. This change addresses growing memory and command
size; it is not reported as a latency improvement. Invalidation remains
non-snapshot under concurrent writes. Earlier batches can succeed before a later
transport failure; callers must not treat this as an atomic multi-key transaction.

The audit benchmark uses real PostgreSQL, one connection, no overflow, a 150 ms
checkout timeout, two warm-ups and ten measured requests. This pool deliberately
reproduces nested checkout and is not a recommended deployment pool size. Timings
cover the whole ASGI invocation, including the awaited audit attempt.

| Metric | Before | After |
|---|---:|---:|
| Persisted events / successful requests, including warm-ups | 0 / 12 | 12 / 12 |
| Median request plus audit-attempt duration | 156.94 ms | 14.99 ms |
| Maximum event-loop tick gap with a controlled 50 ms audit sink | 55.17 ms | 4.72 ms |

The latency improvement in that reproduction is 90.45%; its main result is
restored audit persistence. The event-loop experiment intentionally substitutes
a 50 ms synchronous sink and samples 1 ms timer ticks over ten requests. It proves
responsiveness under controlled blocking; it is not a measured production DB
write latency. A separate real-database regression submits eight concurrent
requests through a two-connection pool and checks all eight persisted audit events
and zero checked-out connections afterward, both with minimal middleware and the
full application stack.

An initial cold-connection test timed out once while benchmarking was also
running; an isolated repeat passed. The saturation test now establishes both
connections before submitting concurrent requests, isolating session reuse from
first-connect work. Its 500 ms checkout timeout and all assertions were retained.
Cold-start capacity is not claimed as verified. Final benchmarks ran without
another verification workload running concurrently.

## Contracts and limitations

The middleware remains best-effort: failed audit storage does not change an
already successful response. The ASGI invocation waits for persistence, but the
response body can reach the client before the event commits. A client immediately
querying audit history may briefly precede that write. Process crashes or
disconnect cancellation can still lose best-effort events; transactional or
durable audit guarantees require separately designed persistence. No such guarantee
is claimed or silently introduced. Transactional company review/history writes
are separate and unchanged.

Actor, action, resource, request ID, IP, user agent, status and event details retain
their existing persisted semantics. Failed responses, metrics/audit endpoints,
lifespan and WebSocket traffic retain their previous exclusions. No shared
authorization cache, new data exposure or cross-tenant cache key is introduced.

Large-tenant production capacity, live-provider costs, cold-start throughput,
React rendering, dataset-compute speed, TLS and maximum global concurrency remain
outside these bounded findings. They were not measured, and no gains are claimed.
No remaining confirmed code finding from the optimization audit is deferred;
deployment-scale validation still needs representative workload and environment.

## Changed files and verification

- `backend/app/database/redis.py`: bounded invalidation.
- `backend/app/middleware/audit.py`: cleanup ordering and worker-thread persistence.
- `backend/tests/test_remaining_optimizations.py`: eleven regression cases covering
  key bounds, duplicates, partial errors, real pool saturation, event-loop progress,
  streaming/background cleanup, metadata, thread-owned sessions and exclusions.
- `scripts/benchmark_remaining_optimizations.py`: guarded real-service measurements.
- This report, `OPTIMIZATION_AUDIT.md`, `OPTIMIZATION_REPORT.md` and
  `OPTIMIZATION_FOLLOWUP_METRICS.json`: current findings and evidence.

| Status | Command | Result |
|---|---|---|
| PASS | `python scripts/benchmark_remaining_optimizations.py --output /verification/remaining-before.json` | Baseline reproduced both findings |
| PASS | `python scripts/benchmark_remaining_optimizations.py --output /verification/remaining-final.json` | Exact Redis deletion/neighbor assertions and 12 persisted audit events |
| PASS | `python scripts/run_setup_tests.py backend/tests/test_remaining_optimizations.py --junitxml=/verification/remaining-targeted-final.xml` | 11 passed in 16.41 seconds |
| PASS | `python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/remaining-full.xml` | 437 passed, 1 skipped, five existing forecasting warnings; 384.87 seconds |
| PASS | Isolated API readiness after reload | HTTP 200 |
| PASS | `node scripts/verify-company-browser.mjs` | Two-user dataset grants and approvals, expected total 35 and zero comparison delta, owner PDF download, revocation, desktop/mobile, no uncaught browser errors |
| PASS | Post-browser persisted audit check | Recent synthetic owner/reviewer events present: 153 and 36 respectively in the checked five-minute window |

Python runs in the existing isolated API container with `/repo` as working
directory. Test runs explicitly set `DATAPLANE_ENABLED=false` and
`BACKGROUND_WORKER_ENABLED=false`; fixtures enable features as needed. The guarded
runner refuses the application database and disables `.env` loading. The isolated
worker is paused during full-suite job tests. Frontend sources did not change;
their prior lint/build results remain recorded in the original report.

Local evidence: [full suite](../reports/repository-maintenance-local/optimization-followup/full.xml),
[focused suite](../reports/repository-maintenance-local/optimization-followup/targeted.xml),
[baseline](../reports/repository-maintenance-local/optimization-followup/before.json),
and [final measurements](../reports/repository-maintenance-local/optimization-followup/after.json).
The [live browser result](../reports/repository-maintenance-local/optimization-followup/browser.json)
and [persisted audit check](../reports/repository-maintenance-local/optimization-followup/live-audit.json)
are retained separately.
The skipped case requires the optional `DATAPLANE_TEST_CA` fixture. The five
forecasting warnings are unchanged. This is a single complete passing suite,
superseding the earlier report's consolidated full-plus-corrective test count.

## Readiness

**VERIFIED.** Both remaining confirmed optimization findings are implemented and
measured. All 437 backend tests passed in one complete run, with one optional TLS
fixture skipped; focused concurrency/streaming checks and the live two-user
browser journey passed. Both runtime files match the benchmark source hashes,
and scoped diff/whitespace checks pass.

Only the isolated API was reloaded. The isolated worker was restored after tests;
one residual synthetic schedule was disabled with retained history before that
restart. Final isolated API/worker and existing local application backend/worker/
frontend health checks are healthy. Credentials and deployment settings are
unchanged. The changes have not been deployed to production.

Production rollout, paid load tests and any change to audit durability or
infrastructure require a separate concrete deployment decision. Neither code
change needs a database migration to deploy or roll back.
