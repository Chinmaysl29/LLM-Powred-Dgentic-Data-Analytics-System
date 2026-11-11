# Phase 7: provider bandit and chart selector

## 1. Design rationale

This phase adds two NumPy policies that select options without calculating business metrics. Existing embeddings, adaptive systems, provider implementations, prompts and deterministic analytics remain in place. `LEARNING_ENABLED` remains false in the live application; `.env` was not edited.

The chart policy is an averaged perceptron with decay and a conservative margin. It may change only `chart_type` from bar to line for an already validated, chronological, single-series monthly trend of 2–50 points. Explicit chart requests, categorical/ranked/multigroup results, mismatched rows and nonfinite values keep existing behavior. The new React renderer uses the exact returned values and proportional month spacing, preserving missing-month gaps, negative values and zero. It includes an accessible value table. It does not sort, sample or aggregate data.

The provider policy uses reviewed empirical rewards and epsilon-greedy selection (`epsilon=0.05`). Only providers with at least five reviewed training outcomes, all correct, can be selected. Each reward is `correctness - 0.1*min(latency_ms/30000,1) - 0.1*min(cost_usd/0.01,1)`. These constants are policy penalties, not quoted provider prices. Training requires explicit correctness labels and measured latency/cost; a successful HTTP response is never treated as correctness. New reviewed evidence requires staging and evaluating a new version; there is no request-time training.

Provider selection is limited to intent classification in authenticated `/intent/classify` and chat's existing nonanalytics classification path. It wraps the existing classifier with request-local provider instances and does not mutate the shared provider cache or global configuration. The configured provider set must exactly match reviewed model pins. All model identities are checked before inference; drift or setup failure returns to the original provider chain. The selected provider is tried first with the same messages, followed by the remaining configured providers on transport failures. Existing invalid-input exceptions retain their behavior. Adaptive frozen-provider workflows and streaming remain unchanged.

Snapshots use the existing `learner_weights` table with separate learner names. Migration 018 creates only `selection_events`, with forced row security and scoped runtime shadow inserts. Privileged lifecycle operations also require an active owner/admin reviewer. Each approval binds tenant, workspace, owner, dataset version/schema, model bytes and runtime source. One version per learner per tenant may be active; other dataset scopes fall back. Manifest splits have disjoint scenario groups, at least 10 training and 30 golden cases. Promotion requires matching shadow evidence, 100% golden correctness and strict improvement over baseline and current policy. Every possible exploratory provider must be correct on every golden case. Concurrent releases, revoked authorization, changed source and audit failures reject promotion atomically.

Runtime reads are bounded by two worker slots, a 2.5-second caller timeout and database connection/statement/lock limits. Provider preflight has two slots and a five-second caller timeout. Exceptions return to existing behavior. Raw questions and dataset values are absent from the new audit detail. Existing provider transport timeouts are retained.

## 2. Files read and changed

Read the master build prompt, prior phase reports, Docker/verification configuration, migration runner, model registry, chat/intent routes and callers, `backend/app/llm/provider.py`, `intent_classification_service.py`, `natural_language_analytics.py`, existing column lifecycle/store/runtime/table, failure-memory scope/contract, learner tables, integration fixtures and phase tests, `AnalysisPage.tsx`, chart types, frontend scripts/package configuration and Dockerfiles. Applied the local `supabase-postgres-best-practices` skill and its row-security guidance. Existing files were read before modification.

| Changed file | Purpose |
| --- | --- |
| `backend/app/api/v1/routes/chat.py` | Guarded classifier and chart selection hooks |
| `backend/app/api/v1/routes/intent.py` | Guarded scoped classifier hook |
| `backend/app/models/__init__.py` | Register the new audit table |
| `frontend/src/pages/app/AnalysisPage.tsx` | Render verified line charts |
| `backend/app/learning/selection_models.py` | NumPy policies and strict outcome validation |
| `backend/app/learning/selection_contract.py` | Reviewed manifests, training and golden evaluation |
| `backend/app/learning/selection_table.py` | Audit metadata |
| `backend/app/learning/selection_store.py` | Scoped snapshots and source attestations |
| `backend/app/learning/selection_lifecycle.py` | Stage, promote and rollback transactions |
| `backend/app/learning/selection_runtime.py` | Bounded runtime selection and chart guards |
| `backend/app/learning/selection_provider.py` | Request-local provider ordering |
| `migrations/versions/018_selection_policies.py` | Additive audit migration and downgrade |
| `frontend/src/components/analytics/VerifiedTrendChart.tsx` | Exact-value line renderer |
| `frontend/scripts/verify-trend-chart.cjs` | Actual React component rendering checks |
| `backend/tests/test_perceptron_selection.py` | 26 focused tests |
| `scripts/perceptron_selection.py` | Operator lifecycle CLI |
| `scripts/verify_selection_migration.py` | Isolated migration roundtrip |
| `scripts/verify_selection_persistence.py` | Synthetic restart verification |

## 3. Complete diff and operator workflow

[Complete runnable diff](perceptron-verification/phase7.patch) contains all four modified and fourteen new implementation/test files against the exact pre-phase working tree. The reverse-patch check passed. Earlier changes remain unstaged and preserved; no commit or Git identity was created.

Manifests have exactly `format: 1`, `kind`, `models` and `cases`, with 40–500 cases. Chart models are `{}`; chart cases contain `id`, `group`, `split`, `context` and `expected` (`bar` or `line`). Context contains `temporal`, `points`, `dimensions`, `ranking` and `explicit`. Provider models map two or three configured providers (`groq`, `gemini`, `openai`) to exact reviewed model IDs; cases contain `id`, `group`, `split` and paired `outcomes` for every pinned provider. Each outcome contains `correct`, `latency_ms` and `cost_usd`. Synthetic complete examples are in `reviewed_cases()` in the focused tests. They are not user-reviewed production benchmarks.

Review a frozen local manifest and its canonical SHA-256: `sha256(json.dumps(manifest, sort_keys=True, allow_nan=False).encode()).hexdigest()`. Use the same digest throughout. Set the following PowerShell variables to the actual reviewed IDs, paths, kind (`chart` or `provider`) and versions; files must be accessible inside the container:

```powershell
docker compose exec backend python scripts/perceptron_selection.py stage --kind $kind --reviewer-id $reviewerId --dataset-id $datasetId --dataset-version $datasetVersion --manifest $manifestPath --manifest-sha256 $manifestDigest --reviewed
docker compose exec backend python scripts/perceptron_selection.py evaluate --kind $kind --reviewer-id $reviewerId --dataset-id $datasetId --dataset-version $datasetVersion --version $candidateVersion --manifest $manifestPath --manifest-sha256 $manifestDigest --reviewed
docker compose exec backend python scripts/perceptron_selection.py status --kind $kind --reviewer-id $reviewerId --dataset-id $datasetId --dataset-version $datasetVersion
docker compose exec backend python scripts/perceptron_selection.py promote --kind $kind --reviewer-id $reviewerId --dataset-id $datasetId --dataset-version $datasetVersion --version $candidateVersion --expected-version $activeVersion --manifest $manifestPath --manifest-sha256 $manifestDigest --reviewed
```

Staging writes an inactive snapshot. With learning enabled, eligible requests record shadow selections before promotion can succeed. Promotion independently reruns evaluation and checks the expected active version. Gate failure exits 1; invalid authorization/provenance exits 2. No production model was staged or promoted during this phase.

## 4. Exact verification commands

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml up -d --wait --wait-timeout 120 postgres redis chromadb
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase7-baseline.xml
docker exec dataanalyst-perceptron-phase1-postgres-1 pg_dump -U setup -d analyst_setup_test -Fc -f /tmp/before-perceptron-phase7.dump
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_selection_migration.py
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests/test_perceptron_selection.py --junitxml=/verification/phase7-focused.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase7-final.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_selection_persistence.py seed
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml restart postgres
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_selection_persistence.py check
```

Frontend baseline used the scratch-copy typecheck/build command documented in Phase 5. Final frontend verification also renders the actual new React component:

```powershell
@'
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const destination = '/tmp/audit';
const excluded = new Set(['node_modules', 'dist', '.git', '.ui-review']);
fs.cpSync('/source', destination, { recursive: true, filter: entry => !path.relative('/source', entry).split(path.sep).some(part => excluded.has(part)) });
fs.cpSync('/app/node_modules', path.join(destination, 'node_modules'), { recursive: true });
for (const task of ['typecheck', 'build']) {
 const result = spawnSync('npm', ['run', task], { cwd: destination, stdio: 'inherit' });
 if (result.status !== 0) process.exit(result.status ?? 1);
}
const check = spawnSync('node', ['scripts/verify-trend-chart.cjs'], { cwd: destination, stdio: 'inherit' });
process.exit(check.status ?? 1);
'@ | docker run --rm -i --network none --read-only --tmpfs /tmp:rw,exec,size=768m --mount 'type=bind,source=C:\data analyst\frontend,target=/source,readonly' --env npm_config_cache=/tmp/npm-cache --entrypoint node dataanalyst-frontend:latest -
```

Saved spreadsheet regression, offline with unchanged source files and manifest:

```powershell
docker run --rm --network none --read-only --tmpfs /tmp:rw,exec,size=768m --mount 'type=bind,source=C:\data analyst,target=/repo,readonly' --mount 'type=bind,source=C:\data analyst\storage\learning\golden,target=/golden' --workdir /tmp --env PYTHONPATH=/repo --env PYTHONDONTWRITEBYTECODE=1 --env OPENBLAS_NUM_THREADS=1 --entrypoint python dataanalyst-backend:latest /repo/scripts/perceptron_golden.py evaluate --root /repo --manifest /golden/financial-v1/manifest.json --manifest-sha256 69957d10cc13c662987ada53093d3b67d4b767d640fe348d90b26027b7d1476d --report /golden/financial-v1/phase7-seed-evaluation.json
```

Choose a new report filename when rerunning; overwriting evidence is refused.

## 5. Actual verification

Baseline: **282 passed**, five existing forecasting warnings, **225.69 seconds**. Final: **308 passed**, the same five warnings, **241.79 seconds**. All baseline tests remain passing. Focused coverage: **26 passed in 48.02 seconds**. Evidence: [baseline XML](perceptron-verification/phase7-baseline.xml), [focused XML](perceptron-verification/phase7-focused.xml), [final XML](perceptron-verification/phase7-final.xml).

Coverage includes real authenticated chat and intent endpoints, exact preservation of chart values/KPIs/answers, invalid manifests/models, split leakage, unsafe chart shapes, provider fallback and model drift, disabled flag and database outages, tenant/version/schema isolation, revoked membership, source/weight tampering, runtime write denial, concurrent staging/releases, audit rollback, CLI disable, golden rejection of an incorrect exploratory arm and absence of request-time training. Provider transports and measured outcomes are synthetic; no paid provider calls were made and no real speed or cost improvement is claimed.

Frontend typecheck/build passed before and after: Vite **2.07 seconds** baseline and **1.28 seconds** final. React rendering checks passed for exact negative/zero values, month-gap spacing, accessible output, unchanged input, flat series and invalid-series rejection. An initial React title warning was fixed and the final check asserts zero console errors. This is component rendering verification, not a browser end-to-end test.

Migration upgrade 018 / downgrade 017 / upgrade 018 passed; **all 60 existing tables** retained columns, keys, indexes, policies and row counts. Saved spreadsheet regression remains **50/50 answers passed**, with baseline and existing router seed both **33/34 intents**. That seed remains rejected (`quality_gate_passed=false`, expected exit 1); no promotion was performed.

Pre-phase source copies, OpenAPI snapshot and database dumps are saved under `C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase7-20261107`. The live dump is **450,978 bytes**, and `pg_restore --list` validated its archive contents. No live restore was performed.

Persistence verification passed: both synthetic policies and their scoped approvals selected valid options before and after restarting isolated PostgreSQL, using a fresh process for each check. No external provider calls were made, and the live PostgreSQL service was not restarted. All 282 baseline test identities were also checked against the final XML, confirming that none disappeared from the suite.

Both Docker images were rebuilt and saved: backend manifest `sha256:b324491a5354dc418b31fcb6e28cb2f000fe8ab9eeec3215b3ce4c55ed914a1c`, frontend manifest `sha256:05e3afc0433e48e2d5475bd9a4395efc3b9715b896c884171c769a7739dd6252`. Live migration to `018_selection_policies` succeeded. Commands:

```powershell
docker compose build backend frontend
docker compose run --rm migrate python scripts/migrate.py upgrade head
docker compose up -d --no-deps --wait --wait-timeout 120 backend frontend
```

All five live services are healthy, with `unless-stopped` restart policies and existing named data volumes preserved. `/api/v1/health/ready` returned `ready`; schema, PostgreSQL, Redis and Chroma checks passed. The complete parsed OpenAPI document is identical before and after: **222 paths and 249 operations**. Live schema is `018_selection_policies`, `LEARNING_ENABLED=False`, and all selection/resolver events, learner weights, active weights, feedback, mistakes, shadow predictions, router releases and memory links remain zero. No live model or correction was created. `.env` and original dataset files were not changed. [Service evidence](perceptron-verification/phase7-services.json) records health, images, restart policies and named volumes.

The newly rebuilt frontend image was separately rechecked with the same scratch-copy command: typecheck, build (**1.69 seconds**) and actual React component verification all passed before container replacement. The existing frontend dependency volume was retained; Compose reported that it predates its ownership metadata. Its health check passed after restart.

Isolated verification services were stopped with `docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml stop postgres redis chromadb`, retaining their containers and volumes. During the frontend image rebuild, `npm ci` reported 14 dependency audit findings (10 moderate, 4 high) against the unchanged lockfile. Dependency upgrades were not part of this phase.

Limitations: model initialization during provider preflight may add latency, including provider metadata resolution. Actual provider performance needs a user-reviewed benchmark with configured credentials and exact model IDs before promotion. Source-bound approvals must be renewed after relevant code changes; this phase changes chat/intent source also covered by earlier learners' fingerprints. Live weights were zero before this phase, so no active model was invalidated. The new provider policy does not change every LLM call in the application.

## 6. Rollback

Disable either policy in one command while retaining version history:

```powershell
docker compose exec backend python scripts/perceptron_selection.py rollback --kind $kind --reviewer-id $reviewerId --dataset-id $datasetId --dataset-version $datasetVersion --version 0 --expected-version $activeVersion
```

Use `chart` or `provider` for `$kind`. A nonzero rollback target must be a previously approved compatible version; stale expected versions are rejected. Shadow observations may continue while the flag is on, but disabled weights do not select options.

For complete phase removal, retain a database backup and reviewed manifests, disable active selection policies, then run each command only after the preceding command succeeds:

```powershell
git apply --reverse --check docs/perceptron-verification/phase7.patch
docker compose stop backend frontend
docker compose run --rm migrate python scripts/migrate.py downgrade 017_column_resolver
git apply --reverse docs/perceptron-verification/phase7.patch
docker compose build backend frontend
docker compose up -d --no-deps --wait --wait-timeout 120 backend frontend
```

The downgrade removes only the new audit table. Existing weight history remains recoverable and earlier code ignores the separate selection learners. Preserve datasets and Docker volumes. Stop after Phase 7; Phase 8, the read-only learning dashboard, awaits the user's proceed instruction.
