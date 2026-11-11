"""Opt-in dataplane API. Heavy work is queued, never executed in the API."""
import hashlib
import io
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import Field, SecretStr
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.security import get_current_user
from backend.app.core.workspace_authorization import authorize_bound_dataset, dataset_workspace_bindings
from backend.app.database.postgres import get_db_session
from backend.app.models.dataset import Dataset
from backend.app.models.dataset_version import DatasetVersion
from backend.app.models.background_job import DurableJob
from backend.app.dataplane.config import Limits
from backend.app.dataplane.contracts import StrictModel, Metric, QueryPlan, CleaningPlan
from backend.app.dataplane.ingestion_policy import IngestionOptions
from backend.app.dataplane.records import scoped, conditions, artifacts, get_record, add_record
from backend.app.dataplane.service import enqueue, KINDS
from backend.app.dataplane.storage import scope_root, fingerprint
from backend.jobs.persistence import PersistentJobStore

router = APIRouter(prefix="/dataplane", tags=["Data processing"])


def enabled():
    limits = Limits()
    if not limits.enabled:
        raise HTTPException(503, "Data processing is disabled")
    return limits


def public(row):
    value = {k: str(v) if isinstance(v, UUID) else v for k, v in dict(row).items()}
    if value.get("kind") == "connector":
        value["payload"] = {k: v for k, v in value["payload"].items() if k != "encrypted"}
    if value.get('kind') == 'evidence':
        value['payload'] = {k: v for k, v in value['payload'].items() if k not in ('sql', 'parameters', 'estimate', 'curated', 'report_artifact')}
        if value['payload'].get('plan'):
            value['payload']['plan'] = {**value['payload']['plan'], 'filters': [
                {**item, 'value': '[redacted]'} for item in value['payload']['plan'].get('filters', [])]}
    return value


def summary(row):
    value = public(row)
    value["payload"] = {k: v for k, v in value["payload"].items()
                        if k not in ("files", "original", "quarantine", "estimate", "sql", "parameters")}
    if "rows" in value["payload"]:
        value["payload"]["rows"] = value["payload"]["rows"][:100]
    return value


def job_view(job):
    return {k: str(v) if isinstance(v, UUID) else v for k, v in job.items()
            if k in ("id", "kind", "status", "attempt", "error_code", "result", "created_at", "completed_at")}


@router.get("/status")
def status(user=Depends(get_current_user)):
    limits = Limits()
    return {"enabled": limits.enabled, "engine": limits.engine_default, "upload_mb": limits.upload_mb}


@router.get("/dashboard")
def dashboard(workspace_id: UUID, response: Response, offset: int = 0,
              db: Session = Depends(get_db_session), user=Depends(get_current_user), limits=Depends(enabled)):
    access = scoped(db, user.id, workspace_id)
    if not 0 <= offset <= 10000:
        raise HTTPException(422, "Invalid page")
    rows = db.execute(select(artifacts).where(*conditions(access)).order_by(artifacts.c.created_at.desc())
                      .offset(offset).limit(51)).mappings().all()
    from backend.app.core.workspace_authorization import authorized_bound_dataset_ids
    allowed = authorized_bound_dataset_ids(db, access, {row['dataset_id'] for row in rows[:50] if row['dataset_id']})
    visible = [summary(row) for row in rows[:50] if not row['dataset_id'] or row['dataset_id'] in allowed]
    jobs = db.scalars(select(DurableJob).where(DurableJob.workspace_id == workspace_id,
        DurableJob.owner_id == user.id, DurableJob.kind.in_(KINDS))
        .order_by(DurableJob.created_at.desc()).limit(30)).all()
    response.headers["Cache-Control"] = "private, no-store"
    return {"records": visible, "next_offset": offset+50 if len(rows)>50 else None,
            "jobs": [job_view(PersistentJobStore.snapshot(j)) for j in jobs],
            "limits": {"memory_mb": limits.memory_mb, "timeout_s": limits.timeout_s}}


@router.get("/artifacts/{record_id}")
def artifact(record_id: UUID, workspace_id: UUID, response: Response,
             db: Session = Depends(get_db_session), user=Depends(get_current_user), limits=Depends(enabled)):
    response.headers["Cache-Control"] = "private, no-store"
    return public(get_record(db, scoped(db, user.id, workspace_id), record_id))


@router.get("/jobs/{job_id}")
def job_status(job_id: UUID, workspace_id: UUID, db: Session = Depends(get_db_session),
               user=Depends(get_current_user), limits=Depends(enabled)):
    access = scoped(db, user.id, workspace_id)
    row = db.get(DurableJob, job_id)
    if row is None or row.owner_id != access.actor_id or row.workspace_id != access.workspace_id or row.kind not in KINDS:
        raise HTTPException(404, "Job not found")
    if row.payload.get("dataset_id"):
        authorize_bound_dataset(db, access, row.payload["dataset_id"])
    return job_view(PersistentJobStore.snapshot(row))


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: UUID, workspace_id: UUID, db: Session = Depends(get_db_session),
               user=Depends(get_current_user), limits=Depends(enabled)):
    scoped(db, user.id, workspace_id, "write")
    job_status(job_id, workspace_id, db, user, limits)
    db.commit()
    try:
        PersistentJobStore(sessionmaker(db.get_bind())).cancel(job_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from None
    return {"status": "CANCELLED"}


@router.post("/upload", status_code=202)
async def upload(workspace_id: UUID = Form(...), idempotency_key: str = Form(...),
                 file: UploadFile = File(...), ingestion_options: str = Form('{}'), db: Session = Depends(get_db_session),
                 user=Depends(get_current_user), limits=Depends(enabled)):
    access = scoped(db, user.id, workspace_id, "write")
    try:
        if len(ingestion_options.encode()) > 16384:
            raise ValueError('Ingestion settings exceed 16 KiB')
        options = IngestionOptions.model_validate_json(ingestion_options).model_dump(mode='json')
    except ValueError:
        raise HTTPException(422, 'Invalid ingestion settings; use the documented typed policy') from None
    if not 1 <= len(idempotency_key) <= 128:
        raise HTTPException(422, "Invalid idempotency key")
    name = Path((file.filename or "").replace("\\", "/")).name
    suffix = Path(name).suffix.lower()
    if suffix not in {".csv", ".tsv", ".parquet", ".xlsx", ".jsonl", ".ndjson"}:
        raise HTTPException(422, "Use CSV, TSV, Parquet, XLSX or JSONL")
    dataset_id, version_id = str(uuid4()), str(uuid4())
    folder = scope_root(limits.root, access.tenant_id, access.workspace_id, access.actor_id)/"incoming"/dataset_id
    folder.mkdir(parents=True, exist_ok=False)
    source = folder/("original"+suffix)
    size, checksum = 0, hashlib.sha256()
    with source.open("xb") as target:
        while chunk := await file.read(1024**2):
            size += len(chunk)
            if size > limits.upload_mb*1024**2:
                raise HTTPException(413, "Upload exceeds configured limit")
            checksum.update(chunk)
            target.write(chunk)
    if size == 0:
        raise HTTPException(422, "Empty upload")
    lock_key = int.from_bytes(hashlib.sha256((str(workspace_id)+":"+idempotency_key).encode()).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    old = db.scalar(select(DurableJob).where(DurableJob.workspace_id == workspace_id,
        DurableJob.kind == "dp_ingest", DurableJob.idempotency_key == idempotency_key))
    if old:
        if (old.owner_id != user.id or old.payload.get("source_hash") != checksum.hexdigest()
                or old.payload.get('ingestion_options', IngestionOptions().model_dump(mode='json')) != options):
            raise HTTPException(409, "Idempotency key conflicts with existing upload")
        return job_view(PersistentJobStore.snapshot(old))
    db.add(Dataset(dataset_id=dataset_id, owner_id=str(user.id), dataset_name=name,
        file_name=name, file_type=suffix[1:], file_path=str(source), original_path=str(source),
        content_hash=checksum.hexdigest(), size_bytes=size, status="uploaded", canonical_format="dataplane"))
    db.flush()
    db.add(DatasetVersion(version_id=version_id, dataset_id=dataset_id, version_number=1,
        change_type="initial_upload", storage_path=str(source), metadata_snapshot={}, quality_snapshot={},
        is_active=True, created_by=str(user.id)))
    db.execute(dataset_workspace_bindings.insert().values(dataset_id=dataset_id, workspace_id=workspace_id))
    # Dataset, binding, version and queue record commit together: no ready-less upload gap.
    queued = DurableJob(workspace_id=workspace_id, owner_id=user.id, kind="dp_ingest",
        idempotency_key=idempotency_key, payload={"dataset_id": dataset_id,
        "version_id": version_id, "source_hash": checksum.hexdigest(), 'ingestion_options': options}, retry_eligible=True)
    db.add(queued)
    db.flush()
    job = PersistentJobStore.snapshot(queued)
    db.commit()
    return {**job_view(job), "dataset_id": dataset_id}


class Ingest(StrictModel):
    dataset_id: str
    version_id: str
    idempotency_key: str = Field(min_length=1, max_length=128)
    ingestion_options: IngestionOptions = Field(default_factory=IngestionOptions)


@router.post("/ingest", status_code=202)
def ingest(body: Ingest, workspace_id: UUID, db: Session = Depends(get_db_session),
           user=Depends(get_current_user), limits=Depends(enabled)):
    access = scoped(db, user.id, workspace_id, "write")
    from backend.app.dataplane.service import resolve_source
    resolve_source(db, access, body.dataset_id, body.version_id, limits)
    return job_view(enqueue(db, access, "dp_ingest", body.idempotency_key,
                           body.model_dump(mode='json', exclude={"idempotency_key"})))


class DefineMetric(StrictModel):
    dataset_id: str
    snapshot_id: UUID | None = None
    connector_id: UUID | None = None
    definition: Metric


@router.post("/metrics", status_code=201)
def metric(body: DefineMetric, workspace_id: UUID, db: Session = Depends(get_db_session),
           user=Depends(get_current_user), limits=Depends(enabled)):
    access = scoped(db, user.id, workspace_id, "write")
    authorize_bound_dataset(db, access, body.dataset_id)
    if bool(body.snapshot_id) == bool(body.connector_id):
        raise HTTPException(422, "Select exactly one data source")
    parent = get_record(db, access, body.snapshot_id or body.connector_id,
                        "snapshot" if body.snapshot_id else "connector")
    if body.snapshot_id and parent["dataset_id"] != body.dataset_id:
        raise HTTPException(422, "Snapshot dataset mismatch")
    identity = add_record(db, access, "metric", {"definition": body.definition.model_dump(),
        "connector_id": str(body.connector_id) if body.connector_id else None},
        dataset_id=body.dataset_id, parent_id=parent["id"])
    db.commit()
    return {"id": identity}


class Query(StrictModel):
    snapshot_id: UUID | None = None
    connector_id: UUID | None = None
    metric_id: UUID
    plan: QueryPlan
    idempotency_key: str = Field(min_length=1, max_length=128)


@router.post("/query", status_code=202)
def query(body: Query, workspace_id: UUID, db: Session = Depends(get_db_session),
          user=Depends(get_current_user), limits=Depends(enabled)):
    access = scoped(db, user.id, workspace_id, "write")
    definition = get_record(db, access, body.metric_id, "metric")
    if bool(body.snapshot_id) == bool(body.connector_id):
        raise HTTPException(422, "Select exactly one source")
    parent = get_record(db, access, body.snapshot_id or body.connector_id,
                        "snapshot" if body.snapshot_id else "connector")
    if definition["parent_id"] != parent["id"]:
        raise HTTPException(422, "Metric source mismatch")
    payload = body.model_dump(mode="json", exclude={"idempotency_key"})
    payload["dataset_id"] = definition["dataset_id"]
    try:
        return job_view(enqueue(db, access, "dp_query" if body.snapshot_id else "dp_postgres",
                               body.idempotency_key, payload))
    except ValueError as error:
        raise HTTPException(409, str(error)) from None


class Propose(StrictModel):
    plan: CleaningPlan


@router.post("/snapshots/{snapshot_id}/quality", status_code=202)
def quality(snapshot_id: UUID, workspace_id: UUID, db: Session = Depends(get_db_session),
            user=Depends(get_current_user), limits=Depends(enabled)):
    from datetime import datetime, timezone
    access = scoped(db, user.id, workspace_id, "write")
    snapshot = get_record(db, access, snapshot_id, "snapshot")
    key = f"quality:{snapshot_id}:{datetime.now(timezone.utc).date()}"
    return job_view(enqueue(db, access, "dp_quality", key,
                           {"snapshot_id": str(snapshot_id), "dataset_id": snapshot["dataset_id"]}))


@router.post("/snapshots/{snapshot_id}/cleaning", status_code=202)
def proposal(snapshot_id: UUID, body: Propose, workspace_id: UUID, db: Session = Depends(get_db_session),
             user=Depends(get_current_user), limits=Depends(enabled)):
    access = scoped(db, user.id, workspace_id, "write")
    snapshot = get_record(db, access, snapshot_id, "snapshot")
    payload = {"snapshot_id": str(snapshot_id), "dataset_id": snapshot["dataset_id"], "plan": body.plan.model_dump()}
    return job_view(enqueue(db, access, "dp_proposal", fingerprint(payload), payload))


@router.post("/proposals/{proposal_id}/approve", status_code=202)
def approve(proposal_id: UUID, workspace_id: UUID, db: Session = Depends(get_db_session),
            user=Depends(get_current_user), limits=Depends(enabled)):
    access = scoped(db, user.id, workspace_id, "write")
    proposal = get_record(db, access, proposal_id, "proposal")
    # Serialize approvals on this immutable proposal so retries use one approval id.
    db.execute(select(artifacts.c.id).where(artifacts.c.id == proposal_id, *conditions(access)).with_for_update())
    prior = db.execute(select(artifacts).where(*conditions(access), artifacts.c.kind == "approval",
                       artifacts.c.parent_id == proposal_id)).mappings().first()
    approval_id = str(prior["id"]) if prior else add_record(db, access, "approval",
        {"proposal_hash": fingerprint(proposal["payload"]), "approved_by": str(user.id)},
        dataset_id=proposal["dataset_id"], parent_id=proposal_id)
    db.commit()
    return job_view(enqueue(db, access, "dp_clean", "clean:"+str(proposal_id),
        {"dataset_id": proposal["dataset_id"], "snapshot_id": str(proposal["parent_id"]),
         "proposal_id": str(proposal_id), "approval_id": approval_id}))


class Connector(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(5432, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=63)
    username: str = Field(min_length=1, max_length=63)
    password: SecretStr
    schema_name: str = Field("public", min_length=1, max_length=63)
    table: str = Field(min_length=1, max_length=63)


@router.post("/connectors", status_code=201)
def connector(body: Connector, workspace_id: UUID, db: Session = Depends(get_db_session),
              user=Depends(get_current_user), limits=Depends(enabled)):
    access = scoped(db, user.id, workspace_id, "manage")
    from backend.app.dataplane.postgres import encrypt
    config = body.model_dump(exclude={"name", "password"})
    config["password"] = body.password.get_secret_value()
    config["sslmode"] = "verify-full"
    try:
        token = encrypt(config, limits)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    dataset_id = str(uuid4())
    db.add(Dataset(dataset_id=dataset_id, owner_id=str(user.id), dataset_name=body.name,
        file_name=body.table, file_type="postgres", file_path="", status="connected",
        canonical_format="dataplane"))
    db.flush()
    db.execute(dataset_workspace_bindings.insert().values(dataset_id=dataset_id, workspace_id=workspace_id))
    identity = add_record(db, access, "connector", {"name": body.name, "encrypted": token,
        "host": body.host, "table": body.table, "status": "unverified"}, dataset_id=dataset_id)
    db.commit()
    return {"id": identity, "dataset_id": dataset_id, "status": "unverified"}


@router.get("/evidence/{evidence_id}/report")
def report(evidence_id: UUID, workspace_id: UUID, db: Session = Depends(get_db_session),
           user=Depends(get_current_user), limits=Depends(enabled)):
    value = get_record(db, scoped(db, user.id, workspace_id), evidence_id, "evidence")
    if value['payload'].get('require_artifact_review'):
        from backend.app.dataplane.company import current_event
        access = scoped(db, user.id, workspace_id)
        if current_event(db, access, evidence_id)['status'] != 'approved':
            raise HTTPException(409, 'This workflow artifact is awaiting review and approval')
    from backend.app.dataplane.reporting import render_pdf
    if value['payload'].get('report_artifact'):
        from backend.app.dataplane.storage import confined, digest
        access = scoped(db, user.id, workspace_id)
        root = scope_root(limits.root, access.tenant_id, access.workspace_id, access.actor_id)
        stored = value['payload']['report_artifact']
        try:
            path = confined(root, stored['path'])
            if path.stat().st_size != stored['bytes'] or stored['bytes'] > 8 * 1024**2 or digest(path) != stored['sha256']:
                raise ValueError('Report integrity failed')
            content = path.read_bytes()
        except (OSError, ValueError):
            raise HTTPException(410, 'Retained report is unavailable or failed integrity verification; restore its backup') from None
    else:
        content = render_pdf(str(evidence_id), value['payload'])
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="evidence-{evidence_id}.pdf"',
                             "Cache-Control": "private, no-store"})
