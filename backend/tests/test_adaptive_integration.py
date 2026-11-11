"""Real PostgreSQL roles/workers and explicit synthetic selector training pilot."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select,text

from backend.tests.test_verified_learning_integration import (environment,identity,dataset,spec,call,run,status,manager as old_manager)
from backend.app.models.adaptive import AdaptiveCase,AdaptiveControl,AdaptiveDecision,AdaptiveModel,AdaptiveOutcome,AdaptiveWork
from backend.app.models.background_job import DurableJob,utcnow
from backend.app.schemas.learning import TaskSpec
from backend.app.services.adaptive_jobs import execute_adaptive_job
from backend.app.services.adaptive_skills import fixture_task
from backend.app.services.learning_supervisor import bind
from backend.jobs.persistence import PersistentJobStore,LostLeaseError


def path(account,part):
    return f'/api/v1/adaptive/{part}?workspace_id={account["workspace"]}'


def manager(env):
    result=old_manager(env)
    for kind in ('replay','train','generate','test'):
        result.register_durable(f'adaptive_{kind}',execute_adaptive_job)
    return result


def drain(env):
    worker=manager(env)
    for _ in range(200):
        job=asyncio.run(worker.run_next_durable('adaptive-real-role-worker'))
        if not job:
            return
        if job['owner_id'] in env['actors']:
            assert job['status']=='READY',job
    raise AssertionError('Unbounded adaptive job loop')


def initialize(env,account):
    result=call(env,account,'POST',path(account,'skills/bootstrap'),expected=201)
    assert len(result['items'])==8 and all(item['test_result']['passed'] for item in result['items'])
    call(env,account,'PUT',path(account,'controls'),{'mode':'collection','expected_generation':0})


def definition(env,account):
    body={'key':'net_revenue','version':1,'owner':'Synthetic finance owner','source':'Independent order/refund fixture rubric',
        'metric':{'column':'net_amount','aggregation':'sum','missing':'reject','definition_ref':None},
        'filters':[],'units':'USD','currency':'USD','examples':[{'orders_total':300,'refunds':15,'expected_net':285}]}
    return call(env,account,'POST',f'/api/v1/learning/definitions?workspace_id={account["workspace"]}',body,201)


def numeric_case(env,account,tmp_path,split,index,high=False):
    count=2+index%7+(3 if split=='final' else 0)
    partition_index=index+{'train':0,'development':100,'final':1000}[split]
    values=[f'{1234567890100000+partition_index*10+j}.12' if high else f'{(partition_index+1)*(j+2)}.25' for j in range(count)]
    csv='region,amount\n'+''.join(f'group,{value}\n' for value in values)
    ds=dataset(env,account,tmp_path,csv)
    task=spec(account['workspace'],ds)
    total=sum((Decimal(value) for value in values),Decimal(0))
    body={'task':task,'scenario_group':f'{split}-synthetic-schema-scenario-{index}', 'split':split,
        'source_kind':'synthetic','reference':'Independent Decimal sum of the listed synthetic source observations',
        'expected_status':'verified','expected_rows':[{'region':'group','value':format(total,'f')}]}
    created=call(env,account,'POST',path(account,'cases'),body,201)
    return created['id'],{'case_id':created['id'],'csv':csv,'contract_and_gold':body}


def test_orders_refunds_real_run_context_review_and_recipe_generation(environment,tmp_path):
    env=environment;a=identity(env);initialize(env,a);definition(env,a)
    orders=dataset(env,a,tmp_path,'order_id,amount\nA,100\nB,200\n')
    refunds=dataset(env,a,tmp_path,'order_id,refund\nA,10\nA,5\n')
    task=fixture_task(a['workspace'],orders,refunds).model_dump(mode='json')
    records=[]
    for _ in range(3):
        current=run(env,a,orders,task);drain(env);records.append(current['id'])
        result=status(env,a,current['id'])
        assert result['state']=='succeeded',result
        assert result['outcome']['answer']['rows']==[{'value':285}]
    contextual=call(env,a,'GET',f'/api/v1/adaptive/runs/{records[0]}/context')
    assert contextual['context']['diagnosis']['category']=='join_fan_out'
    assert len(contextual['context']['problem']['schema_versions'])==2
    decisions=call(env,a,'GET',path(a,'decisions'))
    assert len(decisions['items'])==3
    assert all(d['outcome']['label_status']=='positive' for d in decisions['items'])
    recipes=call(env,a,'GET',path(a,'skills'))['items']
    recipe=next(s for s in recipes if s['skill_id']=='composed_refund_reconciliation')
    assert recipe['state']=='candidate'
    call(env,a,'POST',path(a,f'skills/{recipe["id"]}/review'),{'action':'activate','expected_state':'candidate','reason':'Generator cannot self-approve'},409)
    call(env,a,'POST',path(a,f'skills/{recipe["id"]}/review'),{'action':'test','expected_state':'candidate','reason':'Run independent expected outputs and counterexamples'})
    drain(env)
    tested=call(env,a,'GET',path(a,f'skills/{recipe["id"]}'))
    assert tested['state']=='verified' and tested['test_result']['passed']
    call(env,a,'POST',path(a,f'skills/{recipe["id"]}/review'),{'action':'activate','expected_state':'verified','reason':'Approved bounded recipe and applicability reviewed'})
    event_task=fixture_task(a['workspace'],orders,refunds,True).model_dump(mode='json')
    event_run=run(env,a,orders,event_task);drain(env)
    events=status(env,a,event_run['id'])
    assert events['outcome']['answer']['rows']==[{'value':2}]
    assert events['outcome']['decisions'][0]['selected_skill']=='refund_event_count'
    # Both inputs remain authorization requirements for status and export.
    other=identity(env)
    call(env,other,'GET',f'/api/v1/learning/runs/{records[0]}/report',expected=404)
    with env['admin']() as db,db.begin():
        from backend.app.core.workspace_authorization import dataset_workspace_bindings
        db.execute(dataset_workspace_bindings.update().where(dataset_workspace_bindings.c.dataset_id==refunds).values(workspace_id=other['workspace']))
    call(env,a,'GET',f'/api/v1/learning/runs/{records[0]}/report',expected=404)


def test_real_train_linear_mlp_shadow_loading_rollback_and_delayed_label(environment,tmp_path):
    env=environment;a=identity(env);initialize(env,a)
    splits={};fixtures=[]
    for split,count in [('train',24),('development',8),('final',8)]:
        splits[split]=[]
        for i in range(count):
            identifier,fixture=numeric_case(env,a,tmp_path,split,i,high=i%2==0)
            splits[split].append(identifier);fixtures.append(fixture)
    replay_body={'case_ids':splits['train']+splits['development'],'idempotency_key':uuid4().hex}
    replay=call(env,a,'POST',path(a,'replays'),replay_body,202);drain(env)
    assert call(env,a,'GET',path(a,f'jobs/{replay["id"]}'))['state']=='succeeded'
    before=call(env,a,'GET',path(a,'decisions')+'&limit=100')['items']
    assert len(before)==64 and {d['outcome']['label_status'] for d in before}=={'positive','negative'}
    # A new replay job with the same action/input pairs does not duplicate events.
    call(env,a,'POST',path(a,'replays'),{**replay_body,'idempotency_key':uuid4().hex},202);drain(env)
    assert len(call(env,a,'GET',path(a,'decisions')+'&limit=100')['items'])==64
    request={'train_case_ids':splits['train'],'development_case_ids':splits['development'],'final_case_ids':splits['final'],
        'max_epochs':60,'idempotency_key':uuid4().hex}
    training=call(env,a,'POST',path(a,'training'),request,202)
    assert call(env,a,'POST',path(a,'training'),request,202)['id']==training['id']
    drain(env)
    job=call(env,a,'GET',path(a,f'jobs/{training["id"]}'))
    assert job['state']=='succeeded',job
    result=job['result'];assert result['trained'] and set(result['models'])=={'linear','mlp'}
    comparison=result['comparison']
    assert all(comparison['metrics'][kind]['final_correct']==8 for kind in ['baseline','linear','mlp'])
    assert not result['release_eligible']
    models=call(env,a,'GET',path(a,'models'))['items'];assert len(models)==2
    bundles={}
    for model in models:
        assert model['state']=='evaluated' and not model['evaluation']['all_weights_zero']
        assert model['calibration_status']=='unavailable' and not model['evaluation']['release_eligible']
        downloaded=call(env,a,'GET',path(a,f'models/{model["id"]}/download'))
        bundles[model['kind']]=downloaded
    cfg=call(env,a,'GET',path(a,'controls'))
    candidate=result['models']['linear']
    with env['api']() as db:
        bind(db,a['user'],a['workspace'])
        with pytest.raises(Exception,match='Immutable adaptive content'):
            db.execute(text("UPDATE adaptive_models SET bundle='{}' WHERE id=:id"),{'id':candidate})
    foreign=identity(env)
    call(env,foreign,'GET',path(a,'models'),expected=404)
    call(env,foreign,'GET',path(foreign,f'models/{candidate}/download'),expected=404)
    call(env,a,'PUT',path(a,'controls'),{'mode':'active','model_id':candidate,'expected_generation':cfg['generation']},409)
    cfg=call(env,a,'PUT',path(a,'controls'),{'mode':'shadow','model_id':candidate,'expected_generation':cfg['generation']})
    # Shadow produces scores but executes one baseline action, never a duplicate external side effect.
    ds=dataset(env,a,tmp_path,'region,amount\nx,10.25\nx,20.25\n');current=run(env,a,ds,spec(a['workspace'],ds));drain(env)
    evidence=status(env,a,current['id']);decision=evidence['outcome']['decisions'][0]
    assert evidence['state']=='succeeded' and decision['selector']=='rules-memory-v1' and decision['shadow_scores']
    assert evidence['repairs']==1
    # Logits are routing scores, not percentages or numeric answer confidence.
    assert evidence['numeric_confidence'] is None and decision['selection_probability']==1
    rolled=call(env,a,'POST',path(a,'rollback'),{'mode':'collection','expected_generation':cfg['generation']})
    assert rolled['mode']=='collection' and rolled['active_model_id'] is None
    output_dir=os.environ.get('ADAPTIVE_EVIDENCE_DIR')
    if output_dir:
        out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
        for filename,payload in [('training-job.json',job),('selector-comparison.json',comparison),('synthetic-fixtures.json',fixtures),('model-bundles.json',bundles)]:
            (out/filename).write_text(json.dumps(payload,indent=2,default=str))
    # Poisoned user feedback cannot relabel an action as numerically correct.
    observation=next(d for d in before if d['outcome']['label_status']=='negative')['outcome']
    call(env,a,'POST',path(a,f'outcomes/{observation["id"]}/review'),{'expected_revision':1,'label_status':'positive','reason':'Thumbs up says correct'},422)
    reviewed=call(env,a,'POST',path(a,f'outcomes/{observation["id"]}/review'),{'expected_revision':1,'label_status':'disputed','reason':'Delayed independent review disputes the target label'})
    assert reviewed['invalidated']['models']==2
    call(env,a,'GET',path(a,f'models/{candidate}/download'),expected=404)
    call(env,a,'PUT',path(a,'controls'),{'mode':'shadow','model_id':candidate,'expected_generation':rolled['generation']},409)
    # Reusing exposed final cases with changed gates/training labels is prohibited.
    call(env,a,'POST',path(a,'training'),{**request,'idempotency_key':uuid4().hex},409)


def test_insufficient_labels_and_split_leakage_do_not_train(environment,tmp_path):
    env=environment;a=identity(env);initialize(env,a);splits={}
    first=None
    for split in ['train','development','final']:
        splits[split]=[]
        for index in range(2):
            identifier,fixture=numeric_case(env,a,tmp_path,split,index+30,high=index==0)
            splits[split].append(identifier)
            if first is None:first=fixture
    leaking=deepcopy(first['contract_and_gold']);leaking['split']='final';leaking['scenario_group']='leaking-copy'
    call(env,a,'POST',path(a,'cases'),leaking,409)
    request={'train_case_ids':splits['train'],'development_case_ids':splits['development'],'final_case_ids':splits['final'],
        'min_examples':8,'min_groups':2,'min_per_class':2,'idempotency_key':uuid4().hex}
    created=call(env,a,'POST',path(a,'training'),request,202);drain(env)
    result=call(env,a,'GET',path(a,f'jobs/{created["id"]}'))
    assert result['state']=='insufficient_evidence' and result['result']['trained'] is False
    assert call(env,a,'GET',path(a,'models'))['items']==[]


def test_skill_revocation_replay_recovery_real_rls_and_model_scope(environment,tmp_path):
    env=environment;a=identity(env);b=identity(env);initialize(env,a)
    identifier,fixture=numeric_case(env,a,tmp_path,'train',78)
    replay=call(env,a,'POST',path(a,'replays'),{'case_ids':[identifier],'idempotency_key':uuid4().hex},202)
    store=PersistentJobStore(env['worker']);claimed=store.claim('dead-adaptive-worker',['adaptive_replay'])
    assert claimed and claimed['payload']['work_id']==replay['id']
    with env['admin']() as db,db.begin():
        db.get(DurableJob,claimed['id']).lease_expires_at=utcnow()-timedelta(seconds=1)
    drain(env)
    assert call(env,a,'GET',path(a,f'jobs/{replay["id"]}'))['state']=='succeeded'
    with pytest.raises(LostLeaseError):store.heartbeat(claimed['id'],claimed['lease_token'])
    observed=call(env,a,'GET',path(a,'decisions'))['items'];assert len(observed)==2
    call(env,b,'GET',path(a,'decisions'),expected=404)
    for sessions in (env['api'],env['worker']):
        with sessions() as db:
            assert db.scalars(select(AdaptiveDecision)).all()==[]
            bind(db,b['user'],b['workspace']);assert db.get(AdaptiveDecision,observed[0]['id']) is None
            bind(db,a['user'],a['workspace']);assert db.get(AdaptiveDecision,observed[0]['id']) is not None
            with pytest.raises(Exception,match='Immutable learning evidence'):
                db.execute(text('UPDATE adaptive_decisions SET features=:data WHERE id=:id'),{'data':'{}','id':observed[0]['id']})
    skills=call(env,a,'GET',path(a,'skills'))['items'];exact=next(s for s in skills if s['skill_id']=='decimal_exact')
    call(env,a,'POST',path(a,f'skills/{exact["id"]}/review'),{'action':'revoke','expected_state':'active','reason':'Synthetic revocation control test'})
    ds=dataset(env,a,tmp_path,'region,amount\nx,1.25\n');current=run(env,a,ds,spec(a['workspace'],ds));drain(env)
    evidence=status(env,a,current['id'])
    assert evidence['outcome']['decisions'][0]['selected_skill']=='decimal_vector_checked'
    # Dataset deletion invalidates source cases and future replay authorization.
    source_id=fixture['contract_and_gold']['task']['datasets'][0]['dataset_id']
    call(env,a,'DELETE',f'/api/v1/datasets/{source_id}');drain(env)
    call(env,a,'POST',path(a,'replays'),{'case_ids':[identifier],'idempotency_key':uuid4().hex},404)


def test_live_action_enrollment_preserves_labels_and_heldout_inputs(environment,tmp_path):
    env=environment;a=identity(env);initialize(env,a)
    ds=dataset(env,a,tmp_path,'region,amount\nx,7.25\nx,2.25\n')
    task=spec(a['workspace'],ds);source=run(env,a,ds,task);drain(env)
    body={'task':task,'scenario_group':'observed-live-task','split':'train','source_kind':'verified_run',
        'source_run_id':source['id'],'reference':'Verified run with independent action postconditions',
        'expected_status':'verified','expected_rows':[{'region':'x','value':'9.50'}]}
    registered=call(env,a,'POST',path(a,'cases'),body,201)
    from backend.app.services.adaptive_jobs import training_rows
    with env['api']() as db:
        access=bind(db,a['user'],a['workspace'])
        x,y,snapshot,_=training_rows(db,access,[registered['id']])
        assert len(x)==1 and y==[1] and snapshot[0]['case_id']==registered['id']
    # The live verified output is usable for training, never an untouched final label.
    call(env,a,'POST',path(a,'cases'),{**body,'split':'final'},422)
    call(env,a,'POST',path(a,'cases'),{**body,'source_kind':'domain_reviewed','source_run_id':None,'split':'final'},409)
    final,_=numeric_case(env,a,tmp_path,'final',92)
    call(env,a,'POST',path(a,'replays'),{'case_ids':[final],'idempotency_key':uuid4().hex},409)
    outcome=call(env,a,'GET',path(a,'decisions'))['items'][0]['outcome']
    with env['api']() as db:
        bind(db,a['user'],a['workspace'])
        with pytest.raises(Exception,match='Immutable action evidence'):
            db.execute(text("UPDATE adaptive_outcomes SET content='{}' WHERE id=:id"),{'id':outcome['id']})
