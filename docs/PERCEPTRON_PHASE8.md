# Phase 8: read-only learning dashboard

**Status: complete and deployed.** All 331 backend tests, frontend typecheck/build and enabled/disabled browser checks passed. The first attempt was reverted under the regression gate and remains documented in [the attempt report](PERCEPTRON_PHASE8_ATTEMPT1.md).

## 1. Design rationale

1. Add a protected `/learning-dashboard` page and one authenticated `GET /api/v1/perceptron/dashboard` endpoint. Preserve the existing Verified Learning workspace, learner runtimes, public contracts and model approval fingerprints. No migration is required.
2. Show persisted evidence without running a learner. Accuracy comes from successful golden-set promotion records. Shadow agreement is separately labeled; failure counts are not trusted labels. Weight history returns metadata rather than model payloads.
3. Authorize active workspace membership and use a separate PostgreSQL `READ ONLY` transaction, existing row-security context, and explicit tenant/workspace/actor/owned-dataset filters. Tenant-wide router metadata is labeled as shared. Other evidence is limited to the user's accessible datasets; deleted, archived and purged datasets are excluded.
4. Bound reporting to 1–90 days, 100 promotion records per audit source and version pages of 1–100 rows with a maximum offset of 10,000. Queries have a 1.5-second statement timeout and 100ms lock timeout. Errors are sanitized. The page cancels superseded requests, hides stale results and offers retry.
5. Keep the live learning flag unchanged. When disabled, the endpoint authorizes access but skips learning-table queries and the page displays the disabled state. There are no training, promotion, rollback or configuration controls. Existing authentication and request auditing remain; the dashboard's evidence transaction cannot write.

## 2. Files read and changed

Read the master prompt, prior phase reports and saved patch; API registration/application factory; memory adapter, recall, review, planner and tests; original Chroma failure logs; learning schemas and release/column/selection lifecycles; ownership/workspace authorization, authentication and database dependency; existing Verified Learning page/service; frontend routing/layout/API client/styles/Vite/package configuration; isolated Compose, browser scripts and test runner. Applied the local `supabase-postgres-best-practices` skill and row-security guidance for reporting queries. Existing files and callers were read before editing.

| File | Purpose |
| --- | --- |
| `backend/app/api/v1/routes/router.py` | Register the new GET route |
| `frontend/src/App.tsx` | Protected dashboard page |
| `frontend/src/layouts/AppLayout.tsx` | Navigation and title |
| `backend/app/learning/dashboard.py` | Scoped read-only summaries and validated metrics |
| `backend/app/api/v1/routes/perceptron_dashboard.py` | Authentication, query bounds and no-store response |
| `backend/tests/test_perceptron_dashboard.py` | 22 dashboard checks |
| `backend/tests/test_perceptron_memory_timeout.py` | Real HTTP timeout, fallback, recovery and isolation regression |
| `frontend/src/services/perceptronDashboardService.ts` | Typed GET-only service |
| `frontend/src/pages/app/LearningDashboardPage.tsx` | Filters, summaries, accuracy timeline, mistakes and version history |
| `frontend/src/styles/learning-dashboard.css` | Responsive accessible presentation |
| `scripts/seed_dashboard_browser.py` | Synthetic browser fixtures and evidence hashes |
| `frontend/scripts/verify-dashboard-browser.mjs` | Real Chromium/API journey |

## 3. Complete diff and behavior

[Complete runnable diff](perceptron-verification/phase8.patch) contains three modified and nine new files against the exact pre-phase working tree. The reverse check passed. Earlier work remains on `feature/learning-layer`; no Git identity or commit was created. Pre-phase source/OpenAPI backups are in `C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase8-20261107`. The [first-attempt patch](perceptron-verification/phase8-attempt1.patch) is preserved separately.

Use **AI Intelligence → Learning Dashboard**, select a workspace and choose 7, 30 or 90 days. Workspace selection is preserved in the URL. Version history covers all dates with Previous/Next controls. Responses use `Cache-Control: private, no-store`. Invalid evaluation summaries are omitted with an explicit count; capped results show a truncation notice. Empty evidence shows an empty state and unavailable agreement rather than a fabricated percentage.

Accuracy rows show promotion time, learner/version, correct/case denominator and benchmark hash. Provider reward is separate; correctness requires every eligible exploratory arm to pass. Only successful promotions were persisted by earlier lifecycles, so this is historical promotion evidence, not rejected-candidate history or production accuracy. Different benchmark hashes are not directly comparable. Selected weights in storage do not imply that runtime approval checks currently pass. Raw questions, dataset contents, weights, prompts and credentials are not returned.

The resumed work adds only a test to the memory subsystem: production memory code, the one-second HTTP deadline, the 2.5-second outer deadline and the original happy-path test assertion are unchanged.

## 4. Exact verification commands

A fresh isolated project was used for the resume. Earlier verification volumes were retained. An empty test-database dump was saved before existing migrations initialized it. Full regression and browser runs are sequential.

```powershell
docker compose -p dataanalyst-perceptron-phase8 -f docker-compose.verify.yml up -d --wait --wait-timeout 120 postgres redis chromadb
docker exec dataanalyst-perceptron-phase8-postgres-1 pg_dump -U setup -d analyst_setup_test -Fc -f /tmp/pre-baseline.dump
docker compose -p dataanalyst-perceptron-phase8 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase8-resume-baseline.xml
docker compose -p dataanalyst-perceptron-phase8 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests/test_perceptron_dashboard.py backend/tests/test_perceptron_memory_timeout.py --junitxml=/verification/phase8-resume-focused.xml
docker compose -p dataanalyst-perceptron-phase8 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase8-resume-final.xml
```

Frontend baseline and final checks use the exact network-disabled/read-only scratch-copy command in [the attempt report, section 4](PERCEPTRON_PHASE8_ATTEMPT1.md#4-exact-verification-commands): `npm run typecheck` then `npm run build` with installed locked dependencies. No source dependencies were updated.

The browser image `dataanalyst-dashboard-browser:verification` caches Chromium and the installed Playwright package from the first attempt. Its creation command is in that report. Account credentials stay in the isolated volume and are not copied into evidence. For reruns use fresh temporary container names or deliberately reuse stopped ones; retain data volumes.

```powershell
docker compose -p dataanalyst-perceptron-phase8 -f docker-compose.verify.yml run -d --no-deps --use-aliases --name phase8-resume-api -e LEARNING_ENABLED=true -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 api
docker compose -p dataanalyst-perceptron-phase8 -f docker-compose.verify.yml -f docker-compose.learning-verify.yml up -d --no-deps frontend-verify
docker compose -p dataanalyst-perceptron-phase8 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/seed_dashboard_browser.py seed
docker run --rm --network dataanalyst-perceptron-phase8_default --shm-size=256m --mount 'type=volume,source=dataanalyst-perceptron-phase8_verify_storage,target=/verification' --mount 'type=bind,source=C:\data analyst\frontend\scripts\verify-dashboard-browser.mjs,target=/app/scripts/verify-dashboard-browser.mjs,readonly' --entrypoint node dataanalyst-dashboard-browser:verification /app/scripts/verify-dashboard-browser.mjs
docker stop phase8-resume-api
docker compose -p dataanalyst-perceptron-phase8 -f docker-compose.verify.yml run -d --no-deps --use-aliases --name phase8-resume-api-disabled -e LEARNING_ENABLED=false -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 api
```

After the disabled API's `/health/ready` returns 200:

```powershell
docker run --rm --network dataanalyst-perceptron-phase8_default --shm-size=256m --mount 'type=volume,source=dataanalyst-perceptron-phase8_verify_storage,target=/verification' --mount 'type=bind,source=C:\data analyst\frontend\scripts\verify-dashboard-browser.mjs,target=/app/scripts/verify-dashboard-browser.mjs,readonly' --entrypoint node dataanalyst-dashboard-browser:verification /app/scripts/verify-dashboard-browser.mjs --disabled
docker compose -p dataanalyst-perceptron-phase8 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/seed_dashboard_browser.py check
```

## 5. Actual verification

The first attempt's final run had 329 passes and one baseline-existing failure, so the entire phase was reverted without deployment. The user then authorized investigation and resumption. Its failed XML and report are retained, not overwritten by the resumed checks.

Investigation: original client logs show collection lookup at `09:01:37.321` and planner fallback at `09:01:38.324`; [Chroma logs](perceptron-verification/phase8-timeout-server.log) show the query reaching index processing at `09:01:39`. This matches the unchanged one-second HTTP read deadline being exceeded. With Phase 8 reverted, the unchanged test passed standalone: **1 passed in 38.34 seconds**. The host-level cause of that latency spike was not established. No deadline, assertion or production memory code was weakened.

The new regression uses actual HTTPX against a deliberately delayed local HTTP server and real isolated PostgreSQL approval data. It confirms `httpx.ReadTimeout` with `client.timeout.read == 1.0`, exact baseline-plan equivalence excluding the fresh workflow ID, successful approved recall on the next request, no request-time query retries and no index calls by an unauthorized actor.

Resumed baseline: **308 passed**, five existing forecasting warnings, **281.00 seconds**. Focused: **23 passed in 20.62 seconds**. Final full run: **331 passed**, the same five warnings, **246.13 seconds**. Frontend baseline typecheck/build passed, Vite **3.04 seconds**. Evidence: [baseline XML](perceptron-verification/phase8-resume-baseline.xml), [focused XML](perceptron-verification/phase8-resume-focused.xml), [final XML](perceptron-verification/phase8-resume-final.xml), [standalone test XML](perceptron-verification/phase8-recovery-reproduction.xml).

Dashboard tests cover authenticated GETs, input bounds, mutation-method rejection, flag-off query avoidance, empty/malformed evidence, accuracy/agreement separation, pagination, archival, revoked membership, tenant/actor isolation under restricted and privileged connections, truncation, missing database and database-enforced read-only behavior.

All 308 baseline test identities remain in the final suite; 23 new tests were added. Final frontend typecheck/build passed, Vite **2.55 seconds**. The Docker rebuild reused the same base images and cached dependency layers.

The resumed enabled and disabled Chromium journeys both passed against the real isolated API and local password authentication. They cover protected navigation, reviewed metrics, separate provider reward and shadow agreement, pagination, period filtering, empty-workspace isolation, URL restoration, mobile layout and zero page errors. The outage check alone substitutes a 503 response, verifies stale evidence disappears, then restores the real API and verifies retry. Every dashboard request was GET. Before/after hashes confirm all seven learning tables were byte-equivalent for the synthetic tenant. Account credentials remain only in the isolated volume.

Evidence: [enabled checks](perceptron-verification/phase8-resume-browser/enabled.json), [disabled checks](perceptron-verification/phase8-resume-browser/disabled.json), [desktop](perceptron-verification/phase8-resume-browser/dashboard-desktop.png), [mobile](perceptron-verification/phase8-resume-browser/dashboard-mobile.png), [disabled state](perceptron-verification/phase8-resume-browser/disabled.png). The screenshots were inspected. Isolated services were stopped without deleting their data or volumes.

Saved Docker image manifests: backend `sha256:9b201fc3f00f8ba375cfffdbdacb4b299cc18740c9819e0e6c3afe10bde3d55f`; frontend `sha256:d77f1a8dd60c4977bdd19d972701091ef4c701678031e224cdef42c114bd0c92`. Deployment commands:

```powershell
docker compose build backend frontend
docker compose up -d --no-deps --wait --wait-timeout 120 backend frontend
```

No live migration was needed. All five live Docker services are healthy with `unless-stopped` restart policies; existing named data volumes were preserved. Readiness confirms schema, PostgreSQL, Redis and Chroma are healthy. Live schema remains `018_selection_policies`. Learning remains disabled, and learner weights, active weights, feedback, mistakes, shadow predictions, router releases, memory links, resolver events and selection events are all zero. No synthetic test data or model was inserted into the live database. `.env` and original datasets were not edited.

The complete parsed OpenAPI document, after removing only the new dashboard path, is identical to the pre-phase snapshot: all **222 prior paths / 249 operations** are unchanged. The new authenticated GET brings totals to **223 paths / 250 operations**. The live dashboard API returns 401 without authentication; `http://localhost:5173/learning-dashboard` serves the application successfully. [Service evidence](perceptron-verification/phase8-services.json) records health, images, restart policies and volumes. The complete phase patch still passes its reverse check. All phases in the supplied build prompt are now implemented; live learning remains disabled pending reviewed production activation through the existing lifecycle controls.

## 6. Rollback

No schema or data rollback is needed. Run each command only after its predecessor succeeds:

```powershell
git apply --reverse --check docs/perceptron-verification/phase8.patch
docker compose stop backend frontend
git apply --reverse docs/perceptron-verification/phase8.patch
docker compose build backend frontend
docker compose up -d --no-deps --wait --wait-timeout 120 backend frontend
```

Preserve `.env`, datasets and Docker volumes. The dashboard does not change the learning flag. Earlier phases and unrelated work remain intact. Phase 8 is the final phase in the supplied build prompt.

