"""Authorized persistent seven-stage run API."""
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.app.database.postgres import get_db_session
from backend.app.core.security import get_current_user
from backend.app.core.workspace_authorization import authorize_workspace, authorize_bound_dataset
from backend.app.models.analysis_run import AnalysisRun, AnalysisStage, AnalysisEvent
from backend.app.models.background_job import DurableJob
from backend.app.models.dataset_version import DatasetVersion
from backend.app.services.analysis_run_service import authorize_run, snapshot, STAGES

router=APIRouter(prefix='/orchestrator/runs',tags=['Analysis runs'])
class CreateRun(BaseModel):
    workspace_id: UUID
    dataset_id: str
    version_number: int | None=Field(None,ge=1)
    query: str=Field(min_length=1,max_length=2000)
    idempotency_key: str=Field(min_length=1,max_length=128)
class ResumeRun(BaseModel):
    query: str | None=Field(None,min_length=1,max_length=2000)

def owned_job(db,run):
    return db.scalar(select(DurableJob).where(DurableJob.id==run.job_id).with_for_update())

@router.post('',status_code=201)
def create_run(body:CreateRun,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=authorize_workspace(db,user.id,body.workspace_id,'write');authorize_bound_dataset(db,access,body.dataset_id)
    version=db.scalar(select(DatasetVersion).where(DatasetVersion.dataset_id==body.dataset_id,
        DatasetVersion.version_number==body.version_number if body.version_number else DatasetVersion.is_active.is_(True)))
    if version is None: raise HTTPException(404,'Version not found')
    existing=db.scalar(select(DurableJob).where(DurableJob.workspace_id==body.workspace_id,DurableJob.kind=='analysis_pipeline',DurableJob.idempotency_key==body.idempotency_key))
    if existing:
        run=authorize_run(db,existing.payload['run_id'],user.id)
        if (run.query,run.dataset_id,run.version_number)!=(body.query,body.dataset_id,version.version_number):raise HTTPException(409,'Idempotency key conflicts')
        return snapshot(db,run)
    run_id=str(uuid4());job=DurableJob(workspace_id=body.workspace_id,owner_id=user.id,kind='analysis_pipeline',idempotency_key=body.idempotency_key,payload={'run_id':run_id},retry_eligible=True)
    db.add(job);db.flush()
    run=AnalysisRun(id=run_id,job_id=job.id,workspace_id=body.workspace_id,owner_id=user.id,dataset_id=body.dataset_id,version_number=version.version_number,query=body.query)
    db.add(run);db.flush()
    db.add_all([AnalysisStage(run_id=run_id,number=n,name=name) for n,name in enumerate(STAGES,1)])
    db.add(AnalysisEvent(run_id=run_id,status='CREATED'))
    db.commit();return snapshot(db,run)

@router.get('')
def list_runs(workspace_id:UUID,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    authorize_workspace(db,user.id,workspace_id)
    return [snapshot(db,r) for r in db.scalars(select(AnalysisRun).where(AnalysisRun.workspace_id==workspace_id,AnalysisRun.owner_id==user.id).order_by(AnalysisRun.created_at.desc()).limit(50))]

@router.get('/{run_id}')
def read_run(run_id:str,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    return snapshot(db,authorize_run(db,run_id,user.id))

@router.post('/{run_id}/cancel')
def cancel_run(run_id:str,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    run=authorize_run(db,run_id,user.id,'write');job=owned_job(db,run)
    if job.status in ('READY','CANCELLED'):raise HTTPException(409,'Run is terminal')
    job.status='CANCELLED';job.lease_token=None;run.status='CANCELLED'
    for stage in db.scalars(select(AnalysisStage).where(AnalysisStage.run_id==run_id,AnalysisStage.status.in_(['PENDING','RUNNING','FAILED','BLOCKED']))):stage.status='CANCELLED'
    db.add(AnalysisEvent(run_id=run_id,status='CANCELLED'));db.commit();return snapshot(db,run)

@router.post('/{run_id}/retry')
@router.post('/{run_id}/resume')
def retry_run(run_id:str,body:ResumeRun,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    run=authorize_run(db,run_id,user.id,'write');job=owned_job(db,run)
    if job.status!='FAILED' or run.status not in ('FAILED','BLOCKED','RUNNING'):raise HTTPException(409,'Only a failed or blocked run can resume')
    if job.attempt>=job.max_attempts:raise HTTPException(409,'Retry limit reached')
    if body.query and body.query!=run.query:
        completed=db.scalar(select(AnalysisStage).where(AnalysisStage.run_id==run_id,AnalysisStage.status=='COMPLETED'))
        if completed:raise HTTPException(409,'Create a new run to change an executed plan')
        run.query=body.query
    job.status='QUEUED';job.error_code=None;job.lease_token=None;run.status='PENDING'
    for stage in db.scalars(select(AnalysisStage).where(AnalysisStage.run_id==run_id,AnalysisStage.status.in_(['FAILED','BLOCKED','RUNNING']))):stage.status='PENDING'
    db.add(AnalysisEvent(run_id=run_id,status='RESUMED'));db.commit();return snapshot(db,run)
