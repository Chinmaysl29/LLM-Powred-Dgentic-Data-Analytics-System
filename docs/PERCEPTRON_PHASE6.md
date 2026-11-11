# Phase 6: reviewed column/metric selection

Date: 2026-11-07 (Asia/Calcutta). Branch: `feature/learning-layer`.

## 1. Design and scope

1. Add a NumPy averaged perceptron that ranks eligible physical numeric columns and an explicit abstention option. It selects the metric column; pandas continues to compute every answer, KPI and chart value.
2. Fit from human-reviewed question-to-column examples scoped to the original owner, tenant, workspace, dataset version and schema. Store inference weights under the separate `column_metric_resolver` learner in the existing weights table; never update shared global weights from a user's examples.
3. Stage inactive snapshots, observe them in shadow mode, then recompute a disjoint golden evaluation before promotion. Require all held-out choices correct and strict improvement over both the parser and any active resolver. Approval binds the manifest, model, scope and runtime source hashes. Concurrent changes invalidate promotion; activation and its audit write commit together.
4. Preserve explicit columns, multiple-column ambiguity, conversation context, filters, unsupported operations, date safeguards and all other clarification reasons. Only the existing single missing-numeric-measure clarification can be resolved. Identifiers, booleans and date columns are ineligible. Unknown vocabulary and low margins abstain.
5. Keep flag-off behavior and failure fallback unchanged. Roll back a resolver version with one CLI command; removing the phase uses the tested additive migration downgrade and complete reverse patch.

The chat path has physical-column selection, while verified business definitions live in the existing learning workflow. This phase integrates with physical metric selection. It does not introduce formula execution, infer accounting definitions, alter the glossary, or change the verified business-definition workflow. Existing embedding, adaptive and PyTorch systems are preserved. New model math uses NumPy; pandas is used for schema dtype checks and the existing executor.

Limits: one active resolver snapshot per tenant, bound to one owner's dataset version/schema; other datasets use the original parser. Training is an explicit operator action, not automatic interpretation of errors as labels. Vocabulary, question features, candidates and payloads are bounded. Questions longer than 64 lexical tokens bypass the learner rather than being partially interpreted. Retrieval has two concurrent slots and bounded DB connect/statement/lock timeouts; it runs in the analytics executor's existing worker thread. No model was trained or promoted using unreviewed live user data. The hashed vocabulary is not encryption and does not establish business meaning by itself.

## 2. Files and reading

Read the master prompt and previous phase reports; natural-language analytics and its chat/golden/verified-learning callers; semantic business layer and adaptive interpretation; analytics/planner request contracts; dataset retrieval, version models and metadata; authorization; existing perceptron, feature extraction, shadow, release and lifecycle modules; model registration; migrations 013–016 and migration verification; Docker configuration; integration fixtures and existing tests. Applied `supabase-postgres-best-practices` for the new audit table, RLS and short release transactions.

| File | Purpose |
| --- | --- |
| `backend/app/learning/column_ranker.py` | Variable-candidate averaged perceptron, finite bounds, margins, hashed vocabulary |
| `backend/app/learning/column_contract.py` | Eligible numeric measures, clarification guards, reviewed splits and evaluator |
| `backend/app/learning/column_table.py` | Resolver lifecycle and shadow audit metadata |
| `backend/app/learning/column_store.py` | Scoped snapshots, integrity checks and source-bound attestations |
| `backend/app/learning/column_lifecycle.py` | Authorized training, promotion, version locking and rollback |
| `backend/app/learning/column_runtime.py` | Bounded fail-open shadow/live selection |
| `backend/app/services/natural_language_analytics.py` | Optional internal resolution hook before unchanged calculations |
| `backend/app/api/v1/routes/chat.py` | Supply the authenticated owner's resolver |
| `backend/app/models/__init__.py` | Register the new audit table |
| `migrations/versions/017_column_resolver.py` | Add only `resolver_events`; no existing schema/policy changes |
| `scripts/perceptron_columns.py` | Operator CLI |
| `scripts/verify_column_resolver_migration.py` | Isolated migration roundtrip and existing-table comparison |
| `scripts/verify_column_resolver_persistence.py` | Synthetic database restart verification |
| `backend/tests/test_perceptron_columns.py` | 22 focused tests |

## 3. Complete code and operator workflow

[Complete runnable diff](perceptron-verification/phase6.patch) contains all 14 files against the exact pre-phase working tree. Changes are additive and unstaged. No public route, request field or response field is added. No `.env` value is edited.

A reviewed manifest has `format: 1`, `schema: {columns, dtypes}`, and `cases`. Every case has exactly `question`, `expected` (eligible column name or null for clarification), `split` (`train` or `golden`), and `group`. Requirements: at least 10 training and 30 golden cases, at least five golden abstentions, no duplicate normalized questions, and disjoint scenario-group names across splits. There is a maximum of 500 total cases and 512 hashed vocabulary entries. The synthetic complete example is `reviewed_cases()` in the focused test file; its labels are synthetic and must not be presented as user-reviewed production labels.

The manifest SHA-256 is calculated over `json.dumps(manifest, sort_keys=True, allow_nan=False).encode()`, matching `backend.app.learning.memory_contract.digest`. Freeze and review the file and its digest before staging; promotion must use that same digest. Files passed to the CLI must be accessible inside the backend container. Assign the PowerShell variables below to the actual reviewed IDs, version, path and digest:

```powershell
docker compose exec backend python scripts/perceptron_columns.py stage --reviewer-id $reviewerId --dataset-id $datasetId --dataset-version $datasetVersion --manifest $manifestPath --manifest-sha256 $manifestDigest --reviewed
docker compose exec backend python scripts/perceptron_columns.py evaluate --reviewer-id $reviewerId --dataset-id $datasetId --dataset-version $datasetVersion --version $candidateVersion --manifest $manifestPath --manifest-sha256 $manifestDigest --reviewed
docker compose exec backend python scripts/perceptron_columns.py status --reviewer-id $reviewerId --dataset-id $datasetId --dataset-version $datasetVersion
docker compose exec backend python scripts/perceptron_columns.py promote --reviewer-id $reviewerId --dataset-id $datasetId --dataset-version $datasetVersion --version $candidateVersion --expected-version $activeVersion --manifest $manifestPath --manifest-sha256 $manifestDigest --reviewed
```

Staging fits only training rows and persists an inactive snapshot. With learning enabled, eligible questions create shadow observations without changing responses. Promotion requires a matching shadow observation and reruns evaluation itself; it does not trust an external report. A refused quality gate exits 1; invalid authorization/provenance exits 2. Lifecycle commands require a privileged database role plus an active tenant owner/admin reviewer. Application roles may append only their own scoped shadow observations, not release approvals or weight changes. Raw questions, dataframe values and column labels are absent from persisted weights/audit detail; manifests remain operator-managed local files.

## 4. Tests and exact commands

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml up -d --wait --wait-timeout 120 postgres redis chromadb
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase6-baseline.xml
docker exec dataanalyst-perceptron-phase1-postgres-1 pg_dump -U setup -d analyst_setup_test -Fc -f /tmp/before-perceptron-phase6.dump
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_column_resolver_migration.py
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests/test_perceptron_columns.py --junitxml=/verification/phase6-focused.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase6-final.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_column_resolver_persistence.py seed
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml restart postgres
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_column_resolver_persistence.py check
```

Frontend checks use the exact read-only, network-disabled scratch-copy Docker command in [Phase 5, section 4](PERCEPTRON_PHASE5.md#4-tests-and-exact-commands), before and after changes. It runs `npm run typecheck` and `npm run build` with the installed dependency image.

The saved user-approved spreadsheets were rechecked offline without changing sources, labels or manifest:

```powershell
docker run --rm --network none --read-only --tmpfs /tmp:rw,exec,size=768m --mount 'type=bind,source=C:\data analyst,target=/repo,readonly' --mount 'type=bind,source=C:\data analyst\storage\learning\golden,target=/golden' --workdir /tmp --env PYTHONPATH=/repo --env PYTHONDONTWRITEBYTECODE=1 --env OPENBLAS_NUM_THREADS=1 --entrypoint python dataanalyst-backend:latest /repo/scripts/perceptron_golden.py evaluate --root /repo --manifest /golden/financial-v1/manifest.json --manifest-sha256 69957d10cc13c662987ada53093d3b67d4b767d640fe348d90b26027b7d1476d --report /golden/financial-v1/phase6-seed-evaluation.json
```

Choose a new report filename when rerunning; the command refuses to overwrite evidence.

## 5. Actual verification

Baseline: **260 passed**, five existing forecasting warnings, **179.71 seconds**. Frontend typecheck/build passed before and after, Vite **1.98 seconds** and **1.55 seconds**.

The initial new-model run correctly refused promotion at 27/30 synthetic golden cases: aggregation words caused three guesses for a novel term. Eight new tests relying on promotion failed, eight passed. A bounded vocabulary guard was added so unfamiliar content terms abstain; labels and the 100% gate were unchanged. The corrected run passed 16/16. After adding release-race and transaction checks, the focused suite passed **22/22 in 40.56 seconds**.

The reviewed synthetic model scores **30/30** held-out column choices versus the unchanged parser's **20/30**. This is a synthetic demonstration, not measured production accuracy. Real authenticated chat selected the reviewed `amount` column and the unchanged executor returned total **1180**, matching its KPI and chart. Tests also cover invalid candidates/models, split leakage, explicit/ambiguous/filter/context preservation, wrong tenant/owner/version/schema, revoked membership, source/weight tampering, flag-off and database outage fallback, runtime write denial, concurrent staging, release/revocation during evaluation, audit failure rollback, failed-gate rejection, CLI disable and no request-time training.

Migration upgrade/downgrade/upgrade passed; **all 59 existing tables** retained columns, keys, indexes, policies and row counts. Reverse-patch check passed. Test database backup and pre-phase source copies are in `C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase6-20261107`.

Saved spreadsheet regression: **50/50 answers passed**. The existing router seed and keyword baseline still score **33/34 intents**; the seed remains rejected (`quality_gate_passed=false`, expected exit 1). This check does not demonstrate learned resolver accuracy on real spreadsheets. Its private report is `storage/learning/golden/financial-v1/phase6-seed-evaluation.json`.

The first full post-change suite passed **282 tests**, five existing forecasting warnings, **203.36 seconds**. Final review added the explicit 64-token rejection and its regression assertion. The final full rerun passed **282 tests**, five existing warnings, **202.22 seconds**. All 260 baseline tests remain passing. Evidence: [baseline XML](perceptron-verification/phase6-baseline.xml), [focused XML](perceptron-verification/phase6-focused.xml), [final XML](perceptron-verification/phase6-final.xml).

Persistence verification passed: an approved synthetic resolver selected `amount` before and after restarting the isolated PostgreSQL container, with a fresh process for each check. Both its weights and source-bound approval survived the restart. The live PostgreSQL service was not restarted.

Before live migration, `ai_analyst` was backed up to `C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase6-20261107\before-perceptron-phase6.dump` (**421,782 bytes**). `pg_restore --list` succeeded; no live restore was performed. The backend image was rebuilt and saved as `dataanalyst-backend:latest`, image manifest `sha256:5db10cfb99e518aadde875a2d4124a7330c1eefd84365998118aa03689a82653`.

Deployment commands:

```powershell
docker compose build backend
docker compose run --rm migrate python scripts/migrate.py upgrade head
docker compose up -d --no-deps --wait --wait-timeout 120 backend
```

All five live containers are healthy. `/api/v1/health/ready` returned `ready` with schema, PostgreSQL, Redis and Chroma healthy. The complete parsed OpenAPI document is identical before/after deployment: **222 paths, 249 operations**. Live schema is `017_column_resolver`; `LEARNING_ENABLED=False`. Resolver events, all learner weights, active weights, feedback, mistakes, memory links, router releases and shadow predictions are all zero. No live model or correction was created. `.env` and original dataset files were not changed.

The isolated verification services were stopped without deleting their containers, data or volumes:

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml stop postgres redis chromadb
```

## 6. Rollback

To disable this resolver and return to the original parser, while preserving version history:

```powershell
docker compose exec backend python scripts/perceptron_columns.py rollback --reviewer-id $reviewerId --dataset-id $datasetId --dataset-version $datasetVersion --version 0 --expected-version $activeVersion
```

A nonzero rollback target must be a previously promoted compatible version. Stale expected versions are rejected. Shadow observation may continue while the feature flag is on, but disabled weights do not select columns.

For complete phase removal, first retain a database backup and any reviewed manifests. Disable active resolver versions before removing the audit table, then run each command only after its predecessor succeeds:

```powershell
git apply --reverse --check docs/perceptron-verification/phase6.patch
docker compose stop backend
docker compose run --rm migrate python scripts/migrate.py downgrade 016_failure_memory
git apply --reverse docs/perceptron-verification/phase6.patch
docker compose build backend
docker compose up -d --no-deps --wait --wait-timeout 120 backend
```

The downgrade removes only `resolver_events`. Existing weights remain as recoverable data; earlier application versions ignore the separate resolver learner. Do not delete datasets or volumes. Earlier phases and unrelated working-tree changes remain preserved. No Git identity or commit is created. Stop after Phase 6; Phase 7 awaits the user's proceed instruction.
