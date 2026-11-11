# Adaptive skills and repair selector — 5 November 2026

## Repository integration map

- Active supervisor: `backend/app/services/learning_engine.py`, `learning_supervisor.py`, `analysis_run_service.py`; seven persisted stages, immutable source fingerprints, two total repair attempts and a run deadline.
- Existing authority: `backend/app/core/workspace_authorization.py`, scoped learning tables/migration 011, `backend/app/api/v1/routes/learning.py` and `frontend/src/pages/app/VerifiedLearningPage.tsx`.
- Durable workers: `backend/jobs/persistence.py`, `manager.py`, `job_worker.py`; reuse leases, fencing and atomic SQL job intent.
- LLM: `backend/app/llm/provider.py`, existing Groq/Gemini/OpenAI adapters. Existing embedding service: `backend/app/llm/embeddings.py`; neither model is trained by this upgrade.
- ML installed: scikit-learn 1.9.1, NumPy 2.4.6, Torch 2.5.1+cpu; use CPU scikit-learn logistic/MLP training with train-only preprocessing and JSON weight artifacts.
- Existing narrow analytics preserves raw representations and excludes arbitrary SQL/Python/predictive execution. Extend only approved dataframe recipes; do not route to unsafe legacy executors.
- Prior changes are uncommitted and preserved. No applicable AGENTS.md found. Verification uses a separately named ephemeral PostgreSQL project, never the application database.

## Decisions

One integrated supervisor and existing worker infrastructure. Shared task/action scoring, not one neural output per skill. Approved built-in implementations and bounded recipes only; no runtime code generation/package installation. Decision-time numerical features exclude outcomes/gold labels. No pooling of tenant data. Rules/memory remain the default. Collection, shadow ranking and evaluated active ranking are separate controls. Synthetic demonstrations may train real candidate weights but cannot establish production readiness.

## Milestones

- [x] Fresh baseline and provider/version inventory — original75 passed in37.70s; actual package inventory saved
- [x] Strict context, diagnosis, skill, decision/outcome and model contracts — `backend/app/schemas/adaptive.py`
- [x] Additive persistence/RLS migration and decision-time capture — migration012, ten scoped tables and immutable evidence triggers
- [x] Trusted skill catalog, isolated testing, lifecycle and composition proposals — eight built-ins; async approved recipe cannot self-activate
- [x] Orders/refunds285 recovery, reuse590 and refund-event exclusion/count2 — real worker and independent unit fixtures
- [x] Real train/dev preparation, logistic and MLP training, safe model loading — train-only scaling, actual numerical JSON weights
- [x] Frozen alternative replay and policy comparison with declared gates — train24/dev8/final8 synthetic cases, same catalog and validators
- [x] Scoped APIs/UI, shadow mode, release controls and rollback — authorization, generation conflicts, source/label invalidation tested
- [x] Failure-mode, real database/worker and browser regression verification —88 backend tests,16 actual Chromium journey checks; exact artifacts and rollback survive PostgreSQL/API restart
- [x] Reproducible fixtures/model manifests/results and operating documentation — `docs/ADAPTIVE_SYSTEM.md`, `docs/adaptive-verification/`, verification/seed/browser/persistence scripts and additive role-grant example

## Evidence and external prerequisites

Final backend run:88 passed in81.70s, covering the original75 checks and13 new adaptive checks. Migration012 downgrade/upgrade preserved earlier learning table counts. Targeted Ruff and frontend ESLint passed; TypeScript/Vite production build passed. Chromium passed16 checks with real local login, UI uploads, worker analysis/chart, report/model downloads, diagnosis, event counting, shadow, rollback and390px layout; no response mocks or uncaught browser errors. Exact bytes of both reports and the model bundle plus rollback state survived actual PostgreSQL/API restart. See [operating guide](ADAPTIVE_SYSTEM.md) and [evidence index](adaptive-verification/README.md).

Ordinary UI fix, not an ML gain: browser refresh previously restored the report but left the task form empty. The form now hydrates once from the pinned task and preserves subsequent user edits; the browser regression asserts restored primary/secondary inputs before changing the task to event counting. Browser-harness synchronization/locator errors were corrected during verification; only the final passing receipt is published.

Training took0.640s on one numerical CPU thread; both logistic (17 parameters) and MLP128/64 (10,497 parameters) fit real weights. All three policies answered8/8 synthetic final cases correctly. Both learned candidates lack trusted final coverage and measured policy benefit; MLP also missed the observed latency gate. No production activation or improvement. Models from the integration pilot are intentionally invalidated later by disputed-label tests; artifacts preserve the earlier immutable training/evaluation snapshot. The browser uses separately trained candidates.

Production definitions/representative labels must be supplied by their authorized owners. Main LLM/embedding weights stay frozen. Provider keys were absent: interpretation provider success, poisoning and transport failure were explicitly mocked; deterministic analytic execution is real. Hosted Supabase sign-in and paid/provider-backed calls are unrun. The primary application database/containers were untouched during implementation verification. Production deployment is not authorized by available credentials.

## Local startup requested by the user — 5 November 2026

Backed up the local `ai_analyst` database to `C:\Users\chinm\.codex\backups\data-analyst\ai-analyst-before-adaptive-20261105-132127.dump` (131,664 bytes), stopped the old backend, applied additive migrations011 and012, and started the development services with the current source. Restarted the frontend. Alembic reports `012_adaptive_skills (head)`; `/health/ready` reports compatible schema and healthy PostgreSQL, Redis and ChromaDB. Confirmed the adaptive controls/training and verified-run APIs appear in the served OpenAPI schema. The durable worker launched successfully. Frontend `/verified-learning` returns HTTP200 at `http://localhost:5173`; API docs are at `http://localhost:8000/docs`. Provider keys remain absent. No learned selector was activated and no workspace policy was changed.
