"""Durable seven-stage execution using existing retrieval, EDA and analytics engines."""
import json
from datetime import timezone
from uuid import UUID, uuid4
from sqlalchemy import select
from backend.app.models.analysis_run import AnalysisRun, AnalysisStage, AnalysisArtifact, AnalysisEvent
from backend.app.models.background_job import DurableJob, utcnow
from backend.app.core.workspace_authorization import authorize_workspace, authorize_bound_dataset
from backend.app.services.data_retrieval_service import DataRetrievalService
from backend.app.services.storage_service import StorageService
from backend.app.core.config import get_settings
from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
from backend.app.services.eda_service import EDAService
from backend.jobs.persistence import LostLeaseError

STAGES = ['Problem formulation', 'Data collection', 'Data preparation', 'Exploratory analysis', 'Data modeling', 'Visualization and reporting', 'Recommendations']

def authorize_run(db, run_id, actor, permission='read'):
    run = db.get(AnalysisRun, str(run_id))
    from fastapi import HTTPException
    if run is None or str(run.owner_id) != str(actor):
        raise HTTPException(404, 'Run not found')
    access = authorize_workspace(db, actor, run.workspace_id, permission)
    authorize_bound_dataset(db, access, run.dataset_id)
    return run

def snapshot(db, run):
    job = db.get(DurableJob, run.job_id)
    return dict(id=run.id, workspace_id=str(run.workspace_id), dataset_id=run.dataset_id,
                version_number=run.version_number, query=run.query,
                status='CANCELLED' if job.status == 'CANCELLED' else run.status,
                job_id=str(run.job_id), job_status=job.status,
                stages=[dict(number=s.number,name=s.name,status=s.status,attempt=s.attempt,error=s.error)
                        for s in db.scalars(select(AnalysisStage).where(AnalysisStage.run_id==run.id).order_by(AnalysisStage.number))],
                artifacts=[dict(id=a.id,stage_number=a.stage_number,content=a.content) for a in db.scalars(select(AnalysisArtifact).where(AnalysisArtifact.run_id==run.id).order_by(AnalysisArtifact.stage_number))])

def fence(db, job):
    row = db.scalar(select(DurableJob).where(DurableJob.id==job['id']).with_for_update())
    expiry = row.lease_expires_at if row else None
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if not row or row.status != 'RUNNING' or row.lease_token != job['lease_token'] or not expiry or expiry <= utcnow():
        raise LostLeaseError('Analysis lease lost')

async def execute_analysis_job(store, job):
    """Called by the existing durable worker. Caller owns heartbeat and READY transition."""
    run_id = job['payload']['run_id']
    for number in range(1,8):
        store.heartbeat(job['id'], job['lease_token'])
        with store.sessions() as db, db.begin():
            fence(db, job)
            run = authorize_run(db, run_id, job['owner_id'], 'write')
            stage = db.scalar(select(AnalysisStage).where(AnalysisStage.run_id==run_id,AnalysisStage.number==number))
            if stage.status == 'COMPLETED':
                continue
            if number > 1:
                previous = db.scalar(select(AnalysisStage).where(AnalysisStage.run_id==run_id,AnalysisStage.number==number-1))
                if previous.status != 'COMPLETED':
                    raise RuntimeError('Stage dependency incomplete')
            stage.status='RUNNING'; stage.attempt+=1; stage.error=None; run.status='RUNNING'
            db.add(AnalysisEvent(run_id=run_id,stage_number=number,status='RUNNING'))
            dataset_id, version, query = run.dataset_id, run.version_number, run.query
        try:
            with store.sessions() as db:
                authorize_run(db,run_id,job['owner_id'],'write')
                retrieval=DataRetrievalService(db,StorageService(get_settings()),owner_id=str(job['owner_id']))
                frame, sampled=retrieval.load_dataframe(dataset_id,version,sample_size=0)
                provenance=dict(run_id=run_id,dataset_id=dataset_id,version_number=version,sampled=sampled)
                analytics=NaturalLanguageAnalyticsService()
                if number==1:
                    result=await analytics.analyze(query,dataframe=frame,dataset_id=dataset_id,dataset_version=version)
                    content=dict(plan=result.get('plan'), clarification=result.get('answer') if result.get('status')=='clarification_required' else None)
                    blocked=result.get('status')=='clarification_required'
                elif number==2:
                    content=dict(row_count=len(frame),columns=[str(c) for c in frame.columns],dtypes={str(c):str(t) for c,t in frame.dtypes.items()}); blocked=False
                elif number==3:
                    content=dict(policy='No transformations applied without approval; source version preserved',missing_values={str(c):int(n) for c,n in frame.isna().sum().items()},duplicate_rows=int(frame.duplicated().sum()),prepared_version=version); blocked=False
                elif number==4:
                    result=EDAService().analyze_dataframe(frame,dataset_id=dataset_id).model_dump(mode='json')
                    # Evidence only: do not propagate heuristic business narratives.
                    content={k:result[k] for k in ('dataset_summary','statistics','missing_values','distributions','outliers','correlations','trends','categorical_analysis') if k in result}; blocked=False
                elif number==5:
                    content=await analytics.analyze(query,dataframe=frame,dataset_id=dataset_id,dataset_version=version)
                    blocked=content.get('status')=='clarification_required'
                elif number==6:
                    model=db.scalar(select(AnalysisArtifact).where(AnalysisArtifact.run_id==run_id,AnalysisArtifact.stage_number==5)).content
                    content=dict(title=query,records=model.get('data',[]),plan=model.get('plan'),summary=model.get('answer'),source_stage=5); blocked=False
                else:
                    model=db.scalar(select(AnalysisArtifact).where(AnalysisArtifact.run_id==run_id,AnalysisArtifact.stage_number==5)).content
                    content=dict(findings=[model.get('answer')],actions=model.get('actionable',[]),limitations=['Descriptive evidence does not establish causation.','No forecast requested or fitted by this run.'],evidence_stage=5); blocked=False
                content['provenance']=provenance
                # Enforce bounded summaries instead of stuffing datasets in polling JSON.
                encoded=json.dumps(content,allow_nan=False,default=str)
                if len(encoded.encode())>2_000_000:
                    raise ValueError('Stage evidence exceeds supported response limit')
                content=json.loads(encoded)
            with store.sessions() as db, db.begin():
                fence(db,job); run=authorize_run(db,run_id,job['owner_id'],'write')
                stage=db.scalar(select(AnalysisStage).where(AnalysisStage.run_id==run_id,AnalysisStage.number==number))
                old=db.scalar(select(AnalysisArtifact).where(AnalysisArtifact.run_id==run_id,AnalysisArtifact.stage_number==number))
                if old: old.content=content
                else: db.add(AnalysisArtifact(run_id=run_id,stage_number=number,content=content))
                stage.status='BLOCKED' if blocked else 'COMPLETED'
                run.status='BLOCKED' if blocked else ('COMPLETED' if number==7 else 'RUNNING')
                db.add(AnalysisEvent(run_id=run_id,stage_number=number,status=stage.status))
            if blocked:
                raise ValueError('CLARIFICATION_REQUIRED')
        except LostLeaseError:
            raise
        except Exception:
            with store.sessions() as db,db.begin():
                fence(db,job)
                stage=db.scalar(select(AnalysisStage).where(AnalysisStage.run_id==run_id,AnalysisStage.number==number))
                run=db.get(AnalysisRun,run_id)
                if stage.status!='BLOCKED':
                    stage.status='FAILED';stage.error='STAGE_EXECUTION_FAILED';run.status='FAILED'
                    db.add(AnalysisEvent(run_id=run_id,stage_number=number,status='FAILED'))
            raise
    return {'run_id':run_id,'status':'COMPLETED'}
