# Performance audit — 10 November 2026

This is the audit for the new architecture/performance specification, separate
from the earlier eight-feature implementation. The existing dirty working tree
is retained. No repository AGENTS.md was found. Production Compose, credentials
and application databases are outside this change's mutation scope.

## Architecture and baseline

React 19/TypeScript/Vite calls the FastAPI application factory and v1 routes.
SQLAlchemy sessions and PostgreSQL are authoritative for identities, scoped
metadata, immutable evidence and durable jobs. Redis is optional cache/notification
infrastructure. Chroma supplies candidates; canonical PostgreSQL checks determine
eligibility. The dataplane runs bounded DuckDB jobs in a separate killable child,
one heavy job at a time. Legacy analysis stages already offload synchronous work.
Route chunks, bounded aggregate results, immutable versions and lease-fenced
publication already exist and do not justify architectural replacement.

The running isolated test image reports Python 3.11.18, FastAPI 0.162.0,
Pydantic 2.14.2, SQLAlchemy 2.1.6, psycopg 3.3.7, Redis client 5.3.1,
Chroma 0.6.3, pandas 2.3.3, numpy 2.4.6, DuckDB 2.0.0 and Arrow 26.0.1.
Docker sees 12 logical CPUs and 5,084,327,936 bytes of host memory. These are the
actual verification environment values, not a promise about deployment capacity.
Existing application and isolated test containers share this machine; benchmarks
are local comparisons, not production SLAs.

## Prioritized findings before edits

| Priority / severity | Location | Observed problem and evidence | Impact | Intervention | Risk and verification |
|---|---|---|---|---|---|
| 1 / High | `dataplane/company_api.py:workflows` | One jobs query and two history queries per workflow; another history query per completed output | Page cost grows with workflows × runs | Bounded batch retrieval with per-workflow top-ten jobs and latest events | Keep actor/workspace/RLS predicates, review revision ordering and per-parent limits; compare complete response objects and query counts under restricted roles |
| 2 / High | `dataplane/company_api.py:incidents` | Each incident reloads the same latest 100 outputs; each workflow output reloads its definition | Repeated JSON hydration and nested database round trips | Fetch required lineage once per bounded dataset page, and definitions/events in batches | Preserve 100-per-dataset limit, missing-definition errors and impact semantics; compare complete response objects and foreign/archived access |
| 3 / Medium | `dataplane/api.py:dashboard` | Up to 50 repeated dataset authorization SELECTs after the scoped artifact query | Avoidable polling load | One bounded authorization query for page dataset IDs | Retain explicit owner/binding/status checks even with RLS; test deletion, archive and rebinding |
| 4 / Medium | `CompanyWorkbench.tsx` | Search/offset changes run one effect loading dictionary, workflows, policy and incidents | Four requests per keystroke and unrelated rerenders | Separate search from companion panels; debounce only dictionary search | Keep cancellation, fresh authorization and manual refresh; measure actual browser request counts and verify final search/error states |
| 5 / Medium | `database/redis.py:delete_matching` | Entire SCAN result is collected before a single variadic DELETE | Memory and command size grow with namespace size | Measure bounded deletion batches before selecting a change | Preserve namespace, deletion count and visible transport errors; benchmark dedicated synthetic keys only |

These are code-confirmed repeated-work findings. Baseline and after measurements
will be retained separately. No latency or memory gain is claimed before running
the corresponding measurement.

## Decisions

- Reuse the existing queue, database, renderer and result contracts.
- Prefer request-local batch data to shared caching of grants, revocation state,
  or approvals; those values require fresh authorization.
- Do not change RLS policies or add speculative indexes. Inspect representative
  read plans first. Retain the existing process and memory budgets.
- Do not introduce strategies, factories or reflection for short conditionals.
- No live-provider optimization is justified without measured provider workloads,
  cost authorization and independently checked output fixtures.
- New feature authoring from the old master prompt is not part of this performance
  refactor; existing limitations remain documented in EIGHT_FEATURE_CHECKPOINT.md.

## Additional finding during verification

The original browser search generated 28 requests for seven keystrokes. During
early runs the API stopped answering, PostgreSQL showed 15 idle transactions,
and requests timed out. `get_current_user` was an `async def` containing only
synchronous JWT/JWKS and SQLAlchemy operations. This is a high-priority event-loop
blocking risk under connection pressure. It is now a normal FastAPI dependency,
executed on the framework's bounded worker pool. Token validation, revocation,
provisioning and persisted-role rules are unchanged. A regression test holds an
identity lookup and proves an unrelated asynchronous request can finish before
the lookup is released. The original 28-request search then completed; the
frontend optimization subsequently reduced it to one request. This establishes
responsiveness for those checks, not maximum production concurrency.

The first pass deferred Redis SCAN/DELETE and audit middleware concurrency.
The user subsequently selected completion of those remaining optimization
findings. Both are now measured and implemented; see OPTIMIZATION_FOLLOWUP.md
and OPTIMIZATION_FOLLOWUP_METRICS.json for their verification status and tradeoffs.
No shared-cache architecture change or production index is justified by this work.

## Follow-up findings and interventions

| Severity | Location | Evidence before change | Intervention | Compatibility check |
|---|---|---|---|---|
| High | `middleware/audit.py` | In a deliberately constrained one-connection pool, 12 successful requests persisted zero audit events; the middleware opened another session before request cleanup. A controlled 50 ms sink blocked event-loop ticks for up to 55.17 ms. | Await inner ASGI application cleanup, then persist using the existing bounded worker pool with a thread-owned session | Preserve bodies, headers, actor/request metadata, background work, exclusions and best-effort errors; verify real pool saturation with full application middleware |
| Medium | `database/redis.py:delete_matching` | 10,000 matching keys used about 2.97 MB peak Python traced allocation before one large DELETE | Accumulate and delete at most 200 keys per command, summing Redis's actual deletion counts | Exact namespace, empty sets, duplicate SCAN keys, partial transport failures and neighboring keys |
