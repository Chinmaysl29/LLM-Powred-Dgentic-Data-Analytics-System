# Phase 2 — shadow averaged perceptron

Branch: `feature/learning-layer`. This phase observes decisions only. It does not promote a router, train from requests, or change deterministic business calculations.

## 1. Reasoning summary

1. Establish the current baseline before editing: 151 backend tests and both frontend checks.
2. Implement a bounded NumPy multiclass averaged perceptron, with features initialized from the existing intent registry. Keep the original router authoritative.
3. Record authorized shadow comparisons separately from hard-failure evidence; disagreements are not verified labels.
4. Test the learning rule, serialization, isolation, failure handling, unchanged API responses and actual pandas arithmetic. Test migration reversal before deploying.
5. Preserve a phase-specific reverse patch and back up the live DB before its additive migration.

## 2. Files and reading

Created:

| File | Purpose |
| --- | --- |
| `backend/app/learning/perceptron.py` | NumPy scoring, bounded updates, decay, averaged weights and validated JSON inference snapshots |
| `backend/app/learning/features.py` | Bounded word n-grams, keyword/pattern features, aggregation words, schema flags and column matches |
| `backend/app/learning/shadow.py` | Independent authorized candidate reads and shadow observation writes |
| `backend/app/learning/shadow_table.py` | Append-only observation model |
| `migrations/versions/014_perceptron_shadow.py` | New table, indexes and forced RLS only |
| `backend/tests/test_perceptron_shadow.py` | Numerical, security, privacy, integration and parity tests |
| `scripts/verify_shadow_migration.py` | Guarded migration roundtrip in the disposable DB |

Modified:

| File | Purpose |
| --- | --- |
| `backend/app/learning/evidence.py` | Observe the completed chat route independently of failure capture |
| `backend/app/api/v1/routes/chat.py` | Supply the actual live route to its observation |
| `backend/app/api/v1/routes/intent.py` | Observe the existing classification response with the authenticated actor |
| `backend/app/models/__init__.py` | Register the additional table |

Read: all modified files; Phase 1 report and models; the complete intent registry and classification paths; intent request/response schemas; route aggregation and authorization dependencies; chat callers and observer tests; orchestration caller; workspace authorization; DatasetVersion schema snapshots; migration 013; migration verification and setup-test runners; existing integration fixtures. Reused the Postgres best-practices skill and RLS guidance for the new table.

`.env`, numerical execution services, existing embedding/adaptive systems, dependencies, and frontend sources were not changed.

## 3. Complete code and design

The complete runnable code is in the files above. [phase2.patch](perceptron-verification/phase2.patch) contains exactly this phase's 11 source/test/migration files, relative to the Phase 1 working tree. It excludes earlier and unrelated edits.

The model chooses from the 17 existing `IntentType` values. Its 576-element vector contains fixed registry keyword/pattern slots, aggregation words, schema flags, and deterministic SHA-256 hash buckets for bounded word n-grams and matched column names. Questions are limited to 2,000 characters, token processing to 256 tokens and schema processing to 200 columns. No dataset rows are loaded by the learner.

The fixed global seed gives weight to existing keyword and regex features. It is a starting point, not a trained model or an accuracy claim. Fresh instances do not share mutable weights. An inactive tenant-local `learner_weights` row with `learner='intent_router'` can supply a shadow candidate; the highest version is considered. Labels, feature fingerprint, payload structure, shape, types, finiteness, size and weight magnitude are validated. An incompatible candidate falls back to the seed and records its rejected version. Candidate writes and activation are not exposed in this phase.

The offline `update()` primitive implements the Rosenblatt correction and weight decay. Averaging includes the post-update state after every labelled example, including correct examples. JSON exports are inference snapshots, not resumable training checkpoints. **No request path calls `update()` or writes learner weights.** Failure evidence and router disagreement remain unlabelled.

Shadow prediction abstains on an insufficient score margin or an `unknown` winner. Margin is a score difference, not a calibrated probability. Even a confident shadow prediction never selects a live agent, plan, metric, column or computation in Phase 2.

Observation distinguishes canonical intents from the deterministic analytics route. For example, a chat result with route `analytics` and operation `sum` records `live_intent=NULL` and `live_operation='sum'`; it does not pretend that `sum` is one of the 17 intent labels. This prevents false accuracy comparisons later.

The new table stores only hashes, numeric feature indices/values, allow-listed decisions, model provenance, actor/dataset identifiers, and timestamps. Raw questions, column names, dataset observations, responses, exception strings and credentials are not persisted by this layer. Hashing is not a claim of anonymization. Schema hashes use the same encoding as Phase 1 feedback.

Recording requires an owned dataset with a persisted workspace binding, active membership and an existing selected version. Missing scope, revoked access, model errors and storage outages fail open. Datasetless/unbound requests are not persisted. General `/intent/classify` calls and chat are observed; durable job routing is unchanged. Existing Phase 1 worker failure capture remains intact.

Writes use an independent transaction, two-second connection timeout, 300 ms statement timeout and 100 ms lock timeout. These are per-operation bounds, not a whole-request latency deadline. There is no cross-tenant model cache. RLS enforces tenant/workspace/actor/dataset ownership for restricted roles and permits no runtime update/delete of observations. The live database still uses its existing superuser, so application authorization is also enforced.

## 4. Tests and exact commands

From `C:\data analyst`:

```powershell
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml up -d --wait --wait-timeout 120 postgres redis chromadb
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests/test_perceptron_shadow.py --junitxml=/verification/phase2-shadow.xml
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/run_setup_tests.py backend/tests tests --junitxml=/verification/phase2-final.xml
```

Migration roundtrip, in the disposable database only:

```powershell
docker exec dataanalyst-perceptron-phase1-postgres-1 pg_dump -U setup -d analyst_setup_test -Fc -f /tmp/before-perceptron-phase2.dump
docker compose -p dataanalyst-perceptron-phase1 -f docker-compose.verify.yml run --rm -e BACKGROUND_WORKER_ENABLED=false -e PYTHONDONTWRITEBYTECODE=1 runner python scripts/verify_shadow_migration.py
```

Frontend validation used the exact read-only Docker scratch-copy command in [Phase 1's test instructions](PERCEPTRON_PHASE1.md#4-tests-and-exact-commands), running both `npm run typecheck` and `npm run build` before and after this phase.

Tests cover independently calculated update/average/decay values, ties and abstention, rejected unknown labels and corrupt snapshots, cross-process feature stability, schema signals, seed smoke examples, isolated model instances, disabled-path no-op behavior, privacy, deduplication, tenant-local candidates, invalid-candidate fallback, revoked access, absent versions, restricted-role RLS (including authorized inserts and denied mutations), database failure and response parity.

The real chat test runs pandas over synthetic source values `100, 1000, -20, 100`: the answer remains **1180** even when the shadow model predicts `forecasting`. The test also makes any runtime call to `update()` fail and verifies the stored candidate weights are unchanged.

## 5. Verification

| Check | Result |
| --- | --- |
| Baseline backend | 151 passed, 5 existing warnings, 112.51 s |
| Focused shadow tests | 32 passed, 27.11 s |
| Full suite after Phase 2 | **183 passed**, 5 existing warnings, 150.89 s |
| Frontend before and after | Typecheck and production build passed |
| Migration roundtrip | Passed; all 56 existing tables unchanged in columns, keys, indexes and row counts |
| Reverse patch | `git apply --reverse --check` passed |
| Docker | Backend image rebuilt and container healthy |
| Live schema | `014_perceptron_shadow` |
| Live flag/data | `LEARNING_ENABLED=False`; `shadow_predictions=0`; `learner_weights=0` |
| API contract | Entire parsed OpenAPI unchanged: 222 paths, 249 operations |
| Readiness | `/health/ready` returns `ready` |

Evidence: [baseline XML](perceptron-verification/phase2-baseline.xml), [focused-test XML](perceptron-verification/phase2-shadow.xml), [full-suite XML](perceptron-verification/phase2-final.xml). All 32 new tests also passed in the final full suite. The five forecasting warnings were present in the baseline.

The first whole-OpenAPI comparison flagged four Unicode documentation strings because Windows PowerShell had decoded the saved pre-deployment HTTP body as Latin-1. Recovering its original UTF-8 bytes made the complete parsed contract comparison pass; no route/schema code was changed for this verification artifact issue.

Live backup: `C:\Users\chinm\AppData\Local\AIDataAnalyst\backups\perceptron-phase2-20261106\before-perceptron-phase2.dump` (288,481 bytes). Created before migration, copied outside the repository, and successfully listed using `pg_restore --list`; a live restore was not performed.

Changes remain uncommitted and unstaged. Git identity settings and unrelated working-tree changes were preserved. No new packages or GPU dependencies were introduced. Shadow collection was exercised with the flag on only in the isolated test environment; the live `.env` was not edited.

## 6. Rollback

Learning remains disabled by default. Full Phase 2 rollback, after backing up any observations worth retaining:

```powershell
git apply --reverse --check docs/perceptron-verification/phase2.patch
docker compose stop backend
docker compose run --rm migrate python scripts/migrate.py downgrade 013_perceptron_foundations
git apply --reverse docs/perceptron-verification/phase2.patch
docker compose build backend
docker compose up -d --no-deps backend
```

Run each command only after the previous succeeds. Downgrade removes only `shadow_predictions`, including its rows. Phase 1 and unrelated working-tree changes remain intact; reports are retained as historical evidence. Roll back Phase 2 before using the older Phase 1 reverse patch. The live downgrade was not executed.

This phase does not establish accuracy on the user's datasets. Golden evaluation, promotion, online learning, failure-memory retrieval and the dashboard remain later phases of the approved build sequence.
