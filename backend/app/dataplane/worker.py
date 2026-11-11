"""Separate single-slot worker; Postgres is the durable queue, Redis optional."""
import logging
import socket
import time
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from backend.app.core.config import get_settings
from backend.app.core.database_target import bind_database_schema
from backend.app.dataplane.config import Limits
from backend.app.dataplane.service import KINDS, prepare, publish
from backend.app.dataplane.supervisor import execute, WorkerCapacityError
from backend.jobs.persistence import PersistentJobStore, LostLeaseError

logger = logging.getLogger(__name__)


def process_one(sessions, limits, worker_id):
    store = PersistentJobStore(sessions)
    job = store.claim(worker_id, KINDS)
    if not job:
        return False
    try:
        with sessions() as db:
            request, directory, parent_id = prepare(db, job, limits)
        result = execute(request, directory,
            lambda: store.heartbeat(job["id"], job["lease_token"]), timeout_s=request['limits']['timeout_s'])
        with sessions() as db, db.begin():
            publish(db, job, result, parent_id)
    except LostLeaseError:
        logger.info("Dataplane job lost its lease; no result published")
    except Exception as error:
        # Store a stable code; exception contents can contain sensitive input.
        code = "TIMEOUT" if isinstance(error, TimeoutError) else "CAPACITY_EXCEEDED" if isinstance(error, WorkerCapacityError) else "EXECUTION_REJECTED"
        retryable = isinstance(error, (SQLAlchemyError, OSError)) and job["attempt"] < job["max_attempts"]
        changed = store.fail(job["id"], job["lease_token"], code, retry_eligible=retryable)
        if changed and retryable:
            time.sleep(min(10, 2 ** job["attempt"]))
            store.retry(job["id"])
        logger.warning("Dataplane job failed: %s", code)
    return True


def schedule_quality(sessions, offset=0):
    """Rotating bounded batches; daily keys deduplicate manual and scheduled checks."""
    from datetime import datetime, timezone
    from backend.app.models.background_job import DurableJob
    from backend.app.dataplane.records import scoped, get_record
    from backend.app.dataplane.service import enqueue
    from fastapi import HTTPException
    with sessions() as db:
        jobs = db.scalars(select(DurableJob).where(DurableJob.kind.in_(("dp_ingest", "dp_clean")),
            DurableJob.status == "READY").order_by(DurableJob.created_at, DurableJob.id)
            .offset(offset).limit(100)).all()
        for job in jobs:
            try:
                access = scoped(db, job.owner_id, job.workspace_id, "write")
                snapshot = get_record(db, access, job.result["artifact_id"], "snapshot")
                identity = str(snapshot["id"])
                enqueue(db, access, "dp_quality", f"quality:{identity}:{datetime.now(timezone.utc).date()}",
                        {"snapshot_id": identity, "dataset_id": snapshot["dataset_id"]})
            except HTTPException:
                db.rollback()  # Revoked memberships are not scheduled.
        return offset + len(jobs) if len(jobs) == 100 else 0


def main():
    limits = Limits()
    if not limits.enabled:
        raise SystemExit("DATAPLANE_ENABLED must be true for this worker")
    settings = get_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True, pool_size=2, max_overflow=0)
    bind_database_schema(engine, settings.database_schema)
    sessions = sessionmaker(engine, expire_on_commit=False)
    identity = f"dataplane-{socket.gethostname()}-{uuid4()}"
    heartbeat = limits.root/"worker-health"
    heartbeat.parent.mkdir(parents=True, exist_ok=True)
    scheduled, offset, workflow_scheduled, workflow_offset = 0.0, 0, 0.0, 0
    try:
        while True:
            try:
                if time.monotonic() - workflow_scheduled > 60:
                    from backend.app.dataplane.company_schedule import schedule_workflows
                    workflow_offset = schedule_workflows(sessions, offset=workflow_offset)
                    workflow_scheduled = time.monotonic()
                if limits.monitoring_enabled and time.monotonic()-scheduled > limits.monitoring_interval_s:
                    offset = schedule_quality(sessions, offset)
                    scheduled = time.monotonic()
                worked = process_one(sessions, limits, identity)
                heartbeat.touch()
                if not worked:
                    time.sleep(1)
            except Exception:
                logger.warning("Dataplane queue unavailable")
                time.sleep(5)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
