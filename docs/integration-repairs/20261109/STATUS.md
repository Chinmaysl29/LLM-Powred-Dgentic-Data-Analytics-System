# Repair execution evidence

The user authorized all remaining stages on 9 November 2026. The earlier audit's phase approval stops are superseded; its findings remain a historical baseline.

| Finding | State | Evidence |
| --- | --- | --- |
| F-001 | Fixed, committed `4014841` | `F-001-isolated-backend.log`: 386 passed; frontend typecheck/build passed |
| F-012 | Fixed, committed `56b7f23` | 387 backend tests passed; frontend typecheck/build passed. Owner reads succeed; unrelated tenant and revoked tenant/workspace membership get 404 for both manifest and download. |
| F-002 | Fixed, committed `776a9ae` | 391 backend tests and frontend typecheck/build passed. |
| F-003 | Fixed, committed `fa43ec3` | 394 backend tests and frontend typecheck/build passed. |
| F-004 | Fix under full verification | 7 targeted auth tests passed, including fresh-service replay and concurrent consumption. Restored-copy upgrade/downgrade/upgrade preserved all 4,896 original rows across 62 tables. |
| F-005 through F-011 | Pending | F-005, F-006, F-008, F-009 and F-010 have reproduced failing regressions staged under this evidence directory. See `docs/INTEGRATION_REPAIR_PLAN.md`. |

The first F-012 revocation fixture revoked workspace membership while leaving tenant-owner authority active. Existing `authorize_workspace` explicitly permits tenant owners. The user approved correcting this fixture to revoke both memberships, with the 404 assertions unchanged. The earlier full run was interrupted after discovering this fixture error; it is not accepted verification evidence.

Stopped the obsolete `dataanalyst-dataplane-audit`, `dataanalyst-quality`, `dataanalyst-perceptron-phase8`, and `dataanalyst-perceptron-phase1` verification containers to free Docker resources. Their containers and volumes remain available. The production `dataanalyst` services and current `dataanalyst-integration-audit` database/cache/vector services remain running.

No live deployment of the repair set has been performed yet.

Implementation references: [SQLAlchemy PostgreSQL conflict handling](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert) and [PostgreSQL INSERT/RETURNING](https://www.postgresql.org/docs/17/sql-insert.html). CPU package availability was verified against PyPI's `xgboost-cpu/2.1.4/json` metadata (Linux x86_64/aarch64 and Windows amd64 wheels; NumPy/SciPy runtime requirements).
