# Phase 8: read-only learning dashboard

**Status: reverted; not deployed.** The final regression run failed a baseline-existing failure-memory test. The user's mandatory stop rule was applied: all three existing files were restored and all eight new implementation/test files were removed using the reverse patch. The complete patch, XML and browser evidence below are retained for review. Phase 7 remains the live application; Phase 8 is unfinished.

## 1. Design rationale

1. Add a separate **Learning Dashboard** page at `/learning-dashboard` and one authenticated `GET /api/v1/perceptron/dashboard` endpoint. Preserve the existing Verified Learning workspace, learner runtimes, routes, contracts and all model fingerprints. No migration is needed.
2. Report persisted evidence rather than running a model. Reviewed accuracy comes only from successful golden-set promotion records. Shadow agreement is separately labeled and is never presented as accuracy. Hard failures are counts, not trusted labels. Weight history returns metadata, not model payloads.
3. Authorize the active user and workspace in a separate PostgreSQL `READ ONLY` transaction. Require active workspace membership even for tenant admins, set the existing row-security context and explicitly filter tenant/workspace/actor/owned datasets. Tenant-wide router metadata is labeled as shared; scoped learner evidence is limited to the user's accessible datasets. Deleted, archived and purged datasets are excluded.
4. Bound reporting to 1â€“90 days, at most 100 promotion records per audit source, and version pages of 1â€“100 records with a maximum offset of 10,000. Queries have a 1.5-second statement timeout and a 100ms lock timeout. Errors produce a generic unavailable response. The page clears stale results when filters change or refresh fails, cancels superseded requests and offers retry.
5. Keep the feature flag unchanged. When learning is disabled, the authenticated endpoint returns disabled status without querying learning tables, and the UI hides evidence. There are no training, promotion, rollback or other mutation controls. Existing request auditing/authentication behavior is preserved; the dashboard's evidence transaction cannot write.

## 2. Files read and changed

Read the master build prompt and previous phase reports; API router registration and application factory; chat evidence, shadow, release, column and selection schemas/lifecycles; dataset ownership and workspace authorization; database dependency and current-user authentication; the existing Verified Learning route/page/service; application route/layout and API client; frontend CSS/package/Vite configuration; isolated Compose definitions and browser scripts; integration fixtures and verification runners. Applied `C:\Users\chinm\.codex\skills\supabase-postgres-best-practices\SKILL.md` and its row-security reference before authoring reporting queries. Existing files and their callers were read before modification.

| File | Change |
| --- | --- |
| `backend/app/api/v1/routes/router.py` | Register the new GET endpoint |
| `frontend/src/App.tsx` | Add the protected dashboard page |
| `frontend/src/layouts/AppLayout.tsx` | Add navigation and page title |
| `backend/app/learning/dashboard.py` | Read-only scoped aggregation and validated summaries |
| `backend/app/api/v1/routes/perceptron_dashboard.py` | Authenticated bounded query parameters and no-store response |
| `backend/tests/test_perceptron_dashboard.py` | 22 focused checks |
| `frontend/src/services/perceptronDashboardService.ts` | Typed GET-only API client |
| `frontend/src/pages/app/LearningDashboardPage.tsx` | Filters, summary cards, accuracy timeline, mistakes and version history |
| `frontend/src/styles/learning-dashboard.css` | Responsive layout and scrollable accessible tables |
| `scripts/seed_dashboard_browser.py` | Isolated synthetic browser fixtures and before/after evidence hashes |
| `frontend/scripts/verify-dashboard-browser.mjs` | Real Chromium/API journey |

## 3. Complete code and behavior

[Complete runnable diff](perceptron-verification/phase8-attempt1.patch) contains all three modified and eight new implementation/test files against the exact pre-phase working tree. Its reverse check passed. Source backups and pre-deployment OpenAPI are stored in `C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase8-20261107`. Existing work remains preserved on `feature/learning-layer`; no commit or Git identity was created.

The saved implementation adds **AI Intelligence â†’ Learning Dashboard**, with an accessible workspace selector and last 7, 30 or 90 days. It is not currently installed. The workspace is preserved in the URL. Version history covers all dates and has Previous/Next controls. The endpoint also accepts `days`, `offset` and `limit` within the bounds above. Responses use `Cache-Control: private, no-store`.

Accuracy rows contain the learner/version, promotion timestamp, exact correct/case denominator and benchmark hash. Provider reward is displayed separately; correctness requires every exploratory arm to pass the reviewed cases. Missing or invalid evaluation records are omitted with an explicit count. A truncation notice appears when the promotion-record cap is reached. With no data, the page says so and shows unavailable agreement rather than a fabricated percentage.

Important limits: only successful promotions were persisted by the earlier lifecycle implementations, so this page does not imply that rejected candidates were accurate or display nonexistent evaluation history. These historical golden results are not production accuracy, and differing benchmark hashes are not directly comparable. A stored selected weight version is not a claim that it currently passes runtime approval checks. Runtime collection remains disabled in the live application. Raw questions, dataset contents, model weights, prompts and credentials are not returned.

## 4. Exact verification commands

Baseline, focused and full checks:

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml up -d --wait --wait-timeout 120 postgres redis chromadb
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase8-baseline.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests/test_perceptron_dashboard.py --junitxml=/verification/phase8-focused.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase8-final.xml
```

Frontend checks before and after changes, in a read-only/network-disabled scratch container:

```powershell
@'
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const excluded=new Set(['node_modules','dist','.git','.ui-review']);
fs.cpSync('/source','/tmp/audit',{recursive:true,filter:p=>!path.relative('/source',p).split(path.sep).some(x=>excluded.has(x))});
fs.cpSync('/app/node_modules','/tmp/audit/node_modules',{recursive:true});
for(const task of ['typecheck','build']){const r=spawnSync('npm',['run',task],{cwd:'/tmp/audit',stdio:'inherit'});if(r.status!==0)process.exit(r.status??1);}
'@ | docker run --rm -i --network none --read-only --tmpfs /tmp:rw,exec,size=768m --mount 'type=bind,source=C:\data analyst\frontend,target=/source,readonly' --env npm_config_cache=/tmp/npm-cache --entrypoint node dataanalyst-frontend:latest -
```

The isolated browser API uses local synthetic authentication. It never loads the live `.env` file. The existing browser seed script registers a unique synthetic account; the new seed adds synthetic reporting records and records hashes of all seven learning tables for that tenant. Credentials stay inside the isolated verification volume and are excluded from copied artifacts.

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run -d --no-deps --use-aliases --name phase8-api -e LEARNING_ENABLED=true -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 api
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml -f docker-compose.learning-verify.yml up -d --no-deps frontend-verify
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/seed_dashboard_browser.py seed
docker run -d --name phase8-browser --network dataanalyst-perceptron-phase1_default --shm-size=256m --mount 'type=bind,source=C:\data analyst\frontend,target=/source,readonly' --mount 'type=volume,source=dataanalyst-perceptron-phase1_verify_storage,target=/verification' --entrypoint sh dataanalyst-frontend:latest -c 'apk add --no-cache chromium > /tmp/chromium-install.log 2>&1 && cp /source/scripts/verify-dashboard-browser.mjs /app/scripts/verify-dashboard-browser.mjs && node /app/scripts/verify-dashboard-browser.mjs'
docker commit phase8-browser dataanalyst-dashboard-browser:verification
docker run --rm --network dataanalyst-perceptron-phase1_default --shm-size=256m --mount 'type=volume,source=dataanalyst-perceptron-phase1_verify_storage,target=/verification' --mount 'type=bind,source=C:\data analyst\frontend\scripts\verify-dashboard-browser.mjs,target=/app/scripts/verify-dashboard-browser.mjs,readonly' --entrypoint node dataanalyst-dashboard-browser:verification /app/scripts/verify-dashboard-browser.mjs
docker stop phase8-api
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run -d --no-deps --use-aliases --name phase8-api-disabled -e LEARNING_ENABLED=false -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 api
```

Wait for the disabled API's `/health/ready` to return 200, then:

```powershell
docker run --rm --network dataanalyst-perceptron-phase1_default --shm-size=256m --mount 'type=volume,source=dataanalyst-perceptron-phase1_verify_storage,target=/verification' --mount 'type=bind,source=C:\data analyst\frontend\scripts\verify-dashboard-browser.mjs,target=/app/scripts/verify-dashboard-browser.mjs,readonly' --entrypoint node dataanalyst-dashboard-browser:verification /app/scripts/verify-dashboard-browser.mjs --disabled
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/seed_dashboard_browser.py check
docker stop phase8-api-disabled dataanalyst-perceptron-phase1-frontend-verify-1
```

For reruns use fresh temporary container names or reuse stopped verification containers deliberately; do not remove data volumes. The browser image caches only installed browser dependencies and source; mounted account files are not committed into it.

## 5. Actual verification

Baseline: **308 passed**, five existing forecasting warnings, **249.16 seconds**. Frontend baseline typecheck/build passed, Vite **1.62 seconds**. The initial focused suite passed **19/19**, then **21/21** with empty-state and truncation tests. Final focused suite: **22 passed in 22.04 seconds**, including the missing-database guard. Final frontend typecheck/build passed, Vite **2.11 seconds**.

The first full post-change suite passed **329 tests in 300.73 seconds**, with the same five existing warnings. The final full rerun, including the last missing-database test, finished with **329 passed, 1 failed**, five warnings, **245.37 seconds**. Evidence: [baseline XML](perceptron-verification/phase8-baseline.xml), [focused XML](perceptron-verification/phase8-focused.xml), [final XML](perceptron-verification/phase8-final.xml).

The failure was `backend/tests/test_perceptron_memory.py::test_authenticated_planner_uses_only_owners_memory`, line 240: the planner's `rules_triggered` was empty instead of containing `Added analytical checks from a reviewed past failure.` This test passed in the baseline and first full post-change run. The final logs show the Chroma collection lookup before fallback, but the underlying cause has not been established. It is not being labeled a flaky test or treated as a pass. The test and failure-memory implementation were not modified in this phase.

Backend checks cover actual authenticated GETs, all query bounds, unauthenticated access, rejection of every mutation method, disabled-flag query avoidance, empty/malformed evidence, separate agreement and accuracy, real pagination, archived datasets, revoked memberships, cross-tenant and cross-actor isolation under both restricted and privileged connections, explicit truncation, and PostgreSQL rejection of an attempted write inside the dashboard transaction. Reporting errors are sanitized.

The first browser run found missing `/api/v1` prefixes in the new frontend service; those were corrected. The next run reached the data/filter/pagination checks but its exact `getByLabel` workspace locator did not match Playwright's label-text calculation. Inspection confirmed the actual accessible combobox name was `Workspace`; the test was corrected to select that role/name. The subsequent full enabled journey passed. The real disabled-API journey also passed. These successful checks do not override the final regression failure.

Browser checks verify real password login, protected navigation, four synthetic reviewed evaluations, provider mean reward `0.9000` distinct from `50.0%` shadow agreement, history pagination, period filtering, empty-workspace isolation, URL restoration, mobile layout and zero page errors. The outage test deliberately substitutes one endpoint with 503, confirms stale evidence disappears, then restores the real API and verifies retry. All other dashboard data comes from the actual isolated API. Every dashboard request was GET.

Before/after hashes confirmed all **seven learning tables were byte-equivalent for the synthetic tenant** following browser reads. Existing generic HTTP auditing is outside these learning tables. Screenshots were visually inspected. Artifacts: [enabled checks](perceptron-verification/phase8-browser/enabled.json), [disabled checks](perceptron-verification/phase8-browser/disabled.json), [desktop](perceptron-verification/phase8-browser/dashboard-desktop.png), [mobile](perceptron-verification/phase8-browser/dashboard-mobile.png), [disabled state](perceptron-verification/phase8-browser/disabled.png).

No Phase 8 application image build, deployment or live migration was performed. No live model or learning record was created. `.env`, datasets and previous phases remain preserved. The saved patch passed its forward-application check after reversal. The failure must be investigated and Phase 8 revalidated before deployment.

Post-rollback verification: all three modified source files match their pre-phase backups **byte-for-byte**; the live OpenAPI document is identical to the pre-phase snapshot (**222 paths**, new dashboard endpoint absent). All five live Docker services are healthy, and readiness reports schema, PostgreSQL, Redis and Chroma healthy. The isolated API/frontend and database/cache/vector verification services were stopped without deleting data or volumes. Work stopped at the required regression gate; no retry was used to disregard the failure.

## 6. Rollback

The phase has already been reverted with `git apply --reverse docs/perceptron-verification/phase8-attempt1.patch`. No schema or data rollback was needed. The following deployment rollback recipe is retained for a future successful installation:

```powershell
git apply --reverse --check docs/perceptron-verification/phase8-attempt1.patch
docker compose stop backend frontend
git apply --reverse docs/perceptron-verification/phase8-attempt1.patch
docker compose build backend frontend
docker compose up -d --no-deps --wait --wait-timeout 120 backend frontend
```

Run each command only after its predecessor succeeds. Preserve `.env`, datasets and Docker volumes. The existing learning flag remains the runtime switch; this dashboard provides no controls that change it. Phase 8 is the final phase in the supplied build prompt.

