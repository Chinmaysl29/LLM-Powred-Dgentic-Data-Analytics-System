# AI Data Analyst OS: Windows and Docker development setup

Validated on 4 November 2026. See [verification results](SETUP_VERIFICATION.md) for the limits of the checks, existing code failures, and features that still need credentials.

## Docker recovery verified on 6 November 2026

The Docker engine had no existing containers, images or volumes. Fresh backend/frontend images were built, and the local database was initialized through all 12 migrations to `012_adaptive_skills`. Five application services passed their health checks; the one-shot migration service completed with exit code 0.

Verified frontend HTTP 200, API readiness, frontend-to-backend networking, browser CORS, frontend production build, and all environment-doctor checks. Synthetic PostgreSQL records, Redis keys, Chroma documents and upload-storage files survived container recreation; all temporary probes were then removed. Existing `.env` files and host storage were preserved. This is a fresh local database, not a recovery of a previous Docker database volume.

Provider API keys remain unset, and Docker Desktop's Windows sign-in auto-start setting is disabled. Containers restart when the Docker engine starts unless explicitly stopped. No provider-backed analysis or account sign-in was tested during this recovery.

## Execution environment

Use **Linux containers in Docker Desktop** for the application and development tools. The host is Windows 11 Home, Ryzen 5 5500U (6 cores / 12 threads), with approximately 9.9 GiB usable RAM reported by Windows. Docker currently has 1.916 GiB. Native Windows Python is only a WindowsApps alias; Node/npm are not installed on the Windows PATH. They are installed and verified inside the containers. Do not select a Linux interpreter path in a Windows editor window.

Kiro 0.9.2 is the active editor and uses Open VSX. VS Code 1.103.2 is separately installed and uses Microsoft's Marketplace. Neither Cursor nor Antigravity was detected. Their extension stores were not modified. No system execution policy, Docker memory allocation, or editor version was changed.

The browser runs on Windows; URLs containing `localhost` below refer to Windows. Inside containers, use Compose service names (`postgres`, `redis`, `chromadb`, `backend`).

## Inventory

| Item | Verified version / identifier | Purpose and status | Condition / next action |
| --- | --- | --- | --- |
| Docker Desktop / Engine | 4.98.0 / 29.9.2 | Installed; Linux engine connected | Required |
| Python | 3.11.18, `/usr/local/bin/python` | Installed in backend and devtools; container provides isolation | Required; no Windows virtualenv is used |
| Node | 22.23.4 | Installed in frontend and devtools | Required; repository selects `>=22.13 <23` |
| npm | 10.9.9 | Existing npm lockfile workflow | Use `npm ci` in the container |
| React / TypeScript / Vite | 19.2.8 / 6.0.3 / 8.2.1 | Installed; production build passes | Required |
| Styling / client state | CSS, React Context, Motion 13.2.0 | Implemented | Tailwind is absent; no Tailwind extension installed |
| FastAPI / Uvicorn | 0.162.0 / 0.54.0 | Installed; API responds | Required |
| SQLAlchemy / psycopg | 2.1.6 / 3.3.7 | Installed; schema check passes | Required |
| PostgreSQL | 16.15 | Running; named data volume | Required; host 5432, container `postgres:5432` |
| Redis server / Python client | 7.4.12 / 5.3.1 | Running | Required; host 6379; named volume and append-only persistence; durable jobs are in PostgreSQL |
| Chroma server / client | 0.6.3 / 0.6.3 | Running; tested protocol pairing | Required for RAG; host 8401, container `chromadb:8000` |
| Torch / sentence-transformers | 2.5.1+cpu / 3.4.1 | Imports pass; real MiniLM embedding tested | Required for implemented local embeddings |
| Numerical and file readers | pandas, NumPy, PyArrow, openpyxl, PyMuPDF, pypdf | Installed; imports and upload tests pass | Versions captured in `backend/requirements.lock.txt` |
| Forecasting / ML | prophet, pmdarima, statsmodels, scikit-learn, xgboost | Installed; imports verified | Model accuracy and forecasting journeys not certified by setup |
| Reports | ReportLab 4.5.1, python-docx, openpyxl, python-pptx, Matplotlib | Valid PDF/DOCX/XLSX/PPTX generated and reopened | Native OpenMP and bundled DejaVu font checked |
| Application packages | 53 direct Python requirements, npm dependency tree | All declared constraints satisfied; `pip check` clean | Linux dependency snapshot prevents unrelated upgrades |
| Ruff / debugpy / coverage | 0.17.3 / 1.8.22 / pytest-cov 7.1.0 | Installed in devtools | Developer tools; pinned in `backend/dev-requirements.txt` |
| Prettier | 3.9.10 | Installed in frontend lockfile | Developer tool; formatting is opt-in |
| Playwright | 1.64.0; Chromium 156.0.8078.4 | Package and actual browser/dependencies installed for smoke test | Optional; run `Browsers` after recreating devtools |
| LLM provider | Groq, Gemini, OpenAI adapters | Packages installed; keys absent | Provider-backed workflows need a funded account/key; no paid request tested |
| Supabase | Existing local public browser configuration preserved | Values present | Actual sign-in needs a test account; presence is not proof of access |
| Background worker | `backend.jobs.job_worker.JobWorker` | Launched inside FastAPI; real seven-stage job completed | No separate Celery service; Compose uses one job slot to reduce RAM |
| Learning supervisor | Learning modules exist | No distinct configured Verified Learning Supervisor or durable lesson worker found | Outside setup scope; not advertised as ready |
| Mobile | Three-file React Native scaffold, no platform projects or lockfile | Not a runnable mobile target in this checkout | Android/iOS SDKs and mobile extensions not installed |

The backend entry point is `backend.main:app`, which exports `backend.app.main.app`. The factory is `backend.app.main.create_app()`. The normal launch references the exported app and **does not** use `--factory`. Frontend root is `frontend/`, using npm and `frontend/package-lock.json`.

## Extensions

These are developer tools, not application runtime dependencies. Publisher identity, registry metadata and CLI support were checked before installation. Kiro verified Open VSX signatures during installation; the CLI selected compatible versions.

| Extension ID | Purpose | Kiro installed | VS Code installed | Selection |
| --- | --- | --- | --- | --- |
| `ms-python.python` | Python environment/debug integration | 2026.4.0 | 2026.10.0 | Python development |
| `ms-python.debugpy` | Python debugging | 2026.6.0 | 2026.6.0 | Backend debugging |
| `detachhead.basedpyright` | Python language service | 1.40.2 | Not installed | Kiro only |
| `ms-python.vscode-pylance` | Python language service | Not installed | 2025.10.2 | VS Code only; Dev Container profile uses this |
| `charliermarsh.ruff` | Python lint and formatting | 2026.92.0 | 2026.92.0 | One Python formatter |
| `dbaeumer.vscode-eslint` | Existing frontend lint rules | 3.0.34 | 3.0.34 | Frontend development |
| `esbenp.prettier-vscode` | Frontend formatting | 12.4.0 | 12.4.0 | One frontend formatter; requires project config |
| `redhat.vscode-yaml` | Compose / infrastructure YAML | 2.0.0 | 2.0.0 | Container configuration |
| `ms-azuretools.vscode-containers` | Container management | 2.4.5 | 2.1.0 | Docker workflow |
| `ms-python.vscode-python-envs` | Python extension dependency | 1.20.1 | 1.2.0 | Installed automatically |
| `ms-vscode-remote.remote-containers` | Full container IDE environment | Not installed | 0.469.0 | Optional VS Code workflow, configured below |

Not installed: `humao.rest-client`, `mtxr.sqltools`, `mtxr.sqltools-driver-pg`, `ms-toolsai.jupyter`, `ms-playwright.playwright`, `ms-vscode-remote.remote-wsl`, `bradlc.vscode-tailwindcss`. The current workflow does not require them. The Playwright browser test uses the real package/browser rather than an editor extension. No notebook/kernel workflow was found.

The installer keeps the two editor installations separate:

```powershell
# Working directory: repository root; Windows PowerShell
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action InstallExtensions -Editor Kiro
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action InstallExtensions -Editor VSCode
```

No competing language servers are installed in the same editor. Common recommendations omit a language-server ID deliberately; the installer chooses the editor-specific one.

## Startup, shutdown, and diagnostics

Run all Windows commands from the repository root (`C:\data analyst` on this machine). `RemoteSigned` below applies only to the new PowerShell process; it does not change the machine or user policy. The default policy on this machine blocked unsigned local scripts. On managed machines with an enforced policy, obtain an approved signed script rather than changing system security.

```powershell
# Read-only checks; exit 1 if a mandatory check fails
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action Doctor

# Inspect proposed setup changes without installing, building or modifying files
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action Setup -DryRun

# First setup: preserve existing .env files, build, initialize migrations,
# populate the frontend dependency volume, npm ci, start services, install extensions
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action Setup

# Ordinary start and stop preserve application volumes and uploaded artifacts
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action Start
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action Stop

# Rebuild after source/dependency changes
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action Start -Build

# Logs, without resolving/printing environment files
docker compose logs --tail 60 backend
docker compose ps
```

App: http://localhost:5173. API docs: http://localhost:8000/docs. Readiness: http://localhost:8000/health/ready. RAG protocol readiness: http://localhost:8000/health/rag.

`Setup` may need several minutes for the large CPU/ML dependencies. It does not erase any volumes, reset databases, or overwrite credentials. The application Compose stack now includes a one-shot `migrate` service: `docker compose up` applies checked-in Alembic migrations before starting the backend. After updating code, back up any important database before starting the upgraded stack. To inspect the database or apply migrations manually:

```powershell
docker compose exec -T backend python scripts/schema_preflight.py
# Review pending migrations and back up any existing important database first.
docker compose exec -T backend python scripts/migrate.py upgrade head
docker compose restart backend
```

The doctor checks declared Python constraints, transitive consistency, interpreter, JWT presence, schema/head revision, service readiness, writable storage permissions, native library/font availability, frontend packages and HTTP response. It reports optional provider presence without printing keys. Worker startup log evidence is labelled as such; the live job test provides execution evidence. A green doctor does not certify every application feature.

## Development and debugging

Build and start the optional tools container:

```powershell
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action Devtools
docker compose -f docker-compose.yml -f .devcontainer/compose.yml exec devtools bash
```

In that Linux shell:

```bash
cd /workspace
python -m pip check
ruff check backend scripts
cd frontend
npm run lint
npm run typecheck
npm run build
npm run format:check
```

Do not execute the Linux commands through a Windows virtualenv. The full backend environment lives in the image, with `/usr/local/bin/python`; frontend dependencies use the existing Docker named volume. The dependency image is built before the devtools image. Python development tooling is separate from application dependencies.

For full dependency-aware Python and ESLint editor support, open this folder in **VS Code**, then run **Dev Containers: Reopen in Container**. The checked-in devcontainer config selects `/usr/local/bin/python`, installs extensions in the container, and exposes port 8001 for a separate debugging server. Opening/reloading the editor UI is a manual step and was not automated. Kiro local editing/tasks work, but its Windows extension host cannot see Linux-only packages in the container volume; expect local interpreter/import warnings until using a supported remote environment. No unofficial Kiro remote-container extension was installed.

`.vscode/launch.json` includes the actual Uvicorn app entry point, `/workspace` working directory, root environment file, a debug server on 8001, a Docker attach configuration on 5678, and a browser configuration. The normal app stays on 8000. The attach adapter needs a Python-capable editor environment; on this host the Dev Container is the supported Python environment. Debugging an entire browser sign-in session was not exercised.

For the Docker debug server:

```powershell
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action Debug
```

This waits for a debugger on loopback port 5678 and then serves http://localhost:8001. Stop the foreground task with Ctrl+C. Windows editor tasks cover doctor, infrastructure, backend, frontend, lint/types, isolated tests and debugging. Tasks explicitly labelled Dev Container run inside that environment.

Formatting does not run automatically across the repository. Ruff is the Python formatter; Prettier handles frontend files. Existing ESLint rules are preserved. No deprecated `python.formatting.*` or `python.linting.*` settings are used. Watcher/search exclusions cover generated files, storage, caches and dependency directories while keeping application-source diagnostics visible.

## Configuration and persistence

Backend settings load environment variables first, then root `.env` (`PROJECT_ROOT / '.env'`). Compose explicitly overrides database, Redis, Chroma, upload directory and browser-origin values for container networking. Do not copy host `localhost` database values into container settings. Frontend Vite reads `frontend/.env`; only publishable Supabase configuration and API URL belong in browser variables.

New environment templates use placeholders. Setup generates a random JWT secret when creating a new `.env`, but cannot supply Supabase accounts or provider credentials. Fill `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_PUBLISHABLE_KEY` for your project. For provider-backed features, supply the relevant backend provider key locally, then recreate the backend (`docker compose up -d --force-recreate backend`). Restart frontend after changing its Vite variables. Existing local configuration was preserved.

PostgreSQL, Chroma and Redis use named volumes (`dataanalyst_postgres_data`, `dataanalyst_chroma_data`, `dataanalyst_redis_data`). Redis has append-only persistence with an every-second fsync; a sudden host failure can lose approximately the latest second of Redis writes. Authoritative jobs and analytical history are in PostgreSQL. Uploads and generated studio reports use the host `storage/` bind mount; logs use `logs/`. Hugging Face weights use a persistent storage cache through `HF_HOME`. Avoid `docker compose down -v` and volume-pruning commands. Changing a database password variable does not reset an initialized PostgreSQL volume.

The five application services use `restart: unless-stopped`; Docker restarts them when its engine starts unless they were explicitly stopped. The migration service exits successfully after setup and is expected to show `Exited (0)`. Enable Docker Desktop's **Start Docker Desktop when you sign in** setting if you want the engine to start with Windows. Saved images and volumes survive ordinary restarts and container recreation, but are not backups against disk loss or a Docker factory reset.

For ordinary use after setup:

```powershell
docker compose up -d --wait --wait-timeout 300
docker compose ps -a
docker compose stop
```

The backend waits for healthy PostgreSQL, Redis and Chroma plus a successful migration; the frontend waits for backend readiness. Open http://localhost:5173 for the application and http://localhost:8000/docs for the API. The frontend's `VITE_API_BASE_URL=http://localhost:8000` targets the published backend port from the Windows browser.

Chroma is deliberately pinned to the client's tested 0.6.3 protocol. Do not point an older server at a newer volume. The Python dependency snapshot is a **Linux/Python 3.11 constraints snapshot**, not a Windows lockfile or a cryptographic hash lock. Updating dependencies requires deliberate review, snapshot refresh and retesting.

## Reproducible verification

The test action uses project `dataanalyst-verify`, a dedicated `analyst_setup_test` database, separate log/storage/Chroma volumes, synthetic accounts and no provider keys. It runs migrations twice, existing tests, a local-auth API journey, an actual seven-stage job, PDF download, and a service-restart persistence check. It stops its services afterwards and preserves evidence volumes. It never runs tests against the application database.

```powershell
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action Test
```

For browser checks, start devtools, then install the actual browser and native dependencies in that environment (repeat after recreating the tools container):

```powershell
powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\dev-environment.ps1 -Action Browsers
docker compose -f docker-compose.yml -f .devcontainer/compose.yml exec -T -w /workspace/frontend devtools node scripts/verify-setup-browser.mjs
```

Browser screenshots/results go into ignored `frontend/.ui-review/setup/`. Authenticated Supabase browser tests require test-account credentials supplied locally; the unauthenticated smoke test does not substitute for them. Native API login tests and actual provider tests are separate concerns.

## Troubleshooting

| Symptom | Check and next action |
| --- | --- |
| `node`/`python` unavailable on Windows | Use the container commands or VS Code Dev Container; WindowsApps Python is not the installed runtime |
| Editor reports missing imports / ESLint package | Use the container extension host; do not point Windows to `/usr/local/bin/python` or a Linux node_modules volume |
| Container port already allocated | Inspect `docker compose ps` and Windows `Get-NetTCPConnection`; resolve the conflict without stopping unrelated services |
| Frontend creation stalls at initial nested volume copy | The Setup action explicitly populates `dataanalyst_frontend_node_modules` before creation, then runs `npm ci` |
| Compose asks for `CHROMA_IMAGE` | Set the reviewed pin from `.env.example`; investigate existing volumes before any version change |
| Database authentication fails | Check existing initialized volume/user settings privately; use `schema_preflight.py`; preserve data |
| API is alive but unready | Check the schema, PostgreSQL, Redis and Chroma entries; allow cold import time before diagnosis |
| Jobs remain queued or fail | Check startup worker registration, run/stage status, and logs; the Test action proves actual execution |
| Report download fails | Check ownership/workspace, completed analytical artifacts, `storage/reports/studio`, permissions and renderer errors; a 200 health response is insufficient |
| Local RAG model repeatedly downloads | Verify `HF_HOME` points into persistent `storage/model-cache` and outbound model-host access works |
| Laptop becomes memory constrained | Keep one worker slot and one numerical thread pool; stop devtools/verification services when unused; inspect `docker stats` before raising concurrency |
| Lint fails after setup | See recorded pre-existing ESLint/Ruff failures; installing tools does not correct application code |

Registry references: [Kiro Python guidance](https://kiro.dev/docs/guides/languages-and-frameworks/python-guide/), [Kiro migration and Open VSX](https://kiro.dev/docs/guides/migrating-from-vscode/), [VS Code Dev Containers](https://code.visualstudio.com/docs/devcontainers/containers).
