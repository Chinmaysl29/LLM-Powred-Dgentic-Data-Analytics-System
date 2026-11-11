"""Reviewed policy fitting and gated, atomic release/rollback per tenant and kind."""
import copy
import hashlib
from uuid import UUID, uuid4
from sqlalchemy import select, func, text
from backend.app.learning.column_lifecycle import access
from backend.app.learning.selection_contract import manifest, train, evaluate
from backend.app.learning import selection_store as store
from backend.app.learning.memory_contract import digest


def reviewed(value, expected_digest, kind):
    value = copy.deepcopy(manifest(value))
    if value['kind'] != kind or digest(value) != expected_digest:
        raise ValueError('Reviewed manifest changed')
    return value


def lock(db, tenant, kind):
    db.execute(text("SET LOCAL lock_timeout='2s'")); db.execute(text("SET LOCAL statement_timeout='5s'"))
    key = int.from_bytes(hashlib.sha256(f'{tenant}:{store.learner(kind)}'.encode()).digest()[:8], 'big', signed=True)
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
    db.execute(select(store.weights.c.id).where(store.condition(tenant, kind)).with_for_update()).all()


def state(db, tenant, kind):
    return store.active(db, tenant, kind), db.scalar(select(func.max(store.events.c.id)).where(
        store.events.c.tenant_id == tenant, store.events.c.kind == kind, store.events.c.action != 'shadow')) or 0


def stage(factory, reviewer, dataset_id, dataset_version, kind, value, expected_digest):
    value = reviewed(value, expected_digest, kind)
    with factory() as db, db.begin():
        current = access(db, reviewer, dataset_id, dataset_version)
    source = store.fingerprint()
    payload = {'format': 1, 'kind': kind, 'scope': store.scope_dict(current),
        'manifest_digest': expected_digest, 'model': train(value)}
    store.validate(payload, kind)
    with factory() as db, db.begin():
        if access(db, reviewer, dataset_id, dataset_version) != current or store.fingerprint() != source:
            raise ValueError('Scope/source changed during training')
        lock(db, current.tenant_id, kind)
        version = (db.scalar(select(func.max(store.weights.c.version)).where(store.condition(current.tenant_id, kind))) or 0) + 1
        db.execute(store.weights.insert().values(id=uuid4(), tenant_id=current.tenant_id, learner=store.learner(kind),
            version=version, weights=payload, is_active=False))
        store.event(db, current, kind, 'stage', version, store.active(db, current.tenant_id, kind), payload,
            UUID(str(reviewer)), {'manifest_digest': expected_digest})
    return {'kind': kind, 'version': version, 'active': False, 'model_digest': digest(payload)}


def promote(factory, reviewer, dataset_id, dataset_version, kind, version, expected_version, value, expected_digest):
    value = reviewed(value, expected_digest, kind); source = store.fingerprint()
    with factory() as db, db.begin():
        current = access(db, reviewer, dataset_id, dataset_version)
        before = state(db, current.tenant_id, kind)
        if before[0] != expected_version or version == expected_version:
            raise ValueError('Active selection policy changed or already active')
        payload = store.read(db, current.tenant_id, kind, version)
        if (payload['scope'] != store.scope_dict(current) or payload['manifest_digest'] != expected_digest
                or not store.attested(db, current, kind, version, payload, 'stage')
                or not store.attested(db, current, kind, version, payload, 'shadow')):
            raise ValueError('Missing compatible review/shadow evidence')
        live = store.read(db, current.tenant_id, kind, before[0]) if before[0] else None
        if live and (live['scope'] != store.scope_dict(current) or not store.attested(db, current, kind, before[0], live, 'promote')):
            raise ValueError('Disable incompatible policy first')
    report = evaluate(value, payload['model'], live['model'] if live else None)
    if not report['passed']:
        return {'promoted': False, 'kind': kind, 'version': version, 'evaluation': report}
    with factory() as db, db.begin():
        if access(db, reviewer, dataset_id, dataset_version) != current:
            raise ValueError('Authorization/schema changed during evaluation')
        lock(db, current.tenant_id, kind)
        if (state(db, current.tenant_id, kind) != before or store.fingerprint() != source
                or store.read(db, current.tenant_id, kind, version) != payload
                or (live and store.read(db, current.tenant_id, kind, before[0]) != live)
                or not store.attested(db, current, kind, version, payload, 'stage')
                or not store.attested(db, current, kind, version, payload, 'shadow')):
            raise ValueError('Policy/evidence changed during evaluation')
        db.execute(store.weights.update().where(store.condition(current.tenant_id, kind)).values(is_active=False))
        db.execute(store.weights.update().where(store.condition(current.tenant_id, kind), store.weights.c.version == version).values(is_active=True))
        store.event(db, current, kind, 'promote', version, before[0], payload, UUID(str(reviewer)), report)
    return {'promoted': True, 'kind': kind, 'version': version, 'evaluation': report}


def rollback(factory, reviewer, dataset_id, dataset_version, kind, version, expected_version):
    if type(version) is not int or version < 0:
        raise ValueError('Invalid rollback version')
    with factory() as db, db.begin():
        current = access(db, reviewer, dataset_id, dataset_version)
        lock(db, current.tenant_id, kind)
        previous = store.active(db, current.tenant_id, kind)
        if previous != expected_version:
            raise ValueError('Active policy changed')
        payload = store.read(db, current.tenant_id, kind, version) if version else None
        if payload and (payload['scope'] != store.scope_dict(current) or not store.attested(db, current, kind, version, payload, 'promote')):
            raise ValueError('Rollback target was never compatibly approved')
        db.execute(store.weights.update().where(store.condition(current.tenant_id, kind)).values(is_active=False))
        if version:
            db.execute(store.weights.update().where(store.condition(current.tenant_id, kind), store.weights.c.version == version).values(is_active=True))
        store.event(db, current, kind, 'rollback' if version else 'disable', version, previous, payload, UUID(str(reviewer)))
    return {'kind': kind, 'version': version, 'previous_version': previous, 'rolled_back': True}
