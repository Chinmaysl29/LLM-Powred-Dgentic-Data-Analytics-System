# Setup verification — 4 November 2026

The Docker environment is verified for the workflows below. Existing application defects, provider access and authenticated Supabase browser journeys remain separate concerns. Installing extensions does not certify the entire product.

## Observed checks

| Check | Result / scope |
| --- | --- |
| Active editor / extension registry | Kiro 0.9.2; Open VSX; installed extensions and CLI flags inspected |
| Alternate editor | VS Code 1.103.2; Marketplace; separate installed list verified |
| Extension installation | Required development extensions installed in both editors; Kiro BasedPyright, VS Code Pylance; publisher/registry and signature checks completed |
| Backend package requirements | All 53 direct requirements present at compatible versions; `pip check` reports no broken requirements |
| Backend imports | pandas, NumPy, PyArrow, openpyxl, PyMuPDF, pmdarima, Prophet, XGBoost, scikit-learn, Torch and sentence-transformers passed |
| Dependency snapshot | Installed Linux/Python 3.11 distribution versions captured as constraints; pip dry-run found requirements already satisfied |
| Frontend packages | `npm ls --depth=0` clean; lockfile retained; Prettier added explicitly |
| Frontend production build | TypeScript build and Vite build passed; 2,363 modules transformed |
| Database migrations | Fresh isolated database upgraded through `010_workspace_authorization_tables`; repeat upgrade succeeded without changes |
| Schema / services | Readiness and RAG pairing pass; no missing schema tables, columns, keys or revision mismatch |
| Existing integration tests | **47 passed** after fixing test-environment log permissions and replacing the two external dataset dependencies with synthetic fixtures; 25.93 seconds initially and 55.80 seconds during the final complete script run |
| Live API authentication | Synthetic local account registration, password login, `/auth/me`, unauthenticated denial verified; no Supabase account involved |
| Live data journey | Six-row synthetic CSV uploaded, persisted and bound to a test workspace; histogram total independently checked as **2,100** |
| Actual background execution | Durable queue processed a seven-stage run to `COMPLETED`; every stage completed; no provider mock involved |
| Conversational analysis | Deterministic source-backed revenue question answered through the real `/api/v1/chat` path |
| Report download | Real API generated and downloaded a **23,640-byte**, one-page PDF; pypdf parsed it and verified the expected total |
| Persistence | Isolated PostgreSQL and API services restarted; authorized dataset retrieval and the **identical PDF bytes** remained available |
| Report formats | Generated/reopened PDF 43,498 bytes, DOCX 49,058 bytes, XLSX 7,291 bytes, PPTX 42,910 bytes using temporary synthetic data |
| Embedding model | Real `sentence-transformers/all-MiniLM-L6-v2` loaded and returned a 384-dimensional vector; no deterministic fallback was used |
| Browser smoke test | Chromium 156.0.8078.4: login direct navigation and refresh, three protected route redirects, no uncaught browser errors; 6 checks passed |
| PowerShell / JSON / Compose | Script parsed; workspace/devcontainer JSON parsed; both Compose configurations validated; setup dry-run completed |
| Read-only doctor | Passed once startup finished; reports interpreter, dependency constraints, schema, protocol compatibility, storage permissions, OpenMP, report font, frontend and optional provider presence |
| Doctor failure behavior | Intentionally missing JWT configuration produced exit code 1 and a redacted failed result |
| Repeated setup | Complete Setup action rerun successfully against existing files/volumes; npm ci and repeated migration completed without resetting data |
| Full reproducible test action | Final `dev-environment.ps1 -Action Test` returned exit 0, including 47 tests, local API journey, service restart, PDF byte comparison and stopping verification services |
| Resource measurement | With optional tools/verification stopped, Docker reported approximately 302 MiB combined for the five application containers, against a 1.916 GiB allocation; this is an idle snapshot, excludes swap, and does not predict analysis peaks |

The actual synthetic downloaded PDF is [setup-report.pdf](setup-verification/setup-report.pdf). Browser evidence is generated at ignored `frontend/.ui-review/setup/`. The synthetic journey state/PDF also remain in the verification storage volume. Application volumes and existing uploads were preserved; verification services are stopped when not testing.

## Issues found and limits

**Code-quality follow-up, 8 November 2026:** the ESLint, Ruff, Prettier and frontend dependency findings below have been resolved and deployed locally. See [CODE_QUALITY_VERIFICATION.md](CODE_QUALITY_VERIFICATION.md) for the 334 passing tests, nine browser scenarios, clean checks, patch and rollback. The dated findings below remain as the original setup record.

- **ESLint: 11 errors and 18 warnings.** Existing React memoization, unused-variable and explicit-any rules fail. The rules were preserved. Machine-readable output: [eslint.json](setup-verification/eslint.json).
- **Ruff: 4 existing fatal-name findings** remain: `Any` in `audit_repository.py`, `pd` in `data_lake_lifecycle.py`, `Any` in `connectors/scheduler.py`, and `cost_optimizer_engine` in `continuous_improvement_orchestrator.py`. This setup does not claim a clean static-analysis baseline.
- **Prettier:** check detects existing formatting differences in 113 files. No bulk formatting was performed. This is a newly explicit style check, not proof that the application is broken.
- **npm audit:** 12 moderate and 4 high findings in the complete development dependency tree. Production-only audit (`npm audit --omit=dev`) returned **0 findings** at the time checked. No forced or unrelated upgrades were applied. See [npm-audit.json](setup-verification/npm-audit.json).
- **Three-row durable analysis fixture:** failed at stage 4 (EDA). The six-row worker fixture completed. The stage persists a generic `STAGE_EXECUTION_FAILED`; root cause was not established as part of setup. The product is not certified for every small-data edge case.
- **Provider-backed features:** Groq, Gemini and OpenAI keys are absent. No paid provider call or provider-backed answer was tested. The successful analytical journey was deterministic computation, not a mocked or real LLM-provider test.
- **Authenticated browser journey:** no Supabase test-account credentials supplied. Browser sign-in, authenticated upload/analysis/report UI, visible authenticated API-error states and authenticated refresh remain untested. Local backend password login is a different verified path.
- **RAG:** local model embedding and Chroma version/heartbeat readiness verified. End-to-end PDF ingestion, Chroma collection persistence/retrieval and document citations were not certified by this setup run. The existing MiniLM adapter can silently fall back to feature hashing; the direct model check explicitly bypassed that fallback.
- **Learning:** self-learning and continuous-learning modules exist, including in-memory event collections. No distinct Verified Learning Supervisor, durable lesson persistence contract or configured supervisor worker was found. No such feature was created or enabled.
- **Editor integration:** CLI installations verified. The optional VS Code Dev Container configuration and development image are supplied; opening/reloading the IDE, breakpoint interaction, and an editor-hosted full-stack debug session require a manual UI check. Local Kiro extension hosts cannot resolve dependencies installed only in Linux containers.
- **Mobile:** source scaffold only; no Android/iOS platform projects, reproducible mobile lockfile, SDK installation or mobile runtime verification.
- **Nonblocking dependency logs:** Chroma's telemetry adapter reports a PostHog API mismatch; health/readiness and the tested workflows still pass. This was not hidden or addressed through unrelated dependency changes.

## Setup fixes made

- Installed project-relevant extensions into the actual Kiro editor and completed VS Code's formatter tooling separately.
- Added workspace recommendations, settings, launch configurations and tasks; generated directories are excluded from unnecessary indexing. Python test discovery is off by default to prevent accidental tests against the application database.
- Added a Python/Node tools container and a VS Code Dev Container profile, explicit tooling pins, Prettier configuration, Node engine constraint and typecheck/format scripts.
- Captured the working Python dependency versions in a constraints snapshot and made backend builds use it.
- Added idempotent Windows setup/start/stop/test actions, installation dry-run, and a read-only doctor with nonzero exit status on mandatory failures.
- Added a separate verification stack, dedicated test database/logs/storage, real API journey, service-restart check and Chromium smoke script.
- Replaced two hardcoded customer-dataset test dependencies with independently generated synthetic CSV data.
- Added the missing `StorageService` import used by document-indexing jobs.
- Set numerical thread pools and development worker concurrency to one; added a persistent Hugging Face model cache path.
- Added current-source script mounting; excluded runtime datasets/model caches/artifacts from image inputs; replaced environment-example account values with placeholders while preserving real local configuration.

See [DEVELOPMENT_SETUP.md](DEVELOPMENT_SETUP.md) for the inventory, extension IDs and versions, exact commands, URLs, environment selection and troubleshooting.
