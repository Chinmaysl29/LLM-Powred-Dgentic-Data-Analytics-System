# Phase 4: gated router releases and rollback

**Phase 4 controls are complete and deployed.** The seed candidate remains rejected by the golden gate, and live learning remains disabled. No model was promoted. Phase 5 has not started.

## 1. Reasoning summary

1. Establish the Phase 3 baseline, then add a release-history table without changing existing schemas or policies.
2. Read only approved, compatible, active tenant weights for an owned, bound dataset. Keep original routing on disabled, missing, low-margin or failed learner paths.
3. Use explicit operator commands to stage immutable inference snapshots, evaluate candidates outside database transactions, activate atomically and roll back.
4. Require matching shadow evidence, all golden cases passing and strict improvement over the current version, including fallback outcomes.
5. Verify authorization, corruption handling, transaction rollback, concurrent changes, real arithmetic, migration reversal and API compatibility. Preserve a complete reverse patch and database backup.

## 2. Files and reading

| File | Purpose |
| --- | --- |
| `backend/app/learning/release_table.py` | Tenant release-history metadata |
| `migrations/versions/015_router_releases.py` | One new table with forced RLS and read-only runtime policy |
| `backend/app/learning/release.py` | Version validation, approval and source fingerprints |
| `backend/app/learning/routing.py` | Request-scoped router and fail-open reads |
| `backend/app/learning/lifecycle.py` | Operator authorization, stage, promotion gate, atomic activation and rollback |
| `scripts/perceptron_router.py` | Explicit local operator CLI |
| `scripts/verify_router_release_migration.py` | Guarded isolated upgrade/downgrade/upgrade verification |
| `backend/tests/test_perceptron_releases.py` | 22 new tests after parametrization |
| `backend/app/models/__init__.py` | Register the new table |
| `backend/app/api/v1/routes/intent.py` | Apply the scoped router to authenticated classification |
| `backend/app/api/v1/routes/chat.py` | Apply it only to the existing canonical workflow branch |
| `backend/app/services/orchestrator_service.py` | Carry authenticated owner scope into canonical orchestration |
| `backend/app/learning/perceptron.py` | Opt-in confident `unknown` decisions, preserving the shadow default |
| `backend/app/learning/golden.py` | Evaluate and record that explicit runtime policy |

Read: all modified files and callers; classifier service/registry/schema, agent bridge, orchestrator endpoint and workflow-planner caller; authorization helpers and dataset ownership/version contracts; shadow and feedback code; migrations 013/014; Phase 3 oracle/cases/evaluator; integration fixtures and prior tests; Docker and verification setup. Applied the [Postgres best-practices skill](C:/Users/chinm/.codex/skills/supabase-postgres-best-practices/SKILL.md), including RLS and short-transaction guidance.

No `.env` values, public request/response schemas, numerical calculation services, existing embedding/adaptive systems, dependencies or frontend sources were changed. No online training or global-weight updates were added.

## 3. Complete code and design

[phase4.patch](perceptron-verification/phase4.patch) contains the entire runnable change: six modified files and eight new files, relative to the Phase 3 working tree. It excludes previous unrelated edits. Its reverse application check passed.

### Runtime selection

`LEARNING_ENABLED` retains its Pydantic default of false. When false, the original service is returned without a learner database lookup. Eligible requests obtain actor identity from the existing authenticated caller, never from user-supplied context. Dataset ownership, persisted workspace binding, active tenant/workspace access and the selected dataset version are checked in a separate transaction.

A model must be active in `learner_weights`, have a compatible feature contract, bounded finite weights, and a prior promotion record matching both its payload digest and the current routing/evaluation source fingerprint. Source changes or weight tampering invalidate that approval and fall back. There is no cross-request or cross-tenant model cache.

Live decisions require margin greater than 0.5. Ties and lower margins fall back. A high-margin `unknown` is a valid explicit decision, rather than an abstention; the Phase 2 shadow default still abstains on `unknown`. Promotion evaluates the exact live policy via `allow_unknown=True`. Low-margin abstentions are scored using the fallback result, preventing an apparently correct raw `unknown` from hiding an incorrect fallback route.

The existing response shape is preserved. Learned responses use registry-defined agents and a conservative `confidence=0.5`; reasoning explicitly identifies the uncalibrated margin. That compatibility field is not an empirical probability.

The offline gate evaluates keyword/regex fallback. Therefore this phase applies learned routing only to standard classifier instances with no configured LLM. Existing LLM and custom classifier paths remain unchanged, as do actorless/datasetless callers. It does not claim offline validation of a remote LLM. Direct analytics and document retrieval retain their existing branches, so model choices cannot replace pandas calculations.

Database connection timeout is two seconds, with 300 ms statement and 100 ms lock timeouts. The async caller falls back after 2.5 seconds. A timed-out read-only worker thread may finish later; it writes nothing and disposes its connection. Learner errors do not log questions, raw dataset rows, credentials or driver details.

### Operator lifecycle

There is no new HTTP management endpoint. Commands require both a privileged database operator connection (superuser or BYPASSRLS) and an active tenant owner/admin identity. Ordinary runtime roles cannot insert or mutate release history or learner weights, even when given an owner's actor ID. Existing table policies are unchanged. The live deployment still uses its existing superuser database configuration; application authorization remains necessary.

`stage` validates a JSON inference snapshot and inserts a new inactive tenant-local version. It never changes existing weight payloads. Tenant-specific advisory locks serialize version allocation. A candidate must subsequently have at least one matching Phase 2 shadow observation for that tenant, version, feature contract and exact payload.

`promote` reads the candidate/current version, releases the transaction, and freshly evaluates both on the same hash-pinned manifest. It accepts no uploaded evaluation report. Without an active model, the comparison is the keyword baseline. The gate requires all 84 golden cases to pass, no intent regressions, and strictly higher effective intent accuracy than the current version. Ties are rejected, even if both models are perfect. This follows the prompt's strict improvement requirement.

Before committing, it rechecks authorization, candidate/current payloads, source fingerprint, shadow evidence, expected active version and the tenant release-history generation. A concurrent stage, promotion, rollback, membership revocation or payload change prevents activation. Deactivating the previous version, activating the candidate and inserting the audit event share one transaction. Audit failure rolls everything back. No weights are trained from golden examples.

`rollback` selects a previously promoted version with a still-compatible payload/source approval, or version 0 to disable the learned router. It uses the same lock and expected-version checks, writes an audit record, and leaves weight payloads intact. Disabling remains available even for a corrupted/incompatible active model and when learning is off. A previously unapproved staged version cannot be a rollback target.

### Operator commands

From the repository directory, set `$routerActor` and `$routerTenant` to the existing authorized UUIDs for the intended tenant. These are identity selectors; the command also requires operator database credentials. Do not use test UUIDs or fabricate tenants. The live deployment currently has no staged or active router version.

```powershell
docker compose exec backend python scripts/perceptron_router.py status --actor-id $routerActor --tenant-id $routerTenant
docker compose exec backend python scripts/perceptron_router.py stage --actor-id $routerActor --tenant-id $routerTenant --candidate /app/storage/learning/candidate.json
docker compose exec backend python scripts/perceptron_router.py promote --actor-id $routerActor --tenant-id $routerTenant --version 1 --expected-version 0 --root /app --manifest /app/storage/learning/golden/financial-v1/manifest.json --manifest-sha256 69957d10cc13c662987ada53093d3b67d4b767d640fe348d90b26027b7d1476d
```

The candidate path is an operator-supplied, reviewed inference snapshot, not a file created by this phase. Use the actual version returned by `stage` and active version returned by `status`. The commands above demonstrate the first-version flow; they were not run against a live tenant. Exit 0 means success; exit 1 means golden rejection; exit 2 means authorization, input, integrity, concurrency or storage refusal. An activated version still has no runtime effect while `LEARNING_ENABLED=False`.

One-command emergency rollback from active version 1 to the existing classifier:

```powershell
docker compose exec backend python scripts/perceptron_router.py rollback --actor-id $routerActor --tenant-id $routerTenant --version 0 --expected-version 1
```

Use the actual active version as `--expected-version`. To restore an older approved model, supply its version instead of 0. CLI status and disable were exercised against synthetic tenants in the isolated test database.

## 4. Tests and exact commands

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml up -d --wait --wait-timeout 120 postgres redis chromadb
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase4-baseline.xml
docker exec dataanalyst-perceptron-phase1-postgres-1 pg_dump -U setup -d analyst_setup_test -Fc -f /tmp/before-perceptron-phase4.dump
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_router_release_migration.py
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests/test_perceptron_releases.py --junitxml=/verification/phase4-focused.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase4-final.xml
```

The focused run covered 21 tests before the explicit-unknown edge case was added. The final full run includes all 22 Phase 4 tests and all 211 previous tests. Frontend typecheck and production build used the exact read-only Docker scratch-copy command in [Phase 3](PERCEPTRON_PHASE3.md#4-tests-and-exact-commands), both before and after this phase.

Tests cover tenant/owner isolation, revoked access, version isolation, runtime-role denial, concurrent staging, audit RLS, unapproved/changed/corrupt weights, source invalidation, low-margin fallback, explicit unknown, flag-off response parity, learner and database exceptions, real chat arithmetic, no request-time training, current-versus-candidate gates, shadow prerequisites, fresh real evaluator rejection, concurrent release changes, revocation during evaluation, atomic rollback after audit failure, historical-version rollback and CLI operation.

Positive activation transaction tests use explicitly synthetic evaluator reports to exercise the release state machine; they are not evidence that the actual seed passes. The rejection test invokes the real evaluator on synthetic workbooks. Separately, the actual approved spreadsheets were evaluated offline with networking disabled, `allow_unknown=True`, and `promotion_gate(report)`; this returned 50/50 answer checks, 33/34 intents for both seed and baseline, and `passed=false`.

Private real-data evidence: `storage/learning/golden/financial-v1/phase4-seed-evaluation.json`. Its manifest digest is unchanged from Phase 3. No labels, expected answers or original spreadsheets were modified.

## 5. Actual verification

| Check | Result |
| --- | --- |
| Backend baseline | **211 passed**, 5 existing forecasting warnings, 140.21 s |
| Initial focused release tests | **21 passed**, 36.11 s |
| Final full suite | **233 passed**, 5 existing forecasting warnings, 144.66 s |
| Frontend before and after | Typecheck/build passed; Vite 2.85 s and 1.52 s |
| Migration roundtrip | Passed; all 57 existing tables unchanged in columns, keys, indexes, policies and row counts |
| Real spreadsheet answers | **50/50 passed** |
| Seed effective intent score | **33/34**, tied with keyword baseline; **promotion rejected** |
| Complete reverse patch | Check passed |

Evidence: [baseline XML](perceptron-verification/phase4-baseline.xml), [focused XML](perceptron-verification/phase4-focused.xml), [final XML](perceptron-verification/phase4-final.xml).

Before live migration, `ai_analyst` was backed up to `C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase4-20261106\before-perceptron-phase4.dump` (355,136 bytes). `pg_restore --list` succeeded; a live restore was not performed. Before deployment the schema was 014, with zero weight rows, active models and shadow observations.

Deployment completed with `docker compose run --rm migrate python scripts/migrate.py upgrade head`, `docker compose build backend`, and `docker compose up -d --no-deps --wait --wait-timeout 120 backend`.

All five application containers are healthy and `/api/v1/health/ready` returned `ready`. The complete parsed OpenAPI contract is unchanged: 222 paths and 249 operations. Live schema is `015_router_releases`; `LEARNING_ENABLED=False`; learner weight rows, active models, release records and shadow observations are all zero. All four original spreadsheet hashes still match the frozen manifest. The separate verification services were stopped without deleting volumes. No candidate was staged or promoted in the live database.

## 6. Rollback

For model rollback, use the single operator command above. For complete phase removal, first back up the database and any history worth retaining. Disable any active tenant models with the CLI before removing this phase. Then run each command only after the previous succeeds:

```powershell
git apply --reverse --check docs/perceptron-verification/phase4.patch
docker compose stop backend
docker compose run --rm migrate python scripts/migrate.py downgrade 014_perceptron_shadow
git apply --reverse docs/perceptron-verification/phase4.patch
docker compose build backend
docker compose up -d --no-deps --wait --wait-timeout 120 backend
```

The downgrade removes only the new release-history table and its rows. Stored weight payloads, previous phase tables and all original datasets remain. The live downgrade was not executed. Roll back Phase 4 before applying earlier phase reverse patches, because it extends the perceptron and evaluator. Unrelated working-tree changes remain preserved; changes are unstaged and uncommitted, and Git identity settings were not altered.
