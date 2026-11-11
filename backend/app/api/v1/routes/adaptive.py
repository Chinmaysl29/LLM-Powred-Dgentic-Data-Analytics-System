"""Authenticated adaptive skills, numerical selector training and review APIs."""
from uuid import UUID
import json

from fastapi import APIRouter,Depends,Query,Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import get_current_user
from backend.app.database.postgres import get_db_session
from backend.app.models.adaptive import (AdaptiveCase,AdaptiveContext,AdaptiveControl,AdaptiveDecision,
    AdaptiveLabelRevision,AdaptiveModel,AdaptiveOutcome,AdaptiveSkill,AdaptiveSkillRevision,AdaptiveWork)
from backend.app.models.background_job import DurableJob,utcnow
from backend.app.schemas.adaptive import (AdaptiveCaseRequest,InterpretationRequest,LifecycleRequest,
    OutcomeReviewRequest,ReplayRequest,SelectorControlRequest,SkillManifest,SKILL_TRANSITIONS,TrainingRequest)
from backend.app.schemas.learning import transition
from backend.app.services.analysis_run_service import authorize_run
from backend.app.services.learning_supervisor import audit,bind,definitions,error
from backend.app.services.learning_engine import RUNTIME_IDENTITY,digest
from backend.app.services.adaptive_service import (authorized_frames,bootstrap,controls,invalidate,model_valid,queue_gap,queue_work)
from backend.app.services.adaptive_jobs import queue_replay,queue_training,register_case
from backend.app.services.adaptive_selector import JsonScorer
from backend.app.services.adaptive_interpretation import interpret

router=APIRouter(prefix='/adaptive',tags=['Adaptive skills and repair selector'])


def skill_json(row):
    return {'id':row.id,'skill_id':row.skill_id,'version':row.version,'state':row.state,
        'manifest':{**row.manifest,'lifecycle':row.state},'content_hash':row.content_hash,
        'test_result':row.test_result,'created_at':row.created_at,'activated_at':row.activated_at}


def model_json(row,weights=False):
    result={'id':row.id,'kind':row.kind,'state':row.state,'content_hash':row.content_hash,'invalid_reason':row.invalid_reason,
        'created_at':row.created_at.isoformat(),'evaluation':row.bundle['evaluation'],'training_manifest':row.bundle['training_manifest'],
        'feature_version':row.bundle['feature_version'],'embedding_version':row.bundle['embedding_version'],
        'calibration_status':row.bundle['calibration_status']}
    if weights:
        result['bundle']=row.bundle
    return result


def work_json(db,row):
    job=db.get(DurableJob,row.job_id)
    return {'id':row.id,'kind':row.kind,'state':row.state,'manifest':row.manifest,'result':row.result,
        'job_status':job.status,'attempt':job.attempt,'max_attempts':job.max_attempts,
        'error_code':job.error_code,'retry_eligible':job.retry_eligible,'created_at':row.created_at}


@router.get('/controls')
def read_controls(workspace_id:UUID,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id)
    cfg=controls(db,workspace_id)
    model=db.get(AdaptiveModel,cfg['active_model_id']) if cfg['active_model_id'] else None
    return {**cfg,'can_review':access.role in {'admin','owner'},'can_write':access.role in {'analyst','admin','owner'},
        'effective_selector':model.kind if cfg['mode']=='active' and model_valid(db,workspace_id,model) else 'rules-memory-v1'}


@router.put('/controls')
def change_controls(workspace_id:UUID,body:SelectorControlRequest,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'manage')
    from backend.app.models.workspace import Workspace
    db.scalar(select(Workspace.id).where(Workspace.id==workspace_id).with_for_update())
    row=db.get(AdaptiveControl,workspace_id)
    if (row.generation if row else 0)!=body.expected_generation:
        error(409,'CONTROL_VERSION_CONFLICT','Reload selector controls before changing them.')
    if body.mode in {'shadow','active'}:
        model=db.get(AdaptiveModel,body.model_id) if body.model_id else None
        if not model_valid(db,workspace_id,model):
            error(409,'MODEL_UNAVAILABLE','A compatible evaluated candidate and valid source lineage are required.')
        try:
            JsonScorer(model.bundle,model.content_hash)
        except (ValueError,KeyError,TypeError):
            error(409,'MODEL_INCOMPATIBLE','The numerical model failed integrity or compatibility checks.')
        if body.mode=='active' and not model.bundle['evaluation'].get('release_eligible'):
            error(409,'SELECTOR_RELEASE_GATES_NOT_PASSED','Synthetic training or classification fit alone cannot activate a selector.')
    if not row:
        row=AdaptiveControl(workspace_id=workspace_id,actor_id=access.actor_id);db.add(row);db.flush()
    if row.active_model_id!=body.model_id:
        row.previous_model_id=row.active_model_id
    row.active_model_id=body.model_id if body.mode in {'shadow','active'} else None
    row.mode=body.mode;row.generation+=1;row.actor_id=access.actor_id;row.updated_at=utcnow()
    if body.mode=='active':
        model.state='active'
    audit(db,access,'selector_mode_changed',str(workspace_id),mode=row.mode,model_id=row.active_model_id,generation=row.generation)
    result=controls(db,workspace_id);db.commit();return result


@router.post('/rollback')
def rollback(workspace_id:UUID,body:SelectorControlRequest,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'manage')
    row=db.scalar(select(AdaptiveControl).where(AdaptiveControl.workspace_id==workspace_id).with_for_update())
    if not row or row.generation!=body.expected_generation:
        error(409,'CONTROL_VERSION_CONFLICT','Reload controls before rollback.')
    row.previous_model_id=row.active_model_id;row.active_model_id=None;row.mode='collection';row.generation+=1;row.updated_at=utcnow()
    audit(db,access,'selector_rollback_to_rules',str(workspace_id),previous_model_id=row.previous_model_id)
    result=controls(db,workspace_id);db.commit();return result


@router.post('/interpret')
async def interpret_task(workspace_id:UUID,body:InterpretationRequest,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'write')
    frames=authorized_frames(db,access,body.task)
    from backend.app.services.learning_supervisor import optional_memory
    from backend.app.services.learning_engine import schema_hash
    lessons,_=optional_memory(db,body.task,schema_hash(next(iter(frames.values()))),utcnow())
    examples=[{'lesson_id':item['lesson_id'],'scope':item['scope'],'operation':item['correction']}
              for item in lessons[:5]]
    return await interpret(body.task,frames,definitions(db,workspace_id),body.use_provider,verified_examples=examples)


@router.post('/skills/bootstrap',status_code=201)
def seed_skills(workspace_id:UUID,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'manage')
    rows=bootstrap(db,access);result={'items':[skill_json(row) for row in rows],'next_offset':None}
    db.commit();return result


@router.get('/skills')
def list_skills(workspace_id:UUID,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),
                db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    bind(db,user.id,workspace_id)
    rows=db.scalars(select(AdaptiveSkill).where(AdaptiveSkill.workspace_id==workspace_id)
        .order_by(AdaptiveSkill.skill_id,AdaptiveSkill.version).offset(offset).limit(limit+1)).all()
    return {'items':[skill_json(row) for row in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/skills/{skill_id}')
def read_skill(skill_id:str,workspace_id:UUID,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    bind(db,user.id,workspace_id);row=db.get(AdaptiveSkill,skill_id)
    if not row or row.workspace_id!=workspace_id:
        error(404,'SKILL_NOT_FOUND','Skill not found.')
    return {**skill_json(row),'revisions':[{'state':r.state,'evidence':r.evidence,'at':r.created_at} for r in db.scalars(
        select(AdaptiveSkillRevision).where(AdaptiveSkillRevision.workspace_id==workspace_id,AdaptiveSkillRevision.skill_id==skill_id)
        .order_by(AdaptiveSkillRevision.created_at))]}


@router.post('/skills/{skill_id}/review')
def review_skill(skill_id:str,workspace_id:UUID,body:LifecycleRequest,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'manage')
    row=db.scalar(select(AdaptiveSkill).where(AdaptiveSkill.id==skill_id,AdaptiveSkill.workspace_id==workspace_id).with_for_update())
    if not row:
        error(404,'SKILL_NOT_FOUND','Skill not found.')
    if row.state!=body.expected_state:
        error(409,'STALE_SKILL_REVIEW','Skill lifecycle changed; reload before review.')
    target={'test':'testing','activate':'active','reject':'rejected','revoke':'revoked','supersede':'superseded'}[body.action]
    try:
        transition(row.state,target,SKILL_TRANSITIONS)
    except ValueError:
        error(409,'ILLEGAL_SKILL_TRANSITION','This skill lifecycle transition is not allowed.')
    if target=='active' and (not row.test_result or not row.test_result['passed'] or row.test_result['implementation_hash']!=row.manifest['implementation_hash']):
        error(409,'SKILL_TEST_EVIDENCE_REQUIRED','Independent tests for the exact implementation are required.')
    row.state=target
    if target=='testing':
        queue_work(db,access,'test',{'skill_id':row.id,'runtime':RUNTIME_IDENTITY},f'test:{row.id}:{row.content_hash}')
    if target=='active':
        row.activated_at=utcnow()
    if target in {'revoked','superseded'}:
        invalidate(db,access,skill_hash=row.manifest['implementation_hash'])
    db.add(AdaptiveSkillRevision(workspace_id=workspace_id,skill_id=row.id,state=target,actor_id=access.actor_id,evidence={'reason':body.reason}))
    audit(db,access,f'skill_{target}',row.id,reason=body.reason)
    result=skill_json(row);db.commit();return result


@router.post('/skills/detect-gaps/scan')
def scan_gaps(workspace_id:UUID,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'manage');queue_gap(db,access,'manual-scan')
    db.commit();return {'status':'scan_completed','policy':'Three evidenced join-grain observations can propose one bounded recipe per code version; no automatic activation.'}


@router.get('/runs/{run_id}/context')
def read_context(run_id:str,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    run=authorize_run(db,run_id,user.id);bind(db,user.id,run.workspace_id)
    row=db.get(AdaptiveContext,run_id)
    return {'run_id':run_id,'context':row.content if row else None,'skill_snapshot':row.skill_snapshot if row else [],
        'selector_mode':row.selector_mode if row else 'disabled','model_id':row.model_id if row else None}


@router.get('/decisions')
def decisions(workspace_id:UUID,run_id:str|None=None,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),
              db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id)
    query=select(AdaptiveDecision).where(AdaptiveDecision.workspace_id==workspace_id)
    if access.role not in {'admin','owner'}:
        query=query.where(AdaptiveDecision.owner_id==access.actor_id)
    if run_id:
        authorize_run(db,run_id,user.id);query=query.where(AdaptiveDecision.run_id==run_id)
    rows=db.scalars(query.order_by(AdaptiveDecision.created_at.desc()).offset(offset).limit(limit+1)).all()
    items=[]
    for row in rows[:limit]:
        outcome=db.scalar(select(AdaptiveOutcome).where(AdaptiveOutcome.workspace_id==workspace_id,AdaptiveOutcome.decision_id==row.id))
        items.append({'id':row.id,'run_id':row.run_id,'case_id':row.case_id,'decision':row.content,'features':row.features,
            'outcome':{'id':outcome.id,'revision':outcome.revision,'label_status':outcome.label_status,'record':outcome.content} if outcome else None})
    return {'items':items,'next_offset':offset+limit if len(rows)>limit else None}


@router.post('/outcomes/{outcome_id}/review')
def review_outcome(outcome_id:str,workspace_id:UUID,body:OutcomeReviewRequest,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'manage')
    row=db.scalar(select(AdaptiveOutcome).where(AdaptiveOutcome.id==outcome_id,AdaptiveOutcome.workspace_id==workspace_id).with_for_update())
    if not row:
        error(404,'OUTCOME_NOT_FOUND','Outcome not found.')
    if row.revision!=body.expected_revision:
        error(409,'STALE_LABEL_REVIEW','Outcome revision changed; reload before review.')
    row.revision+=1;row.label_status=body.label_status
    db.add(AdaptiveLabelRevision(workspace_id=workspace_id,outcome_id=row.id,number=row.revision,actor_id=access.actor_id,
        content={'label_status':body.label_status,'reason':body.reason,'previous_evidence_retained':True}))
    invalidated=invalidate(db,access,outcome_id=row.id)
    audit(db,access,'action_label_reviewed',row.id,status=row.label_status,reason=body.reason)
    result={'id':row.id,'revision':row.revision,'label_status':row.label_status,'invalidated':invalidated}
    db.commit();return result


@router.post('/cases',status_code=201)
def create_case(workspace_id:UUID,body:AdaptiveCaseRequest,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'manage');row=register_case(db,access,body)
    result={'id':row.id,'content_hash':row.content_hash,'split':row.split};db.commit();return result


@router.get('/cases')
def cases(workspace_id:UUID,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),
          db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    bind(db,user.id,workspace_id,'manage')
    rows=db.scalars(select(AdaptiveCase).where(AdaptiveCase.workspace_id==workspace_id)
        .order_by(AdaptiveCase.created_at.desc()).offset(offset).limit(limit+1)).all()
    return {'items':[{'id':r.id,'split':r.split,'scenario_group':r.scenario_group,'available':r.available,
        'source_kind':r.content['source_kind'],'task':r.content['task'],'content_hash':r.content_hash} for r in rows[:limit]],
        'next_offset':offset+limit if len(rows)>limit else None}


@router.post('/replays',status_code=202)
def replay(workspace_id:UUID,body:ReplayRequest,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'manage');row=queue_replay(db,access,body)
    result=work_json(db,row);db.commit();return result


@router.post('/training',status_code=202)
def train(workspace_id:UUID,body:TrainingRequest,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'manage');row=queue_training(db,access,body)
    result=work_json(db,row);db.commit();return result


@router.get('/jobs')
def jobs(workspace_id:UUID,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),
         db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    bind(db,user.id,workspace_id,'manage')
    rows=db.scalars(select(AdaptiveWork).where(AdaptiveWork.workspace_id==workspace_id)
        .order_by(AdaptiveWork.created_at.desc()).offset(offset).limit(limit+1)).all()
    return {'items':[work_json(db,row) for row in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/jobs/{work_id}')
def read_job(work_id:str,workspace_id:UUID,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    bind(db,user.id,workspace_id,'manage');row=db.get(AdaptiveWork,work_id)
    if not row or row.workspace_id!=workspace_id:
        error(404,'ADAPTIVE_JOB_NOT_FOUND','Adaptive job not found.')
    return work_json(db,row)


@router.post('/jobs/{work_id}/retry')
def retry_job(work_id:str,workspace_id:UUID,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    access=bind(db,user.id,workspace_id,'manage');row=db.get(AdaptiveWork,work_id)
    if not row or row.workspace_id!=workspace_id or row.owner_id!=access.actor_id:
        error(404,'ADAPTIVE_JOB_NOT_FOUND','Adaptive job not found.')
    job=db.scalar(select(DurableJob).where(DurableJob.id==row.job_id).with_for_update())
    if job.status!='FAILED' or not job.retry_eligible or job.attempt>=job.max_attempts:
        error(409,'RETRY_NOT_ALLOWED','Only bounded transient failures are retryable; permission failures are terminal.')
    job.status='QUEUED';job.error_code=None;job.lease_token=None;row.state='queued';row.result=None
    audit(db,access,'adaptive_job_retried',row.id,attempt=job.attempt)
    result=work_json(db,row);db.commit();return result


@router.get('/models')
def models(workspace_id:UUID,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),
           db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    bind(db,user.id,workspace_id,'manage')
    rows=db.scalars(select(AdaptiveModel).where(AdaptiveModel.workspace_id==workspace_id)
        .order_by(AdaptiveModel.created_at.desc()).offset(offset).limit(limit+1)).all()
    return {'items':[model_json(row) for row in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/models/{model_id}/download')
def download_model(model_id:str,workspace_id:UUID,db:Session=Depends(get_db_session),user=Depends(get_current_user)):
    bind(db,user.id,workspace_id,'manage');row=db.get(AdaptiveModel,model_id)
    if not model_valid(db,workspace_id,row):
        error(404,'MODEL_UNAVAILABLE','Model or source lineage is unavailable.')
    return Response(json.dumps(model_json(row,True),sort_keys=True,allow_nan=False),media_type='application/json',
        headers={'Content-Disposition':f'attachment; filename="repair-selector-{UUID(row.id)}.json"','Cache-Control':'private, no-store','ETag':f'"{row.content_hash}"'})
