"""Reviewed training, shadow prerequisites, held-out promotion and atomic rollback."""
import copy
import hashlib
from uuid import UUID, uuid4

from sqlalchemy import select, func, text
from backend.app.models import Dataset
from backend.app.learning.failure_memory import scope
from backend.app.learning.lifecycle import operator
from backend.app.learning.column_ranker import ColumnRanker, FEATURE_VERSION
from backend.app.learning.column_contract import manifest, train, evaluate
from backend.app.learning.column_store import (weights, events, LEARNER, condition, read, active,
    attested, event, fingerprint, scope_dict)
from backend.app.learning.memory_contract import digest


def access(db, reviewer, dataset_id, dataset_version):
    owner = db.scalar(select(Dataset.owner_id).where(Dataset.dataset_id == dataset_id))
    if owner is None:
        raise ValueError('Dataset unavailable')
    current = scope(db, owner, dataset_id, dataset_version)
    operator(db, reviewer, current.tenant_id)
    return current


def lock(db, tenant):
    db.execute(text("SET LOCAL lock_timeout='2s'"))
    db.execute(text("SET LOCAL statement_timeout='5s'"))
    key = int.from_bytes(hashlib.sha256(f'{tenant}:{LEARNER}'.encode()).digest()[:8], 'big', signed=True)
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
    db.execute(select(weights.c.id).where(condition(tenant)).with_for_update()).all()


def state(db, tenant):
    return active(db, tenant), db.scalar(select(func.max(events.c.id)).where(
        events.c.tenant_id == tenant, events.c.action != 'shadow')) or 0


def checked_manifest(value, expected_digest):
    value = copy.deepcopy(manifest(value))
    if digest(value) != expected_digest:
        raise ValueError('Reviewed manifest changed')
    return value


def stage(factory, reviewer, dataset_id, dataset_version, value, expected_digest):
    value = checked_manifest(value, expected_digest)
    with factory() as db, db.begin():
        current = access(db, reviewer, dataset_id, dataset_version)
        if current.schema_hash != digest(value['schema']):
            raise ValueError('Reviewed schema differs from dataset version')
    source = fingerprint()
    model = train(value)  # No DB transaction or lock during fitting.
    payload = {'format': 1, 'feature_version': FEATURE_VERSION, 'scope': scope_dict(current),
        'manifest_digest': expected_digest, 'weights': model.snapshot(), 'vocabulary': sorted(model.vocabulary)}
    with factory() as db, db.begin():
        if access(db, reviewer, dataset_id, dataset_version) != current or fingerprint() != source:
            raise ValueError('Scope/code changed while training')
        lock(db, current.tenant_id)
        version = (db.scalar(select(func.max(weights.c.version)).where(condition(current.tenant_id))) or 0) + 1
        db.execute(weights.insert().values(id=uuid4(), tenant_id=current.tenant_id, learner=LEARNER,
            version=version, weights=payload, is_active=False))
        event(db, current, 'stage', version, active(db, current.tenant_id), payload, UUID(str(reviewer)),
            {'manifest_digest': expected_digest, 'training_cases': sum(r['split'] == 'train' for r in value['cases'])})
    return {'version': version, 'active': False, 'model_digest': digest(payload)}


def promote(factory, reviewer, dataset_id, dataset_version, version, expected_version, value, expected_digest):
    value = checked_manifest(value, expected_digest)
    source = fingerprint()
    with factory() as db, db.begin():
        current = access(db, reviewer, dataset_id, dataset_version)
        before = state(db, current.tenant_id)
        if before[0] != expected_version or version == expected_version:
            raise ValueError('Active resolver changed or already selected')
        payload = read(db, current.tenant_id, version)
        if (payload['scope'] != scope_dict(current) or payload['manifest_digest'] != expected_digest
                or current.schema_hash != digest(value['schema'])
                or not attested(db, current, version, payload, 'stage')
                or not attested(db, current, version, payload, 'shadow')):
            raise ValueError('Missing compatible review/shadow evidence')
        live = read(db, current.tenant_id, before[0]) if before[0] else None
        if live is not None and (live['scope'] != scope_dict(current) or not attested(db, current, before[0], live, 'promote')):
            raise ValueError('Disable incompatible active resolver first')
    report = evaluate(value, ColumnRanker(payload['weights'], payload['vocabulary']),
        ColumnRanker(live['weights'], live['vocabulary']) if live else None)
    if not report['passed']:
        return {'promoted': False, 'version': version, 'evaluation': report}
    with factory() as db, db.begin():
        if access(db, reviewer, dataset_id, dataset_version) != current:
            raise ValueError('Authorization/schema changed during evaluation')
        lock(db, current.tenant_id)
        if (state(db, current.tenant_id) != before or fingerprint() != source
                or read(db, current.tenant_id, version) != payload
                or (live is not None and read(db, current.tenant_id, before[0]) != live)
                or not attested(db, current, version, payload, 'stage')
                or not attested(db, current, version, payload, 'shadow')):
            raise ValueError('Resolver changed during evaluation')
        db.execute(weights.update().where(condition(current.tenant_id)).values(is_active=False))
        db.execute(weights.update().where(condition(current.tenant_id), weights.c.version == version).values(is_active=True))
        event(db, current, 'promote', version, before[0], payload, UUID(str(reviewer)), report)
    return {'promoted': True, 'version': version, 'evaluation': report}


def rollback(factory, reviewer, dataset_id, dataset_version, version, expected_version):
    if type(version) is not int or version < 0:
        raise ValueError('Invalid resolver rollback version')
    with factory() as db, db.begin():
        current = access(db, reviewer, dataset_id, dataset_version)
        lock(db, current.tenant_id)
        previous = active(db, current.tenant_id)
        if previous != expected_version:
            raise ValueError('Active resolver changed')
        payload = read(db, current.tenant_id, version) if version else None
        if payload and (payload['scope'] != scope_dict(current) or not attested(db, current, version, payload, 'promote')):
            raise ValueError('Rollback requires a previously approved compatible version')
        db.execute(weights.update().where(condition(current.tenant_id)).values(is_active=False))
        if version:
            db.execute(weights.update().where(condition(current.tenant_id), weights.c.version == version).values(is_active=True))
        event(db, current, 'rollback' if version else 'disable', version, previous, payload, UUID(str(reviewer)))
    return {'version': version, 'previous_version': previous, 'rolled_back': True}
