# Phase 3 attempt: golden set and evaluation harness

Status: **implementation reverted after the required regression gate failed**. Phase 3 is not complete. Phase 2 remains in place; Phase 4 has not started.

## 1. Reasoning summary

The user approved reading the four saved financial spreadsheets because the live database has no registered datasets. The attempted implementation added an offline evaluator with independently calculated expected answers. It did not register datasets, change runtime routes, train weights, activate candidates, change the database, or edit `.env`.

The master build prompt says: “If anything that passed before now fails, STOP, revert the phase, and report.” The pre-phase backend suite passed all 183 tests. The post-phase suite passed 210 tests and failed one existing test. The phase was therefore reverted, with its complete patch and evidence preserved for review. No corrective changes to the existing connector were attempted.

## 2. Files and reading

The preserved patch contains exactly six files relative to the pre-phase working tree:

| File | Attempted change |
| --- | --- |
| `.gitignore` | Keep dataset-derived golden answers and reports local |
| `backend/app/learning/golden_cases.py` | 84 curated question contracts across the approved sources |
| `backend/app/learning/golden_reference.py` | Independent openpyxl/Decimal reference calculations |
| `backend/app/learning/golden.py` | Hash validation, offline evaluation and fail-closed quality gate |
| `scripts/perceptron_golden.py` | Explicit freeze/evaluate CLI; refuses output overwrites |
| `backend/tests/test_perceptron_golden.py` | 28 synthetic tests for correctness, integrity and isolation |

After rollback, all five new source/test files are absent, and `.gitignore` matches its exact pre-phase SHA-256. Earlier and unrelated working-tree changes remain untouched. This report, the patch and JUnit evidence remain as historical artifacts.

Read: the master build prompt; prior phase reports and tests; `.gitignore`, `.dockerignore`, Dockerfile, verification Compose and test runner; the canonical intent enum, registry and classifier; feature extraction and perceptron; the deterministic analytics parser/executor and tabular loader; saved workbook structures and contents locally; connection endpoint and its failing integration test. No new dependencies or database migrations were needed.

## 3. Complete implementation and frozen artifacts

[phase3.patch](perceptron-verification/phase3.patch) contains the entire attempted implementation. Both `git apply --reverse --check` before rollback and `git apply --check` after rollback passed. It is preserved, **not currently applied**.

The golden set contains 34 canonical intent checks (two for each of 17 intents) and 50 deterministic analytics checks: 36 scalar aggregates, four record counts, four clarification cases, and six grouping/ranking cases. Labels were assigned from question meaning rather than classifier output. Expected numbers were frozen using openpyxl and 50-digit Decimal arithmetic independently of the application's pandas executor. Comparisons use absolute tolerance `1e-8` or relative tolerance `1e-14`, whichever is larger; ranking order and group membership are checked.

The manifest and both evaluations were moved outside the repository during rollback, preserving local financial answers without leaving them unignored:

`C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase3-20261106\financial-v1\`

Files: `manifest.json`, `seed-evaluation.json`, `seed-evaluation-repeat.json`.

Manifest SHA-256: `69957d10cc13c662987ada53093d3b67d4b767d640fe348d90b26027b7d1476d`.

Both evaluation files have SHA-256 `2af6d62100d5e458749dcb3e7bd53e98f2d73e6af7562739263ee6dc8fe868e6`.

| Original source | Rows | SHA-256 |
| --- | ---: | --- |
| cashflow.xlsx | 1187 | `e725377455680fd4ee51eac683708b9f65182c0ecaa5cb3c431586992c8f0095` |
| profitandloss.xlsx | 1276 | `9f76b2bfdb35bbe91fbb98977ca92c02b4674a8deb8e5bbc5051cd3cb7989af0` |
| balancesheet.xlsx | 1312 | `ae25967d1babd4ac68c2c7fab1633b8f86303283d0ccafb5cc158ac9c7a64a36` |
| prosandcons.xlsx | 16 | `c92e6f99b1409f9694b7c0f10dc6d6baeeb883b190ecaec39f4d703f7a8acab5` |

Original workbooks remain in `storage/raw/excel/`; their exact filenames are recorded in the archived manifest. No original workbook was edited or moved.

## 4. Tests and commands actually run

Before editing:

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml up -d --wait --wait-timeout 120 postgres redis chromadb
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase3-baseline.xml
```

After implementation, before rollback:

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests/test_perceptron_golden.py --junitxml=/verification/phase3-focused.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase3-final.xml
```

Frontend validation before and after used the exact read-only Docker scratch-copy procedure in [Phase 1](PERCEPTRON_PHASE1.md#4-tests-and-exact-commands): `npm run typecheck` followed by `npm run build`, with no writes to host frontend build artifacts.

Golden commands ran in a read-only backend-image container, with networking disabled, repository mounted read-only at `/repo`, a writable `/golden` bind for generated output, `/tmp` tmpfs, and working directory `/tmp`. Environment: `PYTHONPATH=/repo`, `PYTHONDONTWRITEBYTECODE=1`, `OPENBLAS_NUM_THREADS=1`. Inner commands were:

```text
python /repo/scripts/perceptron_golden.py freeze --root /repo --manifest /golden/financial-v1/manifest.json --source cashflow=storage/raw/excel/6ac6f755-9978-4ce0-b3dc-928b70c2eeff_cashflow.xlsx --source profitandloss=storage/raw/excel/d52ee852-1b08-4163-9b7f-bfeccd884530_profitandloss.xlsx --source balancesheet=storage/raw/excel/4e1dda96-fee4-460f-b749-c402b01c3d63_balancesheet.xlsx --source prosandcons=storage/raw/excel/38003018-eeb7-4842-afad-78844a3bbec8_prosandcons.xlsx
python /repo/scripts/perceptron_golden.py evaluate --root /repo --manifest /golden/financial-v1/manifest.json --manifest-sha256 69957d10cc13c662987ada53093d3b67d4b767d640fe348d90b26027b7d1476d --report /golden/financial-v1/seed-evaluation.json
```

The second evaluation used `seed-evaluation-repeat.json`. Both evaluations exited **1**, indicating the quality gate rejected the candidate. The CLI and original output locations no longer exist in the working tree after rollback; these commands document the attempted run, rather than instructions to execute on the reverted tree.

## 5. Actual verification results

| Check | Result |
| --- | --- |
| Backend baseline | 183 passed, 5 existing forecasting warnings, 146.94 s |
| New focused tests | 28 passed, 10.73 s |
| Full backend after changes | **1 failed, 210 passed**, 5 existing warnings, 137.17 s |
| Frontend before and after | Typecheck and production build passed |
| Real spreadsheet answers | **50/50 passed** |
| Keyword intent baseline | **33/34 correct** |
| Seed shadow intent router | **33/34 correct**, no regressions against baseline, one abstention |
| Golden quality gate | **Failed**; no promotion and no training |
| Repeated golden evaluation | Byte-identical report |
| Rollback | Reverse patch applied successfully; patch can be reapplied cleanly |

Evidence: [baseline XML](perceptron-verification/phase3-baseline.xml), [focused XML](perceptron-verification/phase3-focused.xml), [post-phase XML](perceptron-verification/phase3-final.xml).

Existing failing test: `backend/tests/test_application_and_eda_recovery.py::test_external_connection_test_postgresql_and_ssrf`, line 287:

```text
assert "datasets" in result["tables"]
AssertionError: assert 'datasets' in ['adaptive_label_revisions', 'learning_audit', 'learning_evaluations', 'adaptive_outcomes', 'comments', 'workspace_memberships', ...]
```

The endpoint returned HTTP 200 and a successful connection. Its existing code returns `tables[:50]`. That truncation may explain the omitted table; causality has not been established, and no connector fix or repeat test was made to bypass the required stop condition.

The independent golden failure is `intent-unknown-2`: “Tell me a bedtime story about a dragon” is labelled `unknown`, but both routers predict `rag_query`. The registry searches keyword substrings, so `rag` inside `dragon` matches the RAG keyword. The label was retained, rather than changed to make the evaluation pass. Future promotion must remain blocked until a candidate meets the full golden gate and the required comparison against the live version.

No backend image rebuild, live migration, deployment or container replacement occurred during this attempt. The prior application's five containers were healthy when checked. Changes remain uncommitted; Git identity and earlier work were preserved.

## 6. Rollback completed

Executed successfully:

```powershell
git apply --reverse --check docs/perceptron-verification/phase3.patch
git apply --reverse docs/perceptron-verification/phase3.patch
git apply --check docs/perceptron-verification/phase3.patch
```

Only this phase's five new source/test files and `.gitignore` delta were reverted. Generated golden files were preserved in the private archive above. No database downgrade or runtime restart was necessary. The disposable verification services are stopped without deleting volumes. Phase 3 needs a fresh authorized retry after addressing the test gate; Phase 4 remains pending.
