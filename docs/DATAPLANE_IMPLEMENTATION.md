# Large data processing and monitoring: implementation and handoff

Deployed locally on 8 November 2026. The user authorized completion of all phases after the Phase 0 audit, including reuse of durable jobs, dataset versions, psycopg and the available 4.74 GiB Docker budget. This supersedes the audit's historical pending-approval note.

## Delivered scope

| Phase | Result |
| --- | --- |
| 0 | Baseline audit, source/database backups and legacy ingestion measurements. See `DATAPLANE_PHASE0.md`. |
| 1 | Default-off feature flag, bounded configuration, existing durable job infrastructure, isolated worker and additive migration 019. |
| 2 | DuckDB engine and bounded CSV/TSV, JSONL/NDJSON, XLSX and Parquet ingestion; immutable originals, checksummed Parquet snapshots and restart checkpoints. |
| 3 | Restricted aggregate SQL grammar, parameter binding, authorization, process timeout, memory/spill/result limits, cancellation and lease-fenced publication. |
| 4 | User-defined immutable metrics, aggregate compiler, grouped queries, curated Parquet results and stored evidence; flagged chat routing. |
| 5 | Missingness, duplicates, schema changes, numeric summaries, snapshot age and historical weekday baselines; recurring quality jobs and findings in Data Health. |
| 6 | Sample cleaning proposal, explicit approval, new inactive dataset version, rejected-row quarantine and reconciliation. Originals remain unchanged. |
| 7 | Responsive Data Health dashboard, jobs, definitions, results and authenticated evidence PDF downloads. |
| 8 | Allowlisted, verified-TLS PostgreSQL pushdown with restricted credentials, read-only transaction, scan estimates and bounded results. |
| 9 | Independent aggregate oracles at 1M, 10M and 100M rows, baseline comparison and decision below. |

Existing learning and embedding systems remain in place. No new model training or Spark service was added. Spark and streaming interfaces are extension points only.

## Use and deployment

Open http://localhost:5173/data-health and sign in. Select a workspace, upload a supported file, wait for its snapshot, register a metric and run an aggregate query. Review quality findings and cleaning samples before approving a new version. Download a PDF from stored query evidence.

Deployment is explicitly enabled with:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dataplane.yml --profile dataplane up -d --build backend frontend dataplane-worker
```

The deployed release used verified locally built images with `--no-build`; the checked-in Dockerfile and pinned requirements support rebuilds. Migration 019 is applied by the migration service before backend/worker startup. Base Compose alone defaults the new feature off. `.env` was not changed.

The worker has a 1 GiB container memory limit, no additional swap, two CPUs and one job slot. DuckDB is limited to 512 MiB. Defaults include a 120-second task timeout, 100 MiB upload cap, 4 GiB scan cap, 2 GiB spill cap and a 5,000-row/1 MiB result cap. Dashboard previews and PDF tables are additionally bounded.

Files persist in the host's `storage/dataplane` bind mount. Metadata persists in the existing PostgreSQL volume. Containers use `unless-stopped`; Docker itself must be running. Back up both database and storage together, including the credential encryption key. Restarting/recreating a container does not erase these volumes. Do not use `down -v` as a restart procedure.

```powershell
docker compose -f docker-compose.yml -f docker-compose.dataplane.yml --profile dataplane ps
docker compose -f docker-compose.yml -f docker-compose.dataplane.yml --profile dataplane logs --tail 100 dataplane-worker
```

## Company PostgreSQL configuration

No real company credentials were supplied. The adapter is implemented and tested against an isolated TLS-enabled PostgreSQL server; external company connectivity is not claimed.

Set `DATAPLANE_POSTGRES_HOSTS` to exact permitted hostnames in the deployment environment before recreating backend and worker. Use a dedicated login with SELECT permission on the intended table, without administrative or write privileges. The remote certificate must validate against trusted roots; a private CA requires a mounted CA file and `DATAPLANE_POSTGRES_CA_FILE` in both services. Do not disable certificate verification.

An authenticated workspace manager registers the source with `POST /api/v1/dataplane/connectors?workspace_id=...`: `name`, `host`, `port`, `database`, `username`, `password`, `schema_name`, `table`. The response supplies connector and dataset IDs. Register a metric against that connector using `/metrics`, then submit its semantic plan through `/query`. API schemas are available at http://localhost:8000/docs. Passwords are encrypted at rest; connector registration reports unverified until an actual job succeeds. There is no connector configuration screen in this release.

## Verification evidence

Artifacts are under `dataplane-verification/build-20261108/`:

- `backend-full.xml`: 382 tests passed, with five existing forecasting warnings.
- `backend-release-focused.xml`: final 50 dataplane tests passed after the final typing and raw/curated-output changes. The full-suite count is from the preceding revision; it is not a claim that the full suite was rerun after those changes.
- `browser/results.json`: seven real browser scenarios passed, including separate-worker upload, independently expected totals, PDF download, cleaning approval, stale-state recovery and mobile layout.
- `scale-benchmark.json`: all three aggregate benchmark oracles passed.
- `ingestion-comparison.json`: final 2M-row ingestion comparison, source hash unchanged.
- `deployment.json`: final local deployment and restart health checks.

Frontend ESLint, Prettier, TypeScript and production build passed. Focused backend fatal/name checks passed. Migration upgrade/downgrade/upgrade in the isolated database preserved all 61 existing tables and their checked metadata/data. Runtime `pip check` passed. Production reached migration `019_dataplane`, and all six services were healthy. The new worker was restarted and its health checked again.

The TLS test fixture uses an expiring test-only certificate (`test-ca.crt`). Future TLS test runs must regenerate a matching server certificate with the isolated PostgreSQL hostname in its SAN, configure that isolated server's certificate/key and SSL setting, and pass the public certificate through `DATAPLANE_TEST_CA`. Never reuse this fixture as production trust.

## Measurements and decision

| Synthetic rows | Aggregate engine time | Process peak RSS |
| --- | ---: | ---: |
| 1 million | 18.99 ms | 94.1 MiB |
| 10 million | 97.44 ms | 95.1 MiB |
| 100 million | 716.45 ms | 99.9 MiB |

These are single-machine measurements over three numeric columns, four groups and highly compressible Parquet, under a 1 GiB container limit and 512 MiB DuckDB budget. They exclude file generation and are not a general latency guarantee. The 100M-row file was supplied directly to the engine, not uploaded through the default 100 MiB HTTP limit.

The same 2M-row, 87.42 MiB CSV used in Phase 0 now ingests in 4.80 seconds, with 154.0 MiB peak RSS, producing 88 bounded Parquet parts. Its original checksum is unchanged. The legacy Phase 0 path exhausted its 2 GiB test container at this size.

Decision: retain DuckDB and PostgreSQL pushdown for this deployment. These measurements do not justify adding Spark within the current memory budget. Reevaluate using representative high-cardinality, wide-column and concurrent workloads before expanding infrastructure.

## Deliberate boundaries

Queries operate on one authorized source with registered aggregate metrics. Arbitrary SQL, joins, CTEs and unrestricted raw-row queries are unavailable. Business definitions must be registered by the user; none are invented. CSV identifier columns preserve text, and XLSX preserves native numeric cells. Incompatible late type drift is rejected rather than silently coerced. JSON arrays and legacy XLS are not supported by the new bounded upload route.

Storage uses bounded Parquet parts, not guessed business-date partitions. Snapshot age is not a business-event freshness guarantee. Historical baselines require enough history. Remote queries retain their result evidence and transaction snapshot identifier; a later remote rerun can differ if the source changes. Existing legacy analytics remain available, but security/resource denials do not trigger unrestricted fallback.

## Rollback

Source and database backups are in `C:/Users/chinm/.codex/backups/dataplane-20261108/`. Predeployment images are tagged `dataanalyst-backend:dataplane-before-20261108` and `dataanalyst-frontend:dataplane-before-20261108`.

For a feature rollback, stop `dataplane-worker`, set `DATAPLANE_ENABLED=false` in the deployment shell and recreate backend using the same Compose files. Keep storage and migration 019 intact so evidence remains available for recovery. Image rollback alone does not undo bind-mounted source: restore only the intended source files from the backup after reviewing intervening user changes. Database downgrade would discard the new artifact table and is not needed to disable the feature.
