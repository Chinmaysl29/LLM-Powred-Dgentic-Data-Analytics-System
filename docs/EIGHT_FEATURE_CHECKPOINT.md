# Eight-feature continuation — 9–10 November 2026

## Reviewer-policy continuation

The user selected explicit reviewer grants per dataset. The previous source-owner
authorization boundary is retained for raw records, downloads and execution.
Migration 023, `reviewer.py`, `reviewer_api.py` and `DatasetReviewPanel.tsx` now
provide owner-assigned, expiring reviewer access with optimistic revisions,
renewal/revocation, a restricted inbox and retained approval history. A separately
granted workspace viewer can approve submitted definitions, workflows and
aggregate results. Unsubmitted workflow drafts remain private. Source lifecycle,
membership changes, expiry and revocation are rechecked, including in the narrow
database projection functions. Self-grants and cross-workspace grants are denied.

Real restricted-role tests cover two-person dictionary/workflow/output approval,
owner-only raw/download/execution boundaries, stale grant revisions, expiry,
cross-dataset denial, membership removal and source archiving. The browser journey
also completed with two independently authenticated users and self-approval
disabled, then downloaded the owner's PDF and revoked the grant. The final full
backend regression is **419 passed, 1 skipped**, with five existing forecasting
warnings, in **374.21 seconds** (`backend-reviewer-full.xml`). The optional TLS
fixture remains unconfigured. Frontend lint, formatting, TypeScript and production
build passed. Migration 023 passed fresh-schema upgrade/no-op/roundtrip and both
company-record and reviewer-history downgrade guards (`migration-023.json`).
`reviewer-browser.json`, `reviewer-comparison.json`, `reviewer-workflow.pdf` and
`reviewer-desktop.png`/`reviewer-mobile.png` retain the two-user browser evidence.
The final reviewer UI shows the formula/source/coverage/validation summary before
optional technical metadata (`reviewer-inbox.png`). A separate PDF parser verified
the downloaded artifact's value **35**, formula `sum(amount)`, full coverage and
passed validation (`reviewer-pdf-validation.json`).

The earlier 022 guard release also passed **414 tests, 1 skipped**
(`backend-guarded.xml`); its final affected-path check passed **68 tests**
(`final-slices.xml`). These supersede the older failed Chroma attempt described
below, while preserving that failure's record. The intermittent recall failure
did not reproduce in either subsequent full run; no timeout or expected answer
was relaxed.

A second custom-format local backup was saved before migration 023:
`C:/Users/chinm/.codex/backups/company-review-20261110/before-reviewer-grants.dump`
(683,366 bytes). The local application is now at **023_dataset_review_grants**,
with healthy backend/worker and HTTP 200 readiness. Its grant table and
workflow/schedule artifact count are both zero: only synthetic test accounts
received grants. `.env` is unchanged. Two residual controlled-clock test schedules
were disabled with retained history after the final full run.

## Verified starting point

The supplied master prompt is a specification, not a prior completion record. The
working tree contains substantial earlier, uncommitted work; it is retained.

| Feature | Starting implementation | Missing at continuation |
| --- | --- | --- |
| Dictionary | `dataplane/api.py` metrics; `models/learning.py` BusinessDefinition | Draft/review/approval, effective scope, aliases, production binding |
| Calculation evidence | `dataplane/task.py`, `reporting.py`, DataHealthPage | Shared contract, redacted drawer, current definition advisories |
| Health impact | `dataplane/quality.py`, worker scheduling | Field lineage, explicit gates, incident review history |
| Cleaning | `dataplane/cleaning.py`, lease-fenced publication | Before/after rows, active-version selection and optimistic undo |
| Corrections | LearningLesson, independent verification, scoped retrieval, VerifiedLearningPage | Preserve and test; unsupported correction operators remain rejected |
| Comparison | Immutable query evidence exists | Comparability and deterministic deltas/export |
| Release checks | Existing dataplane/learning integration suites | Regression cases for the new vertical slices and CI wiring |
| Workflows | DurableJob leases, retries, cancellation | Approved immutable manifests, manual runs, artifact review, disabled schedules |

## Continuation design

Reuse BusinessDefinition and LearningAudit for dictionary review; reuse immutable
dataplane artifacts for workflow versions, policy, state events and incidents.
Reuse DurableJob and the single-slot dataplane worker for execution. No second
queue, vector authority, feedback store or report renderer is introduced.
Existing ungoverned metrics remain exploratory; company-approved runs require a
canonical eligible definition at enqueue, worker preparation and publication.
Historical evidence is never reconstructed when its inputs are unknown.

## Implementation map and scope

| Feature | Implemented and exercised | Important boundary |
| --- | --- | --- |
| 1. Dictionary | Existing BusinessDefinition store, immutable draft versions, review/approval/revocation, alias/effective conflicts, independent examples, approved query/chat binding | Metric definitions only; general glossary/dimension/join/mapping authoring remains incomplete |
| 2. Calculation evidence | Typed contract, source/definition/field lineage, accessible calculation dialog, redacted technical view, same-row PDF export, revocation advisories | Legacy records remain explicitly unknown; all legacy KPI/chart/report surfaces have not been connected to the drawer |
| 3. Health impact | Full-snapshot not-null/unique/range rules, required-field gates, deduplicated incidents, impact paths, unknown historical lineage, evidence-based recovery | Incremental connected-source monitors, relationship/freshness rule editors and organization-wide output indexing remain incomplete |
| 4. Cleaning | Bounded sample rows, immutable staged cleaning, quarantine/reconciliation, explicit version selection, optimistic undo, retained history | Existing trim/drop-null/deduplicate operators; no ambiguous date conversion or financial imputation is introduced |
| 5. Corrections | Existing independent verification, scope/expiry/revocation, review UI and reuse regressions retained; dictionary revocation invalidates dependent lessons | No second feedback store or new correction operator; existing adaptive join recipe is preserved rather than presented as new generic correction memory |
| 6. Comparison | Immutable input authorization, comparability checks, exact decimal deltas, undefined zero-baseline %, missing/new/removed groups, reconciled additive contributions, JSON export | Non-additive attribution is declined; normalized rerun UI is not implemented |
| 7. Release checks | New company regressions, wrong-example rejection, current full backend checks, migration roundtrip/rollback guard, CI migration hook, real browser journey | Provider evaluation and new representative-scale benchmarking are not run |
| 8. Workflows | Immutable aggregate manifests, review/activation/pause, resource caps, pinned/active-at-start sources, absolute/relative windows, durable manual runs, separate artifact approval, disabled schedules, DST/slot deduplication tests, explicit dataset reviewer grants | Single aggregate step; multi-step workflow authoring remains incomplete |

Core implementation locations: `backend/app/dataplane/company.py`,
`company_api.py`, `company_contracts.py`, `company_checks.py`, `company_schedule.py`,
and the extended existing `service.py`, `task.py`, `worker.py`, `api.py`, `chat.py`,
`cleaning.py`, `reporting.py`. The frontend extends DataHealthPage using
`CompanyWorkbench.tsx`, `CalculationDrawer.tsx` and `companyService.ts`; analysis
citations open the same drawer. Migration 021 extends the existing stores.

Architecture and limitations: [EIGHT_FEATURE_ARCHITECTURE.md](EIGHT_FEATURE_ARCHITECTURE.md).
Operations and exact commands: [EIGHT_FEATURE_OPERATIONS.md](EIGHT_FEATURE_OPERATIONS.md).

## Verification evidence

Artifacts are under `docs/company-verification/20261109/`.

- Baseline: `pytest backend/tests/test_dataplane_engine.py backend/tests/test_dataplane_integration.py`
  — **49 passed**. This includes real PostgreSQL/API/child-process checks.
- Earlier complete regression run: `DATAPLANE_ENABLED=false BACKGROUND_WORKER_ENABLED=false`
  with `python scripts/run_setup_tests.py backend/tests tests` — **411 passed,
  1 skipped**, five existing forecasting warnings, 304.70 seconds. See
  `backend-full.xml`. The two last company acceptance cases were added after
  collection of that run; the final release report below supersedes its count.
- Expanded company suite: **15 passed**, 59.21 seconds. Includes controlled-clock
  relative periods with independently expected 5, active-version changes after
  enqueue, matching/new/removed dimension contributions, warning-rule rejection
  when a definition requires nonmissing input, and historical recovery evidence.
- Final expanded full run: **412 passed, 1 failed, 1 skipped**, 344.18 seconds,
  five forecasting warnings (`backend-release.xml`). The failure was the existing
  `test_real_index_review_recall_and_privacy`: Chroma recall returned no candidate.
  The same test and all 15 company cases then passed together: **16 passed** in
  54.40 seconds (`company-and-recall.xml`), including the final literal-redaction
  guard. Its intermittent recall failure is unresolved; no timeout was increased,
  validation bypassed, assertion weakened or expected answer changed. The earlier
  complete 411-test pass is retained separately rather than presented as a pass of
  the final expanded suite.
- Migration: `python scripts/verify_company_migration.py` — upgrade/no-op upgrade/
  downgrade/upgrade preserve a representative legacy definition; new governance
  remains unknown, and lossy downgrade is rejected. `migration.json` records the
  outcomes. This runs in a freshly generated isolated schema and cleans up only
  that schema. The CI migration job runs it as well.
- Browser: `frontend/scripts/verify-company-browser.mjs` — **four end-to-end
  scenarios passed** with real authentication, separate worker, persisted company
  review, calculation dialog, downloaded comparison JSON and reviewed PDF.
  Expected/actual result **35**, self-comparison absolute delta **0**. Desktop and
  mobile had no uncaught browser errors or horizontal overflow. `browser.json`,
  `comparison.json`, `workflow.pdf`, `desktop.png`, `mobile.png` retain evidence.
- The real browser journey was repeated after the final application changes and
  passed again. A separate PDF parser reopened the downloaded workflow artifact
  and verified value **35**, formula `sum(amount)`, full coverage and passed
  validation (`pdf-validation.json`).
- Frontend: lint, Prettier source check, TypeScript and production build passed;
  final formatting/build checks are repeated after accessibility label changes.
- One separately running worker's four-row fixture recorded **193,597,440 bytes**
  process peak RSS and **4.002 ms** engine aggregate time. This is a tiny synthetic
  workload, not a scale benchmark or SLA. Existing engine/container limits remain
  conservative; earlier scale measurements were not rerun for this release.

The optional PostgreSQL TLS pushdown test is skipped because its expiring test
certificate fixture was not configured. No live LLM-provider evaluation, company
database connection, accuracy percentage or production acceptance is claimed.

The first broad test attempt inherited a dataplane-enabled HTTP fixture and an
uncontrolled background worker: 403 passed, 8 failed, 1 skipped, 1 teardown error.
The enabled flag intentionally rejected unbounded legacy fixtures, while the
worker competed with explicit test job claims. Verification now runs with explicit
flags, and `serve_setup_api.py` disables its competing worker. A genuine cleaning
preview cursor-consumption bug and shutdown CancelledError handling were fixed.
The 63-test focused regression run then passed, followed by the complete run above.
The first browser attempt exposed unstable select accessible names; explicit
labels fixed the issue and the real journey was rerun successfully.

## Local runtime and checkpoint

The application database was at migration 019 when work began; its backend was
unhealthy before these changes. A custom-format database backup was written to
`C:/Users/chinm/.codex/backups/company-review-20261109/before-company-review.dump`
(656,318 bytes). Migrations 020 and 021 were applied locally and backend/worker
restarted. The backend now returns HTTP 200 from `/health/ready`. `.env` was not
changed. No real company definition, approval policy or recurring schedule was
activated. No external messages were sent.
The final local backend and dataplane worker are healthy. The isolated worker's
inherited HTTP healthcheck was replaced by a heartbeat check and it is healthy
after recreation. Eight residual controlled-clock test schedules were explicitly
disabled with retained review history; the application database contains zero
workflow/schedule artifacts.

Full completion of the supplied master specification is **not claimed**. The
table's remaining authoring/review/integration gaps require further implementation;
real company rules and provider/
connector acceptance also remain deployment inputs. Do not approve this release
as satisfying every acceptance criterion merely because its supported paths pass.

Next checkpoint action: implement the remaining glossary/join/workflow authoring
and legacy evidence integrations before declaring the entire eight-feature
specification complete. Preserve the observed intermittent recall failure for
investigation if it recurs. The
current supported local flows and their verification artifacts are saved.
