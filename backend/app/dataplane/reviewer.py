"""Explicit per-dataset review capability; execution and raw access stay owner-only."""
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import String, select, text, func
from backend.app.core.workspace_authorization import (authorize_workspace, authorize_bound_dataset,
    dataset_workspace_bindings)
from backend.app.dataplane.records import artifacts, conditions, get_record
from backend.app.dataplane.storage import fingerprint
from backend.app.models.dataset import Dataset
from backend.app.models.user import User
from backend.app.models.review_grant import DatasetReviewGrant

grants = DatasetReviewGrant.__table__


def lock_review(db, access, identity):
    key = int(fingerprint(['company-review', str(access.workspace_id), str(identity)])[:15], 16)
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})


def lock_grant(db, access, dataset_id, reviewer_id):
    lock_review(db, access, f'grant:{dataset_id}:{reviewer_id}')


def owns(db, access, dataset_id):
    return db.scalar(select(Dataset.dataset_id).join(dataset_workspace_bindings,
        dataset_workspace_bindings.c.dataset_id == Dataset.dataset_id).where(
        Dataset.dataset_id == dataset_id, Dataset.owner_id == str(access.actor_id),
        dataset_workspace_bindings.c.workspace_id == access.workspace_id)) is not None


def has_grant(db, access, dataset_id, lock=False):
    if lock:
        lock_grant(db, access, dataset_id, access.actor_id)
    return db.scalar(select(grants.c.id).join(Dataset, Dataset.dataset_id == grants.c.dataset_id)
        .join(User, User.id == grants.c.owner_id).where(grants.c.dataset_id == dataset_id,
        grants.c.tenant_id == access.tenant_id, grants.c.workspace_id == access.workspace_id,
        grants.c.reviewer_id == access.actor_id, grants.c.active.is_(True),
        grants.c.expires_at > func.clock_timestamp(), Dataset.owner_id == grants.c.owner_id.cast(String),
        User.is_active.is_(True), Dataset.status.not_in(['deleted', 'archived', 'purged']))) is not None


def require_review(db, access, dataset_id):
    if owns(db, access, dataset_id):
        if access.role not in {'analyst', 'admin', 'owner'}:
            raise HTTPException(403, 'Review changes require source-owner write permission')
        authorize_bound_dataset(db, access, dataset_id)
        return False
    if not has_grant(db, access, dataset_id, lock=True):
        raise HTTPException(404, 'Review resource not found')
    return True


def shared_record(db, access, identity, dataset_id=None):
    value = db.scalar(text('SELECT company_review_artifact(CAST(:identity AS uuid), :dataset)'),
                      {'identity': str(identity) if identity else None, 'dataset': dataset_id})
    if value is None:
        raise HTTPException(404, 'Review resource not found')
    return value


def record_for_review(db, access, identity):
    try:
        return get_record(db, access, identity)
    except HTTPException as error:
        if error.status_code != 404:
            raise
    return shared_record(db, access, identity)


def source_for_review(db, access, dataset_id):
    if owns(db, access, dataset_id):
        row = db.execute(select(artifacts).where(*conditions(access), artifacts.c.dataset_id == dataset_id,
            artifacts.c.kind == 'snapshot').order_by(artifacts.c.created_at.desc()).limit(1)).mappings().first()
        if row:
            return dict(row)
        raise HTTPException(409, 'Create an immutable source snapshot before approval')
    require_review(db, access, dataset_id)
    return shared_record(db, access, None, dataset_id)


def set_grant(db, access, dataset_id, reviewer_id, body):
    from backend.app.services.learning_supervisor import audit
    if access.role not in {'analyst', 'admin', 'owner'} or not owns(db, access, dataset_id):
        raise HTTPException(403, 'Only a source owner with write permission may grant review access')
    authorize_bound_dataset(db, access, dataset_id)
    if access.actor_id == reviewer_id:
        raise HTTPException(422, 'Reviewer grants cannot authorize self-approval')
    authorize_workspace(db, reviewer_id, access.workspace_id, 'read')
    now = datetime.now(timezone.utc)
    if body.expires_at.tzinfo is None or not now < body.expires_at <= now + timedelta(days=366):
        raise HTTPException(422, 'Use an offset-aware expiry within the next 366 days')
    lock_grant(db, access, dataset_id, reviewer_id)
    row = db.execute(select(grants).where(grants.c.dataset_id == dataset_id,
        grants.c.workspace_id == access.workspace_id, grants.c.owner_id == access.actor_id,
        grants.c.reviewer_id == reviewer_id)).mappings().first()
    revision = row['revision'] if row else 0
    if body.expected_revision != revision:
        raise HTTPException(409, 'Reviewer grant changed; reload before saving')
    identity = row['id'] if row else uuid4()
    values = {'active': True, 'expires_at': body.expires_at, 'revision': revision + 1}
    if row:
        db.execute(grants.update().where(grants.c.id == identity).values(**values))
    else:
        db.execute(grants.insert().values(id=identity, tenant_id=access.tenant_id,
            workspace_id=access.workspace_id, dataset_id=dataset_id, owner_id=access.actor_id,
            reviewer_id=reviewer_id, **values))
    audit(db, access, 'dataset_reviewer_granted', str(identity), dataset_id=dataset_id,
          reviewer_id=str(reviewer_id), revision=revision + 1, reason=body.reason,
          expires_at=body.expires_at.isoformat())
    return {'id': str(identity), 'reviewer_id': str(reviewer_id), **values}


def revoke_grant(db, access, identity, body):
    from backend.app.services.learning_supervisor import audit
    row = db.execute(select(grants).where(grants.c.id == identity, grants.c.tenant_id == access.tenant_id,
        grants.c.workspace_id == access.workspace_id)).mappings().first()
    if row is None:
        raise HTTPException(404, 'Reviewer grant not found')
    if not owns(db, access, row['dataset_id']) and access.role not in {'admin', 'owner'}:
        raise HTTPException(403, 'Only the source owner or workspace manager may revoke this grant')
    lock_grant(db, access, row['dataset_id'], row['reviewer_id'])
    row = db.execute(select(grants).where(grants.c.id == identity)).mappings().one()
    if row['revision'] != body.expected_revision:
        raise HTTPException(409, 'Reviewer grant changed; reload before revoking')
    db.execute(grants.update().where(grants.c.id == identity).values(active=False, revision=row['revision']+1))
    audit(db, access, 'dataset_reviewer_revoked', str(identity), dataset_id=row['dataset_id'],
          reviewer_id=str(row['reviewer_id']), reason=body.reason, revision=row['revision']+1)
    return {'status': 'revoked', 'revision': row['revision']+1}
