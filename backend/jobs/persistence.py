"""SQL persistence adapter for BackgroundJobManager, with fenced lease commits."""
from datetime import timedelta
from uuid import UUID, uuid4
from sqlalchemy import select, update, or_, and_
from sqlalchemy.exc import IntegrityError
from backend.app.models.background_job import DurableJob, utcnow

ACTIVE = ('RUNNING', 'EXTRACTING', 'CHUNKING', 'EMBEDDING', 'INDEXING')
PHASES = ('RUNNING', 'EXTRACTING', 'CHUNKING', 'EMBEDDING', 'INDEXING', 'READY')


class LostLeaseError(RuntimeError):
    pass


class PersistentJobStore:
    def __init__(self, session_factory, lease_seconds=60):
        self.sessions = session_factory
        self.lease_seconds = lease_seconds

    @staticmethod
    def snapshot(row):
        return {column.name: getattr(row, column.name) for column in DurableJob.__table__.columns}

    def get(self, job_id):
        with self.sessions() as db:
            row = db.get(DurableJob, UUID(str(job_id)))
            return self.snapshot(row) if row else None

    def create(self, *, workspace_id, owner_id, kind, key, payload, retry_eligible=True):
        values = dict(workspace_id=UUID(str(workspace_id)), owner_id=UUID(str(owner_id)),
                      kind=kind, idempotency_key=key, payload=payload, retry_eligible=retry_eligible)
        try:
            with self.sessions() as db, db.begin():
                job = DurableJob(**values)
                db.add(job)
                db.flush()
                return self.snapshot(job)
        except IntegrityError:
            with self.sessions() as db:
                existing = db.scalar(select(DurableJob).where(DurableJob.workspace_id == values['workspace_id'],
                    DurableJob.kind == kind, DurableJob.idempotency_key == key))
                if existing is None or existing.owner_id != values['owner_id'] or existing.payload != payload:
                    raise ValueError('Idempotency key conflicts with existing request') from None
                return self.snapshot(existing)

    def claim(self, worker_id, kinds):
        now = utcnow()
        with self.sessions() as db, db.begin():
            expired = and_(DurableJob.status.in_(ACTIVE), DurableJob.lease_expires_at < now)
            db.execute(update(DurableJob).where(expired, or_(DurableJob.attempt >= DurableJob.max_attempts,
                                                           DurableJob.retry_eligible.is_(False)))
                       .values(status='FAILED', error_code='LEASE_RETRIES_EXHAUSTED', retry_eligible=False,
                               completed_at=now, updated_at=now, lease_token=None))
            row = db.scalar(select(DurableJob).where(DurableJob.kind.in_(kinds),
                DurableJob.attempt < DurableJob.max_attempts,
                or_(DurableJob.status == 'QUEUED', and_(expired, DurableJob.retry_eligible.is_(True))))
                .order_by(DurableJob.created_at).with_for_update(skip_locked=True).limit(1))
            if row is None:
                return None
            # Row lock protects PostgreSQL claims; CAS also protects engines without row locks.
            token = uuid4()
            claimed = db.execute(update(DurableJob).where(DurableJob.id == row.id,
                DurableJob.attempt == row.attempt, DurableJob.status == row.status,
                DurableJob.lease_token == row.lease_token).values(status='RUNNING', attempt=row.attempt+1,
                worker_id=worker_id, lease_token=token, lease_expires_at=now+timedelta(seconds=self.lease_seconds),
                started_at=row.started_at or now, updated_at=now, completed_at=None, error_code=None))
            if claimed.rowcount != 1:
                return None
            db.flush()
            db.expire_all()
            return self.snapshot(db.get(DurableJob, row.id))

    def advance(self, job_id, token, status, result=None):
        now = utcnow()
        with self.sessions() as db, db.begin():
            row = db.get(DurableJob, UUID(str(job_id)))
            if row is None or row.status not in ACTIVE or row.lease_token != token:
                raise LostLeaseError('Job lease lost or cancellation committed')
            if status not in PHASES or PHASES.index(status) < PHASES.index(row.status):
                raise ValueError('Invalid job transition')
            values = dict(status=status, updated_at=now)
            if status == 'READY':
                values.update(result=result, completed_at=now, lease_token=None, lease_expires_at=None)
            changed = db.execute(update(DurableJob).where(DurableJob.id == row.id,
                DurableJob.status == row.status, DurableJob.lease_token == token,
                DurableJob.lease_expires_at > now).values(**values).execution_options(synchronize_session=False))
            if changed.rowcount != 1:
                raise LostLeaseError('Job lease expired or state changed')

    def heartbeat(self, job_id, token):
        now = utcnow()
        with self.sessions() as db, db.begin():
            changed = db.execute(update(DurableJob).where(DurableJob.id == UUID(str(job_id)),
                DurableJob.lease_token == token, DurableJob.status.in_(ACTIVE),
                DurableJob.lease_expires_at > now).values(lease_expires_at=now+timedelta(seconds=self.lease_seconds), updated_at=now))
            if changed.rowcount != 1:
                raise LostLeaseError('Cannot renew lost lease')

    def fail(self, job_id, token, code, retry_eligible):
        now = utcnow()
        with self.sessions() as db, db.begin():
            changed = db.execute(update(DurableJob).where(DurableJob.id == UUID(str(job_id)),
                DurableJob.lease_token == token, DurableJob.status.in_(ACTIVE), DurableJob.lease_expires_at > now)
                .values(status='FAILED', error_code=code, retry_eligible=retry_eligible,
                        lease_token=None, completed_at=now, updated_at=now))
            return changed.rowcount == 1

    def cancel(self, job_id):
        with self.sessions() as db, db.begin():
            changed = db.execute(update(DurableJob).where(DurableJob.id == UUID(str(job_id)),
                DurableJob.status.in_(('UPLOADED', 'QUEUED', *ACTIVE))).values(
                    status='CANCELLED', lease_token=None, updated_at=utcnow(), completed_at=utcnow()))
            if changed.rowcount != 1:
                raise ValueError('Job cannot be cancelled from its current state')

    def retry(self, job_id):
        with self.sessions() as db, db.begin():
            changed = db.execute(update(DurableJob).where(DurableJob.id == UUID(str(job_id)),
                DurableJob.status == 'FAILED', DurableJob.retry_eligible.is_(True),
                DurableJob.attempt < DurableJob.max_attempts).values(status='QUEUED', error_code=None,
                    lease_token=None, updated_at=utcnow(), completed_at=None))
            if changed.rowcount != 1:
                raise ValueError('Job is not eligible for retry')
