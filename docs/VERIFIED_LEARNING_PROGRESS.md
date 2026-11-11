# Verified Learning Supervisor implementation checklist

Task received 4 November 2026. Existing uncommitted environment/setup changes belong to the user and are preserved. Never migrate the application database as part of verification.

## Repository findings

- Actual application: `backend/app/main.py`, `backend/app/api/v1/routes/router.py`, `frontend/src/App.tsx`. React/TypeScript and FastAPI/Pydantic/SQLAlchemy; installed versions recorded in verification evidence.
- Durable orchestration: `backend/app/services/analysis_run_service.py`, `backend/app/api/v1/routes/analysis_runs.py`. Seven stages, persisted artifacts, dataset version pinning; not the alternative orchestrators advertised elsewhere.
- Authorization: `backend/app/core/workspace_authorization.py` checks active tenant/workspace memberships and account-owned dataset bindings. Reuse in every request and worker effect. `backend/app/core/security.py` binds authenticated users.
- Jobs: `backend/jobs/persistence.py`, `backend/jobs/manager.py`, `backend/jobs/job_worker.py`. SQL atomic claims, leases/heartbeats, bounded delivery, fenced completion. Reuse this as the outbox; Redis is optional for these jobs.
- Raw/versioned data: `backend/app/services/data_retrieval_service.py`, `backend/app/models/dataset_version.py`. Supervisor operates on copies, no source overwrite.
- Existing deterministic computation: `backend/app/services/natural_language_analytics.py`; ambiguous requests are already returned for clarification. Existing reports/chat have separate evidence and are not automatically supervisor-certified.
- Existing `backend/autonomous/self_learning.py` and `backend/operations/continuous_learning.py` are not a verified persistent learning authority.
- Existing `docs/SETUP_VERIFICATION.md` records 47 passing tests, existing lint errors, and absent LLM keys. Fresh baseline verification is required.
- No applicable AGENTS.md found in repository or workspace parents.

## Decisions

One supervisor module/package integrated with the real durable analysis path; no new service, agents, weight training or mandatory vector index. PostgreSQL retrieval with eligibility rechecks. Approved descriptive dataframe operations only; generated SQL/Python and forecasting fail closed in this feature until isolated executors/data contracts exist. Trusted versioned business definitions are explicit, never inferred from feedback. Numeric confidence unavailable without independent calibration labels. Defaults: collection disabled, learning application disabled, two total repairs, deadline and zero provider usage for deterministic operations.

## Durable checklist

- [x] Fresh baseline tests and installed-version inventory
- [x] Strict contracts, state transitions, versioned business definitions
- [x] Persistence migration, scoped RLS, durable event/job capture
- [x] Profile, approved execution, validators, bounded repair and evidence
- [x] Feedback, extraction, independent verification, review, snapshots/retrieval, invalidation
- [x] Frozen paired evaluation, gates, limited rollout controls, monitoring and rollback
- [x] Typed UI/API integration with error/loading/permission/empty states
- [x] Unit, real PostgreSQL authorization/durability and end-to-end tests
- [x] Evaluation artifacts and operating/recovery/retention documentation

Phases 1–3 are implemented for the explicitly bounded descriptive executor. Phase 4 delivers label/split collection, evaluation interfaces and the explicit unavailable confidence state. Calibration fitting is blocked by absent independent calibration labels. Production rollout remains blocked by the declared evidence gates: two synthetic paired cases score equally (2/2 in both arms), with no measured benefit and no trusted production final scenarios. Neither weights nor production deployment were authorized/performed.

Final local/test verification: 75 tests passed; 12 actual local-auth browser checks passed; production frontend build and targeted ESLint/Ruff/Prettier checks passed. See `VERIFIED_LEARNING_SUPERVISOR.md` and `learning-verification/` for scope, commands, results and limitations. Existing unrelated lint findings and earlier user setup work are not claimed fixed.

Record external blockers and unrun checks explicitly in the final operating document. Synthetic recovery demonstrations are not production accuracy measurements.
