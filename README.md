AI Data Analyst OS
An AI-assisted, agentic workspace for turning datasets and documents into evidence-based analytical results, visualizations, and reports.
AI Data Analyst OS brings dataset management, natural-language analytics, exploratory data analysis (EDA), visualizations, retrieval-augmented generation (RAG), and reporting into one workspace. It is designed around a traceable analytical workflow: understand the question, identify the correct data, calculate results, explain findings, and preserve evidence for later review.
Project scope: This README describes the application's architecture, intended end-to-end workflow, and the modules under development. Feature availability depends on the checked-out revision and configured services. It is not a claim that every described workflow has completed production acceptance.

Contents
1. Overview
2. Core capabilities
3. System architecture
4. Seven-stage analytical workflow
5. User journey
6. Agentic analysis and RAG
7. Data management and storage
8. Exploratory analysis and visualization
9. Analysis history and reporting
10. Technology stack
11. Local development
12. Configuration
13. Quality and verification
14. Repository organization
15. Roadmap
Overview
Traditional analytical work often involves moving between spreadsheets, SQL tools, Python notebooks, charting software, and report editors. AI Data Analyst OS aims to provide a coherent interface for those activities while keeping the underlying computations grounded in actual data.
The platform is organized around workspaces, versioned datasets, analytical runs, and reusable results. Users can upload supported data, inspect its structure, explore patterns, ask natural-language questions, and work toward actionable insights.
Design principles
- Evidence before explanation: Numeric claims come from validated calculations, not language-model guesses.
- Dataset awareness: Analyses reference the selected dataset and its version.
- Appropriate visualization: Charts depend on the available columns and their analytical types.
- Traceability: Results should retain their source, filters, methods, and calculation scope.
- Reusable work: Analysis history and reports are designed to reference the same analytical artifacts.
- Workspace boundaries: Data access is scoped to authorized identities and workspaces.
Core capabilities
Module	Purpose
Workspace & authentication	Organize user access and analytical resources
Datasets	Upload, catalog, inspect, and version structured sources
Data connections	Interface for configuring supported external data sources
Data warehouse	Organize analytical data assets and related metadata
AI Analysis	Ask questions in natural language and receive dataset-grounded results
EDA Studio	Examine types, completeness, statistics, categories, and relationships
Visualizations	Build data-aware charts and KPI views
Insights	Present analytical observations and recommendations supported by evidence
Forecasting	Explore suitable time-series and predictive workflows
Reports	Assemble and export analytical findings and supporting artifacts
RAG	Retrieve relevant context from indexed documents and knowledge sources
Analysis history	Revisit sessions, questions, runs, and previously generated artifacts


Some modules are actively being integrated; the interface or repository may expose a module before all of its end-to-end capabilities are available.
System architecture
flowchart TD
    U[User / Browser] --> F[React + TypeScript Frontend]
    F --> A[FastAPI Backend]
    A --> AUTH[Authentication and Workspace Authorization]
    A --> DATA[Dataset and Metadata Services]
    A --> ORCH[Analysis Orchestrator]
    DATA --> PG[(PostgreSQL)]
    DATA --> STORE[(Versioned File / Artifact Storage)]
    ORCH --> RET[Data Retrieval]
    ORCH --> EDA[EDA and Statistics]
    ORCH --> MODEL[Modeling / Forecasting]
    ORCH --> RAG[RAG Retrieval]
    RAG --> CHROMA[(ChromaDB)]
    RAG --> LLM[Configured LLM Provider]
    ORCH --> RESULT[Validated Result Artifacts]
    RESULT --> PG
    RESULT --> REPORT[Visualization and Reporting]
    REPORT --> F
    A --> REDIS[(Redis / Background Coordination)]

Responsibility separation: PostgreSQL stores application metadata and relational state; file/artifact storage retains source and generated assets; ChromaDB supports vector retrieval; backend analytical services perform calculations; LLMs help interpret questions and communicate grounded findings.
Seven-stage analytical workflow
The project follows a structured data-analysis lifecycle.
1. Problem formulation and requirements
Capture the analytical question, desired outcome, available datasets, relevant measures, dimensions, and constraints. Clarify ambiguous requests rather than choosing arbitrary fields.
Output: An analytical objective and validated execution plan.
2. Data collection
Select an authorized workspace and dataset, verify the source artifact and version, and identify available tables, sheets, columns, and records. Supported ingestion paths depend on the current implementation and parser configuration.
Output: A verified data source and schema profile.
3. Data cleaning and preparation
Inspect missing values, duplicates, inconsistent formats, categorical encodings, dates, and financial values stored as text. Apply explicit transformations without silently modifying original uploaded data.
Output: Prepared data and a record of transformations.
4. Exploratory data analysis (EDA)
Compute descriptive statistics, missingness, frequency distributions, group comparisons, correlations where appropriate, and time-based summaries. Distinguish full-dataset calculations from previews or samples.
Output: Reproducible analytical summaries and chart-ready data.
5. Modeling and transformation
When the question and data support it, apply relevant transformations, statistical models, or forecasting methods. Preserve model assumptions, feature choices, and evaluation evidence.
Output: Model or transformation artifacts with interpretation limits.
6. Visualization and reporting
Select charts based on real data types and analytical goals: histograms for distributions, scatter plots for paired numeric observations, time-series charts for temporal patterns, and category charts for grouped metrics.
Output: Charts, tables, KPIs, and report-ready artifacts.
7. Actionable insights and recommendations
Interpret validated findings, distinguish observation from inference, and describe practical next steps supported by the data. Include caveats when evidence is incomplete.
Output: Grounded insights and recommendations.

User journey
flowchart LR
    LOGIN[Sign in] --> WS[Choose workspace]
    WS --> UP[Upload or select dataset]
    UP --> PROFILE[Inspect schema and profile]
    PROFILE --> ASK[Ask an analytical question]
    ASK --> PLAN[Plan and execute analysis]
    PLAN --> ANSWER[View answer, KPIs, charts]
    ANSWER --> FOLLOW[Ask follow-up questions]
    ANSWER --> SAVE[Save analysis history]
    SAVE --> REP[Open Reports]
    REP --> EXPORT[Preview and export report]

    Example: A user selects a company financial dataset and asks, “Compare the companies by profit.” The system should inspect actual column names, identify an appropriate company dimension and profit measure, compute the comparison over the intended data population, and show the result with relevant visualizations. If a required field is missing or ambiguous, it should explain what is needed instead of inventing an answer.
Agentic analysis and RAG
Agentic workflow
The backend coordinates specialized responsibilities such as:
- Intent and planning: Translate a natural-language request into an analytical plan.
- Data retrieval: Resolve the authorized source and required records or aggregates.
- EDA and statistics: Compute descriptive summaries and comparisons.
- Visualization: Convert validated calculations into chart-ready specifications.
- Interpretation: Explain the results in accessible language.
- Reporting: Reuse saved analytical evidence in structured documents.
A completed agent step is not itself an analytical result. The useful output is the validated calculation, supporting evidence, and explanation delivered to the user.

Retrieval-augmented generation
RAG provides supporting context from indexed documents, such as definitions, policies, business notes, or source documentation.
flowchart LR
    DOC[Document] --> PARSE[Extract and chunk]
    PARSE --> EMBED[Generate embeddings]
    EMBED --> VDB[(ChromaDB)]
    Q[User question] --> SEARCH[Authorized retrieval]
    VDB --> SEARCH
    SEARCH --> CONTEXT[Relevant context and references]
    CONTEXT --> LLM[LLM explanation]
    CALC[Verified structured-data calculations] --> LLM
    LLM --> OUT[Grounded response]

Important: RAG supplies documentary context; structured numerical results should be computed by the analytical engine rather than estimated by the LLM.
Provider integration is configurable. A valid API key does not necessarily imply that a provider has available billing, quota, or service access. The architecture should keep provider-specific behavior isolated behind adapters.
Data management and storage
Dataset lifecycle
1. Upload a supported file.
2. Validate its format and parseability.
3. Associate it with the authorized workspace.
4. Persist metadata and source artifact references.
5. Detect schema and profile the contents.
6. Register a dataset version.
7. Make the version available to retrieval and analytics.
8. Record analytical outputs with the relevant source/version identifiers.
The project has worked with structured formats such as CSV, XLSX, JSON, and Parquet, as well as PDF/document retrieval workflows. Exact enabled upload formats should be confirmed against the active parser configuration; DOCX upload is not part of the requested upload scope.
Persistence responsibilities
Storage component	Role
PostgreSQL	Users, workspaces, datasets, versions, runs, and application metadata
File/artifact storage	Uploaded source files and generated analytical assets
ChromaDB	Document chunks and vector retrieval indexes
Redis	Caching, coordination, or worker-related functionality where configured


The database and file store serve complementary purposes: a metadata record alone is not a substitute for a durable source artifact.
Exploratory analysis and visualization
The analytical interface uses a modular bento-card layout with an emphasis on readable comparisons and contextual evidence.
Chart selection guide
Analytical question	Appropriate representation
How are numeric values distributed?	Histogram
How do two numerical variables relate?	Scatter plot
How does a measure change over time?	Line or time-series chart
Which categories contribute most?	Ranked bar chart
What is the overall total or average?	KPI card
How complete is the dataset?	Missingness summary or matrix
How do numeric columns co-vary?	Correlation view, when valid


Chart calculations should use the intended analytical population, not silently reuse a limited preview. Every chart should retain its metric, dimension, filters, dataset version, and any sampling disclosure.
Design language
The existing visual direction uses dark charcoal, warm off-white, and lime accents, with asymmetric cards and concise analytical labels. Functionality and numerical correctness take priority over decorative chart elements.
Analysis history and reporting
The intended persistent workflow connects AI Analysis and Reports through shared session, run, and artifact records.
Analysis history
A history entry can capture the question, selected dataset/version, execution state, analytical response, tables, charts, and references. Sessions support the intended experience of revisiting prior work and asking contextual follow-up questions.
Detailed reports
A comprehensive analytical report may contain:
1. Title, source details, and generation date.
2. Executive summary and analytical objective.
3. Dataset description and methodology.
4. Data preparation and quality observations.
5. Statistical findings and validated KPIs.
6. Visualizations and supporting tables.
7. Document references and evidence, where applicable.
8. Insights, recommendations, and limitations.
9. Appendix with calculation definitions and source versions.
Report generation should reuse validated analytical artifacts instead of silently recomputing different numbers. Export capabilities depend on the report renderer and format support present in the checked-out revision.
Technology stack
Layer	Technologies used in the project
Frontend	React, TypeScript, Vite, CSS-based application styling
Backend API	Python, FastAPI, Pydantic
Relational database	PostgreSQL, SQLAlchemy, Alembic
Authentication	Supabase Auth / verified token integration
Vector retrieval	ChromaDB
Background and cache infrastructure	Redis and existing worker/orchestration services
AI providers	Configurable LLM and embedding integrations, including OpenAI/Groq/Gemini paths where configured
Analytical processing	Python data processing, statistical and EDA services
Containerization	Docker / Docker Compose
CI	GitHub Actions


Dependency versions and enabled optional providers should be taken from the repository's active lockfiles and environment configuration.
Local development
These are orientation steps, not a substitute for the exact commands in the checked-out repository. Confirm paths, scripts, and service names before running them.

Prerequisites
- Git
- A supported Python version for the backend
- Node.js and npm compatible with the frontend lockfile
- Docker Desktop / Docker Engine and Compose where used
- PostgreSQL, Redis, and ChromaDB according to the selected local run mode
- Supabase configuration for authenticated workflows
- Optional LLM/embedding credentials for provider-backed features
1. Clone and inspect
git clone <YOUR_REPOSITORY_URL>
cd ai-data-analyst-os
2. Configure services
Use the repository's existing environment templates and Compose configuration. Confirm local port mappings rather than assuming container ports match host ports. Historical local development has used FastAPI on 127.0.0.1:8000, Vite on localhost:5173, and PostgreSQL published on host port 5433.
3. Start backend
The Windows-local development workflow has used:
python scripts/run_local_backend.py
Run this from the directory expected by the script, after configuring the database and supporting services. Confirm the script exists in your checkout.
4. Start frontend
cd frontend
npm ci
npm run dev
5. Validate readiness
Confirm the backend health/readiness endpoints, authenticated access, schema compatibility, and connectivity to required services. The frontend should use the configured backend API base URL.
6. Start analyzing
Sign in, choose a workspace, upload or select an authorized dataset, inspect its schema, and open AI Analysis or EDA Studio.
Configuration
The application separates browser-public configuration from backend-only credentials.
Configuration group	Purpose
Backend database URL	PostgreSQL connection
Supabase project URL and publishable key	Browser authentication client
JWT verification settings	Backend token validation
Redis URL	Cache/coordination service
ChromaDB endpoint	Vector retrieval service
LLM provider settings	Model routing and API credentials
File/artifact storage settings	Durable source and output storage
Frontend API base URL	Browser-to-backend connectivity


Never commit .env files containing secrets, database dumps, provider credentials, customer data, or local browser profiles. Public frontend variables must never contain service-role keys or secret provider tokens.
Quality and verification
The project uses backend and frontend tests, migration checks, authentication and dataset-isolation scenarios, and browser-level validation. Useful verification categories include:
- Dataset parsing and schema detection.
- Statistical and numerical correctness.
- Chart-data contracts and rendering.
- RAG retrieval and source attribution.
- Analysis run and session persistence.
- Workspace and dataset access boundaries.
- Database migration compatibility.
- Report artifact accuracy and readability.
- Frontend build and TypeScript checks.
- GitHub Actions CI checks.
For a trustworthy release, results should be verified against known-answer datasets and the actual target environment rather than relying on page rendering alone.
Repository organization
The repository includes, or has historically used, components organized along these lines. Actual paths should be checked against the current revision.
ai-data-analyst-os/
├── frontend/                 # Active React / TypeScript application
├── backend/                  # FastAPI and backend services
├── migrations/               # Database migration history
├── scripts/                  # Development and verification utilities
├── tests/                    # Backend and integration test assets
├── .github/
│   └── workflows/            # CI/CD definitions
├── storage/                  # Configured local data/artifact storage
└── README.md                 # Project documentation
Some deployments and revisions may place backend modules, test directories, or infrastructure files differently. This tree is a conceptual guide, not an audited file manifest.
Roadmap
The major integration goals are:
- Durable seven-stage analytical execution with restart-aware runs.
- Complete, numerically validated EDA/chart-data integration.
- Reliable PDF/document indexing and RAG retrieval lifecycle.
- Persistent AI Analysis conversations and reusable analytical artifacts.
- Detailed report generation and history-based report workflows.
- Version-aware dashboards and forecasting.
- Repeatable authenticated end-to-end and scale testing.
These describe engineering direction, not guaranteed completion status.
Project summary
AI Data Analyst OS combines structured-data analytics, agentic orchestration, document retrieval, visualization, and reporting in a single analytical workspace. Its central objective is to make data exploration more accessible while retaining the precision, provenance, and reproducibility expected from serious analytical software.
Built as an ongoing AI-powered data analytics engineering project.
    
