"""One shared heavy-work budget for the existing PostgreSQL durable queue.

Claims, not private subsystem counters, own admission. The transaction lock only
serializes the short admission decision; the durable lease owns the running slot.
Executors must terminate children when their lease cannot be renewed.
"""
from sqlalchemy import select, text

from backend.app.models.background_job import DurableJob


HEAVY_KINDS = frozenset({
    'dp_ingest', 'dp_query', 'dp_quality', 'dp_proposal', 'dp_clean',
    'dp_postgres', 'dp_workflow', 'analysis_pipeline', 'rag', 'learning_eval',
    'adaptive_replay', 'adaptive_train',
})
LOCK_NAMESPACE = 1145130835  # Stable application namespace, not Python's salted hash.
LOCK_RESOURCE = 1


def admitted_kinds(db, kinds, now, active_states):
    """Keep heavy work queued while any unexpired heavy lease holds the slot.

    Must be called within the same transaction that claims the job. PostgreSQL
    is the deployed durable authority. Unsupported databases fail closed for
    heavy work instead of pretending to enforce process-wide concurrency.
    """
    kinds = tuple(dict.fromkeys(kinds))
    if not HEAVY_KINDS.intersection(kinds):
        return kinds
    if db.get_bind().dialect.name != 'postgresql':
        raise RuntimeError('Heavy-job admission requires the PostgreSQL durable queue')
    acquired = db.scalar(text('SELECT pg_try_advisory_xact_lock(:namespace, :resource)'),
        {'namespace': LOCK_NAMESPACE, 'resource': LOCK_RESOURCE})
    if not acquired:
        return tuple(kind for kind in kinds if kind not in HEAVY_KINDS)
    running = db.scalar(select(DurableJob.id).where(
        DurableJob.kind.in_(HEAVY_KINDS), DurableJob.status.in_(active_states),
        DurableJob.lease_expires_at > now).limit(1))
    if running is not None:
        return tuple(kind for kind in kinds if kind not in HEAVY_KINDS)
    return kinds
