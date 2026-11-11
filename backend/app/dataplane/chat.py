"""Route registered aggregate intents without loading the source into the API."""
from uuid import UUID
from sqlalchemy import select
from backend.app.dataplane.config import Limits
from backend.app.dataplane.records import scoped, conditions, artifacts, get_record
from backend.app.dataplane.service import enqueue
from backend.app.dataplane.storage import fingerprint
from backend.app.dataplane.contracts import QueryPlan
from backend.app.core.authorization import owned_dataset


def reply(message, status="clarification_required", **extra):
    return {"answer": message, "status": status, "data": [], "explanation": message,
            "actionable": ["Open Data health to view jobs, define metrics and inspect evidence."], **extra}


def route(db, actor, workspace, dataset_id, version_number, message, analytics):
    limits = Limits()
    if not limits.enabled or db is None or not dataset_id:
        return None
    dataset = owned_dataset(db, dataset_id, actor)
    size = dataset.size_bytes
    if size is None and dataset.file_path:
        try:
            size = Path(dataset.file_path).stat().st_size
        except Exception:
            pass
    bounded_legacy = (dataset.canonical_format != "dataplane"
                      and (size is None or size <= 8*1024**2)
                      and (dataset.row_count is None or dataset.row_count <= 10000))
    if not workspace:
        return None if bounded_legacy else reply("Select an authorized workspace before processing this dataset.")
    access = scoped(db, actor, workspace, "write")
    from backend.app.core.workspace_authorization import authorize_bound_dataset
    from backend.app.models.dataset_version import DatasetVersion
    authorize_bound_dataset(db, access, dataset_id)
    version_query = select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
    version_query = version_query.where(DatasetVersion.version_number == version_number) if version_number else version_query.where(DatasetVersion.is_active.is_(True))
    version = db.scalar(version_query)
    if version is None:
        return reply("The requested dataset version is unavailable.")
    candidates = db.execute(select(artifacts).where(*conditions(access), artifacts.c.kind == "snapshot",
        artifacts.c.dataset_id == dataset_id).order_by(artifacts.c.created_at.desc()).limit(100)).mappings().all()
    snapshot = next((r for r in candidates if r["payload"]["version_id"] == version.version_id), None)
    if not snapshot:
        return None if bounded_legacy else reply("Create a data processing snapshot before querying this dataset.")
    schema = snapshot["payload"]["schema"]
    numeric = [c for c, t in schema.items() if any(s in t.lower() for s in ("int", "float", "double", "decimal"))]
    parsed = analytics.parse(message, list(schema), numeric, [])
    if parsed.clarification_required or parsed.operation not in ("sum", "average", "count") or parsed.aggregation not in ("sum", "mean", "avg", "count", None):
        return None if bounded_legacy else reply("Choose a registered sum, average or count metric for this snapshot.")
    aggregation = {"mean": "avg", "average": "avg"}.get(parsed.aggregation or parsed.operation, parsed.aggregation or parsed.operation)
    from backend.app.models.learning import BusinessDefinition
    from backend.app.dataplane.company import query_payload, eligible
    from backend.app.dataplane.company_contracts import CompanyQuery
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from fastapi import HTTPException
    approved = []
    governed_match = False
    for candidate in db.scalars(select(BusinessDefinition).where(BusinessDefinition.workspace_id == access.workspace_id).limit(100)):
        spec = candidate.governance.get('spec')
        if not spec or spec['dataset_id'] != dataset_id:
            continue
        base = spec['definition']['metric']
        if base['column'] != parsed.metric or {'mean': 'avg'}.get(base['aggregation'], base['aggregation']) != aggregation:
            continue
        governed_match = True
        if not candidate.active or candidate.governance.get('status') != 'approved':
            continue
        business_date = datetime.now(timezone.utc).astimezone(ZoneInfo(spec['timezone'])).date()
        try:
            eligible(db, access, candidate.id, business_date)
        except HTTPException:
            continue
        approved.append((candidate, business_date))
    if len(approved) > 1:
        return reply('Several approved company meanings match. Choose the definition and business date in Data health.')
    if governed_match and not approved:
        return reply('No eligible approved company definition is available. Review the definition and effective date in Data health.')
    company_payload = None
    if approved:
        selected, business_date = approved[0]
        company_payload = query_payload(db, access, CompanyQuery(definition_id=selected.id,
            snapshot_id=snapshot['id'], business_date=business_date,
            plan=QueryPlan(metric=selected.key, dimensions=parsed.dimensions, limit=100), idempotency_key='chat'))
    metrics = db.execute(select(artifacts).where(*conditions(access), artifacts.c.kind == "metric",
        artifacts.c.parent_id == snapshot["id"]).order_by(artifacts.c.created_at.desc()).limit(100)).mappings().all()
    match = next((m for m in metrics if m["payload"]["definition"]["aggregation"] == aggregation
                  and m["payload"]["definition"]["column"] == parsed.metric), None)
    if not match and not company_payload:
        return reply("Define and review this metric in Data health before it can be calculated.")
    if company_payload:
        payload = company_payload
    else:
        plan = QueryPlan(metric=match["payload"]["definition"]["name"], dimensions=parsed.dimensions, limit=100)
        payload = {"dataset_id": dataset_id, "snapshot_id": str(snapshot["id"]), "metric_id": str(match["id"]),
                   "plan": plan.model_dump()}
    job = enqueue(db, access, "dp_query", fingerprint(payload), payload)
    if job["status"] == "READY":
        access = scoped(db, actor, workspace)
        evidence = get_record(db, access, job["result"]["artifact_id"], "evidence")
        data = evidence["payload"]
        answer = "; ".join(", ".join(f"{k}: {v}" for k, v in row.items()) for row in data["rows"][:10])
        return {"answer": answer or "No matching groups.", "status": "complete", "data": data["rows"],
                "plan": data["plan"], "explanation": "Computed by the recorded engine against an immutable snapshot.",
                "actionable": [], "citations": [{"evidence_id": str(evidence["id"]), "workspace_id": str(workspace), "query_hash": data["query_hash"]}]}
    if job["status"] in ("FAILED", "CANCELLED"):
        return reply("The data processing job did not complete. Inspect its status in Data health.", "failed",
                     plan={"job_id": str(job["id"])})
    return reply("Calculation queued. View its result and evidence in Data health.", "queued",
                 plan={"job_id": str(job["id"])})

