# Internal UI recovery: root cause

> Historical snapshot. Current 2026-10-12 evidence and unresolved gates are maintained in the [analytical correctness verification matrix](../reports/ANALYTICAL_CORRECTNESS_REMEDIATION_REPORT.md). Browser access has recovered through manual sign-in; 78 captures verified layout/navigation, with recommendations HTTP 503 from a missing database table still open. The backend has since restarted with current contracts and readiness 200. Earlier completion or blocked-browser statements do not supersede that record.

Date: 2026-10-12. Runtime source mismatch confirmed and corrected; redesigned protected routes verified after manual sign-in.

## Active frontend

- Host source: `C:\data analyst\ai-data-analyst-os\frontend`.
- Served root: `/app`, Windows source mounted through Docker Desktop's 9p/DrvFS filesystem.
- Origin checked: `http://localhost:5173` and `http://127.0.0.1:5173`.
- Mode: Vite development, command `node /app/node_modules/.bin/../vite/bin/vite.js --host`, launched through `npm run dev -- --host` in the development Dockerfile.
- Active entry: `src/main.tsx` -> `App.tsx` -> `RequireAuth` -> `AppLayout` -> routed page.
- Source identity verified using the running process mountinfo and HTTP `?raw` responses. Main entry, AppLayout and Dashboard source matched local files exactly.

## Confirmed cause

The running Vite server returned an obsolete transformed `main.tsx`. Its JavaScript imported `index.css` but omitted `styles/workspace-design.css`. The same server's `main.tsx?raw` response included that import and matched the host source byte-for-byte. Therefore the correct files exist in the active mount, but the server's transformed-module cache was not invalidated after host-side changes.

The source mount is Windows-to-Linux 9p. `vite.config.ts` had no polling watcher configuration. This provides a concrete explanation for missed host change notifications and the stale transform; it is not a browser-cache assumption. The missing final stylesheet leaves the dark-blue defaults in `src/index.css` active. A raw request for `styles/workspace-design.css` succeeds, so the stylesheet is present rather than missing from the repository.

## Source and routing findings

`src/App.tsx` imports the actual existing internal page files, and all protected routes share `src/layouts/AppLayout.tsx`. There is no second internal routing system. `frontend` is the browser application; the other package.json found is for `mobile`. Previous redesign work is present as uncommitted edits and new files, including the stylesheet, hooks and pages; it was not absent from the checkout. The active branch was `main`, latest inspected commit `c7a600c`. Existing unrelated work is preserved.

Actual CSS order: `main.tsx` imports `index.css` (which includes phase23-part1 through part5) then `styles/workspace-design.css`. AppLayout calls `useApplyAppearance`; stored appearance may intentionally select dark mode. This setting is independent of the missing stylesheet defect.

A second source-confirmed shell defect: the desktop selector `.ws-main.ws-main--expanded` has greater specificity than the mobile `.ws-main--expanded` reset, leaving a 260px margin on small screens. The mobile rule must use matching specificity.

## Corrective action and risks

Enabled development-server file polling at 500ms and strict port selection in the existing Vite configuration. Reloaded the existing frontend process by touching its config through the active Linux mount. The normal entry transform now imports the redesign stylesheet. Corrected the mobile margin selector. No backend or authentication code was changed during this recovery.

Polling adds development-only filesystem work; a 500ms interval limits that overhead. Strict port selection prevents a second unnoticed server from silently choosing a different port. Reloading the frontend may refresh an open page; backend services and data are not restarted. Do not clear unrelated caches, delete build output or create a second frontend.

## Verification requirements

Check that the normal `/src/main.tsx` response imports the redesign stylesheet and that served module source maps match local source. Exercise a reversible host-side edit to confirm cache invalidation. Run the existing production build, lint and tests. Then verify the authenticated shell and all thirteen pages in a browser at the requested widths.

At initial investigation, CUA reported no browser and could not create a Chrome tab. The computer-use node runtime failed with `failed to write kernel assets ... path specified`. Figma design context and screenshot calls for the supplied files returned the Starter-plan tool limit. The referenced screen recording and third screenshot were not available in this attachment. No screenshots, Figma fidelity or authenticated-route visual checks are claimed.

## Completed runtime checks

`node scripts/check-served-source.mjs --check-watcher` passed: all 16 normal transformed modules (entry, router, layout, 13 pages) contain source maps matching this checkout, and the redesign stylesheet is served. A temporary comment appended on the Windows host appeared in the normal Vite transform without a manual reload. Only that marker was removed afterward; the check was repeated against restored source successfully.

Playwright with the installed Chrome provides a working browser fallback. A separate headed window is open at the real login page for manual sign-in. No reusable configured test account was identified, and no credentials or sessions were fabricated. A separate signed-out browser verified that all 13 protected routes redirect to login and that login has no horizontal document overflow at all six requested widths. Login screenshots were captured; the mobile screenshot was inspected. Authenticated page screenshots and exact Figma comparisons remain pending.

Subsequently, the user completed manual sign-in in that browser. Authenticated captures now confirm all 13 new route interfaces at all six widths, with zero document overflow. Visual inspection caught additional legacy CSS conflicts and a blank lowercase `ready` status label, which were fixed. Interaction checks passed; the remaining service failure is HTTP 503 for the selected dataset's recommendations. See `UI_TEST_RESULTS.md` for final evidence and limits. Exact Figma comparison remains unavailable.
