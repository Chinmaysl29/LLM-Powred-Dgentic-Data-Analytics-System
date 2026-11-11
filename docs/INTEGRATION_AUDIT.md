# Integration audit: Stages 0–2

Started 8 November and completed 9 November 2026, Asia/Calcutta. Repository: `C:/data analyst`; branch: `fix/integration-audit`.

**Status: RED against the requested acceptance criteria.** The live application remains available and its six services are healthy, but this audit reproduced authentication, data-integrity and integration defects. A passing existing test suite does not cover these newly discovered cases.

Application code, migrations, `.env`, existing tests and live datasets were not changed. No repair commits or model promotions were made. This report ends at the requested Stage 2 approval stop; it is not the Stage 6 post-repair report.

**Stage 4 correction (9 November):** The user subsequently authorized all remaining stages. A stronger real two-account report regression reproduced an additional P1 finding, F-012: report manifest/download endpoints did not authorize their source run. The earlier Stage 2 multi-tenancy PASS did not establish report-file isolation; its existing named isolation test only exercised sessions. See the repair plan and final verification for the correction and repair evidence.

## Ground truth

| Check | Observed result | Evidence under `integration-audit/20261108/` |
| --- | --- | --- |
| Clean image build | Backend and frontend built from their checked-in Dockerfiles using separate audit image tags; backend dependencies downloaded and installed afresh | `build.log`, `audit-image-ids.txt` |
| Installed packages | All 214 package names/versions match between fresh backend image and tested deployed image; `pip check` passes | `build-package-comparison.json`, `fresh-pip-check.txt` |
| Backend suite | **384 passed, 0 failed, 0 errors, 0 skipped**, five forecasting warnings; 413.61 seconds | `backend-full.xml`, `backend-tests.log`, `test-summary.json` |
| Frontend | TypeScript, ESLint with zero warnings, and production build pass | `frontend-checks.log` |
| Migrations | Empty isolated PostgreSQL upgraded through the complete chain to the single head `019_dataplane`; repeated upgrade was a no-op | `backend-tests.log`, `migration-files.txt`, `schema-audit.json` |
| API inventory | **264 operations / 237 paths**; historical 114-route inventory was unavailable, so an exact route-set diff is unverified | `live-routes.txt` |
| Flag matrix | All four off/on combinations passed the same local-auth upload, chart, durable analysis, chat and PDF journey, each with the independent total 2,100 | `flags-false-false.log`, `flags-false-true.log`, `flags-true-false.log`, `flags-true-true.log` |
| Fresh-image startup | Isolated API, worker and frontend started from rebuilt images; real API journey passed again | `fresh-start.log`, `fresh-journey.log`, `fresh-config.json` |
| Browser | Seven scenarios passed on a fresh synthetic account: authentication, worker upload, aggregate totals, PDF, health/cleaning approval, stale-state recovery and mobile layout | `browser/results.json`, screenshots, `browser.log` |
| Native dataplane chat | First request queued; repeat after completion returned 35 with a persisted evidence citation; evidence rows also contain 35 | `dataplane-chat.log` |
| Raw-file preservation | 744 pre-existing files compared with backup: zero changed, zero missing; worker heartbeat excluded | `raw-immutability.json` |

The suite ran against the deployed dependency image and current read-only source in a newly created isolated database. The fresh image was then checked for exact package parity and exercised by the real API journey; this is not a claim that the entire suite was run a second time on that image.

Actual versions include Python 3.11.18, Node 22.23.4, Docker 29.9.2, FastAPI 0.162.0, Pydantic 2.14.2, SQLAlchemy 2.1.6, Alembic 1.20.1, psycopg 3.3.7, pandas 2.3.3, NumPy 2.4.6 and DuckDB 2.0.0. The application uses synchronous SQLAlchemy/psycopg sessions; asyncpg is not installed. Chroma's internal port is 8000 and the live host mapping is 8401. These differ from the historical prompt, without themselves demonstrating defects.

## Findings

All findings below are reproduced. Severity follows the supplied definitions: P1 covers incorrect data or security exposure; P2 covers degraded behavior and integration gaps. No current live outage was found.

| ID | Sev | Area | Symptom | Reproduction/evidence |
| --- | --- | --- | --- | --- |
| F-001 | P1 | XLSX ingestion | Duplicate `amount` headers containing 10 and 99 become a single column containing 99, without rejection | `ingestion-repro.jsonl`; `ingestion_probe.py` |
| F-002 | P1 | JSONL ingestion | `{"a":1}` followed by `{"a":2,"b":99}` loses column `b` in the snapshot | `ingestion-repro.jsonl`; `ingestion_probe.py` |
| F-003 | P1 | Logout | After successful logout, the same access token still receives HTTP 200 from `/api/v1/auth/me` | `auth-probe.log`; `http_probe.py --mode auth` |
| F-004 | P1 | Session revocation | A revoked refresh token receives 401 before API restart and 200 after restart | `auth-probe.log`, `auth-restart.log` |
| F-005 | P1 | Dataset versions | Database accepts two active versions for one dataset; declared uniqueness index is absent | `active-version-repro.json`, `version-indexes.txt` |
| F-006 | P2 | CSV encoding | Latin-1 text is accepted as binary, then grouping by that column fails JSON serialization | `encoding-repro.json`, `engine-probes.jsonl` |
| F-007 | P2 | Migration metadata | Alembic comparison proposes removing four live Core tables and their indexes; also reports nullable/index drift | `schema-audit.json`, `schema-diff-details.jsonl` |
| F-008 | P2 | Dependencies | CUDA package `nvidia-nccl-cu12==2.32.3` is installed despite the no-GPU-dependencies requirement | `gpu-dependency.json`, `build.log` |
| F-009 | P2 | Monitoring policy | Distribution warning appears with one previous observation; history/threshold values are literals rather than configuration | `monitor-repro.json`; `quality.py` |
| F-010 | P2 | Report format contract | Requesting CSV through `/reports/from-analysis` reaches an unsupported generator and returns HTTP 500 | `dataplane-chat.log`; `http_probe.py --mode dataplane` |
| F-011 | P2 | Dataplane → KPI/report | Scalar answer and evidence contain 35, but `kpis` is null and the Excel metric grid is empty; 35 appears only in narrative text | `dataplane-chat.log`, `export-reopen.json`, `export-cells.json` |

### Confirmed causes

- **F-001:** XLSX rows are converted with `dict(zip(header, row))` before duplicate names are checked. A dictionary overwrites the earlier duplicate, so the later schema check cannot detect the lost column. The original uploaded bytes are preserved; the derived snapshot is incomplete.
- **F-002:** `pa.Table.from_pylist()` infers fields from the first mapping when no schema is supplied. The ingestion code does not validate or union subsequent record keys first. This behavior is confirmed by the installed Arrow 26.0.1 docstring and the [Apache Arrow API documentation](https://arrow.apache.org/docs/python/generated/pyarrow.Table.html).
- **F-003:** Logout records revocation in `AuthService`, but protected-route authentication uses the separate `core.security.verify_token()` path. That path validates signature, expiry and token type without consulting the revocation store.
- **F-004:** Refresh-token revocations are kept in a process-local set. Restarting the API discards that set, allowing an otherwise valid revoked refresh token to be used again.
- **F-005:** `DatasetVersion` declares `uq_dataset_active_version`, but the migrated database lacks it. A synthetic transaction successfully inserted two active versions and was rolled back. A read-only live check found **zero currently conflicting datasets**; the finding concerns the missing invariant, not an observed live conflict.
- **F-006:** Arrow infers non-UTF-8 CSV strings as binary. The engine's scalar conversion leaves bytes unchanged, and the result serializer rejects them. Ingestion reports success before this downstream failure.
- **F-007:** Alembic's target is `Base.metadata`, while membership/binding and dataplane tables use separate Core metadata. The generic schema compatibility check reports compatible while autogeneration sees these tables as extra. The comparison was read-only: no generated removal or other DDL was applied.
- **F-008:** Linux XGBoost 2.1.4 declares the NVIDIA NCCL dependency. Pinning Torch to `2.5.1+cpu` does not prevent that separate dependency. Existing Torch/sentence-transformer systems were preserved as previously instructed; removing them is not an audit repair already authorized here.
- **F-009:** Volume checks wait for eight same-weekday observations, but distribution checks compare against a single previous summary. Their cutoffs are hardcoded (`6 × MAD`, `3 × standard deviation`), and `Limits` has no history/threshold settings. This is a mismatch with the requested monitoring acceptance policy, not proof that a business anomaly occurred.
- **F-010:** The request schema accepts arbitrary format strings, while the report generator supports PDF/DOCX/XLSX/PPTX. CSV is not supported, and the rejection escapes as a server error. Supporting CSV versus explicitly rejecting it is a repair-plan decision; the API should not promise a successful CSV export today.
- **F-011:** Dataplane chat returns result rows and citations without a structured KPI mapping. The report consumes those missing KPI fields, yielding an empty metric grid despite correct narrative text. The scalar response's null chart alone is not treated as a defect.

## Stage 2 verification matrix

PASS applies to the stated fixtures and commands, not every possible dataset or all 264 endpoints.

| Item | Status | Evidence and boundary |
| --- | --- | --- |
| 1. Four flag combinations | PASS | Four `verify_setup_journey.py` runs; equal legacy numeric result and valid PDF. Native dataplane checked separately. Universal exception fallback is not proven and must not bypass authorization/resource limits. |
| 2. Config/env | PASS | `env-key-comparison.json`: all 56 actual key names are represented in the example. Defaults/Compose provide additional optional flags. Real container settings and startup verified; no secret values printed. |
| 3. Dependencies | FAIL | Clean build and `pip check` pass, but F-008 violates the no-GPU condition. Existing deep-learning libraries also remain, per earlier preservation instructions. |
| 4. Database | FAIL | Empty migration chain/single head and PostgreSQL restart recovery pass. F-005/F-007 prevent claiming no schema drift. Observed session snapshot had no idle-in-transaction connections; extended transaction monitoring is unverified. |
| 5. Dataplane | FAIL | F-001/F-002/F-006. UTF-8 BOM and TSV accepted; empty, header-only and duplicate-header CSV rejected. Five sum/avg/min/max/count pandas/DuckDB comparisons pass. Resource settings, idempotency/lease/timeout tests pass in the suite. |
| 6. SQL safety | PASS | Existing validator rejection, isolation and bounded execution tests all passed. The actual TLS PostgreSQL fixture verified read-only pushdown and rejection after granting a write privilege; the certificate was supplied, so this test did not skip. |
| 7. Semantic/chat/evidence | FAIL | Native queued→complete result and stored evidence agree; F-011 leaves KPI/report integration incomplete. |
| 8. Monitors/dashboard | FAIL | Real browser verified missingness units, findings and cleaning flow. F-009 fails the requested configurable/minimum-history policy. |
| 9. Learner/router | UNVERIFIED | Router fallback, allowlists, shadow, approval and rollback regression tests pass. This audit did not run a new evaluation of a live promoted tenant model against the private golden set, so live accuracy versus keyword baseline is not newly established. |
| 10. Failure Memory | PASS | Real isolated PostgreSQL/Chroma index/retrieval tests pass. Stopping Chroma still allowed chat to return the correct total 1,180. |
| 11. Reports/exports | FAIL | PDF and Excel download/reopen and contain evidence value 35 in text. CSV returns 500; Excel's numeric grid is empty for this dataplane result. |
| 12. Multi-tenancy | PASS | Existing two-tenant API and restricted-role tests for datasets, artifacts, learning/feedback/memory and reports passed. Synthetic identities only; no attempt to access another real user's data. |
| 13. Frontend/API contracts | UNVERIFIED | Typecheck/lint/build and seven browser scenarios pass, including 401, empty/loading/error recovery. Exhaustive response compatibility for every endpoint and the mobile client was not tested. |
| 14. Resilience | PASS | Actual Redis/Chroma stops preserve deterministic chat. Actual worker kill during a 4M-row ingestion resumes on attempt 2 after 64.65 s, preserving source hash. PostgreSQL restart preserves dataset and exact PDF bytes. |
| 15. Security basics | FAIL | F-003/F-004. Existing expiry/access-type/tenant/upload-limit tests pass. A configured chat rate limit was not found in the inspected route/middleware; a rate-limit load test and exhaustive secret-log scan remain unverified. |
| 16. Performance | PASS | Warm API journey including runner startup: 9.79 s. 10M-row aggregate: 109.056 ms engine time, 0.317 s total query process work, 99,762,176 bytes peak RSS; exact oracle passes under 1 GiB container / 512 MB engine limits. |

The performance fixture has three numeric columns and four groups; it does not establish a wide-table, join, high-cardinality or concurrent-user SLA. Docker reports 5,084,336,128 bytes available (about 4.74 GiB). No Spark/GPU workload was introduced.

## Safety net and audit procedure

Backups: `C:/Users/chinm/.codex/backups/integration-audit-20261108/`.

- Non-mutating tracked-state stash snapshot retained in Git; its object ID is in `stash-id.txt`. The working tree was not cleared. `git diff stash@{0}` showed no tracked application changes from this audit.
- `source-before.tgz`: source including untracked work, excluding local environments, runtime storage, `.env` and build caches.
- `storage-before.tgz`: storage backup, 8,394 archive entries; includes uploaded/Parquet storage and persistent keys. Keep private.
- `database-before.dump`: custom-format live PostgreSQL dump, successfully listed by `pg_restore --list` (623 lines).
- Backup checksums: `backup-hashes.json`. `.env` was neither printed nor committed.

No live services were stopped/recreated. Restart and failure injection targeted only `dataanalyst-integration-audit-*`. Tests used `analyst_setup_test`, synthetic credentials and separate volumes. The fresh image tags did not replace `latest`. Temporary audit services were stopped at the end; their volumes remain available.

The initial browser/chat probes overlapped in one synthetic workspace, allowing one probe to change the metric selected by the other. Those logs are explicitly named `*-shared-fixture-invalid.log`; they are not findings. Separate-account reruns produced the accepted results. An initial worker probe started before API readiness, and the first kill occurred after job completion; neither establishes recovery. The accepted second kill probe observed attempt 2 and a matching checksum. Existing tests were not altered to accommodate these harness issues.

### Reproduction commands

Run from the repository root. The audit Compose overlays contain only synthetic settings. The TLS certificate is short-lived and must be regenerated/configured in the isolated PostgreSQL fixture before repeating the TLS test.

```powershell
# Build separate audit images.
docker compose -p dataanalyst-integration-audit -f docker-compose.verify.yml -f docker-compose.learning-verify.yml -f docker-compose.dataplane-browser.yml -f docs/integration-audit/20261108/compose-audit.yml build runner frontend-verify

# Full suite; configure the isolated TLS fixture and mount its public certificate first.
docker compose -p dataanalyst-integration-audit -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 -e DATAPLANE_TEST_CA=/tmp/test-ca.crt -v C:/Users/chinm/.codex/backups/integration-audit-20261108/test-ca.crt:/tmp/test-ca.crt:ro runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/integration-audit-full.xml

# Small synthetic ingestion reproductions; use the audit image after building it.
Get-Content -Raw docs/integration-audit/20261108/ingestion_probe.py | docker run --rm -i --entrypoint python dataanalyst-backend:integration-audit -

# Real HTTP probes require the isolated API and seeded synthetic account.
docker compose -p dataanalyst-integration-audit -f docker-compose.verify.yml run --rm --no-deps runner python docs/integration-audit/20261108/http_probe.py --mode auth
docker compose -p dataanalyst-integration-audit -f docker-compose.verify.yml run --rm --no-deps runner python docs/integration-audit/20261108/http_probe.py --mode dataplane
```

Files inspected include both Compose stacks/overlays, Dockerfiles and dependency manifests; application config, startup, authentication/security and database/session/schema code; migration environment, dataset/version/job models; dataplane API/records/service/worker/supervisor/ingestion/engine/compiler/validator/chat/quality/cleaning/reporting; learning evidence/router/column/selection/memory code and tests; analysis sessions/history/report generation; frontend dataplane service/browser runner and check scripts. The audit only added documentation, probe scripts and evidence.

## Restore and next step

No live application rollback is needed: no repairs were applied. Do not apply the stash over the current dirty working tree. To inspect the saved tracked state without touching it:

```powershell
$auditBackup = 'C:/Users/chinm/.codex/backups/integration-audit-20261108'
$snapshot = (Get-Content "$auditBackup/stash-id.txt").Trim()
git show --stat $snapshot
```

For a restore drill, extract into a **new empty directory**, not over the workspace:

```powershell
$restore = 'C:/Users/chinm/.codex/backups/integration-audit-restore-review'
New-Item -ItemType Directory -Path $restore
tar -xzf "$auditBackup/source-before.tgz" -C $restore
tar -xzf "$auditBackup/storage-before.tgz" -C $restore
```

Restore the dump only to a separately created empty review database, with `pg_restore --no-owner --no-acl --dbname=<review-database> <database-before.dump>`. Restoring live data or changing published contracts is not part of this audit. No destructive cleanup or database downgrade was performed.

**Next is Stage 3: prepare the defect-by-defect repair plan, then obtain its approval before changing application code.** This follows the attached prompt's explicit Stage 2 and Stage 3 stops. Suggested but not done: broaden golden/contract coverage, add documented rate-limit policy, and evaluate high-cardinality performance after the integrity/security defects are repaired.
