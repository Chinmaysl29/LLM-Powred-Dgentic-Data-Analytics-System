"""Real PostgreSQL admission tests across independently claiming worker sessions."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import update

from backend.app.models.background_job import DurableJob, utcnow
from backend.jobs.persistence import PersistentJobStore, LostLeaseError
from backend.tests.test_verified_learning_integration import environment, identity


def enqueue(store, owner, kind):
    return store.create(workspace_id=owner['workspace'], owner_id=owner['user'],
        kind=kind, key=str(uuid4()), payload={}, retry_eligible=True)


def test_analytics_and_training_claim_one_shared_heavy_slot(environment):
    owner = identity(environment)
    store = PersistentJobStore(environment['worker'])
    jobs = [enqueue(store, owner, kind) for kind in ('dp_query', 'adaptive_train')]
    rendezvous = Barrier(2)
    def claim(index):
        rendezvous.wait(timeout=5)
        return PersistentJobStore(environment['worker']).claim(f'shared-slot-{index}',
            ('dp_query', 'adaptive_train'))
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            claimed = list(pool.map(claim, range(2)))
        winners = [job for job in claimed if job is not None]
        assert len(winners) == 1
        assert store.claim('another-worker', ('dp_query', 'adaptive_train')) is None
        light = enqueue(store, owner, 'lesson_extract')
        light_claim = store.claim('light-worker', ('lesson_extract',))
        assert light_claim['id'] == light['id']
        store.cancel(light_claim['id'])
        store.cancel(winners[0]['id'])
        remaining = store.claim('next-heavy', ('dp_query', 'adaptive_train'))
        assert remaining is not None and remaining['id'] != winners[0]['id']
    finally:
        for job in jobs:
            current = store.get(job['id'])
            if current['status'] in ('QUEUED', 'RUNNING'):
                store.cancel(job['id'])


def test_expired_heavy_lease_can_recover_but_stale_attempt_cannot_renew(environment):
    owner = identity(environment)
    store = PersistentJobStore(environment['worker'])
    job = enqueue(store, owner, 'adaptive_train')
    first = store.claim('expired-heavy', ('adaptive_train',))
    assert first['id'] == job['id']
    try:
        with environment['admin']() as db, db.begin():
            db.execute(update(DurableJob).where(DurableJob.id == job['id']).values(
                lease_expires_at=utcnow()-timedelta(seconds=1)))
        second = store.claim('replacement-heavy', ('adaptive_train',))
        assert second['id'] == first['id'] and second['lease_token'] != first['lease_token']
        with pytest.raises(LostLeaseError):
            store.heartbeat(first['id'], first['lease_token'])
    finally:
        store.cancel(job['id'])
