"""Scoped adaptive authority integrated with the verified supervisor and outbox."""
from datetime import timezone
from uuid import uuid4

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.core.workspace_authorization import authorize_bound_dataset
from backend.app.models.background_job import DurableJob,utcnow
from backend.app.models.dataset_version import DatasetVersion
from backend.app.models.adaptive import (AdaptiveCase,AdaptiveContext,AdaptiveControl,AdaptiveDecision,
    AdaptiveLabelRevision,AdaptiveModel,AdaptiveOutcome,AdaptiveSkill,AdaptiveSkillRevision,AdaptiveWork)
from backend.app.schemas.adaptive import OutcomeRecord,ProblemContext,SkillManifest
from backend.app.schemas.learning import TaskSpec
from backend.app.services.data_retrieval_service import DataRetrievalService
from backend.app.services.storage_service import StorageService
from backend.app.services.learning_engine import RUNTIME_IDENTITY,digest,frame_hash,schema_hash
from backend.app.services.learning_supervisor import audit,aware,bind,definitions,error
from backend.app.services.adaptive_skills import catalog,context,diagnose,test_skill,RECIPE
from backend.app.services.adaptive_routing import RepairRouter


def controls(db,workspace):
    row=db.get(AdaptiveControl,workspace)
    return {'mode':row.mode if row else 'disabled','active_model_id':row.active_model_id if row else None,
        'previous_model_id':row.previous_model_id if row else None,'generation':row.generation if row else 0,
        'numeric_confidence':None,'routing_calibration':'unavailable','live_exploration':False,
        'main_llm_weights':'frozen','embedding_weights':'frozen'}


def authorized_frames(db,access,task,primary=None):
    if task.workspace_id!=access.workspace_id:
        error(404,'TASK_NOT_FOUND','Task scope not found.')
    loader=DataRetrievalService(db,StorageService(get_settings()),owner_id=str(access.actor_id));frames={}
    for index,ref in enumerate(task.datasets):
        authorize_bound_dataset(db,access,ref.dataset_id)
        version=db.scalar(select(DatasetVersion.version_id).where(DatasetVersion.dataset_id==ref.dataset_id,DatasetVersion.version_number==ref.version))
        if not version:
            error(404,'VERSION_NOT_FOUND','Pinned dataset version not found.')
        if index==0 and primary is not None:
            frame=primary
        else:
            frame,sampled=loader.load_dataframe(ref.dataset_id,ref.version,sample_size=0,preserve_representation=True)
            if sampled:
                error(409,'EXACT_DATA_REQUIRED','Adaptive evaluation cannot use an undeclared sample.')
        frames[ref.dataset_id]=frame
    return frames


def bootstrap(db,access):
    from backend.app.models.workspace import Workspace
    db.scalar(select(Workspace.id).where(Workspace.id==access.workspace_id).with_for_update())
    created=[]
    for manifest in catalog(access.workspace_id):
        old=db.scalar(select(AdaptiveSkill).where(AdaptiveSkill.workspace_id==access.workspace_id,
            AdaptiveSkill.skill_id==manifest.skill_id,AdaptiveSkill.version==manifest.version))
        if old:
            created.append(old);continue
        evidence=test_skill(manifest)
        if not evidence['passed']:
            error(409,'BUILTIN_SKILL_TEST_FAILED',f'Independent tests failed for {manifest.skill_id}.')
        payload=manifest.model_dump(mode='json')
        row=AdaptiveSkill(workspace_id=access.workspace_id,skill_id=manifest.skill_id,version=manifest.version,
            state='active',manifest=payload,content_hash=digest(payload),test_result=evidence,
            actor_id=access.actor_id,activated_at=utcnow())
        db.add(row);db.flush()
        db.add(AdaptiveSkillRevision(workspace_id=access.workspace_id,skill_id=row.id,state='active',actor_id=access.actor_id,
            evidence={'source':'Repository-reviewed release','tests':evidence}))
        created.append(row)
    audit(db,access,'trusted_skill_catalog_initialized',str(access.workspace_id),count=len(created))
    return created


def manifests(db,workspace,snapshot=None,cutoff=None):
    rows=db.scalars(select(AdaptiveSkill).where(AdaptiveSkill.workspace_id==workspace)).all()
    if not rows and snapshot is None:
        return catalog(workspace)
    refs={r['id']:r for r in snapshot} if snapshot is not None else None
    result=[]
    for row in rows:
        if row.state!='active' or row.content_hash!=digest(row.manifest) or cutoff and (aware(row.created_at)>aware(cutoff) or not row.activated_at or aware(row.activated_at)>aware(cutoff)):
            continue
        if refs is not None and (row.id not in refs or refs[row.id]['hash']!=row.content_hash):
            continue
        try:
            result.append(SkillManifest.model_validate({**row.manifest,'lifecycle':row.state}))
        except ValueError:
            continue
    if snapshot and not rows:
        # Built-ins captured before registry initialization remain code-version pinned.
        permitted={r['skill_id'] for r in snapshot if r.get('builtin')}
        return [s for s in catalog(workspace) if s.skill_id in permitted]
    return result


def prepare_context(db,access,run,row,primary):
    task=TaskSpec.model_validate(row.task)
    cfg=controls(db,access.workspace_id)
    has_catalog=db.scalar(select(AdaptiveSkill.id).where(AdaptiveSkill.workspace_id==access.workspace_id).limit(1))
    if cfg['mode']=='disabled' and not task.relationships and not has_catalog:
        return None,{task.datasets[0].dataset_id:primary}
    frames=authorized_frames(db,access,task,primary)
    hashes={key:frame_hash(value) for key,value in frames.items()}
    old=db.get(AdaptiveContext,run.id)
    if old:
        if old.input_hashes!=hashes or old.content['runtime']!=RUNTIME_IDENTITY:
            error(409,'ADAPTIVE_INPUT_OR_POLICY_CHANGED','Pinned adaptive inputs or policy changed; create a new run.')
        return old,frames
    problem=context(task,frames)
    available=manifests(db,access.workspace_id,cutoff=row.memory_cutoff)
    rows=db.scalars(select(AdaptiveSkill).where(AdaptiveSkill.workspace_id==access.workspace_id,AdaptiveSkill.state=='active')).all()
    by_key={(r.skill_id,r.version):r for r in rows};refs=[]
    for skill in available:
        record=by_key.get((skill.skill_id,skill.version))
        refs.append({'id':record.id if record else skill.skill_id,'skill_id':skill.skill_id,
            'version':skill.version,'hash':record.content_hash if record else digest(skill.model_dump(mode='json')),
            'builtin':record is None})
    old=AdaptiveContext(run_id=run.id,workspace_id=access.workspace_id,
        content={'problem':problem.model_dump(mode='json'),'diagnosis':diagnose(problem,frames,definitions=definitions(db,access.workspace_id)).model_dump(mode='json'),'runtime':RUNTIME_IDENTITY},
        input_hashes=hashes,skill_snapshot=refs,model_id=cfg['active_model_id'],selector_mode=cfg['mode'],generation=cfg['generation'])
    db.add(old);db.flush();return old,frames


def model_valid(db,workspace,row):
    if not row or row.workspace_id!=workspace or row.state not in {'evaluated','active'} or row.invalid_reason or row.content_hash!=digest(row.bundle):
        return False
    if not set(row.bundle['compatibility']['trained_implementation_hashes'])<={s.implementation_hash for s in manifests(db,workspace)}:
        return False
    snapshots=row.bundle['training_manifest'].get('label_snapshot',[])
    for item in snapshots:
        outcome=db.get(AdaptiveOutcome,item['id'])
        if not outcome or outcome.workspace_id!=workspace or outcome.revision!=item['revision'] or outcome.label_status!=item['label_status']:
            return False
    for ref in row.bundle['training_manifest'].get('case_snapshot',[]):
        case=db.get(AdaptiveCase,ref['id'])
        if not case or case.workspace_id!=workspace or not case.available or case.content_hash!=ref['hash']:
            return False
        try:
            from backend.app.core.workspace_authorization import authorize_workspace
            source_access=authorize_workspace(db,case.actor_id,workspace)
            for dataset in case.content['task']['datasets']:
                authorize_bound_dataset(db,source_access,dataset['dataset_id'])
        except Exception:
            return False
    return True


def run_router(store,job,run_id,task,frames,snapshot,lessons=None):
    from backend.app.services.analysis_run_service import authorize_run,fence
    if snapshot is None:
        return None
    workspace=snapshot.workspace_id
    def recheck():
        with store.sessions() as db:
            authorize_run(db,run_id,job['owner_id'],'write')
            bind(db,job['owner_id'],workspace,'write')
            available=manifests(db,workspace,snapshot.skill_snapshot,snapshot.created_at)
            cfg=controls(db,workspace);model=db.get(AdaptiveModel,snapshot.model_id) if snapshot.model_id else None
            allowed=cfg['mode'] in {'shadow','active'} and cfg['generation']==snapshot.generation and cfg['active_model_id']==snapshot.model_id and model_valid(db,workspace,model)
            return available,allowed
    with store.sessions() as db:
        bind(db,job['owner_id'],workspace,'write')
        available=manifests(db,workspace,snapshot.skill_snapshot,snapshot.created_at)
        model=db.get(AdaptiveModel,snapshot.model_id) if snapshot.model_id else None
        bundle=model.bundle if model_valid(db,workspace,model) else None
    def before(record,features):
        with store.sessions() as db,db.begin():
            fence(db,job);authorize_run(db,run_id,job['owner_id'],'write')
            access=bind(db,job['owner_id'],workspace,'write')
            key=digest([run_id,record['source_hash'],record['selected_implementation_hash']])
            old=db.scalar(select(AdaptiveDecision).where(AdaptiveDecision.workspace_id==workspace,AdaptiveDecision.dedup_key==key))
            if old:
                return old.id
            # Disabled mode retains mandatory context but does not collect training events.
            if controls(db,workspace)['mode']=='disabled':
                return f'uncollected:{key[:24]}'
            row=AdaptiveDecision(workspace_id=workspace,owner_id=access.actor_id,run_id=run_id,dedup_key=key,
                content=record,features=features,input_hash=record['source_hash'])
            db.add(row);db.flush();return row.id
    def after(record,outcome):
        if record['id'].startswith('uncollected:'):
            return
        with store.sessions() as db,db.begin():
            fence(db,job);authorize_run(db,run_id,job['owner_id'],'write')
            access=bind(db,job['owner_id'],workspace,'write')
            if controls(db,workspace)['mode']=='disabled':
                return
            db.scalar(select(AdaptiveDecision).where(AdaptiveDecision.id==record['id']).with_for_update())
            if db.scalar(select(AdaptiveOutcome.id).where(AdaptiveOutcome.decision_id==record['id'])):
                return
            outcome['parent_run_id']=run_id
            payload=OutcomeRecord.model_validate(outcome).model_dump(mode='json')
            row=AdaptiveOutcome(workspace_id=workspace,decision_id=record['id'],content=payload,label_status=payload['label_status'])
            db.add(row);db.flush();db.add(AdaptiveLabelRevision(workspace_id=workspace,outcome_id=row.id,number=1,
                actor_id=access.actor_id,content={'label_status':row.label_status,'policy':payload['label_policy'],'evidence':payload['evidence']}))
    return RepairRouter(task,frames,available,snapshot.selector_mode,bundle,snapshot.model_id,before,after,recheck,lessons)


def queue_work(db,access,kind,manifest,key):
    from backend.app.models.workspace import Workspace
    db.scalar(select(Workspace.id).where(Workspace.id==access.workspace_id).with_for_update())
    old=db.scalar(select(AdaptiveWork).where(AdaptiveWork.workspace_id==access.workspace_id,
        AdaptiveWork.kind==kind,AdaptiveWork.idempotency_key==key))
    if old:
        if old.owner_id!=access.actor_id or old.manifest!=manifest:
            error(409,'IDEMPOTENCY_CONFLICT','This job key already describes another request.')
        return old
    job=DurableJob(workspace_id=access.workspace_id,owner_id=access.actor_id,kind=f'adaptive_{kind}',
        idempotency_key=key,payload={},retry_eligible=True)
    db.add(job);db.flush()
    row=AdaptiveWork(workspace_id=access.workspace_id,owner_id=access.actor_id,job_id=job.id,kind=kind,
        idempotency_key=key,manifest=manifest)
    db.add(row);db.flush();job.payload={'work_id':row.id};return row


def invalidate(db,access,dataset_id=None,definition_ref=None,outcome_id=None,skill_hash=None):
    invalid_cases=[]
    for case in db.scalars(select(AdaptiveCase).where(AdaptiveCase.workspace_id==access.workspace_id,AdaptiveCase.available.is_(True))):
        task=case.content['task']
        if dataset_id and any(d['dataset_id']==dataset_id for d in task['datasets']) or definition_ref and definition_ref in task['definition_refs']:
            case.available=False;invalid_cases.append(case.id)
    revoked=[]
    for model in db.scalars(select(AdaptiveModel).where(AdaptiveModel.workspace_id==access.workspace_id,AdaptiveModel.state.in_(['candidate','evaluated','active']))):
        manifest=model.bundle['training_manifest']
        affected=any(r['id'] in invalid_cases for r in manifest.get('case_snapshot',[])) or any(r['id']==outcome_id for r in manifest.get('label_snapshot',[])) or skill_hash in model.bundle['compatibility']['trained_implementation_hashes']
        if affected:
            model.state='revoked';model.invalid_reason='Source, label or executable skill invalidated';revoked.append(model.id)
    cfg=db.get(AdaptiveControl,access.workspace_id)
    if cfg and cfg.active_model_id in revoked:
        cfg.mode='collection';cfg.previous_model_id=cfg.active_model_id;cfg.active_model_id=None;cfg.generation+=1
    if invalid_cases or revoked:
        audit(db,access,'adaptive_source_invalidation',dataset_id or outcome_id or 'policy',cases=invalid_cases,models=revoked)
    return {'cases':len(invalid_cases),'models':len(revoked)}


def queue_gap(db,access,run_id):
    if controls(db,access.workspace_id)['mode']=='disabled':
        return
    contexts=db.scalars(select(AdaptiveContext).where(AdaptiveContext.workspace_id==access.workspace_id).limit(1000)).all()
    sources=[r.run_id for r in contexts if r.content['diagnosis']['category']=='join_fan_out' and r.content['diagnosis']['established']]
    if len(set(sources))>=3:
        payload={'recipe':RECIPE,'category':'join_fan_out','source_runs':sorted(set(sources))[:20],'runtime':RUNTIME_IDENTITY}
        key=f'gap:join:{digest([RECIPE,RUNTIME_IDENTITY])[:32]}'
        if not db.scalar(select(AdaptiveWork.id).where(AdaptiveWork.workspace_id==access.workspace_id,AdaptiveWork.kind=='generate',AdaptiveWork.idempotency_key==key)):
            queue_work(db,access,'generate',payload,key)
