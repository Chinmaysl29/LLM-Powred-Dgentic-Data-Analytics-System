# Frontend architecture audit — 2026-10-12

Scope: frontend implementation and requested UI documentation only. Existing backend, infrastructure, storage and other uncommitted changes belong to the pre-existing workspace and must be preserved.

## Baseline

React 19, TypeScript 6, Vite 8, React Router 7; handwritten CSS, Lucide and Motion. No Tailwind configuration or separate chart package in the frontend package. Existing SVG chart components and chartDataTransforms provide eight chart modes. All 13 destinations already have lazy route imports and an authentication guard. Supabase/session authentication and the shared fetch client's authorization, timeout and cancellation behavior must remain intact.

`npm.cmd run build` passed before editing. Three existing Node workbench tests passed. Lint started separately. PowerShell blocks npm.ps1; use npm.cmd. Existing Docker/nginx and environment setup are outside the edit scope. Never print environment secrets.

## Findings and actions

| Area | Existing state inspected | Action |
|---|---|---|
| Authentication | Supabase or backend session flow; eight-second transformation with 0/2000/4500/7200/8000 ms stages and reduced-motion mode | Preserve; visually inspect |
| Dashboard | Five-item dataset registry and analysis shortcut, no operational summary | Add source-labeled registry summary without fictional counts |
| Datasets | List/upload/detail/profile/quality/cleaning service calls | Preserve functionality and align tokens |
| Connections | Unavailable message; enterprise connector routes need capability review | Show supported/unavailable capability honestly |
| Warehouse | Unavailable message although /schema routes exist | Inspect route registration and schema contracts; connect read-only metadata if available |
| AI Analysis | /chat, abort, context selection, returned evidence, session question history | Preserve; dark editorial hero and usable composer |
| Visualizations | Hardcoded sales/marketing data, false recent history, inert controls; reusable SVG renderers | Replace production data source; retain supported chart types, field mapping and filters; source-labeled sample scope |
| Insights | Existing analysis-backed workflow | Preserve and restyle |
| Forecasting | Dataset preview and model endpoints, diagnostics, JSON export | Preserve; maintain sample disclosure |
| Reports | History and detail routes; unavailable creation/editing explicitly stated | Preserve honest state; expose request failures |
| Dashboard Studio | Existing dataset-backed dashboard workflow | Preserve and restyle |
| AI Memory | Explicit workspace/session lookup with export/search | Preserve and restyle; no invented discovery/deletion |
| Profile | Authenticated profile, unsupported management explained | Preserve real identity |
| Settings | Unavailable-only placeholder | Implement browser appearance preferences and persistence; distinguish admin controls |
| API client | Shared fetch, bearer token, timeout, AbortSignal, typed errors | Reuse; no endpoint invention |
| Responsive | Existing mobile drawer with focus trap, inert content and Escape handling | Preserve; test all requested widths |
| Accessibility | Existing labels and reduced motion; inconsistent form/layout styling | Visible focus, semantic chart alternatives, responsive controls |

## Figma access

Both files were accessible for metadata. Login frame 1:2; application frames: Dashboard 2:2, Datasets 2:87, Connections 2:173, Warehouse 2:262, Analysis 2:334, Visualizations 2:396, Insights 2:538, Forecasting 2:624, Reports 2:709, Studio 2:798, Memory 2:880, Profile 2:966, Settings 2:1034. These are 1440x960 interior concepts with a 260px sidebar and 74px header.

Figma Starter-plan MCP limit blocked get_design_context and get_screenshot. High-fidelity tokens, screenshots and motion extraction could not be obtained. No reference screenshots were attached to this turn. Use the directive's explicit fallback palette, black/lime editorial composition, and existing conventions. Do not claim pixel fidelity. Preserve working functionality where conceptual Figma metrics or layouts would misrepresent actual data.

## Integration boundaries

Backend files are inspected read-only to establish contracts. Live authorization, provider availability and server-side data isolation require runtime verification; frontend layout changes cannot establish production readiness. Keep unavailable capabilities clearly marked and do not add backend behavior to satisfy visual concepts.
