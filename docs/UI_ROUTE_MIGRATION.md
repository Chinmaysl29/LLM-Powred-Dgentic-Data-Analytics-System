# Internal route migration

Updated 2026-10-12. **All 13 redesigned routes confirmed in the authenticated running application.**

All routes use `frontend/src/main.tsx` → `frontend/src/App.tsx` → `RequireAuth` → `frontend/src/layouts/AppLayout.tsx` → the component below. Components were refactored in place; no parallel router or preview application was introduced. All share `src/index.css`, then `src/styles/workspace-design.css`, with persisted appearance applied by `useApplyAppearance`.

Paths below are relative to `frontend/src/pages/app/`. “Source” means the normal running Vite transform matches the local file, not that an authenticated browser rendered it. Initial component SSR checks pass for all 13.

| Route | Previous component | Active redesigned component | Interface | Source / initial render | Live verified |
| --- | --- | --- | --- | --- | --- |
| `/dashboard` | DashboardPage.tsx | DashboardPage.tsx | Lime metric tile, dark question composer, registry and report overview | Pass / pass | Yes (render) |
| `/datasets` | DatasetsPage.tsx | DatasetsPage.tsx | Editorial heading, upload, filterable registry, metadata, detail links | Pass / pass | Yes (render) |
| `/connections` | ConnectionsPage.tsx | ConnectionsPage.tsx | Connector cards, capability states, warehouse action | Pass / pass | Yes (render) |
| `/data-warehouse` | DataWarehousePage.tsx | DataWarehousePage.tsx | Schema explorer and table inspector, designed metadata-unavailable state | Pass / pass | Yes (render) |
| `/analysis` | AnalysisPage.tsx | AnalysisPage.tsx | Dark hero, dataset selector, question composer, recorded answers | Pass / pass | Yes (render) |
| `/visualizations` | VisualizationsPage.tsx | VisualizationsPage.tsx | Asymmetric dark/lime gallery, distribution and scatter, chart controls | Pass / pass | Yes (render) |
| `/insights` | InsightsPage.tsx | InsightsPage.tsx | Recommendation summary, evidence cards, dataset drill-down | Pass / pass | Yes (render) |
| `/forecasting` | ForecastingWorkbenchPage.tsx | ForecastingWorkbenchPage.tsx | Model controls, dated historical/forecast plot, interval band, exact values | Pass / pass | Yes (render) |
| `/reports` | ReportsPage.tsx | ReportsPage.tsx | Searchable saved-report gallery, record preview, JSON download | Pass / pass | Yes (render) |
| `/dashboard-studio` | DashboardStudioPage.tsx | DashboardStudioPage.tsx | Configuration inspector, snapshot canvas, grid/stacked layout | Pass / pass | Yes (render) |
| `/memory` | AIMemoryExplorerPage.tsx | AIMemoryExplorerPage.tsx | Session lookup inspector, searchable conversation timeline | Pass / pass | Yes (render) |
| `/profile` | ProfilePage.tsx | ProfilePage.tsx | Account identity/editor and security panel | Pass / pass | Yes (render) |
| `/settings` | SettingsPage.tsx | SettingsPage.tsx | Persisted appearance and honest account/workspace capability panels | Pass / pass | Yes (render) |

Upload, dataset details and report subroutes retain their existing route registrations and handlers. `/insights/what-if` remains mapped to InsightsPage without fabricated scenario results. All 13 routes were captured at 1440, 1280, 1024, 768, 390 and 360px after the user signed in through the real login form. Each had one active sidebar destination and no document overflow. Desktop screenshots were visually inspected; account disclosure and mobile drawer navigation passed. Insights renders its error state because its recommendations endpoint returns HTTP 503. Render verification does not certify every backend workflow or exact Figma fidelity.
