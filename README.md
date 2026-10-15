# AI-Powered Data Analyst Platform

> Current status (2026-10-12): the redesigned internal UI is wired and authenticated browser-reviewed. Analytical correctness repairs pass documented regression checks, but the backend now runs locally with selected live checks passing; Insights schema drift and broader Phase 24?28 work remain open. See the [current verification matrix](reports/ANALYTICAL_CORRECTNESS_REMEDIATION_REPORT.md) and [remaining checklist](reports/ANALYTICAL_CORRECTNESS_REMEDIATION_CHECKLIST.md). The phase narrative below is historical, not current readiness evidence.

A full-stack, enterprise AI-powered data analytics platform that allows users to upload datasets, inspect them, and interact with their data through AI-driven insights, natural-language queries, visualisations, automated reports, and predictive modeling. The backend provides a versioned FastAPI gateway, typed configuration, PostgreSQL, Redis, and ChromaDB adapters, request middleware, structured logging, lifecycle management, truthful health checks, and a comprehensive test foundation.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Technology Stack](#technology-stack)
- [Infrastructure & Services](#infrastructure--services)
- [Project Structure](#project-structure)
- [Development Progress — Phase Tracker](#development-progress--phase-tracker)
  - [Phase 1 — Authentication & Profile UI](#phase-1--authentication--profile-ui)
  - [Phase 2A — Architecture Audit](#phase-2a--architecture-audit)
  - [Phase 2B — Dataset Workspace & Initial Dataset List](#phase-2b--dataset-workspace--initial-dataset-list)
  - [Phase 2C — Dataset Search, Filter & Sort](#phase-2c--dataset-search-filter--sort)
  - [Phase 2D — Dataset Detail Page & Navigation](#phase-2d--dataset-detail-page--navigation)
  - [Phase 2E — Dataset Data Preview](#phase-2e--dataset-data-preview)
- [Running Locally](#running-locally)
- [Environment Variables](#environment-variables)
- [Backend API Status](#backend-api-status)
- [Frontend Routes](#frontend-routes)
- [Design System](#design-system)
- [Future Phases (Planned)](#future-phases-planned)

---

## Project Overview

The **AI-Powered Data Analyst Platform** is a production-oriented, multi-phase project. At its core, it is a web application that lets analysts:

1. Upload and manage structured datasets (CSV, Excel, JSON, Parquet)
2. Inspect dataset metadata and preview data samples
3. Query data using natural language (AI Chat — planned)
4. Generate visualisations automatically (planned)
5. Run SQL against their data via an AI SQL agent (planned)
6. Receive AI-generated forecasts and recommendations (planned)
7. Export automated reports (planned)

The project is built **phase by phase**. Each phase is reviewed and approved before the next begins. The detailed phase narrative below preserves the historical **Phase 2E** snapshot; use the current verification matrix above for present status.

---

## Technology Stack

### Frontend
| Technology | Version | Purpose |
|---|---|---|
| React | 19.x | UI framework |
| TypeScript | ~6.0 | Type safety |
| React Router DOM | 7.x | Client-side routing (SPA) |
| Vite | 8.x | Dev server & bundler |
| Vanilla CSS | — | Styling (design-system tokens, no framework) |
| ESLint | 10.x | Linting |

### Backend
| Technology | Version | Purpose |
|---|---|---|
| FastAPI | ≥0.115 | REST API framework |
| Uvicorn | ≥0.30 | ASGI server |
| SQLAlchemy | ≥2.0 | ORM / database access |
| psycopg (v3) | ≥3.2 | PostgreSQL driver |
| Pydantic Settings | ≥2.5 | Environment config |
| python-multipart | ≥0.0.9 | File upload handling |
| pytest + httpx | ≥8.0 / ≥0.27 | Testing |

### Infrastructure
| Service | Image / Tool | Purpose |
|---|---|---|
| PostgreSQL | postgres:16 | Primary relational database |
| Redis | redis:7 | Caching & session management |
| ChromaDB | chromadb/chroma | Vector store for RAG / semantic search |
| Docker Compose | — | Local multi-service orchestration |

---

## Infrastructure & Services

All services run via Docker Compose:

```
Backend   → http://localhost:8000   (FastAPI)
Frontend  → http://localhost:5173   (Vite dev server)
PostgreSQL → localhost:5432
Redis      → localhost:6379
ChromaDB   → http://localhost:8401
```

**Docker network:** `ai-analyst-network`

**Persistent volumes:**
- `postgres_data` — PostgreSQL data directory
- `chroma_data` — ChromaDB embeddings store
- `frontend_node_modules` — Node modules cached in a volume (avoids host/container mismatch)

---

## Project Structure

```
llm-powered-data-analyst/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── requirements.txt         # Python dependencies
│   ├── Dockerfile
│   ├── api/                     # Route handlers (reserved stubs)
│   │   ├── routes.py            # Router registration
│   │   ├── auth.py              # Reserved — not yet implemented
│   │   ├── upload.py            # Reserved — not yet implemented
│   │   ├── analytics.py         # Reserved — not yet implemented
│   │   ├── chat.py              # Reserved — not yet implemented
│   │   ├── dashboard.py         # Reserved — not yet implemented
│   │   ├── forecasting.py       # Reserved — not yet implemented
│   │   ├── rag.py               # Reserved — not yet implemented
│   │   ├── recommendations.py   # Reserved — not yet implemented
│   │   ├── reports.py           # Reserved — not yet implemented
│   │   ├── sql.py               # Reserved — not yet implemented
│   │   └── visualization.py     # Reserved — not yet implemented
│   ├── schemas/                 # Pydantic schemas (confirmed contract)
│   ├── agents/                  # LLM agent definitions (planned)
│   ├── analytics/               # Analytics engine (planned)
│   ├── cache/                   # Redis cache utilities (planned)
│   ├── core/                    # App config & core utilities
│   ├── database/                # DB connection & session management
│   ├── forecasting/             # Forecasting module (planned)
│   ├── memory/                  # Agent memory / LangGraph (planned)
│   ├── orchestrator/            # Workflow orchestration (planned)
│   ├── rag/                     # RAG pipeline (planned)
│   ├── recommendations/         # Recommendation engine (planned)
│   ├── reports/                 # Report generation (planned)
│   ├── security/                # Auth & security utilities (planned)
│   ├── services/                # Business logic services (planned)
│   ├── sql_agent/               # SQL agent (planned)
│   ├── visualization/           # Visualization engine (planned)
│   └── workflows/               # LangGraph workflows (planned)
│
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── Dockerfile
│   └── src/
│       ├── App.tsx              # Route declarations
│       ├── main.tsx             # React entry point
│       ├── index.css            # Design system (tokens + all component styles)
│       ├── datasetUtils.ts      # Shared dataset data & pure utilities
│       ├── api/                 # HTTP client (ApiError, base fetch wrapper)
│       ├── components/
│       │   └── StatusBadge.tsx  # Reusable status badge component
│       ├── layouts/
│       │   ├── AppLayout.tsx    # Sidebar nav + <Outlet>
│       │   └── AuthLayout.tsx   # Centered card layout for auth pages
│       ├── pages/
│       │   ├── NotFoundPage.tsx
│       │   ├── auth/
│       │   │   ├── LoginPage.tsx
│       │   │   ├── SignupPage.tsx           # Stub
│       │   │   └── ForgotPasswordPage.tsx   # Stub
│       │   └── app/
│       │       ├── DashboardPage.tsx        # Stub
│       │       ├── DatasetsPage.tsx         # Phase 2B–2D: Dataset list
│       │       ├── DatasetDetailPage.tsx    # Phase 2D–2E: Detail + preview
│       │       └── ProfilePage.tsx          # Stub
│       ├── services/
│       │   └── authService.ts   # Auth service boundary (PENDING backend)
│       └── types/
│           ├── auth.ts          # Auth domain types
│           └── datasets.ts      # Dataset domain types (Dataset, DatasetPreview)
│
├── datasets/                    # Filesystem storage for uploaded files
│   ├── raw/                     # Uploaded originals
│   ├── validated/               # Post-validation copies
│   └── processed/               # Pipeline output
│
├── infrastructure/              # Infrastructure-as-code (future)
├── tests/                       # Backend test suite
├── docker-compose.yml
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

---

## Development Progress — Phase Tracker

### Phase 1 — Authentication & Profile UI
**Status: ✅ COMPLETE**

**What was built:**

- **Auth layout** (`AuthLayout.tsx`) — centered card layout for all auth pages.
- **Login page** (`LoginPage.tsx`) — fully implemented UI:
  - Email + password fields with validation.
  - Password visibility toggle.
  - Inline field-level error messages.
  - Form-level error banner.
  - Loading/submitting state with spinner.
  - "Forgot password?" link.
  - "Sign up" prompt footer.
  - Keyboard accessible; all form elements properly labelled.
- **Signup page** (`SignupPage.tsx`) — route stub (reserved for a future phase).
- **Forgot password page** (`ForgotPasswordPage.tsx`) — route stub.
- **Auth service boundary** (`authService.ts`) — defines the full anticipated auth API surface:
  - `login()`, `signup()`, `logout()`, `me()`, `forgotPassword()`, `resetPassword()`, `getProfile()`, `updateProfile()`
  - All methods currently map to PENDING backend endpoints. No real HTTP calls succeed — the backend auth module is not yet implemented.
- **Auth domain types** (`types/auth.ts`) — `LoginRequest`, `LoginResponse`, `SignupRequest`, `User`, etc.
- **Design system** (`index.css`) — full auth UI token set and component classes:
  - `.auth-layout`, `.auth-card`, `.auth-form`, `.form-input`, `.form-label`, `.form-error`
  - `.auth-submit`, `.auth-spinner`, `.auth-alert`, `.auth-link`
  - Responsive at ≤480 px.
  - Dark mode via `prefers-color-scheme: dark`.

**Key decisions:**
- No authentication boundary (route guard) is injected yet — the protected route wrapper is deferred to a future phase so pages are navigable during UI development.
- The auth service is written to the anticipated API contract, not yet a confirmed one.

---

### Phase 2A — Architecture Audit
**Status: ✅ COMPLETE**

**What was done:**

- Full audit of the backend schema contract (`backend/schemas/datasets.py`).
- Confirmed backend `DatasetResponse` fields: `dataset_id`, `filename`, `size_bytes`, `uploaded_at`, `status`.
- Confirmed that the backend `path` field **must never be exposed in the UI** (server filesystem path).
- Confirmed only `'uploaded'` as a definite backend status value. All other statuses (`validating`, `validated`, `processing`, `processed`, `failed`) are **anticipated** from the observed pipeline architecture (`datasets/raw → datasets/validated → datasets/processed`) — not yet a confirmed backend enum.
- Confirmed that `GET /api/datasets` **does not exist yet**.
- Locked architecture decisions for Phase 2B onwards:
  - Frontend dataset types mirror the confirmed schema only.
  - Development data is used exclusively for UI rendering until the backend endpoint exists.
  - The presentation layer must be data-source agnostic so that switching to a real API requires no component rewrites.

---

### Phase 2B — Dataset Workspace & Initial Dataset List
**Status: ✅ COMPLETE**

**What was built:**

- **App shell** (`AppLayout.tsx`):
  - Sticky left sidebar with inline SVG icons (no icon library).
  - Navigation links: Dashboard, Datasets, Profile.
  - Active state via React Router's `aria-current="page"` — no manual class management.
  - Collapses to a horizontal top bar on mobile (≤768 px).
  - CSS classes: `.app-layout`, `.app-sidebar`, `.app-nav`, `.app-nav-link`, `.app-nav-icon`.

- **Datasets page** (`DatasetsPage.tsx`) — initial implementation:
  - Page header with title and description.
  - Dataset summary bar showing total dataset count.
  - Dataset list table with columns: Dataset (filename + extension badge), Size, Uploaded, Status, Actions (reserved).
  - `StatusBadge` component: colour-coded pill with dot indicator + text label (never colour-only).
  - `DatasetRow` component: formats file size (`formatFileSize`), date (`formatDate`), extension (`getExtension`).
  - **Loading state**: skeleton rows with pulse animation.
  - **Error state**: error banner with `role="alert"`.
  - **Empty state**: no-datasets illustration with explanatory copy.
  - Data source: `DEV_DATASETS` — 6 isolated development records seeded synchronously. No HTTP call is made, no backend is invoked.

- **`DEV_DATASETS`** (moved to `datasetUtils.ts` in Phase 2D):
  ```
  dev-001  sales_q1_2026.csv           2.3 MB   processed
  dev-002  customer_survey_results.xlsx 835 KB   validated
  dev-003  inventory_snapshot.json      125 KB   processing
  dev-004  marketing_spend_2025.csv     65.6 KB  uploaded
  dev-005  user_events_raw.parquet      18 MB    validating
  dev-006  product_catalog_v3.xlsx      422 KB   failed
  ```

- **Design tokens & component CSS** added to `index.css`:
  - Page layout: `.page-header`, `.page-title`, `.page-description`
  - Summary bar: `.dataset-summary`, `.dataset-stat`, `.dataset-stat-value`, `.dataset-stat-label`
  - Table: `.dataset-table-wrapper`, `.dataset-table`, `.dataset-filename`, `.dataset-filetype`, `.dataset-meta`, `.dataset-actions`
  - Status badges: `.status-badge`, `.status-badge--{status}` (all 6 variants, light + dark mode)
  - Empty state: `.dataset-empty`, `.dataset-empty-icon`, `.dataset-empty-title`, `.dataset-empty-body`
  - Loading skeleton: `.dataset-skeleton`, `.dataset-skeleton-row`, `.skeleton-block` (pulse animation)
  - Error: `.dataset-error`
  - Screen reader utility: `.sr-only`

---

### Phase 2C — Dataset Search, Filter & Sort
**Status: ✅ COMPLETE**

**What was built (incremental addition to Phase 2B):**

- **Search input** — searches datasets by filename:
  - Case-insensitive, trims leading/trailing whitespace.
  - `type="search"` input with semantic `<label>` and `aria-label`.
  - Local React state: `searchQuery` (default `""`).

- **Status filter** — `<select>` dropdown filtering by `Dataset.status`:
  - Options: All statuses, Uploaded, Validating, Validated, Processing, Processed, Failed.
  - Local React state: `statusFilter` (default `"all"`).

- **Sort control** — `<select>` dropdown with 6 options:
  - Recently uploaded (default — preserves Phase 2B order)
  - Oldest uploaded
  - Name A–Z
  - Name Z–A
  - Largest size
  - Smallest size
  - Sort comparisons use raw values (`uploaded_at` timestamps, `size_bytes`, `filename`) — never formatted display strings.
  - Local React state: `sortOption` (default `"recently-uploaded"`).

- **Derived data pipeline** — pure function `deriveVisibleDatasets()`:
  ```
  DEV_DATASETS → search → status filter → sort → visible list → table
  ```
  `DEV_DATASETS` is **never mutated**. `.sort()` is called on a spread copy.

- **Dual result count** in the summary bar:
  - Total count always reflects `DEV_DATASETS.length`.
  - Result count appears only when filtering/searching is active.

- **Clear filters button** — appears only when `searchQuery !== ""` or `statusFilter !== "all"`. Resets both. Sort is **not** reset (independent control).

- **Two distinct empty states**:
  1. **No datasets at all** — "No datasets yet." (Phase 2B state preserved)
  2. **Filter produced no results** — "No matching datasets." + "Clear search & filters" action button.

- **`DatasetTable` props extended**: `totalCount`, `isFiltered`, `onClearFilter`.

- **CSS additions** to `index.css`:
  - `.dataset-controls` — flex toolbar, wraps on small screens.
  - `.dataset-control-group` — label + input/select pair.
  - `.dataset-control-label` — small label above each control.
  - `.dataset-control-input` — search input (reuses `.form-input` token-compatible styling).
  - `.dataset-control-select` — status & sort selects.
  - `.dataset-clear-btn` — ghost-style clear button aligned to controls row.
  - `.dataset-filter-clear-action` — inline action button inside the filtered-empty state.
  - Responsive: controls stack vertically at ≤600 px.

---

### Phase 2D — Dataset Detail Page & Navigation
**Status: ✅ COMPLETE**

**What was built (incremental addition):**

- **Route** `/datasets/:datasetId` → `DatasetDetailPage`.
- **"View" link** added to each `DatasetRow` in the actions cell — navigates to the detail page.
- **`DatasetDetailPage`** (`DatasetDetailPage.tsx`):
  - Reads `:datasetId` via `useParams()`.
  - Resolves the dataset from `DEV_DATASETS` (client-side lookup by `dataset_id`).
  - **Not Found state**: shown when the ID does not exist in `DEV_DATASETS`.
  - **Metadata section**: displays `filename`, extension badge, `size_bytes` (formatted), `uploaded_at` (formatted with time), `status` badge, `dataset_id`.
  - **Back link** → `/datasets` (React Router `<Link>`).
  - Designed for future integration: replaces the synchronous lookup with `datasetService.get(datasetId)`.

- **Shared utilities extracted** to `datasetUtils.ts` (plain `.ts`, no React):
  - `DEV_DATASETS` — moved here to avoid ESLint `react-refresh/only-export-components` violation.
  - `formatFileSize()`, `formatDate()`, `formatDateTime()`, `getExtension()`.

- **`StatusBadge`** extracted to `components/StatusBadge.tsx` (named export) — used by both `DatasetsPage` and `DatasetDetailPage`.

- **CSS additions** to `index.css` for the detail page:
  - `.detail-header`, `.detail-back`, `.detail-title`, `.detail-subtitle`
  - `.detail-meta-grid`, `.detail-meta-item`, `.detail-meta-label`, `.detail-meta-value`
  - `.detail-not-found` — full-page not-found state for invalid IDs.

---

### Phase 2E — Dataset Data Preview
**Status: ✅ COMPLETE**

**What was built (incremental addition to Phase 2D):**

- **Data Preview section** added to `DatasetDetailPage`:
  - Displays a bounded sample of rows and columns from the dataset.
  - Shows "Showing X of Y rows" caption.
  - Horizontally scrollable table for wide datasets.
  - Column headers from `DatasetPreview.columns`.
  - Null/missing cell values rendered as an em-dash (`—`) in muted style.
  - **Preview loading state**: skeleton rows (separate from the metadata loading state).
  - **Preview error state**: inline error banner.
  - **Empty preview state**: "This dataset has no preview data available."

- **`DEV_PREVIEWS`** added to `datasetUtils.ts`:
  - Isolated development preview data for all 6 `DEV_DATASETS` entries.
  - Includes representative columns and sample rows for each dataset type.
  - No browser-side file parsing occurs — the preview data is a bounded in-memory representation only.

- **New types** added to `types/datasets.ts`:
  - `CellValue` — `string | number | boolean | null`
  - `PreviewRow` — `Record<string, CellValue>`
  - `DatasetPreview` — `{ columns: string[]; rows: PreviewRow[]; totalRows: number }`

- **Integration path documented** in `DatasetDetailPage.tsx`:
  - Replace `DEV_PREVIEWS` lookup with `datasetService.preview(datasetId)` — no presentation changes required.

- **CSS additions** to `index.css`:
  - `.detail-preview-section`, `.detail-preview-header`, `.detail-preview-caption`
  - `.preview-table-wrapper` (overflow-x scroll), `.preview-table`
  - `.preview-cell--null` (muted null value style)
  - `.detail-preview-empty`, `.detail-preview-error`
  - `.detail-preview-skeleton` skeleton rows.

---

## Running Locally

### Prerequisites
- Docker & Docker Compose
- Node.js 20+ (for frontend-only development without Docker)
- Python 3.12+ (for backend-only development without Docker)

### With Docker Compose (recommended)

```bash
# 1. Copy environment file
cp .env.example .env
# Edit .env — add your OPENAI_API_KEY or other LLM provider key

# 2. Start all services
docker compose up --build
```

Open the frontend at `http://localhost:5173` and the API health endpoint at `http://localhost:8000/api/v1/health`.

### Frontend only (development)

```bash
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

### Backend only (development)

**Option 1 — From repository root (recommended):**

```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
# → http://localhost:8000 (Health check: http://localhost:8000/api/v1/health)
```

**Option 2 — From inside the `backend` directory:**

Because application modules use absolute imports (`backend.app...`), set `PYTHONPATH` to the parent repository root when launching from inside the `backend` folder:

```bash
cd backend
pip install -r requirements.txt

# Linux / macOS:
PYTHONPATH=.. uvicorn backend.main:app --reload --port 8000

# Windows (PowerShell):
$env:PYTHONPATH=".."; uvicorn backend.main:app --reload --port 8000

# Windows (Command Prompt):
set PYTHONPATH=.. && uvicorn backend.main:app --reload --port 8000
# → http://localhost:8000
```

**Option 3 — Running with Docker Compose:**

```bash
docker compose up --build
# Or backend only with its dependencies:
docker compose up backend postgres redis chromadb
```

### Running Backend Tests

```powershell
docker compose exec backend pytest -q
# or locally in venv:
pytest -q
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values.

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `CHROMA_HOST` | Yes | ChromaDB hostname |
| `CHROMA_PORT` | Yes | ChromaDB port |
| `OPENAI_API_KEY` | Future | LLM API key (needed when AI agents are implemented) |
| `POSTGRES_HOST_PORT` | Optional | Override host-side PostgreSQL port (default: 5432) |

---

## Backend API Status

> The backend is **structurally scaffolded** but has **no implemented endpoints** yet. All route modules exist as reserved stubs. Implementation follows the frontend development in a later phase.

| Endpoint | Status | Phase |
|---|---|---|
| `POST /api/auth/login` | ⏳ Not implemented | Future |
| `POST /api/auth/signup` | ⏳ Not implemented | Future |
| `POST /api/auth/logout` | ⏳ Not implemented | Future |
| `GET  /api/auth/me` | ⏳ Not implemented | Future |
| `POST /api/auth/forgot-password` | ⏳ Not implemented | Future |
| `GET  /api/datasets` | ⏳ Not implemented | Future |
| `GET  /api/datasets/:id` | ⏳ Not implemented | Future |
| `GET  /api/datasets/:id/preview` | ⏳ Not implemented | Future |
| `POST /api/upload` | ⏳ Not implemented | Future |
| `POST /api/chat` | ⏳ Not implemented | Future |
| `GET  /api/analytics` | ⏳ Not implemented | Future |
| `GET  /api/dashboard` | ⏳ Not implemented | Future |
| `GET  /api/reports` | ⏳ Not implemented | Future |

---

## Frontend Routes

| Path | Component | Status | Notes |
|---|---|---|---|
| `/` | Redirect | ✅ | Redirects to `/dashboard` |
| `/login` | `LoginPage` | ✅ | Fully implemented UI |
| `/signup` | `SignupPage` | 🔲 Stub | Reserved |
| `/forgot-password` | `ForgotPasswordPage` | 🔲 Stub | Reserved |
| `/dashboard` | `DashboardPage` | 🔲 Stub | Reserved |
| `/datasets` | `DatasetsPage` | ✅ | Full list, search, filter, sort |
| `/datasets/:datasetId` | `DatasetDetailPage` | ✅ | Metadata + data preview |
| `/profile` | `ProfilePage` | 🔲 Stub | Reserved |
| `*` | `NotFoundPage` | ✅ | 404 fallback |

---

## Design System

All styles live in a single file: `frontend/src/index.css`.

**No external CSS framework is used.**

### CSS Custom Properties (Design Tokens)

| Token | Light | Dark | Usage |
|---|---|---|---|
| `--text` | `#6b6375` | `#9ca3af` | Body text |
| `--text-h` | `#08060d` | `#f3f4f6` | Headings, emphasis |
| `--bg` | `#fff` | `#16171d` | Page background |
| `--border` | `#e5e4e7` | `#2e303a` | Borders, dividers |
| `--accent` | `#aa3bff` | `#c084fc` | Brand, interactive |
| `--accent-bg` | `rgba(170,59,255,0.1)` | `rgba(192,132,252,0.15)` | Hover / active tint |
| `--accent-border` | `rgba(170,59,255,0.5)` | `rgba(192,132,252,0.5)` | Focus rings |
| `--code-bg` | `#f4f3ec` | `#1f2028` | Table headers, summary bars |
| `--shadow` | subtle light | deeper dark | Card shadows |
| `--sans` | `system-ui, Segoe UI, Roboto` | — | Body font stack |
| `--heading` | `system-ui, Segoe UI, Roboto` | — | Heading font stack |
| `--mono` | `ui-monospace, Consolas` | — | Monospace (file extensions) |

**Dark mode** is applied automatically via `@media (prefers-color-scheme: dark)`.

---

## Future Phases (Planned)

> These phases have not started. No code has been written for them yet.

| Phase | Description |
|---|---|
| 2F | Dataset upload UI |
| 2G | Dataset delete / management actions |
| 3 | Backend authentication implementation |
| 4 | Backend dataset API (`GET /api/datasets`, `GET /api/datasets/:id`) |
| 5 | AI Chat interface (natural-language queries against datasets) |
| 6 | SQL Agent (AI-generated SQL with result tables) |
| 7 | Visualisation engine (auto-generated charts) |
| 8 | Forecasting module |
| 9 | Recommendations engine |
| 10 | RAG pipeline (semantic search over dataset content) |
| 11 | Automated report generation & export |
| 12 | Dashboard (summary metrics, recent activity) |
| 13 | Profile & settings |
| 14 | Admin panel |
| 15 | Production hardening, auth boundary, deployment |

---

## Autonomous Intelligence & Phase Readiness

Phase 15 autonomous intelligence is available as a decision-support API at `/api/v1/autonomous`. See [Phase 15 readiness](docs/PHASE15_READINESS.md) for the current production gap and the recommended implementation sequence.

---

## License

See [LICENSE](./LICENSE).
