# Verified Learning Supervisor

Implementation and local verification, 4 November 2026. This is verified memory and evaluation, **not weight training**. The application starts with optional collection and memory application disabled. No production database or hosted account was migrated or changed during verification.

## Architecture actually implemented

The active application is `backend/app/main.py` → `backend/app/api/v1/routes/router.py` and `frontend/src/App.tsx`. The integration extends the persisted seven-stage run in `backend/app/services/analysis_run_service.py`, rather than the alternative in-memory orchestrators.

| Concern | Implementation |
| --- | --- |
| Strict contracts and legal transitions | `backend/app/schemas/learning.py`: TaskSpec, TransformationPlan, StageResult, ValidationResult, LessonCandidate/Version, EvaluationManifest, budgets, feedback and labels |
| Current-run loop and registry | `backend/app/services/learning_engine.py`: interpretation checks, source-preserving profile, approved descriptive aggregation, targeted repair, independent reconciliation |
| Scoped learning authority | `backend/app/services/learning_supervisor.py`: authenticated binding, definitions, feedback, extraction, independent verification, snapshots, retrieval, invalidation, durable cleanup |
| Release loop | `backend/app/services/learning_evaluation.py`: frozen paired evaluation, case separation, metrics, declared gates and limited release |
| Persistence | `backend/app/models/learning.py`; migration `011_verified_learning` and frozen `migrations/learning_schema_v1.sql` |
| Queue/outbox | Existing `background_jobs` table and `backend/jobs/persistence.py`: SQL claims, leases, heartbeats, fenced publication and bounded attempts |
| API | `backend/app/api/v1/routes/learning.py`; existing `/orchestrator/runs` now accepts an optional strict task contract and budget |
| UI | `/verified-learning`, `frontend/src/pages/app/VerifiedLearningPage.tsx`, typed `frontend/src/services/learningService.ts`; linked from navigation and Analysis |

Installed versions were inspected, not inferred from README claims: FastAPI 0.162.0, Pydantic 2.14.2, SQLAlchemy 2.1.6, Alembic 1.20.1, pandas 2.3.3, Redis client 5.3.1, Chroma client/server 0.6.3, Groq SDK 0.37.1; React 19.2.8, TypeScript 6.0.3, Vite 8.2.1. PostgreSQL is 16; the exact server build is captured in `docs/learning-verification/environment.json`.

The existing natural-language parser is reused for legacy unstructured requests. Material ambiguity returns a waiting state. The UI supplies a complete explicit contract. Revenue, sales, profit and churn terminology requires a selected, authorized business definition. Definitions store immutable content/version/hash, owner, source, scope and expected examples. Invalidation is separate from changing content; changes require a new version.

Runtime policy hashes and computation-dependency versions are captured at process import, included in frozen bundles/stage evidence/results, and checked before evaluation/release and resumed execution. Restart processes after code changes. A changed policy or dependency cannot silently reuse an older passing evaluation.

### Supported execution boundary

This first coherent executor supports one pinned tabular dataset, one measure, sum/mean/min/max/count, up to three explicit grouping dimensions, explicit equality/membership exclusions, and a formatted, timezone-bound half-open date range. The UI exposes one grouping dimension; the API supports three. `__records__` is an explicit record-count measure. `value` is reserved for the result measure and cannot also be a grouping name.

Source CSV/TSV representations are preserved before financial/date heuristics. This is a new option on the existing retrieval service, not an independent storage system. JSON, Excel and Parquet use their declared representations. Missing values are rejected or explicitly excluded; never imputed as zero. Duplicate-looking rows and extremes are retained. Input/schema fingerprints are pinned across stages. Raw files are not overwritten. Limits are 50 MB input, 500,000 rows, 200 columns and 1,000 output groups; some typed formats must be decoded before their row count is known. Deadlines are cooperative around bounded approved operations, not an OS process sandbox.

The one initial technical lesson operator is **lossless canonical decimal parsing**. It rejects currency symbols, ambiguous separators, exponents in text, leading-zero ambiguity, nonfinite values and unsupported precision. Numeric inputs are limited to 18 significant/integer digits and eight fractional places. Decimal arithmetic uses 28 significant digits; nonterminating means are rounded at that precision. JSON represents nonintegral results as decimal strings to preserve precision through TypeScript.

The supervisor does not dispatch generated SQL, generated Python, joins, forecasting or fitted preprocessing. These requests abstain instead of reaching the legacy unconstrained execution paths. A join-cardinality preflight and a training-split/feature-availability validator are supplied and tested, but are **not evidence that the separate legacy SQL or forecasting workflows are secured or leakage-free**. Supporting those workflows requires database-enforced read roles/object/function allowlists or a constrained code worker, plus explicit forecasting/model/data contracts. No such unsafe executor was added to the API process.

Charts, numeric claim cells and the downloadable JSON report use the same hashed validated result. Numeric narrative text is generated from a fixed template and checked; unsupported causal statements cannot be inserted into a verified claim. Existing conversational reports/PDF exports remain a separate workflow and do not acquire supervisor verification labels automatically. Supervised evidence exports are JSON, not a new PDF renderer.

## Three bounded loops

1. **Current run:** queued → running → execute/check → at most two total repair attempts → recheck → succeeded, waiting-for-input, failed or cancelled. Partial is part of the contract for future stage integrations. The default deadline is 120 seconds, anchored to the original run, including restarts. Budgets can be reduced per request. Defaults are proposed operating limits, not measured optima. Provider is explicitly `none`, with zero calls/tokens/provider cost; unsupported provider requests cannot silently spend usage.
2. **Experience:** completion or structured feedback commits extraction intent in the same transaction → existing asynchronous worker drafts a narrow candidate → authorized review runs independent positive/counterexample checks → verified → active. No recursive extraction/evaluation chain exists.
3. **Release:** freeze references and cutoff → asynchronous paired comparison → inspect declared gates → manager-only stable allocation of at most 10% → monitor or rollback. Ordinary scoped lessons follow verification and applicability under the released policy. They do not mutate global prompts/models. Every live run freezes its own compatible reference snapshot. Evaluations always use their explicit frozen bundle. No API permits arbitrary global prompt/model policy editing; such a code/configuration change needs a new evaluated release.

Equivalent actions without a matching committed replay reservation stop with `NO_PROGRESS`. Repair budgets are reserved durably before the pure effect. After a crash the worker may reconstruct that same transformation from the same input fingerprint without consuming another attempt. Completed stage publications are skipped; attempt histories remain separate. Auth failures are terminal and cannot use the transport retry path. Transient dependency retries are separate, explicit and bounded by the existing durable job attempt limit (default three); there is no provider retry loop in the deterministic executor.

## Authorization, retrieval and persistence

Every API and worker binds `get_current_user`/job owner to active tenant/workspace membership before schema, memory, files or labels are accessed. Dataset ownership and workspace binding remain required. Lesson review, definitions, labels, evaluation, controls and rollback require `admin`/`owner`, enforced server-side. Run evidence, feedback and exports also require the run's owning account.

Migration 011 adds twelve scoped tables for run evidence/attempts, feedback, lessons/revisions, verification, definitions, labels, frozen bundles, evaluations, controls and policy audit. Foreign keys and scoped uniqueness protect lineage and event/job/feedback extraction deduplication. Frozen case/bundle/audit/revision/verification evidence has database update/delete triggers. Current lesson status is separate from immutable revisions and content hashes. Feedback comments are bounded and common credential/email patterns are redacted; comments never enter lessons or execution. All five feedback categories are retained. Only supported calculation corrections can produce technical candidates; other feedback is not treated as a numeric label or silently converted into a domain/preference lesson. Authenticated preference learning beyond collecting feedback is outside this operator's scope.

PostgreSQL is authoritative. Retrieval filters workspace, technical lesson type, lifecycle, schema fingerprint, task type, measure, business-definition versions, live source, verification evidence, activation time and cutoff before loading structured correction metadata. Eligibility is rechecked before use and publication. Revocation/expiry/source invalidation override snapshots. Contradictory corrections are excluded. Retrieval is bounded to five references and 4,096 serialized UTF-8 bytes (a conservative byte bound, not a tokenizer estimate). Similarity/confidence scores are not fabricated. No cross-tenant template sharing, retrieval cache or lesson vector index is enabled, so no stale cache/vector copy can override PostgreSQL. An optional Chroma lesson index is unnecessary for this bounded deployment.

Optional memory reads run inside a savepoint. Failure degrades observably to the validated baseline; authorization and mandatory result persistence do not degrade. Never bypass a failed membership or mandatory validator because memory is unavailable.

RLS is enabled and forced on all new tables. Request/worker binding sets transaction-local `app.actor_id` and `app.workspace_id`; missing or mismatched context returns no rows. Application-level capability checks remain necessary. PostgreSQL superusers bypass RLS even with FORCE: use separate non-superuser, non-BYPASSRLS application and worker credentials. Verification actually executes under `learning_verify_app` and `learning_verify_worker`, not just a superuser pretending to filter rows. The test-only administrator grants fixtures and switches to those roles on distinct connections. Membership context variables are supplied only by authenticated server code, never request bodies. RLS is defense in depth for these new tables, not a claim that all legacy tables have RLS.

`infrastructure/learning_role_grants.sql` documents the additional grants for **existing** reviewed application/worker roles. It does not create login passwords or deploy credentials. The development Compose app still uses its pre-existing PostgreSQL superuser; do not use that credential arrangement in a deployment that relies on RLS.

## API and UI use

Open **Verified Learning** from the sidebar or Analysis. Choose an authorized workspace and an owned dataset already bound to it. Enter its version, objective, measure, units, grouping and missing-value policy. Business definitions fill explicit metric/filter settings. Source timezone controls date localization; the UI's date-bound inputs are explicitly UTC. Start a run; its URL preserves the run/workspace on refresh. Checks distinguish task meaning, data quality, execution and answer evidence. Download is available only after the entire run succeeds and its result hash matches.

Managers can enable collection in Controls. A validated representation repair creates an asynchronous candidate. In Lessons, inspect conditions, exceptions, before/after correction, provenance, schema/definition scope and evidence; supply a review reason to verify, activate, reject or revoke. “Verified lesson saved” means the displayed bounded checks passed, not universal applicability. Rejected candidates remain deduplicated.

In Evaluation, register independent references against the configured task. Keep scenario groups and datasets separated across development/calibration/final. Labels are immutable and remain outside executor inputs. Freeze a candidate, select final cases and declare gates before running. A final set cannot be reused for changed gates or a changed candidate after its results have been exposed; identical frozen repeats are permitted. The default gate needs 30 independent domain-reviewed final scenarios, zero correctness regression/harmful applications, latency at most 1.5× baseline, zero extra provider cost and measured benefit. These performance/sample defaults are proposals to evaluate, not universal guarantees. Synthetic cases do not count toward trusted production evidence. Authorization, mandatory correctness, no unsupported verified claim and predictive-workflow exclusion are hard gates.

Routes under `/api/v1/learning`:

| Method | Route | Capability |
| --- | --- | --- |
| GET | `/controls`, `/runs`, `/runs/{id}`, `/lessons`, `/lessons/{id}`, `/definitions` | scoped read; owned runs |
| POST | `/runs/{id}/feedback` | owned run + write + collection enabled; idempotency key |
| GET | `/runs/{id}/report` | owned completed run, live dataset, hash check, private/no-store |
| POST | `/lessons/{id}/review` | manage; expected current lifecycle state |
| POST | `/definitions`, `/definitions/{id}/invalidate` | manage; immutable versioned definition |
| POST/GET | `/bundles`, `/cases`, `/evaluations` | manage; evaluation POST is 202 with idempotency |
| GET | `/evaluations/{id}`, `/monitor` | manage |
| PUT | `/controls` | manage; optimistic generation; disabled/collection/shadow |
| POST | `/release`, `/rollback` | manage; evaluated gates/optimistic generation |

Workspace-scoped collection routes require `?workspace_id=<uuid>`. Lists use `limit` and `offset`, returning `items` and `next_offset`; definitions are bounded to 100 versions. Run-specific scope comes from the authorized run, not a client workspace claim. The server's `/docs` and `/openapi.json` expose request schemas. Structured errors use existing `message`, `error_code`, `request_id`; invalid required contracts return 422. UI has loading, empty, connection failure, denied capability and saved/resumed progress states.

## Reproducible local/test verification

Prerequisite: existing backend/frontend images and the devtools image from `docs/DEVELOPMENT_SETUP.md`. All commands below use a separate Compose project and `analyst_setup_test`, with disposable synthetic storage. The verification script refuses other database names/users/environments and disables providers. The optional migration round trip **deletes supervisor test evidence in that dedicated test database**; never substitute a real database.

```powershell
docker compose -p analyst-learning-final -f docker-compose.verify.yml up -d postgres redis chromadb
docker compose -p analyst-learning-final -f docker-compose.verify.yml run --name analyst-learning-verifier runner python scripts/run_learning_verification.py --migration-roundtrip
docker compose -p analyst-learning-final -f docker-compose.verify.yml run --rm runner python scripts/capture_learning_fixtures.py
docker cp analyst-learning-verifier:/verification/learning-evidence ./docs/learning-verification
docker compose exec -T frontend npm run build
docker compose exec -T frontend npx eslint src/pages/app/VerifiedLearningPage.tsx src/services/learningService.ts
```

Use an unused container name on subsequent runs, or `run --rm` when evidence need not be copied from that container. The named verification volume also retains evidence. The script records the environment, schema, JUnit results and a synthetic paired manifest/results. It runs the original 47 regression checks plus supervisor tests. It drives real workers explicitly under their database role; legacy test clients' in-process worker is disabled to avoid racing test claims.

Real browser journey with a synthetic local password identity (no API response mocking):

```powershell
docker volume create dataanalyst_dev_browser_cache
docker compose -p analyst-learning-final -f docker-compose.verify.yml -f docker-compose.learning-verify.yml run --rm frontend-verify npm ci --no-audit --no-fund
docker compose -p analyst-learning-final -f docker-compose.verify.yml -f docker-compose.learning-verify.yml build browser
docker compose -p analyst-learning-final -f docker-compose.verify.yml -f docker-compose.learning-verify.yml up -d api frontend-verify
docker compose -p analyst-learning-final -f docker-compose.verify.yml run --rm runner python scripts/seed_learning_browser.py
docker compose -p analyst-learning-final -f docker-compose.verify.yml -f docker-compose.learning-verify.yml run --rm browser
docker cp analyst-learning-final-api-1:/verification/learning-evidence/browser ./docs/learning-verification/browser
docker compose -p analyst-learning-final -f docker-compose.verify.yml restart postgres api
docker compose -p analyst-learning-final -f docker-compose.verify.yml run --rm runner python scripts/verify_learning_persistence.py
```

Synthetic browser account credentials stay in the isolated volume and are not copied to documentation. Screenshots/reports contain only synthetic data. Hosted Supabase login is a separate untested path. `scripts/verify_setup_journey.py` supplies a trusted fixture definition for its revenue run; it continues testing the separate conversational PDF/report journey.

Stop the isolated API before rerunning tests so its background worker cannot race the tests' explicit lease claims. The browser image installs the installed Playwright version's Linux dependencies; it is separate from application images.

To test the standard local app after an appropriate local backup, apply `alembic upgrade head` using its **local** configuration, then restart backend/worker and use `/verified-learning`. No such application-database migration was performed by this task. A deployment requires reviewed credentials, role grants and an explicit deployment action; merely finding credentials does not authorize deployment.

## Recovery, retention, revocation and rollback

- Restart the existing worker (`python -m backend.jobs.job_worker`) or API with `BACKGROUND_WORKER_ENABLED=true`. For a separately operated worker, set that variable false on the API. Committed queue intent survives Redis/API restarts. Leases recover abandoned deliveries within the existing attempt limit. Publication is fenced and idempotent; computation can occur more than once. This is at-least-once delivery, not exactly-once execution.
- `/learning/monitor` exposes failed extraction/evaluation/cleanup jobs and policy audit. Inspect `background_jobs.error_code`, attempt and lease state with scoped administration. Retry only transient eligible jobs via `PersistentJobStore.retry`; after the bounded limit, fix the cause and submit a new idempotent request. Permission failures must be resolved through ownership/membership and a newly authorized request, not an automatic retry.
- Cancelling an in-flight run fences later stage publication. Waiting runs preserve their evidence; changing an already executed task requires a new run. Per-run deadline and consumed repair budget do not reset with a worker restart or retry.
- Revoke a lesson through its review action. Definition invalidation revokes dependent lessons. Dataset deletion first tombstones the source, revokes dependent lessons and commits a physical-cleanup job atomically. All owned dataset reads and exports deny the tombstone immediately. Cleanup replays safely; existing document vectors are deleted through the document store for document sources. No supervisor vector index exists. Existing storage deletion **archives a recovery copy** according to the existing data-lake policy; it is not an irreversible erasure promise. Purging those archives requires the separately authorized data-retention process.
- Invalidating a lesson in an active frozen bundle suspends application to shadow immediately. Every application rechecks live policy/eligibility, even if its run snapshot is older. Expired lessons are ineligible without waiting for a status sweeper. A manager can record the explicit expired lifecycle transition.
- Rollback atomically stops application (shadow, 0%), swaps the previous/active bundle references, increments generation and records audit. It does not immediately apply an older potentially stale bundle. Re-evaluate before another limited release. Mandatory invariant failures are observable; they never produce a verified answer.
- Candidates expire after 90 days as a proposed default. No existing organization retention/erasure schedule was found; collection therefore starts disabled and must be enabled under an approved local policy. Existing run/report evidence retention remains unchanged. Feedback redaction and source revocation are immediate, but immutable history is not automatically erased. An authorized retention operator must first disable collection, cancel jobs, invalidate affected sources/lessons and remove source artifacts/archives; a privileged, reviewed retention migration may then remove dependent immutable evidence in FK order. Application/worker roles cannot disable the append-only triggers. Do not use the test downgrade as a production retention tool.
- Stop only verification services when finished: `docker compose -p analyst-learning-final -f docker-compose.verify.yml -f docker-compose.learning-verify.yml stop`. Do not use `down -v` against application volumes. Synthetic verification volumes may be retained for audit or removed in a separately named cleanup.

## Measured results and limitations

Fresh pre-change baseline: **47 passed in 26.32 seconds**. Supervisor checks include contracts, ambiguity, missing data, ambiguous dates/currency, legitimate extreme/duplicate-looking records, cancelled sales/refunds, joins, forecast leakage preflight, wrong chart/narrative values, no provider dependency, schema mismatch, scoped retrieval, cutoff/expiry/revocation, malicious feedback, unauthorized review, real RLS roles, crash/replay, repair-budget exhaustion, optional-memory failure, export integrity, deletion and rollback.

Final combined run: **75 passed in 36.43 seconds**; fresh migration/head compatibility and upgrade/downgrade/re-upgrade passed. Frontend production build, targeted ESLint, targeted Ruff and new-file Prettier checks passed. The real local-auth browser journey passed **12 checks**, including refresh, scoped review, report download, rollback, a 390px viewport and no uncaught runtime errors. The separate live upload/chart/seven-stage/conversational PDF journey passed with total 2,100 and a 23,640-byte one-page PDF. These are synthetic local acceptance checks, not production acceptance.

Evidence: [environment](learning-verification/environment.json), [JUnit results](learning-verification/pytest.xml), [paired manifest](learning-verification/synthetic-manifest.json), [paired results](learning-verification/synthetic-results.json), [browser checks](learning-verification/browser/browser-results.json), [analysis screenshot](learning-verification/browser/analysis-evidence.png), [lesson review](learning-verification/browser/lesson-review.png), [verified JSON report](learning-verification/browser/verified-report.json). Package-wide pre-existing lint/style findings described in the setup report were not bulk-fixed.

The [synthetic fixture bundle](learning-verification/synthetic-fixtures.json) includes source/held-out CSV bytes, immutable gold/task contracts, the business definition and frozen lesson/bundle contents. `scripts/capture_learning_fixtures.py` regenerated the known inputs and independently reproduced both stored baseline result hashes. The [restart receipt](learning-verification/persistence.json) confirms the identical 6,104-byte supervised report survived a real isolated PostgreSQL/API restart. The existing conversational PDF also survived with identical bytes.

Two directly blocking baseline fixes are separate from learning: the hosted Supabase client now initializes lazily so the existing local-auth fallback can start without hosted credentials, and validation errors omit non-JSON exception context instead of turning model-level contract errors into HTTP 500. The schema regression check now follows the actual Alembic head instead of hard-coding revisions 009/010. These are engineering corrections, not memory-driven improvement.

The checked-in synthetic comparison uses two distinct held-out datasets/scenarios, frozen memory and identical validators/tools/code in both arms. Baseline and candidate both score **2/2**; correctness delta **0**, useful/harmful correctness-changing applications **0/0**. This demonstrates scoped memory use and recovery, **not an accuracy improvement**. Release remains blocked for insufficient independent trusted evidence and no measured benefit. Latency, denominators and zero provider usage are in the machine-readable result; infrastructure cost is not measured. Ordinary source-preservation/validator corrections are baseline engineering changes, not learning gains.

No independent production label set, calibration-fitting set or untouched calibration-test set was supplied. Numeric confidence, Brier score, reliability bins and error/coverage curves are explicitly unavailable rather than fabricated. Label collection/split/evaluation interfaces are present; no calibrator is fitted or deployed. Forecast intervals are not generated by this descriptive feature.

Production domain definitions and the required independent held-out scenarios are external inputs that cannot be invented. The supported technical correction is deliberately narrow. Additional technical/preference/domain/dataset-fact operators require their own independent verifier, ownership/applicability contracts and tests. No production improvement, arbitrary SQL/Python isolation, complete legacy-workflow security, calibrated probabilities, universal semantic correctness or permanent self-improvement is claimed.

Future fine-tuning is a separate authorization and evidence gate: choose a trainable provider/model (SDK presence or an inference key does not imply training support), review data rights/privacy, deduplicate high-quality examples, define target behavior, freeze held-out evaluation, allocate training resources, version training/data/model artifacts, run regression/isolation checks, confirm deployment support and keep a rollback model. First demonstrate an advantage over better definitions, prompts, validators and memory. No weights were trained in this implementation.

## Change inventory and checks not run

New runtime files are the learning schemas/models/API, `learning_engine.py`, `learning_supervisor.py`, `learning_evaluation.py`, the frozen migration/SQL, and the VerifiedLearning page/service/styles. Existing integration changes touch the analysis-run API/service, dataset deletion/ownership/repository/retrieval, model/router registries, app/standalone worker registration, worker enablement configuration, safe validation errors, frontend routing/navigation/Analysis link and lazy hosted-auth initialization. No new package dependency was introduced by this feature.

New verification files are the two supervisor test modules, `run_learning_verification.py`, `capture_learning_fixtures.py`, `seed_learning_browser.py`, `verify_learning_persistence.py`, the browser runner/journey/config, the learning verification Compose override and browser Dockerfile. The existing setup journey gained an explicit trusted revenue fixture contract, and the existing schema-preflight assertion now follows the migration head. CI/CD test jobs disable the in-process worker because tests drive the real durable worker explicitly; only their existing named ephemeral databases are allowed by the integration test guard. Workflow/Compose YAML parsed successfully. Remote GitHub CI jobs were **not** run from this workspace.

Unrelated pre-existing setup, dependencies, Docker/editor changes and old lint findings were preserved. No production deployment, hosted Supabase login, paid provider analysis, production business-definition certification, SQL/code sandbox acceptance, predictive-model evaluation, numeric calibration fit or weight training was performed. Remaining capability boundaries and exact missing external evidence are stated above; no placeholder endpoint claims those capabilities are complete.
