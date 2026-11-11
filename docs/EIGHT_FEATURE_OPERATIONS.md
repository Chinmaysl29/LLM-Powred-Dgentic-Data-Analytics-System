# Company review: local operations

Read `EIGHT_FEATURE_CHECKPOINT.md` for actual verification and remaining work.
Read `EIGHT_FEATURE_ARCHITECTURE.md` for supported semantics and limitations.

## Run the local application

Use the repository root, `C:\data analyst`. Keep PostgreSQL metadata and
`storage/dataplane` together in backups. Preserve the source-credential encryption
key. Do not delete volumes to restart the application.

```powershell
docker compose -f docker-compose.yml -f docker-compose.dataplane.yml --profile dataplane run --rm migrate
docker compose -f docker-compose.yml -f docker-compose.dataplane.yml --profile dataplane up -d --build backend frontend dataplane-worker
docker compose -f docker-compose.yml -f docker-compose.dataplane.yml --profile dataplane ps
```

`migrate` uses this repository's migration runner and must reach
`023_dataset_review_grants` before processes import the extended models.
Migration 022 refuses conflicting active versions without choosing or deleting
records; it creates the existing model's partial unique index so legacy writers
also respect the single-active-version rule.
Existing configured Chroma pin and authentication settings are still required;
do not replace `.env` with sample credentials. `.env` is not modified by this work.

Open `http://localhost:5173/data-health`, sign in and choose an authorized workspace.
Upload a supported file and wait for a snapshot. In Company definitions and
reporting, select the source, create a draft using an actual approved company
meaning and examples, and submit it for review. A manager must decide the
self-approval policy explicitly before author approval is possible. No real
company policy or business definition is seeded by this implementation.

For independent review, select an owned snapshot and expand **Manage reviewers
for selected dataset**. Select a named member, enter an expiry and a reason, then
grant access. A coworker opens the same workspace's **Assigned review inbox** to
inspect and approve submitted definitions, workflows and aggregate outputs. Use
**Refresh company review** to retrieve another person's decision before owner
activation. An explicit self-approval policy is unnecessary for an independent
granted reviewer. Renewals use the displayed grant revision; stale changes are
rejected. Revocation and expiry remove subsequent reviewer access without
rewriting prior approval history. No grant is created automatically.

For deployments using non-superuser service roles, apply
`infrastructure/company_review_role_grants.sql` with the existing reviewed app and
worker role names after migration 023. The narrow projection functions require a
trusted migration owner able to read the FORCE-RLS-protected artifacts. Keep
PUBLIC execution revoked and retain their fixed search path. Do not transfer
function ownership to an untrusted app role or grant end users database access.
The app role needs the documented grant-table privileges; worker execution only
needs the narrow projection function to evaluate shared review-history policies.

Select an approved definition and business date to calculate. View the calculation
dialog and frozen evidence PDF. A critical finding appears as a blocking incident;
fix the input through reviewed versioning, rerun and link the passing recovery.
Changing an active version affects future runs, not historical reports.

Save a calculation as a workflow draft, review/approve/activate the version, then
run it manually. If artifact review is required, open its calculation dialog,
submit and approve the actual output before downloading the PDF. Schedules require
an explicit action after a successful manual run; leave them disabled until the
owner has reviewed the source-selection and time-window policy.

## Limits and schedules

The existing worker runs one heavy job at a time with a 1 GiB container limit,
512 MiB DuckDB budget, two threads, 120-second task timeout, 2 GiB temporary spill,
4 GiB scan budget, 5,000 aggregate rows and a 1 MiB result bound. Workflow versions
can lower memory/thread/time/result caps; they cannot increase these defaults.
These are configured limits, not a general workload performance guarantee.

Snapshot monitoring now defaults off with `DATAPLANE_MONITORING_ENABLED=false`.
Manual checks remain available. To enable the existing global monitoring loop,
an administrator must explicitly configure that environment flag and recreate
the worker. Workflow schedules remain separately controlled and default disabled.
In-app output is the only delivery destination. No email/Slack messages are sent.

Schedules repeat the approved manifest. `pinned` keeps the original snapshot;
`active_at_start` resolves the dataset's authorized active immutable version at
enqueue. `relative_window` supports completed local days over a timezone-aware
timestamp field. The resolved boundaries, source, definition and plan are frozen
for the queued run. The UI currently creates pinned workflows; advanced source/
window selection is available through the typed workflow API in `/docs`.

## Recovery and rollback

The queue persists attempts, leases, cancellation, timeouts and results in the
existing `background_jobs` table. Restart the worker to recover expired eligible
leases; publication is fenced and retries do not create a second report. Inspect
jobs and stable error codes in Data Health. `QUALITY_BLOCKED` links a retained
incident. `EXECUTION_REJECTED` can indicate revoked access, a revoked definition,
an incompatible manifest or an invalid source. Do not turn a failure into success
by editing queue rows or bypassing authorization.

Pause a workflow to stop new runs and prevent an in-flight run from publishing.
Disable its schedule before revising recurring behavior. New approved steps need
a new workflow version and review. Output approval is independent of workflow
approval. Old reports retain their frozen definitions and current revocation
advisories remain visible.

For application rollback, restore compatible code/images while retaining the
additive schema and storage. Migration downgrade cannot restore a previous prompt
or model. Migration 021 deliberately refuses downgrade while its new artifact
kinds or governed definitions exist; migration 022 also preserves its guard while
those company records exist. Migration 023 refuses to discard any retained
reviewer grant. A multi-revision downgrade can commit an empty newer revision
before an older guard refuses; inspect the actual revision and restore head
before restarting the current code.
Do not delete review evidence merely to make downgrade succeed.
Restore a coordinated database/storage backup if a database rollback is necessary.
Review any intervening user changes before restoring files.

## Reproduce verification in the existing isolated environment

The commands below target the synthetic `dataanalyst-integration-audit` project,
not the user's application database. Stop its background worker while test helpers
drive jobs; otherwise two workers can race for the same synthetic job.

```powershell
docker stop dataanalyst-integration-audit-dataplane-worker-1
docker exec -e DATAPLANE_ENABLED=false -e BACKGROUND_WORKER_ENABLED=false -w /repo dataanalyst-integration-audit-api-1 python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/eight-feature-full.xml
docker exec -w /repo dataanalyst-integration-audit-api-1 python scripts/pause_company_verification_schedules.py
docker exec -e COMPANY_MIGRATION_RESULT=/verification/company-migration.json -w /repo dataanalyst-integration-audit-api-1 python scripts/verify_company_migration.py
docker exec -w /app dataanalyst-integration-audit-frontend-verify-1 npm run lint
docker exec -w /app dataanalyst-integration-audit-frontend-verify-1 npm run format:check
docker exec -w /app dataanalyst-integration-audit-frontend-verify-1 npm run build
```

After test completion, restart the isolated API and worker so they load the same
source revision, then run the browser script with the existing shared test volume:

```powershell
docker restart dataanalyst-integration-audit-api-1
docker start dataanalyst-integration-audit-dataplane-worker-1
docker exec -w /repo dataanalyst-integration-audit-api-1 python scripts/seed_company_reviewer_browser.py
docker run --rm --entrypoint sh --network dataanalyst-integration-audit_default --volumes-from dataanalyst-integration-audit-frontend-verify-1 --mount type=volume,src=dataanalyst-integration-audit_verify_storage,dst=/verification -w /app dataanalyst-dashboard-browser:verification -c "apk add --no-cache chromium > /tmp/company-chromium-install.log 2>&1 && node scripts/verify-company-browser.mjs"
```

The browser account is synthetic and its credentials remain in the isolated
volume. Browser evidence contains no account secrets. CI already discovers the
new backend tests; its migration job now runs the guarded migration roundtrip.
Live provider evaluations are not part of these deterministic checks and must be
reported separately with credentials, cost budget, held-out cases and model IDs.
