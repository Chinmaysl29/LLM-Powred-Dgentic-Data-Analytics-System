# Adaptive skills and repair selector

Implemented 5 November 2026. This extends the [verified supervisor](VERIFIED_LEARNING_SUPERVISOR.md), its seven persisted stages, authorization, validators, immutable source handling and PostgreSQL workers. The main LLM and embedding model remain frozen. Real logistic and MLP numerical weights are trained and exported; the observed synthetic candidates remain **evaluated, release blocked**. Rules/memory continues to execute. No production deployment or demonstrated production improvement is claimed.

## Implementation and flow

| Responsibility | Implementation |
| --- | --- |
| Strict contracts | `backend/app/schemas/adaptive.py`, relationship extension in `schemas/learning.py` |
| Persistence | `models/adaptive.py`, migration `012_adaptive_skills`, frozen `migrations/adaptive_schema_v1.sql` |
| Context, authorization and lineage | `services/adaptive_service.py`, existing `analysis_run_service.py` |
| Frozen LLM interpretation | `services/adaptive_interpretation.py`, existing provider selection; profiles, authorized definitions and compatible verified operator examples |
| Evidence-based diagnosis and approved skills | `services/adaptive_skills.py` |
| Eligibility, rules, learned scores and shadow | `services/adaptive_routing.py` |
| CPU fitting and safe JSON inference | `services/adaptive_selector.py` |
| Async replay, training, evaluation and composition | `services/adaptive_jobs.py`, existing durable worker registrations |
| Authenticated endpoints | `api/v1/routes/adaptive.py` |
| UI | `/verified-learning` → Adaptive; `components/AdaptiveWorkbench.tsx`, `services/adaptiveService.ts` |

Authenticate and bind the workspace, authorize every input/version, validate the explicit task, profile immutable inputs, pin compatible memory/catalog/model versions, filter eligible actions, rank, reserve bounded repair, reauthorize/recheck revocation, execute an approved function and run independent postconditions. Persist the decision before execution and the local action outcome afterward. Publish chart/narrative/report from one validated result. Budget is two total repairs per run plus the existing deadline. No arbitrary SQL, generated Python, installation or external side effects are added.

The optional LLM call sends bounded authorized profiles, definitions and validated lesson metadata, not raw dataset rows. It cannot execute tools or change workspace/input versions. A proposal requires explicit UI review before starting a run. Invalid/unavailable provider output retains the explicit contract. Unit/aggregation disagreement is established only against an authorized definition. Observations, hypotheses and distinguishing checks are stored separately. No chain of thought is retained.

## Executable skills

Eight repository implementations initialize only after independent checks pass: exact decimal parsing, checked vector conversion, refund aggregation per order, unique-refund join, refund-event counting, cardinality validation, explicit date validation and chart/result consistency. Validators are catalog tools; only applicable repair implementations enter ranking. Eligibility includes current workspace, active lifecycle, implementation hash, definitions, supported stage/task, schema and resource constraints. A revoked implementation cannot execute from a stale snapshot.

Candidate → testing → verified → active is separate from rejected, superseded and revoked. Testing runs in the existing worker against constants and rejection counterexamples. Three evidenced join-grain contexts can enqueue one bounded composition proposal per implementation version. The recipe consists only of approved aggregation, validated join, subtraction, aggregation and result validation; it remains a candidate until independently tested and separately activated by an administrator/owner. New tools still require repository code review and release.

The synthetic orders A=100/B=200 and refunds A=10/A=5 expose the naive join total385. The approved skill aggregates refunds by order, performs a validated one-to-one left join and independently reconciles285. A different compatible input yields590. Event-count tasks exclude this recipe and preserve both refund events (2). These are capability checks, separate from learned-policy improvement.

## Training data and prediction target

The prediction target is: **does this approved task/action pair satisfy its independent numeric/structural postconditions?** It is not whole-answer truth or preference. Only executed alternatives receive positive/negative outcomes. Untried actions, missing outcomes and infrastructure failures remain unknown; disputed labels are excluded. Ratings cannot manufacture correctness. Outcome evidence is immutable; delayed unknown/disputed reviews append label revisions and invalidate dependent bundles.

Live decisions collect continuously when enabled. Administrators can enroll a completed verified run into train/development cases with its exact task/result/source lineage. Existing live action features are then reusable without repeating the action. Isolated alternative replay adds evidence only on authorized train/development fixtures. Synthetic cases carry explicit provenance. No cross-tenant pooling occurs.

Case splits are immutable. Scenario groups, dataset identities and identical input fingerprints cannot cross train/development/calibration/final partitions. Previously analyzed inputs cannot be newly labeled as untouched final data. Final/calibration cases cannot be exposed through development replay. Changed settings, labels or code cannot reuse a previously exposed final set. Exact fingerprints do not prove independence of semantically similar cases; owners must supply representative groups and review near duplicates. The pilot's common synthetic template is explicitly not representative production evidence.

Sixteen numerical decision-time features describe input size/quality/precision, observed failure, remaining repairs and the candidate's approved method. Gold labels, future outcomes, private tenant identifiers and text embeddings are excluded. Embeddings are unused and explicitly versioned; the application's existing embedding weights remain unchanged. A common scorer ranks task/action pairs, rather than a fixed output neuron per skill. New implementations trigger cold-start rules fallback.

Default evidence thresholds:40 train action observations,6 train groups,8 positives and8 negatives, at least4 development actions with both classes. Configurable requests may raise or lower evidence thresholds within typed bounds; hard release safeguards cannot be disabled. Insufficient evidence completes the job with `insufficient_evidence` and no weights.

StandardScaler fits train only. Logistic candidates use C=0.1/1. MLP candidates use ReLU hidden layers32/16 and128/64, Adam, regularization0.01, explicit development loss and patience12; no implicit random early-stopping split. Seed17, up to120 epochs by default, CPU numerical threads1. Development chooses hyperparameters; final cases are loaded only after fitting. Process RSS is sampled at training boundaries/epochs, not a guaranteed whole-system peak. Inference latency covers the JSON scorer; policy latency covers the isolated executor and excludes queue/input loading. Provider cost is0 for approved local repair execution; CPU cost is not assigned a monetary estimate.

## Bundles, evaluation and operating states

Bundles contain JSON weights/biases, train-fitted scaling, feature order/version, embedding version, code/runtime/package compatibility, exact skill hashes, case/label snapshots, gates, metrics and provenance. No pickle, untrusted artifact upload or arbitrary module loading. Loader rejects malformed/nonfinite/topologically invalid or incompatible bundles. Missing/corrupt models and new skills fall back to rules. Source revocation/deletion, definition changes, label disputes and authorization loss invalidate dependent candidates. Current authority overrides frozen versions.

Paired final evaluation executes rules/memory, linear and MLP against the same skill catalog, input data, budget and validators. It records first repair success, final correctness, all repair attempts, rejected attempts, repeated errors, harmful verified answers, abstention, unknowns, latency and available cost. `first_attempt_correct` means the first repair succeeded (or an already correct/appropriately abstaining result); it is not unassisted raw execution accuracy. Repeated errors count recurring failure codes across final cases. Denominators and scenario-bootstrap intervals are included in artifacts. Selected-action classification loss is not presented as a policy improvement or off-policy estimate.

Release gates are declared before results: no final/first-attempt regressions, no harmful verified repair, mandatory validation/authorization/integrity, no provider-cost increase, p95 within1.5× baseline by default, configured trusted final scenario coverage (default30 groups) and actual policy benefit. Synthetic groups never satisfy trusted coverage. Prefer linear when its verified correctness/first-attempt performance matches MLP. Calibration is unavailable: no confidence percentages, Brier score or reliability chart is fabricated. Scores are raw routing logits; they are not probabilities of a correct answer.

| Mode | Behavior |
| --- | --- |
| disabled (default) | Rules execution; no adaptive decision/outcome collection |
| collection | Rules execution with durable local action evidence |
| shadow | Rules execution; learned scores recorded, no alternative side effects |
| active | Only a compatible candidate that passed all release gates may select repairs |

Controls update atomically with an expected generation. Existing runs pin their model/catalog; current rollback or revocation wins before execution. Rollback returns to collection/rules and retains previous model identity. No mutable model cache or live per-task weight updates exist.

## APIs and UI

All `/api/v1/adaptive` endpoints require backend authentication and workspace membership. Reads use pagination where applicable. Analysts may inspect/interpret authorized tasks; administrators/owners manage skills, cases, training, reviews and policy. Input ownership and workspace binding apply to APIs, workers, artifacts and downloads. FORCE RLS is tested with separate non-superuser/non-bypass API and worker roles; immutable-evidence triggers add protection.

| Endpoint | Purpose |
| --- | --- |
| `POST /interpret?workspace_id=…` | Validated interpretation/diagnosis; optional frozen provider |
| `GET /runs/{run_id}/context` | Pinned context and catalog/model references |
| `POST /skills/bootstrap`, `GET /skills[/{id}]` | Initialize tested catalog, inventory and revisions |
| `POST /skills/{id}/review` | Test, activate, reject, supersede or revoke with expected state |
| `POST /skills/detect-gaps/scan` | Schedule eligible bounded proposal |
| `GET /decisions`, `POST /outcomes/{id}/review` | Action evidence and delayed unknown/disputed review |
| `GET/POST /cases` | Immutable authorized grouped cases |
| `POST /replays`, `POST /training` | Durable idempotent work; return202 |
| `GET /jobs[/{id}]`, `POST /jobs/{id}/retry` | Scoped status and eligible bounded transient retry |
| `GET /models`, `GET /models/{id}/download` | Evaluated manifests and private immutable JSON download |
| `GET/PUT /controls`, `POST /rollback` | Collection, shadow, gated execution and rollback |

Use the Analysis tab to select metric, definition and optional second refund input. The Adaptive tab exposes Understanding, Skills, Decisions, Training and Controls. Training supports case registration, selected train/dev replay, frozen candidate fitting, actual async status, comparison metrics and downloads. Loading, empty, error and role-restricted states are explicit. Reports from the verified path are JSON; the older conversational PDF/report engine remains a separate path.

## Local migration and configuration

The existing application database and primary containers were not migrated/restarted during this verification. After reviewing local changes, apply the additive migration with the repository's normal migration owner, grant existing roles the new table privileges and restart API/worker processes:

```powershell
docker compose exec -T backend alembic upgrade head
# With your existing reviewed role names and migration-owner connection:
# psql ... -v app_role=existing_app -v worker_role=existing_worker -f infrastructure/adaptive_role_grants.sql
docker compose restart backend
```

`infrastructure/adaptive_role_grants.sql` complements existing baseline/learning grants. It adds no credentials or bypass privileges. Migration012 downgrade removes only adaptive tables/functions, preserving earlier learning tables; it deliberately removes adaptive history, so use normal backups/release procedures outside ephemeral testing. Schema SQL is frozen, not generated from future live ORM metadata.

No new service, API key or embedding download is required for numerical training. Existing configuration is reused:

```dotenv
BACKGROUND_WORKER_ENABLED=true
BACKGROUND_WORKER_CONCURRENCY=1
# Existing DATABASE_URL / REDIS_URL / CHROMA_HOST / CHROMA_PORT remain unchanged.
# Optional existing provider key: GROQ_API_KEY or GEMINI_API_KEY or OPENAI_API_KEY.
# Never put provider/server credentials in VITE_* browser variables.
```

Default collection is disabled per workspace. Start with the tested catalog and collection; inspect evidence, register representative groups, replay permissible alternatives, train asynchronously, review final results and then use shadow. Activation remains denied when gates fail. Authorization-denied jobs are not retried. Existing durable outbox, leases, heartbeat fencing, idempotency and bounded retries handle crashes; the worker never treats a new delivery as fresh repair budget.

## Reproduce isolated verification

Run from the repository root using Linux Docker containers. The scripts reject non-test databases and disable real provider keys. This project uses separate volumes from the application:

```powershell
docker compose -p analyst-adaptive-verify -f docker-compose.verify.yml run --name analyst-adaptive-proof runner python scripts/run_adaptive_verification.py --migration-roundtrip
docker compose -p analyst-adaptive-verify -f docker-compose.verify.yml -f docker-compose.learning-verify.yml run --rm frontend-verify sh -c 'npm ci --no-audit --no-fund && npx eslint src/components/AdaptiveWorkbench.tsx src/pages/app/VerifiedLearningPage.tsx src/services/adaptiveService.ts src/services/learningService.ts && npm run build'
# Start live synthetic API/worker only after tests finish, to avoid worker races:
docker compose -p analyst-adaptive-verify -f docker-compose.verify.yml -f docker-compose.learning-verify.yml up -d api frontend-verify
docker compose -p analyst-adaptive-verify -f docker-compose.verify.yml run --rm runner python scripts/seed_adaptive_browser.py
docker compose -p analyst-adaptive-verify -f docker-compose.verify.yml -f docker-compose.learning-verify.yml run --name analyst-adaptive-browser-proof browser node scripts/run-adaptive-browser.mjs
docker compose -p analyst-adaptive-verify -f docker-compose.verify.yml restart postgres api
docker compose -p analyst-adaptive-verify -f docker-compose.verify.yml run --rm runner python scripts/verify_adaptive_persistence.py
docker cp analyst-adaptive-proof:/verification/adaptive-evidence/. ./docs/adaptive-verification
```

Browser setup requires the existing `dataanalyst-learning-browser:latest` image (build with the learning-verify Compose file) and cached Chromium can be installed by the runner. Account secrets stay in the isolated volume and must never be copied to evidence. Artifacts contain synthetic data only. Use unique container names on reruns. See [progress/evidence index](ADAPTIVE_IMPLEMENTATION_PROGRESS.md) for observed runs and limitations.

## Remaining prerequisites and scope

No funded provider credentials were configured: provider success/failure/scope checks used explicitly mocked providers; browser analysis used approved deterministic functions. Hosted Supabase sign-in is unrun; the browser uses real local backend password auth. Production-domain definitions and representative independent positive/negative examples must come from authorized owners. The pilot does not establish production improvement or calibrated confidence. Exact duplicate checks require human scenario review for semantic near duplicates. Training is manually submitted after evidence checks, not scheduled unattended. Predictive/forecasting leakage controls are not retrofitted into unrelated legacy executors by this change. The new path remains a bounded descriptive aggregate and approved two-input relationship engine.
