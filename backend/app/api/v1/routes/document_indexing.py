"""Authorized document lifecycle, retrieval and immutable source download."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker
from backend.app.database.postgres import get_db_session
from backend.app.core.security import get_current_user
from backend.app.core.workspace_authorization import authorize_workspace
from backend.app.services.document_indexing_service import DocumentIndexingService

router = APIRouter(prefix='/datasets', tags=['Document indexing'])


class VersionRequest(BaseModel):
    version: int = Field(ge=1)


class QuestionRequest(VersionRequest):
    query: str = Field(min_length=1, max_length=4000)


def service(db):
    return DocumentIndexingService(sessionmaker(bind=db.get_bind(), expire_on_commit=False))


@router.get('/{dataset_id}/indexing')
def indexing_state(dataset_id: str, version: int | None = None, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    return service(db).state(dataset_id, user.id, version)


@router.post('/{dataset_id}/indexing/{action}')
def indexing_action(dataset_id: str, action: str, body: VersionRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    index = service(db)
    current = index.state(dataset_id, user.id, body.version)
    if not current['job_id'] or not current['workspace_id']:
        raise HTTPException(409, 'Bind an authorized workspace before requesting indexing')
    authorize_workspace(db, user.id, current['workspace_id'], 'write')
    try:
        if action == 'retry':
            index.jobs.retry(current['job_id'])
        elif action == 'cancel':
            index.jobs.cancel(current['job_id'])
        else:
            raise HTTPException(404, 'Unknown indexing action')
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return index.state(dataset_id, user.id, body.version)


@router.post('/{dataset_id}/ask')
def ask(dataset_id: str, body: QuestionRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    return service(db).query(dataset_id, user.id, body.version, body.query)


@router.get('/{dataset_id}/source')
def source(dataset_id: str, version: int, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    index = service(db)
    dataset, selected, _ = index.resource(db, dataset_id, user.id, version, require_workspace=False)
    if dataset.file_type != 'pdf':
        raise HTTPException(409, 'This source is not a PDF')
    return FileResponse(selected.storage_path, media_type='application/pdf', filename=dataset.file_name)
