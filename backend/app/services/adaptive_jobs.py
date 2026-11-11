"""Durable isolated replay, skill testing/composition and numerical-weight training."""
import asyncio
from collections import Counter
from datetime import datetime,timezone
import time
from uuid import uuid4

from sqlalchemy import select,or_

from backend.app.models.adaptive import (AdaptiveCase,AdaptiveDecision,AdaptiveLabelRevision,AdaptiveModel,
    AdaptiveOutcome,AdaptiveSkill,AdaptiveSkillRevision,AdaptiveWork)
from backend.app.models.background_job import utcnow
from backend.app.schemas.adaptive import AdaptiveCaseRequest,OutcomeRecord,SkillManifest,TrainingRequest
from backend.app.schemas.learning import Budget,TaskSpec
from backend.app.services.learning_engine import RUNTIME_IDENTITY,digest,execute,frame_hash,same_rows
from backend.app.services.learning_evaluation import paired_interval,percentile
from backend.app.services.learning_supervisor import audit,bind,definitions,error
from backend.app.services.adaptive_service import authorized_frames,manifests,queue_work
from backend.app.services.adaptive_skills import (RECIPE,baseline_score,context,diagnose,eligible,feature_vector,
    implementation_hash,numeric_skill,relational_skill,test_skill)
from backend.app.services.adaptive_selector import fit_models
from backend.app.services.adaptive_routing import RepairRouter,relational_analysis


def register_case(db,access,request):
    from backend.app.models.learning import LearningRun
    if request.source_kind=='verified_run':
        from backend.app.services.analysis_run_service import authorize_run
        authorize_run(db,request.source_run_id,access.actor_id)
        source=db.get(LearningRun,request.source_run_id)
        if not source or source.state!='succeeded' or digest(source.task)!=digest(request.task.model_dump(mode='json')) or not same_rows(source.outcome['answer']['rows'],request.expected_rows):
            error(409,'UNVERIFIED_SOURCE_RUN','Enrollment must preserve the verified source task, result and lineage.')
    frames=authorized_frames(db,access,request.task)
    input_hashes={key:frame_hash(value) for key,value in frames.items()}
    dataset_ids={r.dataset_id for r in request.task.datasets}
    if request.split=='final':
        observed=db.scalars(select(LearningRun).where(LearningRun.workspace_id==access.workspace_id,LearningRun.owner_id==access.actor_id)).all()
        if any(row.task and dataset_ids & {ref['dataset_id'] for ref in row.task['datasets']} for row in observed):
            error(409,'FINAL_INPUT_ALREADY_OBSERVED','Previously analyzed inputs cannot become an untouched final set.')
    for old in db.scalars(select(AdaptiveCase).where(AdaptiveCase.workspace_id==access.workspace_id)):
        same_group=old.scenario_group==request.scenario_group
        same_input=bool(dataset_ids & {r['dataset_id'] for r in old.content['task']['datasets']}) or sorted(old.input_hashes.values())==sorted(input_hashes.values())
        if old.split!=request.split and (same_group or same_input):
            error(409,'SPLIT_CONTAMINATION','Scenario groups, datasets and duplicate input fingerprints cannot cross splits.')
    payload=request.model_dump(mode='json');hashed=digest(payload)
    old=db.scalar(select(AdaptiveCase).where(AdaptiveCase.workspace_id==access.workspace_id,AdaptiveCase.content_hash==hashed))
    if old:
        return old
    row=AdaptiveCase(workspace_id=access.workspace_id,actor_id=access.actor_id,scenario_group=request.scenario_group,
        split=request.split,content=payload,content_hash=hashed,input_hashes=input_hashes)
    db.add(row);db.flush();audit(db,access,'adaptive_case_registered',row.id,split=row.split,source_kind=request.source_kind)
    return row


def checked_cases(db,access,ids,load=False):
    result=[]
    if len(set(ids))!=len(ids):
        error(422,'DUPLICATE_CASE','Case IDs must be unique.')
    for identifier in ids:
        row=db.get(AdaptiveCase,identifier)
        if not row or row.workspace_id!=access.workspace_id or not row.available or row.content_hash!=digest(row.content):
            error(404,'ADAPTIVE_CASE_UNAVAILABLE','A source case is unavailable or invalidated.')
        request=AdaptiveCaseRequest.model_validate(row.content)
        # Authorization is mandatory even when only stored decision features are used.
        from backend.app.core.workspace_authorization import authorize_bound_dataset
        for ref in request.task.datasets:
            authorize_bound_dataset(db,access,ref.dataset_id)
        if load:
            frames=authorized_frames(db,access,request.task)
            if {key:frame_hash(value) for key,value in frames.items()}!=row.input_hashes:
                error(409,'SOURCE_VERSION_CHANGED','Pinned evaluation input changed.')
            result.append((row,request,frames))
        else:
            result.append(row)
    return result


def queue_replay(db,access,request):
    cases=checked_cases(db,access,request.case_ids)
    if any(case.split not in {'train','development'} for case in cases):
        error(409,'HELD_OUT_REPLAY_FORBIDDEN','Final/calibration alternatives cannot be exposed through development replay.')
    skills=manifests(db,access.workspace_id)
    manifest={'case_ids':request.case_ids,'catalog':[s.model_dump(mode='json') for s in skills],'runtime':RUNTIME_IDENTITY}
    return queue_work(db,access,'replay',manifest,request.idempotency_key)


def queue_training(db,access,request):
    all_ids=request.train_case_ids+request.development_case_ids+request.final_case_ids
    cases=checked_cases(db,access,all_ids)
    expected=[('train',request.train_case_ids),('development',request.development_case_ids),('final',request.final_case_ids)]
    groups=[]
    for split,ids in expected:
        selected=[case for case in cases if case.id in ids]
        if any(case.split!=split for case in selected):
            error(422,'WRONG_SPLIT','Training, development and final lists must match immutable case split assignments.')
        groups.append({case.scenario_group for case in selected})
    if any(groups[i]&groups[j] for i in range(3) for j in range(i)):
        error(409,'SCENARIO_LEAKAGE','Scenario groups cannot cross partitions.')
    payload=request.model_dump(mode='json');payload.pop('idempotency_key')
    existing=db.scalar(select(AdaptiveWork).where(AdaptiveWork.workspace_id==access.workspace_id,AdaptiveWork.kind=='train',AdaptiveWork.idempotency_key==request.idempotency_key))
    if existing:
        if existing.manifest['request']!=payload or existing.owner_id!=access.actor_id:
            error(409,'IDEMPOTENCY_CONFLICT','Training key already describes another request.')
        return existing
    _,_,train_snapshot,_=training_rows(db,access,request.train_case_ids)
    _,_,dev_snapshot,_=training_rows(db,access,request.development_case_ids)
    label_snapshot=train_snapshot+dev_snapshot
    for prior in db.scalars(select(AdaptiveWork).where(AdaptiveWork.workspace_id==access.workspace_id,AdaptiveWork.kind=='train')):
        old=prior.manifest.get('request',{})
        if set(old.get('final_case_ids',[]))&set(request.final_case_ids) and (old!=payload or prior.manifest['runtime']!=RUNTIME_IDENTITY or prior.state=='succeeded' and prior.manifest.get('label_snapshot')!=label_snapshot):
            error(409,'FINAL_SET_ALREADY_EXPOSED','Changed models, gates or training settings require a new untouched final set.')
    skills=manifests(db,access.workspace_id)
    manifest={'request':payload,'case_snapshot':[{'id':case.id,'hash':case.content_hash} for case in cases],
        'catalog':[s.model_dump(mode='json') for s in skills],'runtime':RUNTIME_IDENTITY,'label_snapshot':label_snapshot,'frozen_at':utcnow().isoformat()}
    # Idempotency is based on the original request, not a freshly generated timestamp.
    old=db.scalar(select(AdaptiveWork).where(AdaptiveWork.workspace_id==access.workspace_id,AdaptiveWork.kind=='train',AdaptiveWork.idempotency_key==request.idempotency_key))
    if old:
        if old.manifest['request']!=payload or old.owner_id!=access.actor_id:
            error(409,'IDEMPOTENCY_CONFLICT','Training key already describes another request.')
        return old
    return queue_work(db,access,'train',manifest,request.idempotency_key)


def replay_case(db,access,case,request,frames,skills):
    problem=context(request.task,frames);diagnosis=diagnose(problem,frames)
    candidates=eligible(skills,problem,frames,diagnosis,2)
    features={s.skill_id:feature_vector(problem,s,frames,diagnosis,2) for s in candidates}
    result=[]
    for skill in candidates:
        key=digest(['isolated-alternative',case.id,skill.implementation_hash,'independent-action-postconditions-v1'])
        old=db.scalar(select(AdaptiveDecision).where(AdaptiveDecision.workspace_id==access.workspace_id,AdaptiveDecision.dedup_key==key))
        if old and db.scalar(select(AdaptiveOutcome.id).where(AdaptiveOutcome.decision_id==old.id)):
            result.append(old.id);continue
        record={'context_version':problem.version,'feature_version':'task-action-features-v1',
            'context_hash':digest(problem.model_dump(mode='json')),'eligible_candidates':[{'skill_id':s.skill_id,'version':s.version,'implementation_hash':s.implementation_hash} for s in candidates],
            'selected_skill':skill.skill_id,'selected_version':skill.version,'selector':'isolated-alternative-replay-v1','model_id':None,
            'scores':{s.skill_id:baseline_score(s) for s in candidates},'shadow_scores':{},'fallback_reason':None,
            'decided_at':utcnow().isoformat(),'remaining_repairs':2,'selection_probability':None,'exploration':False,
            'selected_implementation_hash':skill.implementation_hash,'diagnosis':diagnosis.model_dump(mode='json')}
        decision=old or AdaptiveDecision(workspace_id=access.workspace_id,owner_id=access.actor_id,case_id=case.id,
            dedup_key=key,content=record,features=features,input_hash=digest(case.input_hashes))
        if not old:
            db.add(decision);db.flush()
        outcome=numeric_skill(skill,request.task,next(iter(frames.values()))) if skill.implementation.startswith('decimal_') else relational_skill(skill,request.task,frames,definitions(db,access.workspace_id))
        payload=OutcomeRecord(decision_id=decision.id,action_id=skill.skill_id,action_version=skill.version,
            result='success' if outcome.success else 'failure',label_status='positive' if outcome.success else 'negative',
            label_policy='independent-action-postconditions-v1',evidence=outcome.checks,
            failure_category=None if outcome.success else diagnosis.category,
            usage={'provider':'none','cost_usd':0,'latency_ms':outcome.latency_ms},parent_run_id=None,source_kind=request.source_kind).model_dump(mode='json')
        row=AdaptiveOutcome(workspace_id=access.workspace_id,decision_id=decision.id,content=payload,label_status=payload['label_status'])
        db.add(row);db.flush();db.add(AdaptiveLabelRevision(workspace_id=access.workspace_id,outcome_id=row.id,number=1,
            actor_id=access.actor_id,content={'label_status':row.label_status,'policy':payload['label_policy'],'evidence':payload['evidence']}))
        result.append(decision.id)
    return result


def training_rows(db,access,case_ids):
    cases=checked_cases(db,access,case_ids)
    run_cases={case.content['source_run_id']:case.id for case in cases if case.content.get('source_run_id')}
    rows=db.execute(select(AdaptiveDecision,AdaptiveOutcome).join(AdaptiveOutcome,AdaptiveOutcome.decision_id==AdaptiveDecision.id)
        .where(AdaptiveDecision.workspace_id==access.workspace_id,or_(AdaptiveDecision.case_id.in_(case_ids),AdaptiveDecision.run_id.in_(run_cases)),
               AdaptiveOutcome.workspace_id==access.workspace_id,AdaptiveOutcome.label_status.in_(['positive','negative']))
        .order_by(AdaptiveDecision.created_at,AdaptiveDecision.id)).all()
    x=[];y=[];snapshot=[];hashes=[];seen=set()
    for decision,outcome in rows:
        if outcome.label_status!=outcome.content['label_status']:
            continue  # Human ratings cannot flip immutable independently checked labels.
        feature=decision.features[decision.content['selected_skill']]
        # One action/input observation; repeated event delivery is not a new example.
        effective_case=decision.case_id or run_cases[decision.run_id]
        key=(effective_case,decision.content['selected_implementation_hash'],decision.input_hash)
        if key in seen:
            continue
        seen.add(key);x.append(feature);y.append(int(outcome.label_status=='positive'))
        snapshot.append({'id':outcome.id,'revision':outcome.revision,'label_status':outcome.label_status,
            'decision_id':decision.id,'case_id':effective_case})
        hashes.append(decision.content['selected_implementation_hash'])
    return x,y,snapshot,hashes


def compare_policies(cases,skills,bundles,definitions_by_workspace,budget=None):
    budget=budget or Budget();pairs=[]
    for case,request,frames in cases:
        record={'case_id':case.id,'scenario_group':case.scenario_group,'source_kind':request.source_kind}
        for name in ['baseline','linear','mlp']:
            start=time.perf_counter()
            router=RepairRouter(request.task,frames,skills,'active' if name!='baseline' else 'collection',bundles.get(name),name if name!='baseline' else None)
            try:
                if request.task.relationships:
                    outcome=relational_analysis(request.task,frames,definitions_by_workspace,router,budget)
                else:
                    outcome=execute(request.task,next(iter(frames.values())),definitions_by_workspace,budget,repair_router=router)
                correct=outcome['status']==request.expected_status
                if request.expected_status=='verified':
                    correct=correct and bool(outcome['answer']) and same_rows(outcome['answer']['rows'],request.expected_rows)
                attempts=outcome['repair_attempts']
                first=bool(correct) and (not attempts or attempts[0]['outcome']=='succeeded' or request.expected_status=='insufficient_evidence')
                record[name]={'correct':bool(correct),'first_attempt_correct':first,'status':outcome['status'],
                    'verified_repairs':sum(a['outcome']=='succeeded' for a in attempts),
                    'failed_repairs':sum(a['outcome']=='failed' for a in attempts),'repair_attempts':len(attempts),
                    'harmful_repair':outcome['status']=='verified' and not correct,
                    'error_code':outcome['error_code'],'latency_ms':(time.perf_counter()-start)*1000,'provider_cost_usd':0,
                    'selected_skills':[r['selected_skill'] for r in router.records],
                    'fallbacks':[r['fallback_reason'] for r in router.records if r['fallback_reason']]}
            except Exception:
                record[name]={'correct':False,'first_attempt_correct':False,'status':'failed','verified_repairs':0,
                    'failed_repairs':0,'repair_attempts':0,'harmful_repair':False,'error_code':'EVALUATION_EXECUTOR_FAILED',
                    'latency_ms':(time.perf_counter()-start)*1000,'provider_cost_usd':0,'selected_skills':[],'fallbacks':[]}
        pairs.append(record)
    metrics={};n=len(pairs)
    for name in ['baseline','linear','mlp']:
        values=[r[name] for r in pairs];errors=Counter(v['error_code'] for v in values if not v['correct'])
        attempts=sum(v['repair_attempts'] for v in values)
        metrics[name]={'cases':n,'first_attempt_correct':sum(v['first_attempt_correct'] for v in values),
            'final_correct':sum(v['correct'] for v in values),'verified_repair_success':sum(v['verified_repairs'] for v in values),
            'attempted_repairs':attempts,'verified_repair_rate':sum(v['verified_repairs'] for v in values)/max(1,attempts),
            'failed_repair_attempts':sum(v['failed_repairs'] for v in values),'repeated_errors':sum(max(0,c-1) for c in errors.values()),
            'harmful_repairs':sum(v['harmful_repair'] for v in values),'abstained':sum(v['status']=='insufficient_evidence' for v in values),
            'unknown':sum(v['status']=='failed' for v in values),'p50_latency_ms':percentile([v['latency_ms'] for v in values],.5),
            'p95_latency_ms':percentile([v['latency_ms'] for v in values],.95),'provider_cost_usd':0}
    return {'pairs':pairs,'metrics':metrics,'sample_size':n,'scenario_groups':len({r['scenario_group'] for r in pairs}),
        'trusted_final_groups':len({r['scenario_group'] for r in pairs if r['source_kind']=='domain_reviewed'}),
        'limits':['Synthetic classification fit does not establish production policy improvement.',
                  'No off-policy estimate is made; alternatives were executed only on isolated local fixtures.',
                  'No stochastic live exploration; routing scores are not calibrated answer probabilities.'],
        'denominators':{'correctness':'All frozen final cases, including failures/unknowns.',
            'repair_success':'Verified local action successes / all executed repair attempts.',
            'harmful':'Wrong final answers marked verified after repairs; rejected attempts counted separately.',
            'latency':'Whole isolated executor, including feature/ranking/validation; excludes queue and input loading.',
            'cost':'Provider usage only; training CPU/RSS are separate measurements.'}}


def release_gates(comparison,kind,gates):
    base=comparison['metrics']['baseline'];candidate=comparison['metrics'][kind];n=comparison['sample_size']
    regressions=sum(r['baseline']['correct'] and not r[kind]['correct'] for r in comparison['pairs'])
    first_regressions=sum(r['baseline']['first_attempt_correct'] and not r[kind]['first_attempt_correct'] for r in comparison['pairs'])
    invariants=all(not r[name]['harmful_repair'] for r in comparison['pairs'] for name in ['baseline',kind])
    values={
        'mandatory_correctness_authorization_integrity':invariants and candidate['unknown']==0,
        'trusted_final_coverage':comparison['trusted_final_groups']>=gates.min_trusted_final_groups,
        'no_final_regression':regressions==0,'no_first_attempt_regression':first_regressions==0,
        'no_harmful_repairs':candidate['harmful_repairs']==0,
        'latency_tolerance':candidate['p95_latency_ms']<=max(1,base['p95_latency_ms'])*gates.max_p95_ratio,
        'no_provider_cost_increase':candidate['provider_cost_usd']<=base['provider_cost_usd'],
        'measured_policy_benefit':candidate['final_correct']>base['final_correct'] or candidate['first_attempt_correct']>base['first_attempt_correct'] or candidate['repeated_errors']<base['repeated_errors'],
    }
    grouped={}
    for pair in comparison['pairs']:
        grouped.setdefault(pair['scenario_group'],[]).append(int(pair[kind]['correct'])-int(pair['baseline']['correct']))
    return {'gates':values,'release_eligible':all(values.values()),'paired_correctness_delta':(candidate['final_correct']-base['final_correct'])/n,
        'paired_scenario_bootstrap_95_interval':paired_interval([sum(v)/len(v) for v in grouped.values()]),
        'calibration':{'available':False,'brier_score':None,'reliability_bins':[],'reliability_diagram':None,
                       'reason':'No independent calibrator-fit and calibration-test data. Routing values are scores only.'}}


def train_job(store,job,work):
    from backend.app.services.analysis_run_service import fence
    manifest=work.manifest
    request=TrainingRequest.model_validate({**manifest['request'],'idempotency_key':work.idempotency_key})
    with store.sessions() as db:
        access=bind(db,job['owner_id'],job['workspace_id'],'manage')
        checked_cases(db,access,request.train_case_ids+request.development_case_ids+request.final_case_ids)
        x,y,train_labels,hashes=training_rows(db,access,request.train_case_ids)
        dx,dy,dev_labels,dev_hashes=training_rows(db,access,request.development_case_ids)
        if train_labels+dev_labels!=manifest['label_snapshot']:
            error(409,'LABEL_SNAPSHOT_CHANGED','Training data changed after queueing; submit a new reviewed training intent.')
        groups={db.get(AdaptiveCase,item['case_id']).scenario_group for item in train_labels}
    counts=Counter(y)
    sufficient=len(x)>=request.min_examples and len(groups)>=request.min_groups and min(counts.get(0,0),counts.get(1,0))>=request.min_per_class and len(dx)>=4 and set(dy)=={0,1}
    if not sufficient:
        return {'state':'insufficient_evidence','trained':False,'train_examples':len(x),'train_groups':len(groups),
            'class_counts':dict(counts),'reason':'Replay or independently verify enough positive AND negative local action outcomes in separate train/development groups.'}
    training_manifest={**manifest,'label_snapshot':train_labels+dev_labels,'label_policy':'independent-action-postconditions-v1',
        'prediction_target':'Approved action satisfies its declared independent numeric/structural postconditions.',
        'preprocessing_fit':'training examples only','embeddings':'unused; existing embedding model frozen'}
    from backend.app.services.adaptive_training import fit_bounded
    bundles,measurements=fit_bounded(store,job,train_x=x,train_y=y,development_x=dx,
        development_y=dy,manifest=training_manifest,implementation_hashes=hashes,
        seed=request.seed,max_epochs=request.max_epochs,deadline_seconds=request.deadline_seconds)
    store.heartbeat(job['id'],job['lease_token'])
    with store.sessions() as db:
        access=bind(db,job['owner_id'],job['workspace_id'],'manage')
        final_cases=checked_cases(db,access,request.final_case_ids,load=True)
        skills=[SkillManifest.model_validate(s) for s in manifest['catalog']]
        current=manifests(db,access.workspace_id)
        if not {s.implementation_hash for s in skills}<={s.implementation_hash for s in current}:
            error(409,'SKILL_SNAPSHOT_INVALIDATED','A frozen skill was revoked or changed during training.')
        comparison=compare_policies(final_cases,skills,bundles,definitions(db,access.workspace_id))
    model_ids={}
    with store.sessions() as db,db.begin():
        fence(db,job);access=bind(db,job['owner_id'],job['workspace_id'],'manage')
        checked_cases(db,access,request.train_case_ids+request.development_case_ids+request.final_case_ids)
        # Recheck after evaluation as well: a revocation during a long final
        # replay must not publish a new bundle using the stale catalog snapshot.
        current_hashes={s.implementation_hash for s in manifests(db,access.workspace_id)}
        if not {s['implementation_hash'] for s in manifest['catalog']}<=current_hashes:
            error(409,'SKILL_SNAPSHOT_INVALIDATED','Frozen catalog changed before bundle publication.')
        for label in training_manifest['label_snapshot']:
            row=db.get(AdaptiveOutcome,label['id'])
            if row.revision!=label['revision'] or row.label_status!=label['label_status']:
                error(409,'LABEL_SNAPSHOT_CHANGED','A delayed review invalidated a frozen training label.')
        for kind,bundle in bundles.items():
            gate_result=release_gates(comparison,kind,request.gates)
            bundle['evaluation']['policy_comparison']=comparison;bundle['evaluation'].update(gate_result)
            existing=db.scalar(select(AdaptiveModel).where(AdaptiveModel.workspace_id==access.workspace_id,AdaptiveModel.work_id==work.id,AdaptiveModel.kind==kind))
            if existing:
                model_ids[kind]=existing.id;continue
            row=AdaptiveModel(workspace_id=access.workspace_id,work_id=work.id,kind=kind,state='evaluated',bundle=bundle,content_hash=digest(bundle))
            db.add(row);db.flush();model_ids[kind]=row.id
        audit(db,access,'selector_weights_trained',work.id,models=model_ids,training_seconds=measurements['training_seconds'])
    preferred=min(['linear','mlp'],key=lambda kind:(-comparison['metrics'][kind]['final_correct'],
        -comparison['metrics'][kind]['first_attempt_correct'],0 if kind=='linear' else 1))
    return {'state':'succeeded','trained':True,'models':model_ids,'measurements':measurements,'comparison':comparison,
        'preferred_candidate':preferred,'active_model':'rules-memory-v1','release_eligible':any(b['evaluation']['release_eligible'] for b in bundles.values()),
        'note':'Main LLM/embedding weights frozen. These are numerically trained selector candidates, not automatically active models.'}


def _execute_work(store,job):
    from backend.app.services.analysis_run_service import fence
    work_id=job['payload']['work_id']
    try:
        with store.sessions() as db,db.begin():
            fence(db,job);permission='write' if job['kind']=='adaptive_generate' else 'manage'
            access=bind(db,job['owner_id'],job['workspace_id'],permission)
            work=db.get(AdaptiveWork,work_id)
            if not work or work.workspace_id!=access.workspace_id or work.owner_id!=access.actor_id:
                error(404,'ADAPTIVE_JOB_NOT_FOUND','Adaptive job not found.')
            if work.state in {'succeeded','insufficient_evidence'}:
                return {'work_id':work.id,'state':work.state}
            if work.manifest.get('runtime')!=RUNTIME_IDENTITY:
                error(409,'POLICY_CHANGED','Queued adaptation work requires the same frozen code.')
            work.state='running';db.flush();db.expunge(work)
        if work.kind=='train':
            result=train_job(store,job,work)
        elif work.kind=='replay':
            ids=[]
            for identifier in work.manifest['case_ids']:
                store.heartbeat(job['id'],job['lease_token'])
                with store.sessions() as db,db.begin():
                    fence(db,job);access=bind(db,job['owner_id'],job['workspace_id'],'manage')
                    case,request,frames=checked_cases(db,access,[identifier],load=True)[0]
                    skills=[SkillManifest.model_validate(s) for s in work.manifest['catalog']]
                    current=manifests(db,access.workspace_id)
                    skills=[s for s in skills if any(c.implementation_hash==s.implementation_hash for c in current)]
                    ids.extend(replay_case(db,access,case,request,frames,skills))
            result={'state':'succeeded','decision_ids':ids,'note':'Permissible alternatives executed locally; no external side effects or off-policy estimate.'}
        elif work.kind=='test':
            with store.sessions() as db,db.begin():
                fence(db,job);access=bind(db,job['owner_id'],job['workspace_id'],'manage')
                skill=db.get(AdaptiveSkill,work.manifest['skill_id'])
                if not skill or skill.workspace_id!=access.workspace_id or skill.state!='testing':
                    error(409,'SKILL_TEST_CANCELLED','Skill is no longer eligible for this test job.')
                evidence=test_skill(SkillManifest.model_validate(skill.manifest))
                skill.test_result=evidence;skill.state='verified' if evidence['passed'] else 'rejected'
                db.add(AdaptiveSkillRevision(workspace_id=access.workspace_id,skill_id=skill.id,state=skill.state,actor_id=access.actor_id,evidence=evidence))
                result={'state':'succeeded','skill_id':skill.id,'test_result':evidence,'lifecycle':skill.state}
        elif work.kind=='generate':
            with store.sessions() as db,db.begin():
                fence(db,job);access=bind(db,job['owner_id'],job['workspace_id'],'write')
                if work.manifest['recipe']!=RECIPE:
                    error(422,'UNAPPROVED_RECIPE','Only the reviewed bounded recipe can be composed.')
                stable='composed_refund_reconciliation'
                old=db.scalar(select(AdaptiveSkill).where(AdaptiveSkill.workspace_id==access.workspace_id,AdaptiveSkill.skill_id==stable,AdaptiveSkill.version==1))
                if not old:
                    base=catalog_manifest(access.workspace_id)
                    old=AdaptiveSkill(workspace_id=access.workspace_id,skill_id=stable,version=1,state='candidate',manifest=base,
                        content_hash=digest(base),actor_id=access.actor_id)
                    db.add(old);db.flush();db.add(AdaptiveSkillRevision(workspace_id=access.workspace_id,skill_id=old.id,state='candidate',
                        actor_id=access.actor_id,evidence={'source_runs':work.manifest['source_runs'],'generator':'Approved tool composition only; independent tests still required.'}))
                result={'state':'succeeded','skill_id':old.id,'lifecycle':old.state}
        else:
            raise ValueError('UNSUPPORTED_ADAPTIVE_JOB')
        with store.sessions() as db,db.begin():
            fence(db,job);bind(db,job['owner_id'],job['workspace_id'],permission)
            row=db.get(AdaptiveWork,work_id);row.state=result['state'];row.result=result
        return {'work_id':work_id,'state':result['state']}
    except Exception:
        try:
            with store.sessions() as db,db.begin():
                fence(db,job);bind(db,job['owner_id'],job['workspace_id'],'write')
                row=db.get(AdaptiveWork,work_id)
                if row and row.state not in {'succeeded','insufficient_evidence'}:
                    row.state='failed';row.result={'error_code':'ADAPTIVE_JOB_FAILED','active_model':'rules-memory-v1'}
        except Exception:
            pass
        raise


def catalog_manifest(workspace):
    return SkillManifest(skill_id='composed_refund_reconciliation',version=1,implementation='approved_recipe',
        implementation_hash=implementation_hash('approved_recipe'),inputs='ProblemContext+authorized-dataframes@1',
        outputs='SkillResult+ValidationResult@1',preconditions=['Trusted net-revenue definition','Unique complete order key','Complete nonnegative refund event amounts'],
        permitted_tools=RECIPE,resource_limits={'max_rows':500000,'max_input_bytes':50000000,'max_seconds':30,'max_repairs':2},
        stages=[5],workspace_id=workspace,definition_refs=[],task_types=['descriptive'],tests=['independent 285 and counterexample suite'],
        lifecycle='candidate',recipe=RECIPE,source='composed_candidate').model_dump(mode='json')


async def execute_adaptive_job(store,job):
    return await asyncio.to_thread(_execute_work,store,job)
