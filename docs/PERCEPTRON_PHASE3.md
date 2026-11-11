# Phase 3: golden set and evaluation harness

**Phase 3 is complete.** The evaluator is implemented and tested. The current seed candidate fails the golden quality gate and has not been promoted. Phase 4 has not started.

## 1. Reasoning summary

The offline harness evaluates fixed questions against independently calculated answers from the four user-approved saved spreadsheets. It does not register datasets, alter runtime routing, train weights, or activate a candidate. The NumPy learner chooses canonical intents; the existing pandas executor performs the business calculations.

The previous attempt was rolled back under the mandatory regression gate. On this retry the connector test failed again with all Phase 3 code absent. Read-only inspection found 58 tables, with `datasets` at position 55. The endpoint returns a preview capped at 50, so the assertion that `datasets` must appear in the preview was invalid. The repaired test checks real table discovery, preview size, uniqueness, valid names and the exact total count, retaining its real connection and SSRF checks. No endpoint change was needed.

The [first-attempt report](PERCEPTRON_PHASE3_ATTEMPT1.md) and its evidence remain preserved. The retry restored the same hash-pinned manifest, questions, labels and expected answers.

## 2. Files and reading

| File | Change |
| --- | --- |
| `backend/tests/test_application_and_eda_recovery.py` | Correct the bounded-preview assertion independently of the learner |
| `.gitignore` | Exclude private generated golden answers and reports |
| `backend/app/learning/golden_cases.py` | 84 curated question contracts |
| `backend/app/learning/golden_reference.py` | Independent openpyxl and 50-digit Decimal oracle |
| `backend/app/learning/golden.py` | Input integrity, evaluation and quality gate |
| `scripts/perceptron_golden.py` | Explicit freeze/evaluate CLI, refusing output overwrites |
| `backend/tests/test_perceptron_golden.py` | 28 tests using synthetic workbooks |

Read: master prompt and prior phase reports; the complete connector regression test and endpoint, frontend connection service and preview caller; intent enum/registry/classifier, perceptron and features, analytics parser/executor and tabular loader; approved workbook structures and local contents; `.gitignore`, `.dockerignore`, Dockerfile, verification Compose, setup test runner, restored implementation and tests.

No dependencies, migrations, runtime routes, calculation services, existing adaptive/embedding systems, frontend sources or `.env` values changed in this phase.

## 3. Complete code and golden set

Full diffs: [connector test repair](perceptron-verification/phase3-connector-test-repair.patch) and [Phase 3 implementation](perceptron-verification/phase3.patch). Both are relative to the pre-phase working tree and exclude unrelated earlier changes. The implementation patch contains all five new Python files and the `.gitignore` delta.

Golden set: `storage/learning/golden/financial-v1/manifest.json`.

Manifest SHA-256: `69957d10cc13c662987ada53093d3b67d4b767d640fe348d90b26027b7d1476d`.

There are 34 canonical intent cases (two for each of 17 intents) and 50 analytics cases: 36 scalar aggregates, four record counts, four clarification cases and six grouping/ranking cases. The sources contain 1187 cashflow rows, 1276 profit-and-loss rows, 1312 balance-sheet rows and 16 pros-and-cons rows. Exact source filenames, hashes, columns and row counts are frozen in the manifest. Original spreadsheets are unchanged.

The reference uses Excel cells and Decimal arithmetic independently of the application's loader and analytics implementation. Evaluation uses the existing loader and deterministic executor. Comparisons use the larger of absolute tolerance `1e-8` and relative tolerance `1e-14`. Nulls, group membership, cardinality and ranking order are checked. This verifies the specified questions and operations, not every possible analytical request or downstream agent.

The evaluator hashes sources, manifest, candidate, features and relevant source code. Changed inputs and invalid candidates are rejected. Reports include case outcomes and provenance without raw data rows. Neither freezing nor evaluation can train or promote weights. Golden cases must remain held out from future training. The baseline is the deterministic registry keyword/regex route, not an external LLM assessment.

Private reports: `seed-evaluation-retry.json` and `seed-evaluation-retry-repeat.json` beside the manifest. Git ignores this directory, and the existing Docker `storage/` exclusion keeps it out of images. The first attempt remains archived under `C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase3-20261106\financial-v1\`.

## 4. Tests and exact commands

Reproduction before repair, with Phase 3 absent:

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml up -d --wait --wait-timeout 120 postgres redis chromadb
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py /repo/backend/tests/test_application_and_eda_recovery.py::test_external_connection_test_postgresql_and_ssrf --junitxml=/verification/phase3-connector-reproduced.xml
```

An initial command used a relative pytest node ID, which the scratch-directory runner could not resolve; it collected no tests. The absolute path above reproduced the actual assertion failure.

After test repair, before restoring Phase 3, and then after restoration:

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase3-retry-baseline.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase3-retry-final.xml
```

Frontend checks before and after restoration ran in a read-only Docker container with a scratch copy, avoiding host build artifacts:

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

Real-data evaluation without network access:

```powershell
docker run --rm --network none --read-only --tmpfs /tmp:rw,exec,size=512m --mount 'type=bind,source=C:\data analyst,target=/repo,readonly' --mount 'type=bind,source=C:\data analyst\storage\learning\golden,target=/golden' --workdir /tmp --env PYTHONPATH=/repo --env PYTHONDONTWRITEBYTECODE=1 --env OPENBLAS_NUM_THREADS=1 --entrypoint python dataanalyst-backend:latest /repo/scripts/perceptron_golden.py evaluate --root /repo --manifest /golden/financial-v1/manifest.json --manifest-sha256 69957d10cc13c662987ada53093d3b67d4b767d640fe348d90b26027b7d1476d --report /golden/financial-v1/seed-evaluation-retry.json
```

The second run uses `seed-evaluation-retry-repeat.json`. Choose a new report filename for future runs: existing artifacts are not overwritten. Exit 0 means the quality gate passed; exit 1 means candidate rejection; exit 2 means input/output validation refused the run. Optional `--candidate` supplies a validated JSON inference snapshot. The CLI never activates it.

Tests cover independent arithmetic and null handling; invalid financial strings; source/manifest hashes and fixed contracts; path traversal and symlinks; wrong-answer rejection; executor errors; candidate validation and rejection; unchanged source bytes and weights; deterministic results; numeric tolerance; group membership and ranking order.

## 5. Verification

| Check | Result |
| --- | --- |
| Connector reproduction with Phase 3 absent | 1 failed, 18.58 s; original failure confirmed |
| Repaired baseline | **183 passed**, 5 existing forecasting warnings, 128.11 s |
| Final backend suite | **211 passed**, 5 existing forecasting warnings, 146.04 s |
| Frontend before and after | Typecheck and build passed; Vite 3.06 s and 2.31 s |
| Real spreadsheet answers | **50/50 passed** |
| Keyword and seed intent accuracy | Both **33/34**, with no regressions against the baseline |
| Golden quality gate | **Rejected**; exit 1, no training, no promotion |
| Repeated evaluation | Byte-identical retry reports |
| Reversal checks | Both phase-specific reverse patches passed |

Evidence: [reproduction XML](perceptron-verification/phase3-connector-reproduced.xml), [baseline XML](perceptron-verification/phase3-retry-baseline.xml), [final XML](perceptron-verification/phase3-retry-final.xml). All 28 new golden tests passed in the final full suite.

The retained intent failure is `intent-unknown-2`: “Tell me a bedtime story about a dragon” should be `unknown`, but both routes predict `rag_query` because `rag` matches inside `dragon`. The label was retained. Phase 3 completes the evaluation machinery; it does not make this candidate eligible for promotion. Phase 4 must enforce the 100% golden requirement and the required comparison against the live router.

Compared with the first attempt, all scores, case results, source hashes and candidate hashes match. The raw code digest changed because Git restored CRLF line endings; it records the actual bytes used. Two runs of the restored code produced identical reports.

Docker: `docker compose build backend` succeeded and saved `dataanalyst-backend:latest` with the evaluator. An isolated, network-disabled image check parsed all four evaluator/CLI modules and confirmed that `/app/storage` and `/app/.env` are absent from the image. No live container replacement was necessary: source and scripts are already bind-mounted, and these offline modules change no request path.

All five application containers are healthy; `/api/v1/health/ready` returned `ready`; live `LEARNING_ENABLED=False`. All four original spreadsheet hashes match the manifest. The separate verification services were stopped without deleting volumes. No live migration or data registration occurred; this phase evaluated the approved saved files directly.

## 6. Rollback

Changes remain uncommitted and unstaged; earlier work and Git identity settings are preserved. To remove the Phase 3 implementation, first copy the private golden directory outside the repository. Then run each command only if the previous one succeeds:

```powershell
git apply --reverse --check docs/perceptron-verification/phase3.patch
git apply --reverse docs/perceptron-verification/phase3.patch
```

Reversing `.gitignore` removes its new exclusion. If retaining the golden files in the repository directory, preserve their exclusion through `.git/info/exclude`. No database downgrade is needed. The connector test repair is independent and may be retained; to undo it separately:

```powershell
git apply --reverse --check docs/perceptron-verification/phase3-connector-test-repair.patch
git apply --reverse docs/perceptron-verification/phase3-connector-test-repair.patch
```

If reverting an already rebuilt image, run `docker compose build backend` after reversing the code. These offline modules change no live request path, so no application restart is needed. Retain original datasets and persistent Docker volumes.
