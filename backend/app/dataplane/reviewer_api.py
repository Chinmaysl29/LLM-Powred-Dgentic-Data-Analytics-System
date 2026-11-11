"""Owner-assigned review permissions and a restricted peer approval inbox."""
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlalchemy import select, or_, and_, text, func, String
from sqlalchemy.orm import Session, aliased
from backend.app.core.security import get_current_user
from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships, dataset_workspace_bindings
from backend.app.database.postgres import get_db_session
from backend.app.dataplane.api import enabled, public
from backend.app.dataplane.records import scoped
from backend.app.dataplane.company_contracts import GrantReviewer, RevokeReviewer
from backend.app.dataplane import reviewer, company
from backend.app.models.user import User
from backend.app.models.dataset import Dataset
from backend.app.models.learning import BusinessDefinition


def private_response(response: Response):
    response.headers['Cache-Control'] = 'private, no-store'


router = APIRouter(prefix='/dataplane/company', tags=['Dataset reviewers'],
                   dependencies=[Depends(enabled), Depends(private_response)])


@router.get('/reviewer-candidates')
def candidates(workspace_id: UUID, dataset_id: str, search: str = Query('', max_length=100),
               offset: int = Query(0, ge=0, le=100000), db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'write')
    if not reviewer.owns(db, access, dataset_id):
        raise HTTPException(404, 'Dataset not found')
    tm, wm = tenant_memberships.c, workspace_memberships.c
    query = select(User.id, User.full_name).join(tenant_memberships, and_(tm.user_id == User.id,
        tm.tenant_id == access.tenant_id, tm.active.is_(True))).outerjoin(workspace_memberships,
        and_(wm.user_id == User.id, wm.workspace_id == workspace_id, wm.active.is_(True))).where(
        User.is_active.is_(True), User.id != user.id, tm.role.in_(['viewer', 'analyst', 'admin', 'owner']),
        or_(tm.role.in_(['owner', 'admin']), wm.role.in_(['viewer', 'analyst', 'admin', 'owner'])))
    if search:
        term = '%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.where(User.full_name.ilike(term, escape='\\'))
    rows = db.execute(query.order_by(User.full_name, User.id).offset(offset).limit(51)).all()
    return {'items': [{'id': str(row.id), 'name': row.full_name or str(row.id)[:8]} for row in rows[:50]],
            'next_offset': offset+50 if len(rows)>50 else None}


@router.get('/review-grants')
def list_grants(workspace_id: UUID, dataset_id: str, offset: int = Query(0, ge=0, le=100000),
                db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id)
    if not reviewer.owns(db, access, dataset_id) and access.role not in {'admin', 'owner'}:
        raise HTTPException(404, 'Dataset not found')
    rows = db.execute(select(reviewer.grants, User.full_name).join(User, User.id == reviewer.grants.c.reviewer_id)
        .where(reviewer.grants.c.workspace_id == workspace_id, reviewer.grants.c.tenant_id == access.tenant_id,
            reviewer.grants.c.dataset_id == dataset_id).order_by(reviewer.grants.c.created_at.desc())
        .offset(offset).limit(51)).mappings().all()
    return {'items': [{**{key: str(value) if isinstance(value, UUID) else value for key, value in row.items()},
                       'name': row['full_name']} for row in rows[:50]], 'next_offset': offset+50 if len(rows)>50 else None}


@router.put('/review-grants/{dataset_id}/{reviewer_id}')
def grant(dataset_id: str, reviewer_id: UUID, body: GrantReviewer, workspace_id: UUID,
          db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'write')
    result = reviewer.set_grant(db, access, dataset_id, reviewer_id, body)
    db.commit()
    return result


@router.get('/review-grants/revision')
def grant_revision(workspace_id: UUID, dataset_id: str, reviewer_id: UUID,
                   db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'write')
    if not reviewer.owns(db, access, dataset_id):
        raise HTTPException(404, 'Dataset not found')
    row = db.execute(select(reviewer.grants).where(
        reviewer.grants.c.dataset_id == dataset_id, reviewer.grants.c.owner_id == user.id,
        reviewer.grants.c.reviewer_id == reviewer_id, reviewer.grants.c.workspace_id == workspace_id)).mappings().first()
    return {'revision': row['revision'] if row else 0, 'active': row['active'] if row else False,
            'expires_at': row['expires_at'] if row else None}


@router.post('/review-grants/{identity}/revoke')
def revoke(identity: UUID, body: RevokeReviewer, workspace_id: UUID,
           db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'write')
    result = reviewer.revoke_grant(db, access, identity, body)
    db.commit()
    return result


@router.get('/reviews')
def inbox(workspace_id: UUID, offset: int = Query(0, ge=0, le=100000),
          db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id)
    rows = db.scalars(text('SELECT company_review_queue(:offset)'), {'offset': offset}).all()
    items = [{**row, 'review': company.current_event(db, access, row['id'])} for row in rows[:50]]
    owner = aliased(User)
    definitions = db.scalars(select(BusinessDefinition).join(reviewer.grants,
        reviewer.grants.c.dataset_id == BusinessDefinition.governance['spec']['dataset_id'].as_string())
        .join(Dataset, Dataset.dataset_id == reviewer.grants.c.dataset_id)
        .join(owner, owner.id == reviewer.grants.c.owner_id)
        .join(dataset_workspace_bindings, dataset_workspace_bindings.c.dataset_id == Dataset.dataset_id)
        .where(BusinessDefinition.workspace_id == workspace_id,
            BusinessDefinition.governance['status'].as_string() == 'review',
            reviewer.grants.c.workspace_id == workspace_id, reviewer.grants.c.tenant_id == access.tenant_id,
            reviewer.grants.c.reviewer_id == user.id, reviewer.grants.c.active.is_(True),
            reviewer.grants.c.expires_at > func.clock_timestamp(), owner.is_active.is_(True),
            Dataset.owner_id == reviewer.grants.c.owner_id.cast(String),
            Dataset.status.not_in(['deleted', 'archived', 'purged']),
            dataset_workspace_bindings.c.workspace_id == workspace_id)
        .order_by(BusinessDefinition.created_at.desc()).offset(offset).limit(51)).all()
    return {'items': items, 'definitions': [company.dictionary_json(row) for row in definitions[:50]],
            'next_offset': offset+50 if len(rows)>50 or len(definitions)>50 else None}


@router.get('/reviews/{identity}')
def detail(identity: UUID, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id)
    row = reviewer.record_for_review(db, access, identity)
    return {**public(row), 'review': company.current_event(db, access, identity)}
