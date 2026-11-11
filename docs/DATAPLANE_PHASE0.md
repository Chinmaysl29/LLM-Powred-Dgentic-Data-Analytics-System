# Data processing layer — Phase 0 audit

Date: 2026-11-08. Status: **audit complete; implementation awaits Phase 0 approval**.

The first bottleneck is canonicalization, before analytical execution. A 21.537 MiB CSV failed at 500,000 rows under a 1 GiB container limit; an 87.420 MiB CSV failed at 2,000,000 rows under a 2 GiB limit. Both are below the current 100 MiB upload cap. The grouped sum completed correctly at every tested size.

These are measured failure points for this synthetic schema and these budgets, **not a universal pandas limit or a measurement of exhausting all host RAM**. The live application remained healthy. No application code, configuration, migrations, dependencies, credentials, user datasets, or production database rows were changed.

## 1. Design rationale and proposed sequence

1. Keep upload streaming, authentication, ownership checks, version selection, and the existing learning systems. Replace the new path's full DataFrame/JSON materialization with bounded conversion and immutable snapshot manifests.
2. Reuse the durable job store and existing dataset-version relationships. Add a separate dataplane worker with process termination on timeout, explicit memory/CPU/spill limits, and fenced publication of artifacts.
3. Establish bounded engine execution and result parity before changing chat routing. Initially route only approved sum/average/grouped metrics; preserve existing routes with the feature disabled.
4. Add semantic definitions, monitoring, approved cleaning, and evidence-linked reports in the supplied phase order. Add company Postgres pushdown later; Spark remains a contract/stub pending measurements.
5. Verify tenant isolation, recovery after crashes, source checksums, numeric correctness, and flag-off compatibility at each applicable phase. Roll back by disabling the new route/worker and reverting only that phase's changes.

This is a design summary, not implementation. The attachment explicitly says: “Start with Phase 0 only” and “Do not write or modify any code until I approve Phase 0.”

### Verified environment and prompt differences

| Item | Observed |
| --- | --- |
| Workspace / branch | C:\data analyst / feature/learning-layer; feature/data-layer not yet created |
| Host physical RAM / logical CPUs | 10,592,444,416 bytes (9.865 GiB) / 12 |
| Docker memory / CPUs | 5,084,336,128 bytes (4.735 GiB) / 12 |
| Live services | backend, frontend, Postgres, Redis, Chroma; all healthy |
| Host ports | backend 8000, frontend 5173, Postgres 5432, Redis 6379, Chroma **8401** |
| Backend tests | **334**, not the prompt's 76 |
| Database driver / revision | psycopg 3.3.7 / 018_selection_policies |
| Installed libraries | pandas 2.3.3; pyarrow 26.0.1; NumPy 2.4.6; SQLAlchemy 2.1.6; FastAPI 0.162.0 |
| Not installed | DuckDB, sqlglot, asyncpg |
| Existing features | durable background jobs, dataset versions, workspace binding, analysis artifacts, learning/adaptive systems |
| Upload / workers | 100 MiB cap; API-embedded background worker enabled, concurrency 1 |

The prompt's 12 GB assumption cannot be used as a Docker execution budget. Existing Compose services do not have a dedicated dataplane memory allocation. A provisional starting point is one 1 GiB worker, a 512 MiB DuckDB engine limit, two threads and concurrency one, subject to measurement and a disk quota. An engine limit is not a whole-process cap.

The prompt's “data layer before learning layer” order no longer matches this repository. Preserve the existing learning/embedding systems, as previously authorized; this project adds no deep-learning, GPU or model-training dependency.

The working tree contains substantial prior work. No reset, stash, branch switch, commit or cleanup of that work occurred. Phase 1 must start by preserving the current tree and database and creating the agreed feature branch.

## 2. Repository map and files

Paths below were inspected at the relevant definitions and callers; this is not a claim of exhaustive review of every module.

| Area / inspected files | Current behavior and implication |
| --- | --- |
| backend/app/api/v1/routes/datasets.py; services/dataset_upload_service.py | Tabular upload awaits canonicalization, metadata, profile, quality, versioning and recommendations inside the request. Documents already use durable indexing. New asynchronous tabular ingestion must not silently change the existing ready-state response contract. |
| services/storage_service.py | Upload reads 1 MiB chunks and enforces the cap. Stores source copies in type-specific raw, legacy raw and dataset-original paths. Dataset UUID paths are not tenant-prefixed. |
| services/dataset_parser_service.py; dataset_json_service.py | Parses the whole table, reads the source again for hashing, creates records and several full JSON representations, writes multiple JSON artifacts, then writes one Parquet file. Conversion to Parquet alone does not make this path bounded. |
| services/tabular_loader.py; dataset_loader.py | Whole CSV/Excel/JSON/Parquet reads. Parquet previews apply head after reading the file. Header detection and financial-number normalization are significant existing semantics. |
| services/metadata_extraction_service.py; data_profiling_service.py; data_quality_service.py | Each has a DataFrame-loading path; upload invokes these sequentially after canonicalization. The benchmark below excludes those additional stages. |
| services/data_retrieval_service.py | Resolves an owned, selected/active version; loads the full file before filtering/sampling. Preserve version pinning and rollback behavior. |
| api/v1/routes/chat.py; services/natural_language_analytics.py | Deterministic analytics loads and computes in threads in the API process. Aggregation copies the DataFrame; ordinary grouped output has no general result-row cap. Preview is limited to 100 rows. |
| services/intent_classification_service.py; schemas/intent.py; workflow_planner_service.py | Existing intent registry and learning-aware planning must remain compatible. Supported intent list is below. |
| services/orchestrator_service.py; agent_registry.py; backend/agents/{data_retrieval_agent,eda_agent,sql_agent}.py | Orchestrator supplies metadata/profile/quality and registers concrete runners; fallback runners also exist. The inspected legacy EDA LLM call uses a findings summary. A universal aggregate-only LLM boundary has not been demonstrated for every route. |
| backend/sql_agent/{sql_generator,sql_guardrails,sql_executor}.py; services/sql_guardrails_service.py | Existing SQL uses sqlparse/regular-expression checks and DataFrame-to-in-memory-SQLite execution. It is not a DuckDB AST/security/resource boundary; some package modules are placeholders. |
| models/{dataset,dataset_version,background_job}.py; core/{authorization,workspace_authorization}.py | Datasets have owner_id; workspace-to-tenant membership and dataset bindings are separate. New snapshots need authorized dataset + workspace + tenant relationships, not an invented datasets.tenant_id. |
| backend/jobs/{manager,persistence,job_worker}.py; app/main.py | Durable claims, retries, idempotency, leases/heartbeats and fencing already exist. Work runs in API lifespan; synchronous handlers use to_thread. Worker CLI exists, but no separate worker Compose service. Threads are not killable timeout boundaries. |
| models/analysis_run.py; services/analysis_run_service.py | Existing analysis run/stage/event/artifact concepts provide useful links for evidence, rather than a second unrelated history system. |
| api/v1/routes/connections.py; backend/connectors | Connection configuration persists a masked password, not a reusable encrypted credential. Company read-only pushdown needs its own verified credential storage, connection restrictions and permission checks. |
| tests/test_analysis_history_and_reports.py; services/report_studio_service.py | Report generation/download and cross-account denial already have regression coverage. Do not assume the prompt's old download defect is still present. |
| services/large_dataset_optimizer.py; backend/data_engineering/benchmark_suite.py | Streaming helpers/benchmarks exist but do not establish the memory bound of the main canonicalization path. Existing tracemalloc figures are not full process RSS. |
| backend/app/core/config.py; backend requirements/lock; Dockerfile; docker-compose.yml; docker-compose.verify.yml | Actual settings, dependency pins, persistent volume setup and isolated test environment inspected. .env was not modified. |
| frontend/package.json; mobile/src/services/api.ts | Frontend scripts verified. Mobile's API base URL is separate from this dataplane task; no mobile change proposed. |

Supported intents from schemas/intent.py:

dataset_overview, eda_analysis, trend_analysis, comparison_analysis, distribution_analysis,
correlation_analysis, ranking_analysis, forecasting, anomaly_detection, dashboard_generation,
report_generation, recommendation_generation, what_if_analysis, sql_query, rag_query,
data_quality, unknown.

Files added in this phase are documentation/evidence only:

- docs/DATAPLANE_PHASE0.md — audit, measured limits, design corrections and approval boundary.
- docs/dataplane-verification/phase0-20261108/REPRODUCE.md — exact commands and inline benchmark harness.
- backend-baseline.xml — full baseline JUnit result in that evidence directory.
- pandas-1g.json and pandas-2g.json — actual measurements, source hashes, results and OOM event deltas.
- verified-summary.json — independently checked aggregate oracles, Parquet metadata and source-checksum results.
- source-hashes.json — SHA-256 provenance for the principal inspected execution paths and lock/config files.
- environment.json — safe environment/version and check metadata, excluding secrets.

## 3. Implementation / patch

**No application implementation or migration was made.** No new flags are active. No dependency was installed, no Docker image rebuilt, and no live container reconfigured. The only executable work was ephemeral baseline/benchmark/validation commands in isolated containers; the full harness is included in REPRODUCE.md.

Raw synthetic inputs and generated artifacts remain in the isolated volume
dataanalyst-dataplane-audit_verify_storage, under:

- /verification/benchmark/phase0-88cc6dd671 — 1 GiB run.
- /verification/benchmark/phase0-878d2cca33 — 2 GiB run.

The application storage volume was not mounted into either benchmark. Network access was disabled. The repository mount and container root filesystem were read-only.

## 4. Tests and exact commands

Backend baseline:

~~~powershell
docker compose -p dataanalyst-dataplane-audit -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/dataplane-phase0-baseline.xml
~~~

The existing setup runner uses an isolated test database and storage and disables external providers. The live database was not used by this suite.

Frontend: npm run typecheck and npm run build, using a scratch copy in a network-disabled container with the current frontend image's node_modules. Full exact wrapper is in REPRODUCE.md; no dist or node_modules files were written into the repository.

Benchmark:

- Deterministic five-column CSV: row_id, unique account_id, four regions, January dates and integer amount_cents.
- Fresh child process for each operation/size; two CPU cores, one numerical-library thread.
- 1 GiB and 2 GiB cgroup limits; swap disabled; 120-second child timeout.
- Materialization calls the actual DatasetJsonService.materialize.
- Analytics calls the actual load_tabular_dataframe and NaturalLanguageAnalyticsService._execute for “sum amount_cents by region”.
- Reported wall times include child startup/imports and the supervisor's post-run source checksum. Input generation and the separate oracle/Parquet validation pass are excluded. These are single runs, not statistical latency percentiles or guaranteed cold disk-cache measurements.
- Successful peak RSS is resource.getrusage; failed-child RSS is sampled from /proc every 25 ms. OOM confirmation uses exit -9 plus cgroup memory.events oom_kill delta = 1.
- RSS and cgroup charged memory are different measures, particularly for shared/file-backed pages; do not treat reported RSS as the cgroup limit itself.
- Successful sum outputs were checked against exact integer oracles; successful Parquet row counts against file metadata; source SHA-256 unchanged in every case.

No new regression tests were authored because this phase changes no application behavior.

## 5. Verification and risk report

### Baseline results

- Backend: **334 passed, 5 warnings in 257.39s**. JUnit: zero failures, errors or skips.
- Warnings: forecasting tests emitted rank-deficient fit, future-return-type, starting-parameter and convergence warnings; no baseline failure.
- Frontend typecheck: exit 0.
- Frontend production build: exit 0; Vite 8.3.6, 2,374 transformed modules, 2.22 seconds.
- All five live services healthy before and after the benchmark.
- Temporary verification Postgres/Redis/Chroma services stopped afterward; their volumes retained.

### Current canonicalization baseline

| Container budget | Rows | CSV MiB | Outcome | Wall seconds | Successful peak RSS MiB | Written artifacts MiB |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| 1 GiB | 100,000 | 4.223 | success | 4.071 | 338.504 | 59.820 |
| 1 GiB | 250,000 | 10.716 | success | 7.857 | 656.488 | 149.737 |
| 1 GiB | 500,000 | 21.537 | OOM killed | 11.111 | — | incomplete |
| 2 GiB | 500,000 | 21.537 | success | 13.065 | 1,102.570 | 299.487 |
| 2 GiB | 1,000,000 | 43.180 | success | 35.913 | 2,052.359 | 598.989 |
| 2 GiB | 2,000,000 | 87.420 | OOM killed | 12.172 | — | incomplete |

The tested success/failure brackets are (250k, 500k] under 1 GiB and (1M, 2M] under 2 GiB, not exact cutoffs. Artifact size excludes the input and the upload service's additional raw copies. At 1M rows, canonicalization writes about 13.9 times the input size.

### Current grouped analytics baseline

| Budget | Rows | Wall seconds | Peak RSS MiB | Exact oracle |
| --- | ---: | ---: | ---: | --- |
| 1 GiB | 100,000 | 2.756 | 188.359 | pass |
| 1 GiB | 250,000 | 2.912 | 214.906 | pass |
| 1 GiB | 500,000 | 3.666 | 267.328 | pass |
| 2 GiB | 500,000 | 3.633 | 267.527 | pass |
| 2 GiB | 1,000,000 | 3.934 | 369.891 | pass |
| 2 GiB | 2,000,000 | 6.091 | 575.910 | pass |

This tests the parser/executor boundary with four output groups. It excludes HTTP upload, database access, profiles/quality, LLMs, concurrent requests, high-cardinality groups and the full SQL/SQLite route. It does not establish a safe upload size, an end-to-end ingestion SLA, or pandas/DuckDB parity. No DuckDB or 10M/100M benchmark was run.

### Risks and required design corrections

| Priority | Finding | Required response |
| --- | --- | --- |
| Critical | The prompt requests pandas fallback on **any** dataplane error. This can bypass denied SQL, authorization and resource gates, or retry a large job in API memory. | Keep flag-off legacy behavior; allow runtime fallback only for explicitly bounded, authorized, compatible requests. Security/resource denials must terminate safely. Agree before routing changes. |
| Critical | Heavy tabular work and background handlers share API process memory; cancellation of a thread does not stop its work. | New dataplane operations run in a separately limited worker with a killable child process, bounded retries and lease-fenced commits. Do not silently change legacy upload contracts. |
| High | Current loaders normalize headers, financial strings, nulls and identifiers. Naive DuckDB inference changes answers. | Version inference decisions; preserve original bytes; parity cases for currency, percent semantics, identifiers with leading zeros, invalid numerics/dates, all-null groups, ordering, rounding and overflow. |
| High | Storage lookup accepts an existing direct path and can search recursively by basename. This is not an authorization or confinement boundary. | New snapshots use server-resolved manifests and canonical tenant/workspace roots with traversal/symlink checks. Never pass arbitrary user paths or broad basename fallback to the new engine. This audit does not claim an exploitable public endpoint was demonstrated. |
| High | Ownership, workspace access and dataset bindings are distinct; jobs run after request-time authorization. | Validate all three relationships and version ownership at enqueue, execution and publication. Two-tenant tests must cover read, evidence, job status, export and cleanup. |
| High | SQL parsing is not execution isolation. Existing guardrails do not prove DuckDB safety. | One parsed statement; explicit dialect; bounded accepted AST; scope-aware tables/columns/CTEs; positive function allowlist; deny file/network/system/extension/write operations. Restrict engine OS privileges and mounts. |
| High | LIMIT caps returned rows, not scan cost, aggregate value size, group cardinality or bytes. | Cap result bytes and rows, reject unbounded collection/string aggregates, set CPU/memory/time/spill-disk budgets and terminate runaway processes. |
| High | Snapshot retries and expired leases can leave partial output or double-publish. | Write staging outputs; record manifests/checkpoints; atomically publish once with lease fencing; never overwrite an existing raw/snapshot artifact. |
| High | Masking a connection password is not encrypted credential persistence or proof of read-only privileges. | Phase 8 needs a credential store, restricted destinations/TLS, least-privilege database identity, read-only transaction and statement timeout; never use the metadata DB as customer analytics fallback. |
| Medium | Evidence contract sketch returns only an Arrow table; query text/hash alone is insufficient for reproducibility. | Record tenant/workspace, dataset/snapshot hash, semantic version, bound parameters, engine/version, result digest, counts and observed execution metrics. Distinguish estimates from actual measurements; do not fabricate monetary costs. |
| Medium | Raw Parquet conversion may coerce original values. | Preserve original upload bytes as immutable evidence; keep inferred/normalized Parquet separately versioned with transformation decisions. |
| Medium | Monitoring lacks business cadence and metric definitions. | Define timezone, grain, late arrivals, minimum history, weekday baselines, zero-MAD handling and deduplication. Findings are investigation alerts, not business conclusions. |
| Medium | An aggregate-only boundary is not proven across all existing LLM routes. | Add a typed bounded evidence/aggregate payload and provider-boundary tests for the new path; preserve authenticated UI previews separately. |
| Medium | The prompt describes report downloads as broken, but regression coverage passes. | Reuse the working report path; add evidence linkage and reproduce any actual download defect before changing it. |

DuckDB's official security guidance treats untrusted SQL as code and recommends isolation; settings alone are insufficient. [DuckDB security](https://duckdb.org/docs/2.0/operations_manual/securing_duckdb/overview)

Spilling is useful but not universal: blocking operators and some aggregate states can still exhaust resources. [DuckDB workload tuning](https://duckdb.org/docs/2.0/guides/performance/how_to_tune_workloads)

The prompt's comment that parse_one raises on multi-statement input is not true of the current SQLGlot documentation: it describes a Block containing multiple statements. The sketch's Select-root check can reject that Block, but explicit statement-count and adversarial tests remain necessary. Neither sqlglot nor DuckDB is installed here, so pin and test selected versions before implementation; current online docs are not proof of future installed behavior. [SQLGlot API](https://sqlglot.com/sqlglot.html)

### Concrete Phase 1 proposal for approval

- Create feature/data-layer after preserving existing work and backing up the metadata database.
- Add typed configuration under backend/app/dataplane and additive example environment keys; DATAPLANE_ENABLED defaults false.
- Reuse background_jobs, its workspace/owner idempotency and leases. Avoid a duplicate generic jobs table. Add only genuinely missing dataplane metadata tables, if required; no existing-column changes.
- Add an optional Compose dataplane worker with explicit resources, health reporting and persistent isolated scratch/output paths; it claims only its registered job kinds.
- Add hard process timeouts, retry classification and checkpoint/publication contracts for new dataplane jobs. Existing handlers and API contracts remain intact in the first phase.
- Test flag-off startup/behavior, job ownership/idempotency, timeout cleanup, stale leases and restart recovery. For any new migrations: dump first, then upgrade/downgrade/upgrade in an isolated database.
- Run the full 334-test baseline and frontend checks after Phase 1. Do not activate new analytical routing in this phase.

Two decisions to carry forward: approve reusing the existing systems within the real Docker budget; approve the narrower fallback policy before routing implementation. Initial business metric definitions are still required before Phase 4. They are not needed for Phase 1.

## 6. Rollback / handoff

There is no application rollback or database downgrade to perform for Phase 0. Production configuration and images were unchanged.

The exact command used to stop the temporary test services was:

~~~powershell
docker compose -p dataanalyst-dataplane-audit -f docker-compose.verify.yml stop
~~~

Benchmark containers used --rm. The temporary stopped evidence-copy container was removed. Synthetic test volumes and all report artifacts were deliberately retained. Do not run a global cleanup or reset the working tree.

Historical status at the audit: Phase 1 was unstarted pending approval. The user subsequently authorized completion of all phases with the existing systems and Docker budget. See [DATAPLANE_IMPLEMENTATION.md](DATAPLANE_IMPLEMENTATION.md) for the deployed result and verification evidence.

