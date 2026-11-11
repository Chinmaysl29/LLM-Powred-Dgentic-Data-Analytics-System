# Company review architecture

## Canonical records and permissions

`backend/app/dataplane/company_contracts.py` contains strict public contracts.
`BusinessDefinition` remains the authoritative definition store. Its existing
immutable content is extended by `governance` with a typed specification, hash,
effective dates, revision, lifecycle state, release-check evidence and reviewer.
The database trigger protects specification and content identity while allowing
the explicit review-to-approved transition. Historical definitions receive `{}`;
this means unreviewed/unknown, not retroactive approval.

`LearningAudit` retains policy decisions and review events. Self-approval starts
unconfigured, and requires an explicit manager policy action. Creation and review
submission require source-owner write permission. Independent reviewers require
an explicit active grant for that dataset; owner self-approval additionally needs
manage permission and the explicit policy. Version selection and workflow
execution controls retain their existing owner/manage checks. The server-derived
workspace membership, tenant state and account ownership checks remain in force.
Workspace IDs are selectors, never proof of permission.

The user selected **explicit reviewer grants per dataset** on 10 November 2026.
Migration 023 adds expiring grants with source-owner assignment, workspace-member
eligibility, optimistic revisions, retained audit history and owner/manager
revocation. A grant permits approval of submitted definitions, workflow manifests
and validated outputs, including by a workspace viewer. It does not permit draft
editing, activation, raw records, SQL, downloads, cleaning or query execution.

`reviewer.py` and `reviewer_api.py` implement this capability independently of
`authorize_bound_dataset`, which remains owner-only. Two narrow SECURITY DEFINER
functions return only submitted metadata and bounded aggregates, with file paths,
raw samples, SQL, parameters and filter literals removed. Both have fixed
`pg_catalog` search paths, schema-qualified references and PUBLIC execution
revoked. Deployers must retain a trusted migration owner able to read canonical
artifacts and grant execution only to service roles using
`infrastructure/company_review_role_grants.sql`. End users never receive DB roles.
The RLS policies and functions recheck active tenant/workspace/user memberships,
source ownership/binding/status and unexpired grants on each request. Grant
revocation is serialized with approval; it stops future access while retaining
the owner's previous approval evidence. Already approved workflow versions keep
their decision history and remain subject to the ordinary execution gates.

## Definition use and lifecycle

The immutable definition lifecycle is draft → review → approved →
superseded/revoked. Edits use a new key/version pair. Revision preconditions reject
stale review actions. Key-level transaction locks serialize overlapping approvals.
Aliases cannot overlap an approved definition in the same dataset/domain/effective
period. Effective end dates are exclusive. Approval verifies the aggregate against
an actual source schema and checks small supplied examples with an independent
Decimal oracle. Examples are metadata bounded to 16 KiB; they do not prove
population correctness or establish company policy.

Approved company runs use `/dataplane/company/query`. They select an explicit
definition ID, source snapshot, business date and structured aggregate plan.
Approved filters are always composed into the executed query. The business date
selects an effective definition; it does not silently filter source records.
Optional time windows require offset-aware boundaries and a timezone-aware source
timestamp. Ambiguous untyped source dates are rejected. The existing chat route
uses the unique eligible approved definition for a matching metric and abstains
when several meanings match or a governed definition has been revoked.

Existing directly registered metrics remain exploratory. The company workflow
cannot promote their output without the new reviewed-definition provenance.
Existing learning definitions/recipes and legacy analytics are preserved.

## Execution and evidence

`DurableJob` and `dataplane.worker` remain the only heavy-job queue and worker.
The worker rechecks identity, source ownership, definition status, effective scope,
content hashes and workflow state before execution and publication. Publication
locks the current lease; stale/cancelled workers cannot publish. The unique job
publication constraint prevents duplicate artifacts after a retry.

`EvidenceContract` validates required version, workspace/run/result IDs, immutable
source, definition identity, coverage, status, time, result/query digests,
precision, model configuration and lineage before publication. Stored engine
results also retain the executed typed plan, actual engine/dependency version,
quality findings and configured resource limits. Provider/model/prompt are `none`
for this deterministic path. No provider call or hidden reasoning is invented.

The calculation dialog reads stored metadata. A separate manager-only technical
view includes parameterized SQL with redacted values. Raw parameters, physical
scan plans and storage paths are excluded from public evidence responses.
PDF generation uses the same bounded result rows and frozen metadata. Current
definition advisories are separate from historical evidence. Legacy report pages
show the explicit historical-evidence-unavailable notice.

## Health and cleaning

Configured not-null, uniqueness and range checks run across the full immutable
snapshot inside the bounded child. They record observed/expected values, rule
version, time, coverage and status. Only failed critical checks on recorded required
fields block company publication. A failed connector/executor is a failed job,
never a passing health finding. No health/accuracy percentage is synthesized.

Blocking incidents are deduplicated by immutable source, definition and finding
content. Incident views list the latest 100 outputs for the dataset, with direct,
unaffected or unknown impact from snapshot/field lineage. Incomplete historical
lineage stays unknown. Acknowledgement never changes the failed evidence.
Resolution needs later passing evidence from the same definition; the original
failed snapshot remains recorded and the recovery evidence is linked separately.

Existing cleaning proposals now include bounded before/after rows, in addition to
the labeled first-1000-row sample counts. Full execution reconciles retained and
quarantined rows and creates an inactive immutable version. Explicit activation
and undo use a dataset lock and expected-active-version precondition. Neither
operation deletes history or modifies original bytes. Missing retained files
produce an actionable retention error. Source hashes and approval hashes remain
checked by the existing engine/publication path.
Migration 022 also repairs the earlier audit's missing partial unique index for
active dataset versions, after refusing any pre-existing conflicts. This guards
the invariant across legacy writers that do not use the new API's dataset lock.

## Comparison and workflows

Comparisons reauthorize both input artifacts, check definitions, units, currency,
grain, filters, timezone, window length, transformations and validation coverage,
and preserve mismatches rather than silently rerunning. Decimal deltas use 38
significant digits; percentages use the absolute baseline and six decimal places.
Zero baselines have undefined percentages. Nulls stay missing. New and removed
groups are explicit. Additive dimension contributions reconcile to totals;
non-additive attribution is declined. Source, quality and engine changes are
reported separately, without claiming a business cause.

Workflow versions are immutable typed aggregate manifests. They support
draft/review/approval/activation/pause/retirement, pinned or active-at-start file
snapshots, absolute or completed-day relative windows, frozen definition versions,
resource caps, idempotent manual runs and independent artifact review.
Exact resolved source/window/filter identities are pinned at enqueue and rechecked
at execution/publication. A subsequent active-version change cannot rewrite a
queued manifest. Output states distinguish awaiting review from succeeded.

Schedules start absent/disabled and require a successful manual run before an
explicit manager enables them. They use an IANA zone, first DST occurrence,
skipped nonexistent local time, no overlap, latest-slot-only bounded catch-up and
durable slot idempotency keys. Recent-run views show actual scheduled slots and
the catch-up policy. Scheduling reuses successful workflow jobs as its registry.
No external message delivery is implemented or enabled.

## Explicit scope limits

The new company path executes approved single-source aggregate definitions. A
general term/dimension/field-mapping editor, arbitrary formula language, company
join authoring and multi-step workflow builder
remain unimplemented. The existing adaptive system retains its separate tested
net-revenue/refund recipe and counterexample; that is not a claim that generic
join definitions or new reviewed correction operators were added here.

Connected PostgreSQL execution remains the earlier read-only exploratory adapter;
the new company workflow does not yet bind approved definitions to live remote
watermarks. External credentials, provider evaluation, real company definitions,
production deployment acceptance, notification destinations and retention policy
have not been supplied or certified by this implementation.
