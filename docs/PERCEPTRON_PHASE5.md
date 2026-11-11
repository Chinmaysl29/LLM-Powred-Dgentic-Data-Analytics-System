# Phase 5: reviewed failure memory

Date: 2026-11-07 (Asia/Calcutta). Branch: `feature/learning-layer`.

## 1. Design and scope

The planner can recall reviewed failures for the authenticated owner, tenant, workspace, dataset version, schema and current intent. Chroma supplies candidate identifiers; Postgres rechecks authorization, active review, payload integrity and similarity before a plan can be applied. The same check runs in ordinary orchestration and dynamic planning. Existing analytics, embeddings and adaptive systems remain intact; the new vector implementation uses NumPy and SHA-256.

A failure alone is not a correct answer. An operator must attest to an exact question and a structured correction using the CLI. Review requires both a privileged database role and an active tenant owner/admin identity. Original failure truth stays null. New failures include dataset/version provenance; older events without that provenance are ineligible. Approval and its audit link commit together; Chroma indexing happens afterward and can be retried. SQL revocation immediately invalidates stale vectors, including when index deletion fails.

Corrections may add only `validation`, `eda` or `statistics` for the existing intent. They cannot supply executable text, SQL, formulas, new intents, cleaning or forecasts. Existing planner rules and dependency ordering still apply. Request-time code does not train weights or compute business metrics.

The feature flag defaults to false. Disabled, unavailable or invalid memory returns the original workflow. Runtime retrieval uses at most two workers, a 2.5-second caller deadline, bounded database/network operations and response sizes. Indexes hold numeric vectors and scoped identifiers, with no raw question or dataset documents. Hashed lexical vectors are not encryption and are not a semantic language model: recall is intentionally conservative (cosine >= 0.90). Collections use the verified local Chroma 0.6.3 protocol and persist in the existing Chroma volume. Other versions fail open until separately verified.

The main risks are unauthorized cross-scope recall, stale approvals and changing analytical behavior. Tests exercise real PostgreSQL/Chroma, forged candidate identifiers, tampering, revocation, outages, unchanged chat arithmetic and both execution paths. No real correction or automatic training label is invented for live data.

## 2. Files and reading

Read the master prompt, prior phase reports, settings, workspace authorization, learning tables/evidence/shadow/release/lifecycle modules, model registration and dataset/version models, planner/orchestrator schemas, services and routes, workflow registry and dependencies, migration configuration and previous migrations, Docker/verification configuration, existing integration/release tests and setup/migration scripts. Read the installed Chroma HTTP implementation to verify v2 request bodies and timeout behavior. Applied the local `supabase-postgres-best-practices` skill for the new table and RLS policy.

| File | Change |
| --- | --- |
| `backend/app/learning/memory_contract.py` | Bounded NumPy vectors and non-executable correction format |
| `backend/app/learning/memory_table.py` | Review provenance, integrity hash and revocation |
| `backend/app/learning/memory_chroma.py` | Isolated bounded Chroma HTTP adapter |
| `backend/app/learning/failure_memory.py` | Authorized, fail-open recall and SQL verification |
| `backend/app/learning/memory_review.py` | Explicit approve, reindex and revoke lifecycle |
| `backend/app/learning/evidence.py` | Dataset/version identifiers in future hard-failure evidence |
| `backend/app/models/__init__.py` | Register the new table |
| `backend/app/services/workflow_planner_service.py` | Owner-scoped recall before existing rules |
| `backend/app/services/orchestrator_service.py` | Recall for ordinary workflows; pass owner into dynamic planner |
| `migrations/versions/016_failure_memory.py` | Add only the new RLS-protected link table |
| `scripts/perceptron_memory.py` | Privileged operator CLI |
| `scripts/verify_failure_memory_migration.py` | Guarded isolated migration roundtrip |
| `scripts/verify_failure_memory_persistence.py` | Synthetic restart persistence check |
| `backend/tests/test_perceptron_memory.py` | 27 focused tests |

## 3. Complete diff and operation

[Complete runnable phase diff](perceptron-verification/phase5.patch) includes all 14 implementation/test/script files, against the exact pre-phase working tree. No `.env` value was changed. There are no new public API endpoints or request/response fields.

An operator correction JSON has exactly this shape:

```json
{"format":1,"intent":"dataset_overview","add_steps":["validation"]}
```

The question file must contain the original question exactly, including whitespace; its SHA-256 must match the captured failure. Use the actual reviewed event, dataset version and authorized reviewer, and files accessible inside the container. Operator commands (PowerShell variables must be assigned actual reviewed identifiers and paths):

```powershell
docker compose exec backend python scripts/perceptron_memory.py approve --reviewer-id $reviewerId --feedback-id $feedbackId --dataset-id $datasetId --dataset-version $datasetVersion --question-file $questionPath --correction-file $correctionPath --reviewed
docker compose exec backend python scripts/perceptron_memory.py reindex --reviewer-id $reviewerId --mistake-id $mistakeId
docker compose exec backend python scripts/perceptron_memory.py revoke --reviewer-id $reviewerId --mistake-id $mistakeId
```

`approved=true,indexed=false` means SQL review committed but indexing needs retry (exit 1). Authorization/provenance rejection exits 2. Revocation reports SQL success separately from index cleanup. Runtime restricted roles have no write policy on corrections or review links. Explicit operator maintenance is available even when runtime learning is disabled, as with Phase 4's release CLI.

## 4. Tests and exact commands

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml up -d --wait --wait-timeout 120 postgres redis chromadb
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase5-baseline.xml
docker exec dataanalyst-perceptron-phase1-postgres-1 pg_dump -U setup -d analyst_setup_test -Fc -f /tmp/before-perceptron-phase5.dump
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_failure_memory_migration.py
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests/test_perceptron_memory.py --junitxml=/verification/phase5-focused.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase5-final.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_failure_memory_persistence.py seed
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml restart chromadb
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_failure_memory_persistence.py check
```

Frontend before/after uses the same isolated scratch copy, with no network and read-only source:

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
'@ | docker run --rm -i --network none --read-only --tmpfs /tmp:rw,exec,size=768m --mount 'type=bind,source=C:\data analyst\frontend,target=/source,readonly' --env npm_config_cache=/tmp/npm-cache --entrypoint node dataanalyst-frontend:latest -
```

## 5. Actual verification

Baseline: **233 passed**, five existing forecasting warnings, 155.96 seconds. Frontend typecheck/build passed before and after (Vite 2.30 and 2.51 seconds).

Initial focused run: 21 passed. After adding six integration/security cases, one new revocation test failed because tenant owners could bypass workspace membership in application authorization while the new RLS policy required it. Memory scope now explicitly checks active workspace membership even for privileged database connections. The corrected focused run: **27 passed, 42.16 seconds**. No existing test failed in these focused runs.

Migration upgrade/downgrade/upgrade passed: all **58 existing tables** retained their columns, keys, indexes, policies and row counts. The complete reverse patch check passed.

Final full suite: **260 passed**, five existing forecasting warnings, **173.04 seconds**. This includes all 233 baseline tests and all 27 new tests. Evidence: [baseline XML](perceptron-verification/phase5-baseline.xml), [focused XML](perceptron-verification/phase5-focused.xml), [final XML](perceptron-verification/phase5-final.xml).

The persistence script passed before and after restarting only the isolated verification Chroma service, using a fresh process for each check. Synthetic reviewed records and their vectors remained retrievable. CLI reindex/revoke, ordinary and dynamic orchestrator execution, authenticated planner scope, unchanged real chat aggregation (synthetic total 1180), restricted-role RLS and request-time no-training checks passed.

Backups and original source copies are in `C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase5-20261106`. The isolated test database was dumped before its migration. Live `ai_analyst` was backed up before deployment to `before-perceptron-phase5.dump` (**405,637 bytes**); `pg_restore --list` succeeded. No live restore was performed.

Deployment commands, each executed after the preceding success:

```powershell
docker compose build backend
docker compose run --rm migrate python scripts/migrate.py upgrade head
docker compose up -d --no-deps --wait --wait-timeout 120 backend
```

The live migration is `016_failure_memory`; `LEARNING_ENABLED=False`. Live feedback, mistakes, review links, weights, release records, shadow observations and active weights are all zero. No candidate or correction was created in the live database. `.env` values, original datasets and spreadsheets were not edited. Work remains uncommitted; Git identity was not changed.

All five live application containers are healthy. `/api/v1/health/ready` returned `ready`, with schema, PostgreSQL, Redis and Chroma healthy. Optional LLM providers remain unconfigured. The complete parsed OpenAPI document is identical before/after deployment: **222 paths, 249 operations**. Runtime inspection confirms `unless-stopped` restart policies, persistent Postgres/Chroma/Redis named volumes, and the preserved host storage bind for uploads. The new backend is saved as `dataanalyst-backend:latest` (image manifest `sha256:b840a1cb15f20fcfe21455ed17084059c90e2beec8e57239d04869ab43b83d40`). The verification services were stopped without removing their volumes:

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml stop postgres redis chromadb
```

## 6. Rollback

For one correction use `revoke`; SQL revocation is authoritative even if Chroma is offline. For phase removal, back up the database and retain any reviewed history first, then execute each command only after the preceding one succeeds:

```powershell
git apply --reverse --check docs/perceptron-verification/phase5.patch
docker compose stop backend
docker compose run --rm migrate python scripts/migrate.py downgrade 015_router_releases
git apply --reverse docs/perceptron-verification/phase5.patch
docker compose build backend
docker compose up -d --no-deps --wait --wait-timeout 120 backend
```

The downgrade removes only the new link table and its review/revocation rows. Existing feedback and mistakes remain; without links the new reviewed mistakes cannot be recalled. New Chroma vectors left behind are inert and may be retained for recovery; do not delete existing application collections or volumes. Prior phases and unrelated working-tree changes are preserved. A live downgrade or database restore is not part of verification. Stop after this phase; Phase 6 requires the user's next proceed instruction.
