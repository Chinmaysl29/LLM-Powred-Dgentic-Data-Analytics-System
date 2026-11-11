# Adaptive verification evidence

All data in this directory are synthetic. Passwords, tokens and provider keys are excluded. Tests run against a separately named PostgreSQL16/Redis7/Chroma0.6.3 Compose project, not the application's database. Main LLM/embedding weights remain frozen.

| Artifact | Meaning |
| --- | --- |
| `baseline/` | Pre-change regression baseline:75 passing checks |
| `pytest.xml` | Final backend regression, actual database roles/workers, recovery and train/evaluate tests |
| `environment.json` | Installed versions, migration/schema inspection and preserved older-table counts |
| `verification.json` | Actual state and automated exit code |
| `synthetic-fixtures.json` |40 declared cases, source CSV observations, immutable split/group and independent Decimal gold |
| `training-job.json` | Durable training request, thresholds/gates frozen at enqueue, case/label/skill/runtime snapshots and measurements |
| `model-bundles.json` | Both real fitted JSON weight artifacts, train-only preprocessing, manifests, compatibility and final evaluation |
| `selector-comparison.json` | Eight paired final cases, three policies, outcomes, cost/latency, denominator definitions and limitations |
| `browser/browser-results.json` | Real Chromium UI journey checks; no response mocks |
| `browser/*.png` | Actual desktop/mobile UI captures |
| `browser/*report.json` | Private reports downloaded through the UI;285 net revenue and2 refund events |
| `browser/linear-model-bundle.json` | Actual live-worker-trained candidate downloaded through the UI |
| `persistence.json` | Exact report/model bytes and rollback state after PostgreSQL/API restart |
| `frontend-check.log` | Targeted lint and production TypeScript/Vite build |
| `tooling.json` | Additional lint/grant/build scope and explicitly unrun external checks |

The classification pilot has24 train cases (48 local action outcomes),8 development cases (16 outcomes) and8 untouched final cases. Every source is labeled synthetic. Train contains36 positive and12 negative actions: exact parsing succeeds, while checked vector conversion rejects high-precision loss. Final alternatives are executed after fitting, using the same catalog/validators for rules, linear and MLP. Fixtures differ in dataset identity and exact fingerprints; they share a synthetic template and do not establish production independence or broad coverage.

Rules, linear and MLP all returned8/8 correct on the final set, with8/8 first-repair successes,0 harmful verified outputs,0 repeated errors,0 abstentions and0 unknowns. Observed paired correctness delta is0; the paired scenario-bootstrap interval is[0,0] on this small synthetic set. Neither learned candidate earned activation. Zero trusted production final groups and no measured policy benefit block release; latency is also checked against the frozen gate. Lower action classification loss does not establish a better policy.

Observed final backend run: **88 passed in81.70s**, including the prior75 regression checks. Migration012 →011 →012 preserved counts in the earlier learning tables. The complete fitting/tuning run took0.640s with one numerical CPU thread. Observed process RSS was740.10MiB (increase0.77MiB); this includes the already loaded application, not just weights, and is sampled rather than a system-wide peak.

| Policy | Final correct /8 | Parameters | Scorer p95 ms | Whole executor p95 ms | Release |
| --- | --- | --- | --- | --- | --- |
| Rules/memory |8 |0 | not separately measured |14.763 | retained |
| Logistic C=1 |8 |17 |0.015 |16.431 | blocked: no benefit or trusted final coverage |
| MLP128/64 |8 |10,497 |0.052 |22.935 | blocked: no benefit, no trusted coverage, latency gate |

Scorer timings use50 calls, policy timings only8 cases on this local CPU/container environment. They are descriptive measurements, not production service-level guarantees. Linear is the preferred candidate on tied correctness; rules remains active.

Chromium passed16 real UI checks, including actual login, upload of both CSVs, verified285 chart/report, restored task form after refresh, diagnosis, skill metadata, refund-event result2, trained model download, shadow execution, rollback and390px layout. Responses were not mocked. After restarting the test PostgreSQL/API services, both report downloads and the JSON model download were byte-identical and rollback persisted (`persistence.json`).

Model artifacts in the integration test are snapshots captured before delayed label disputes intentionally revoke both candidates. The browser pilot trains separate real candidates through live APIs/worker, uses shadow, and rolls back. No production model was activated. No calibration is claimed or plotted. Scores remain logits, live exploration is disabled and provider execution cost is0 for these local approved operations.

The optional frozen-provider interpretation was tested with explicitly mocked responses, poisoning and connection failure. No live provider credentials were present. Browser authentication uses the real backend password path, not hosted Supabase. Historical setup/learning evidence elsewhere in `docs/` is kept separately. See [operating guide](../ADAPTIVE_SYSTEM.md) for exact implementation, run commands and limitations.
