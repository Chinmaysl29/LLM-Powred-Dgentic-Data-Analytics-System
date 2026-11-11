"""Controlled-clock, latest-only scheduling on the existing durable queue."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from fastapi import HTTPException
from backend.app.dataplane.records import scoped, get_record
from backend.app.dataplane.company import current_event
from backend.app.models.background_job import DurableJob
from backend.app.dataplane.service import enqueue


def due_slot(configuration, now):
    """One UTC instant. Fold 0 wins; nonexistent local wall times are skipped."""
    zone = ZoneInfo(configuration['timezone'])
    local = now.astimezone(zone)
    for days in (0, 1):
        target = (local - timedelta(days=days)).replace(hour=configuration['hour'],
            minute=configuration['minute'], second=0, microsecond=0, fold=0)
        utc = target.astimezone(timezone.utc)
        roundtrip = utc.astimezone(zone)
        if roundtrip.replace(tzinfo=None) != target.replace(tzinfo=None):
            continue
        if utc <= now:
            return utc
    return None


def schedule_workflows(sessions, now=None, offset=0):
    now = now or datetime.now(timezone.utc)
    # Existing successful manual runs are the schedule registry; enabling a schedule
    # requires such a run. This avoids a second scheduler/job metadata store.
    with sessions() as db:
        rows = db.execute(select(DurableJob.owner_id, DurableJob.workspace_id,
            DurableJob.payload['workflow_id'].as_string().label('workflow_id'))
            .where(DurableJob.kind == 'dp_workflow', DurableJob.status == 'READY')
            .distinct().order_by(DurableJob.owner_id, DurableJob.workspace_id, 'workflow_id')
            .offset(offset).limit(100)).all()
        for actor, workspace, identity in rows:
            try:
                access = scoped(db, actor, workspace, 'write')
                get_record(db, access, identity, 'workflow')
                configuration = current_event(db, access, identity, 'schedule')
                if not configuration.get('enabled') or current_event(db, access, identity)['status'] != 'active':
                    continue
                slot = due_slot(configuration, now)
                configured = datetime.fromisoformat(configuration['configured_at'])
                if slot is None or slot < configured:
                    continue
                # Do not overlap running or queued effects. Exact slot keys dedupe
                # scheduler restarts; one latest slot bounds catch-up after downtime.
                active = db.scalar(select(DurableJob.id).where(DurableJob.kind == 'dp_workflow',
                    DurableJob.workspace_id == workspace, DurableJob.owner_id == actor,
                    DurableJob.payload['workflow_id'].as_string() == identity,
                    DurableJob.status.in_(['QUEUED', 'RUNNING', 'CANCEL_REQUESTED'])).limit(1))
                if active:
                    continue
                from backend.app.dataplane.company_api import workflow_payload
                payload = workflow_payload(db, access, identity, now=slot)
                payload['schedule_slot'] = slot.isoformat()
                payload['schedule_policy'] = 'Latest due slot only; earlier missed slots skipped'
                enqueue(db, access, 'dp_workflow', f'schedule:{identity}:{slot.isoformat()}', payload)
            except (HTTPException, ValueError):
                db.rollback()  # Access/definition revocation cannot create new jobs.
        return offset + len(rows) if len(rows) == 100 else 0
