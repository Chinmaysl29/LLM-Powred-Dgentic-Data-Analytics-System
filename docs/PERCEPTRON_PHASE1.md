# Perceptron Phase 1 — foundations

Implemented on `feature/learning-layer`, 2026-11-06. Phase 2 has not started.

## 1. Reasoning summary

1. Repair the seven pre-existing test failures with synthetic uploads, isolated connection settings, and the current migration head; establish a green baseline.
2. Add disabled-by-default evidence collection and three new tables. Keep deterministic computation, routing, existing adaptive/embedding systems, and API contracts unchanged.
3. Store only authorized hard-failure evidence. A failed execution is not a correct label: `truth` is NULL. No training, promotion or weight writes occur.
4. Verify fail-open handling, tenant isolation with a non-superuser role, migration reversal, and full regression tests before updating the running Docker application.

## 2. Files and reading

Modified:

| File | Reason |
| --- | --- |
| `backend/app/core/config.py` | Pydantic `learning_enabled=False` |
| `.env.example` | Document `LEARNING_ENABLED=false`; `.env` untouched |
| `backend/app/models/__init__.py` | Register three new tables for schema checks |
| `backend/app/api/v1/routes/chat.py` | Observe execution without replacing its result |
| `backend/app/services/analysis_run_service.py` | Observe failed stages and mandatory validation rejection |
| `backend/tests/test_application_and_eda_recovery.py` | Synthetic Excel uploads and actual test DB configuration |
| `backend/tests/test_visualization_analytics_recovery.py` | Synthetic banner workbook and 1,187-row chart fixtures; assert exact sum 10,950 |
| `tests/test_upload_and_pipeline_recovery.py` | Compare schema revision against migration head |

Created:

| File | Reason |
| --- | --- |
| `backend/app/learning/__init__.py` | Independent optional learning package |
| `backend/app/learning/tables.py` | Weight, feedback and mistake storage contract |
| `backend/app/learning/evidence.py` | Bounded, independent, authorized evidence transactions |
| `migrations/versions/013_perceptron_foundations.py` | Additive tables, tenant/time indexes and forced RLS |
| `backend/tests/test_perceptron_foundations.py` | Twelve foundation tests |
| `scripts/verify_perceptron_migration.py` | Guarded disposable-DB migration roundtrip |

Read before the changes: the modified files and their callers; route aggregation, frontend `AnalysisPage.tsx` and `analysisService.ts`; dataset retrieval, storage, upload and versioning services; natural-language analytics and intent classification; analysis session and job execution paths; workspace authorization; model registry/base, Dataset, DatasetVersion, DatasetMetadata, LearningRun and existing adaptive models; migrations 011/012 and `migrations/env.py`; schema contract; pytest fixtures, setup-test runner, Dockerfiles and Compose configuration. Applied the local `supabase-postgres-best-practices` skill and its schema-types, indexes and RLS references.

## 3. Complete diff and behavior

The complete runnable implementation is in the files above. [phase1.patch](perceptron-verification/phase1.patch) contains only this phase and the authorized baseline-test repairs, relative to the original working tree. It excludes unrelated pre-existing edits.

Capture is limited to exceptions, empty deterministic analytical results, and recognized execution/mandatory validator rejections. Clarification requests, successful zero results, access denials and missing datasets do not become labels. Worker events use a run/stage/attempt UUID to deduplicate delivery. Tenant and workspace are resolved from persisted dataset binding and active memberships, followed by owner authorization.

Privacy choice: `question` remains NULL and `question_hash` holds its SHA-256 digest. Schema names/types are hashed; raw rows, error messages, answers, credentials and corrected plans are not retained. `predicted` is restricted to known deterministic operations; otherwise NULL. Unknown schema remains NULL. This phase cannot retrospectively train from question text; feature extraction belongs to the shadow-router phase.

New writes use an independent connection and transaction with a two-second connection timeout, 300 ms statement timeout and 100 ms lock timeout. Capture failure is swallowed without logging driver exception contents or modifying the caller's transaction. Individual statements are bounded; this is not a whole-request latency deadline.

`learner_weights` and `mistakes` are reserved and receive no application writes. Runtime RLS permits authorized feedback inserts and scoped reads, with no runtime weight/mistake mutation policy. Production currently uses the existing PostgreSQL superuser, so application authorization remains essential; RLS denial was additionally verified under a non-superuser/non-bypass role.

## 4. Tests and exact commands

Run from the repository root:

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml up -d --wait --wait-timeout 120 postgres redis chromadb
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase1-final.xml
```

Migration roundtrip, **disposable test database only**, with backup first:

```powershell
docker exec dataanalyst-perceptron-phase1-postgres-1 pg_dump -U setup -d analyst_setup_test -Fc -f /tmp/before-perceptron-phase1.dump
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_perceptron_migration.py
```

Frontend validation used this scratch copy with networking disabled and repository source mounted read-only:

```powershell
@'
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const destination = '/tmp/audit';
const excluded = new Set(['node_modules', 'dist', '.git', '.ui-review']);
fs.cpSync('/source', destination, { recursive: true, filter: entry => !path.relative('/source',entry).split(path.sep).some(part=>excluded.has(part)) });
fs.cpSync('/app/node_modules', path.join(destination,'node_modules'), {recursive:true});
for (const task of ['typecheck','build']) {
 const result=spawnSync('npm',['run',task],{cwd:destination,stdio:'inherit'});
 if(result.status!==0) process.exit(result.status ?? 1);
}
'@ | docker run --rm -i --network none --read-only --tmpfs /tmp:rw,exec,size=768m --mount 'type=bind,source=C:\data analyst\frontend,target=/source,readonly' --env npm_config_cache=/tmp/npm-cache --entrypoint node dataanalyst-frontend:latest -
```

New tests cover flag defaults/environment configuration, no database access when disabled, original exceptions and successful results preserved, ambiguity/zero handling, persisted privacy and unknown truth, duplicate delivery, unauthorized/revoked users, database failure, restricted-role RLS/forged scope, actual chat and worker hook invocation, and byte-identical serialized chat responses with a fixed clock.

## 5. Verification report

| Check | Actual result |
| --- | --- |
| Initial baseline | 131 passed, 7 failed, 1 skipped |
| Repaired test modules | 33 passed |
| Full baseline after repair | **139 passed**, 5 warnings, 107.89 s |
| New foundation tests | **12 passed**, 18.02 s |
| Full suite after Phase 1 | **151 passed**, 5 warnings, 121.82 s |
| Frontend before and after | `npm run typecheck` and `npm run build` passed |
| Migration roundtrip | PASS; 53 existing tables unchanged in columns, keys and row counts |
| Docker image | `dataanalyst-backend:latest` rebuilt successfully; dependency layers cached |
| Live database | Upgraded from `012_adaptive_skills` to `013_perceptron_foundations` |
| Runtime | `/health/ready` returns `ready`; `LEARNING_ENABLED=False`; new tables all have zero rows |

The five forecasting warnings also occurred before the change. No new test failures occurred. Evidence: [baseline XML](perceptron-verification/phase1-baseline-repaired.xml), [foundation XML](perceptron-verification/phase1-foundations.xml), [full-suite XML](perceptron-verification/phase1-final.xml).

Live DB backup: `C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase1-20261106\before-perceptron-phase1.dump` (264,962 bytes, custom format). `pg_restore --list` successfully read its archive. A live restore was not performed.

No commit was created because Git author identity is unset. No identity configuration was changed. The phase changes are unstaged on `feature/learning-layer`; unrelated working-tree edits were preserved.

## 6. Rollback

The flag is already disabled, so no optional evidence collection is active. The following is a full schema/code rollback, **not executed on the live DB**. Downgrade removes only the three new tables and their contents; take a fresh backup first if they contain evidence. Run from `C:\data analyst`:

```powershell
git apply --reverse --check docs/perceptron-verification/phase1.patch
docker compose stop backend
docker compose run --rm migrate python scripts/migrate.py downgrade 012_adaptive_skills
git apply --reverse docs/perceptron-verification/phase1.patch
docker compose build backend
docker compose up -d --no-deps backend
```

Execute each step only if the preceding command succeeds. The reverse patch also undoes the three baseline test repairs; it leaves unrelated pre-existing changes intact. Verification reports remain as historical evidence. The reverse patch check passed against the completed working tree.

Stop here; Phase 2 requires the user's next `proceed`.
