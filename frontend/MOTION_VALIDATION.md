# Login animation validation — 14 October 2026

## A. Root cause and scope

The checkout already contained a partial single-viewport implementation. In `src/components/auth/DataTransformationAnimation.tsx`, the previous condition `isVerifiedRunning && !isReducedMotion` selected LIVE ANIMATION; every other condition selected STATIC PREVIEW. In `useDataPipelineMotion`, verification began false and became true only after three frame callbacks. Thus startup and deliberate reduced motion shared a misleading label. A fresh baseline session initially showed STATIC PREVIEW at 0.0 seconds, then a second observation verified that the existing loop advanced. A persistent one-cycle freeze was not reproducible; no unsupported claim is made that missing keyframes caused it.

Concrete defects found in the hook: initial OS reduced-motion preference was ignored, preference changes only handled enabling reduction, stored live preference bypassed OS reduction, storage access could throw, and visibility handling merely reset timestamps without explicitly cancelling/restarting playback or clearing the verified badge. Its 200 ms delta clamp could slow the master clock during long active frames. The previous test called a two-second FPS sample an extended-runtime check and assigned memory stability from FPS; it did not test ten minutes.

The controller now handles preferences in both directions, safely accesses storage, pauses/cancels on hidden, resumes with one callback, derives elapsed time modulo 7000 ms, and updates React captions only at phase changes. LIVE appears after advancing callbacks; reduced and waiting states are distinct. This is a lifecycle repair and visual refinement of the existing native animation, not only a label change.

## B. Figma

Requested file: https://www.figma.com/design/pG1Of8WkryiAmfX8SNB9t4

The Figma connector rejected the initial inspection: “You've reached the Figma MCP tool call limit on the Starter plan.” No Figma nodes were changed. No updated frame URL, native loop capability, motion preview, or video export has been verified. The React implementation is the working deliverable; editing and verifying the existing Figma file remains blocked by that external account limit.

## C. React files

- `src/hooks/useDataPipelineMotion.ts`: one active-time requestAnimationFrame controller, preference listeners, visibility lifecycle, phase snapshots, cleanup.
- `src/components/auth/DataTransformationAnimation.tsx`: honest playback status and accessible pause control; stable descriptive screen-reader text.
- `src/components/auth/RawDataStage.tsx`: deterministic drift settles before alignment; continuous boundary positions; removed discontinuous scanning sweep.
- `src/components/auth/CleaningStage.tsx`: validation reveals derive from the master clock without independent spring transitions.
- `src/components/auth/AnimatedChartMorph.tsx`: the same six persistent SVG paths interpolate their Bezier control points from rectangles into circular segments; segment angles now correspond to values. Donut center opacity/scale derives from the timeline.
- `src/components/auth/PipelineProgress.tsx`: transform-based progress; continuous return during reset.
- `src/styles/login-motion.css`: fixed caption/footer boxes, narrow-screen containment, reduced-motion styling.
- `scripts/verify-motion-continuity.mjs`: real-time ten-minute acceptance run, per-cycle geometry checks, browser performance/DOM counters, input and lifecycle tests.
- `scripts/test_motion_loop.mjs`: delegates to the real acceptance suite, replacing the misleading legacy test.
- Additional `scripts/check-motion-*.mjs`: focused accessibility, boundary, cleanup, login, and visibility verification.

Authentication services, route guards, database/RLS, uploaded datasets, and login submission code were not edited in this task. Successful sign-in and dashboard redirection were exercised with the supplied account; its datasets page loaded. Credentials are not stored in test scripts or report artifacts.

## D. Timeline

| Active time | State |
|---|---|
| 0.00–1.50 s | Deterministic scattered raw records |
| 1.50–2.25 s | Overlapping raw-to-structured fade and alignment |
| 2.25–3.35 s | Structured rows and sequential validation |
| 3.35–4.00 s | Rows fade into chart baseline/grid |
| 4.00–4.95 s | Linear, bottom-anchored staggered bar growth |
| 4.95–5.95 s | Continuous compatible SVG-path morph |
| 5.95–6.55 s | Completed donut hold |
| 6.55–7.00 s | Donut-to-raw crossfade; opening geometry restored |

The sequence uses one fixed viewport, a seven-second modulo clock at 1×, and no repeat counter or terminal state. Hidden tabs pause active time; reduced motion shows the completed donut. Unmount removes subscriptions and cancels the pending callback.

## E–F. Test evidence and performance

Final measurements are recorded in `.ui-review/motion-validation/report.json`; focused checks are in `boundary.json`, `cleanup.json`, `login.json`, and `visibility.json`. Screenshots include the raw, structured, chart and morph states, plus desktop/mobile views.

- Build: `npm run build` passed.
- Targeted ESLint: all six edited TypeScript files passed.
- Actual adjacent boundary frames: raw opacity 0.985 ? 1; chart opacity 0.015 ? 0; maximum raw-token displacement 0.1 px.
- Five manual pause/resume cycles: maximum one pending pipeline callback; zero after navigation unmount.
- System reduced motion, preference restoration, and persisted manual pause passed the focused browser check.
- Supplied-account sign-in: passed; redirected to dashboard; animation unmounted; datasets page loaded.
- Controlled `visibilitychange` hide/resume: passed. This is explicitly a synthetic event test.

The sustained run is wall-clock playback, not an accelerated clock. Frame rate measures requestAnimationFrame callback frequency, not GPU presentation FPS. Heap samples include React development mode and bounded test instrumentation; forced-GC retained-heap samples are distinguished from uncollected heap measurements.

## G. Outstanding limitations

Figma authoring/playback is blocked by the connector quota. Actual hidden-tab behavior could not be confirmed by switching automated Edge/Chrome tabs: they kept reporting `document.hidden === false`, including attempts with focus emulation disabled. Synthetic visibility handling and Chromium lifecycle suspension are tested separately and must not be mislabeled as that real-tab result. Mobile checks use browser viewport emulation, not a physical device. Firefox and Safari were not tested. No public deployment was requested or performed; the application is available locally at http://localhost:5173/login.

### Completed sustained run

- PASS: 600.864 seconds of continuous visible playback; 85 observed resets, including 84 fully observed cycles after the initial partial cycle. Every full cycle showed all eight stages, near-zero initial bar height, completed bar height, and distinct intermediate morph geometry.
- PASS: zero sampled blank scenes, zero hidden samples, fixed viewport/form bounds, zero animation-time network requests, and zero uncaught page errors.
- PASS: input typing retained focus, reduced-motion donut remained unchanged, Chromium freeze/resume recovered, and 375 px mobile viewport contained the page.
- Observed requestAnimationFrame rate: 99.80 callbacks/second averaged across the entire run.
- Retained heap after warm-up: 20.02 MiB at 60 seconds to 20.41 MiB at 600 seconds (small increase includes accumulated test cycle records). No runaway growth was observed; this finite test is not a proof against every possible leak.
- Event listeners stayed at 192 in every sample from 60 through 600 seconds. The document count stayed at one after startup.

Reproduce: `node scripts/verify-motion-continuity.mjs` from the frontend directory with the local application running. Default duration is 600,000 ms. The report contains the individual per-cycle evidence and raw measurements.
