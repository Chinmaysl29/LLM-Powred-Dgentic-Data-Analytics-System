# Approved scope: complete Stages 3–6

On 9 November 2026 the user explicitly authorized all remaining stages without further stage approvals. The audit's earlier stop requirements are superseded. Existing runtime/learning systems remain preserved; no new model training is authorized or needed.

| Finding | Smallest repair | Risk / regression |
| --- | --- | --- |
| F-001 | Validate XLSX header uniqueness before constructing dictionaries | Reject ambiguous input without changing originals; duplicate/case-equivalent header tests |
| F-012 (new P1) | Authorize the persisted source run on report manifest/download reads | Reproduced HTTP 200 to another tenant; test both endpoints plus revoked workspace access. Prioritized immediately after F-001. |
| F-002 | Enforce declared first-record JSONL keys before Arrow conversion | Reject extra fields rather than silently discard them; within/across-batch tests |
| F-003 | Consult revocation state in protected local-token verification | Authentication compatibility; real logout token rejection |
| F-004 | Persist hashed revocations and consume refresh tokens atomically | Database outage must fail closed; restart, replay/concurrent refresh tests; additive migration |
| F-005 | Add missing partial unique index after conflict preflight | Refuse migration if conflicting active versions exist; real database constraint test and copied-database roundtrip |
| F-006 | Explicitly reject unsupported text encodings before CSV publication | Preserve valid UTF-8/BOM/TSV; rejected encoding and checksum tests |
| F-007 | Make migration comparison aware of all managed metadata; resolve actual nullable drift | No automatic destructive autogeneration; compare empty-migrated schema and expected tables |
| F-008 | Replace GPU-capable XGBoost distribution with compatible CPU package and update lock | Preserve XGBoost import/API; fresh build, dependency graph and forecasting suite |
| F-009 | Configure monitoring thresholds and gate distribution warnings on sufficient history | Preserve descriptive summaries; minimum-history and custom-threshold boundary tests |
| F-010 | Supply deterministic CSV export of persisted report evidence; reject unknown formats | Preserve existing formats; generate/download/reopen CSV and unsupported-format test |
| F-011 | Derive scalar KPIs from stored evidence and preserve numeric Excel cells | No recalculation or invented values; API/evidence/KPI/report parity tests |

Each repair starts with the audit reproduction plus a failing regression, then targeted verification and the requested full backend/frontend gate before its commit. No existing failing tests will be weakened. A fix that fails twice will be reverted and reported as open, as instructed. Independent future improvements are excluded.

Rollback: each fix has a dedicated commit and can be reverted individually after reviewing subsequent dependencies. Prefer feature rollback over destructive database downgrade. New database objects must have tested downgrades in an isolated copy; no user data is deleted. Existing backups and the audit stash remain retained. Deploy only after verification, then repeat real flag-matrix, browser, authentication/restart, tenant-isolation and evidence export checks.
