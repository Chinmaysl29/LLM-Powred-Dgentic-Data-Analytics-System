"""Synthetic skill/scorer/interpretation tests with independent numeric oracles."""
from copy import deepcopy
from decimal import Decimal
import json
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pandas as pd
import pytest

from backend.app.schemas.learning import Budget,TaskSpec
from backend.app.schemas.adaptive import TrainingRequest
from backend.app.services.adaptive_skills import (FEATURES,catalog,context,diagnose,eligible,feature_vector,
    fixture_definition,fixture_task,numeric_skill,relational_skill,test_skill as run_skill_tests)
from backend.app.services.adaptive_selector import JsonScorer,fit_models
from backend.app.services.adaptive_routing import RepairRouter,relational_analysis
from backend.app.services.adaptive_interpretation import interpret
from backend.app.services.learning_engine import digest,execute,frame_hash


def numeric_task(workspace=None):
    value=fixture_task(workspace or uuid4()).model_dump(mode='json')
    value['datasets']=value['datasets'][:1];value['relationships']=[];value['objective']='Total amount'
    value['definition_refs']=[];value['metrics']=[{'column':'amount','aggregation':'sum','missing':'reject','definition_ref':None}]
    return TaskSpec.model_validate(value)


def test_approved_catalog_independent_checks_and_join_285_reuse_event_exclusion():
    workspace=uuid4();skills=catalog(workspace)
    assert all(run_skill_tests(skill)['passed'] for skill in skills)
    task=fixture_task(workspace)
    frames={'orders':pd.DataFrame({'order_id':['A','B'],'amount':['100','200']}),
            'refunds':pd.DataFrame({'order_id':['A','A'],'refund':['10','5']})}
    naive=frames['orders'].merge(frames['refunds'],on='order_id',how='left')
    assert sum(Decimal(str(v)) for v in naive['amount'])-sum(Decimal(str(v)) for v in naive['refund'].dropna())==385
    before={k:frame_hash(v) for k,v in frames.items()}
    ctx=context(task,frames);diagnosis=diagnose(ctx,frames)
    assert diagnosis.category=='join_fan_out' and diagnosis.established
    assert 'unique_refund_join' not in {s.skill_id for s in eligible(skills,ctx,frames,diagnosis)}
    router=RepairRouter(task,frames,skills)
    result=relational_analysis(task,frames,fixture_definition(task),router,Budget())
    assert result['status']=='verified' and result['answer']['rows']==[{'value':285}]
    assert router.records[0]['selected_skill']=='refunds_per_order'
    assert before=={k:frame_hash(v) for k,v in frames.items()}
    other={'orders':pd.DataFrame({'order_id':['C','D'],'amount':['300','400']}),
           'refunds':pd.DataFrame({'order_id':['C','C','D'],'refund':['25','75','10']})}
    reused=relational_analysis(task,other,fixture_definition(task),RepairRouter(task,other,skills),Budget())
    assert reused['answer']['rows']==[{'value':590}]
    event_task=fixture_task(workspace,events=True);event_context=context(event_task,frames)
    event_skills=eligible(skills,event_context,frames,diagnose(event_context,frames))
    assert {s.implementation for s in event_skills}=={'refund_event_count'}
    events=relational_analysis(event_task,frames,{},RepairRouter(event_task,frames,skills),Budget())
    assert events['answer']['rows']==[{'value':2}]


def test_numeric_skills_reject_lossy_precision_without_harming_baseline():
    task=numeric_task();skills=catalog(task.workspace_id);frame=pd.DataFrame({'amount':['1234567890123456.12','1.10']})
    exact=next(s for s in skills if s.implementation=='decimal_exact')
    fast=next(s for s in skills if s.implementation=='decimal_vector_checked')
    assert numeric_skill(exact,task,frame).success
    assert not numeric_skill(fast,task,frame).success
    router=RepairRouter(task,{'orders':frame},skills)
    result=execute(task,frame,{},Budget(),repair_router=router)
    assert result['status']=='verified' and result['repairs']==1
    assert router.records[0]['selector']=='rules-memory-v1'
    assert set(router.records[0]['eligible_candidates'][0])=={'skill_id','version','implementation_hash'}
    assert not {'gold','outcome','label','expected_rows'} & set(FEATURES)


def test_eligibility_revocation_workspace_and_unsupported_recipes():
    task=numeric_task();frames={'orders':pd.DataFrame({'amount':['1']})};ctx=context(task,frames)
    skills=catalog(task.workspace_id);skill=next(s for s in skills if s.implementation=='decimal_exact')
    revoked=skill.model_copy(update={'lifecycle':'revoked'})
    assert eligible([revoked],ctx,frames,diagnose(ctx,frames))==[]
    foreign=skill.model_copy(update={'workspace_id':uuid4()})
    assert eligible([foreign],ctx,frames,diagnose(ctx,frames))==[]
    assert eligible(skills,ctx,frames,diagnose(ctx,frames),remaining=0)==[]
    unknown=skill.model_copy(update={'implementation_hash':'0'*64})
    assert eligible([unknown],ctx,frames,diagnose(ctx,frames))==[]


@pytest.fixture(scope='module')
def trained():
    task=numeric_task();skills=[s for s in catalog(task.workspace_id) if s.implementation.startswith('decimal_')]
    matrices=[]
    for offset in (0,100):
        x=[];y=[]
        for i in range(24):
            high=i%2==0
            values=[f'{1234567890123000+i+offset}.12']*(2+i%5) if high else [f'{i+offset+1}.25']*(2+i%5)
            frame=pd.DataFrame({'amount':values});frames={'orders':frame};ctx=context(task,frames);di=diagnose(ctx,frames)
            for skill in skills:
                x.append(feature_vector(ctx,skill,frames,di));y.append(int(numeric_skill(skill,task,frame).success))
        matrices.append((x,y))
    bundles,measurements=fit_models(*matrices[0],*matrices[1],{'kind':'synthetic-unit-pilot'},
        [s.implementation_hash for s in skills],max_epochs=45)
    return task,skills,matrices,bundles,measurements


def test_real_linear_and_mlp_weights_train_only_scaler_and_safe_roundtrip(trained):
    task,skills,matrices,bundles,measurements=trained
    assert set(bundles)=={'linear','mlp'} and measurements['training_seconds']>0
    for bundle in bundles.values():
        assert not bundle['evaluation']['all_weights_zero']
        assert np.allclose(bundle['preprocessing']['mean'],np.mean(matrices[0][0],axis=0))
        scorer=JsonScorer(json.loads(json.dumps(bundle)),digest(bundle))
        assert np.isfinite(scorer.logits(matrices[1][0])).all()
        assert bundle['evaluation']['parameter_count']>len(FEATURES)
        assert bundle['calibration_status']=='unavailable'
        assert bundle['evaluation']['train_action_log_loss']<measurements['zero_logit_action_loss']
    assert len(bundles['linear']['weights'])==1 and len(bundles['mlp']['weights'])==3


def test_loading_changed_embeddings_corruption_and_cold_start_fall_back(trained):
    task,skills,matrices,bundles,_=trained
    changed=deepcopy(bundles['mlp']);changed['embedding_version']='different'
    with pytest.raises(ValueError):
        JsonScorer(changed)
    corrupted=deepcopy(bundles['linear']);corrupted['weights'][0][0][0]=float('nan')
    with pytest.raises(ValueError):
        JsonScorer(corrupted)
    with pytest.raises(ValueError):
        JsonScorer(bundles['linear'],'0'*64)
    frame=pd.DataFrame({'amount':['5.25']});router=RepairRouter(task,{'orders':frame},skills,'active',corrupted,'broken')
    result=execute(task,frame,{},repair_router=router)
    assert result['status']=='verified' and router.records[0]['fallback_reason']=='MODEL_INCOMPATIBLE_OR_COLD_START'
    assert router.records[0]['selector']=='rules-memory-v1'


@pytest.mark.asyncio
async def test_frozen_provider_context_is_validated_and_does_not_execute_tools():
    task=numeric_task();frames={'orders':pd.DataFrame({'amount':['1']})}
    class Provider:
        def __init__(self,payload):self.payload=payload;self.calls=0
        async def ainvoke(self,messages):
            self.calls+=1
            assert 'authorized_profiles' in messages[-1].content
            assert 'Never change workspace' in messages[0].content
            return SimpleNamespace(content=json.dumps(self.payload),usage_metadata={'input_tokens':10,'output_tokens':10})
    provider=Provider(task.model_dump(mode='json'))
    response=await interpret(task,frames,{},True,provider)
    assert provider.calls==1 and response['interpretation_status']=='proposal_requires_user_confirmation'
    poisoned=task.model_dump(mode='json');poisoned['workspace_id']=str(uuid4())
    rejected=await interpret(task,frames,{},True,Provider(poisoned))
    assert rejected['interpretation_status']=='baseline_fallback'
    assert rejected['problem_context']['task']['workspace_id']==str(task.workspace_id)
    class FailedProvider:
        async def ainvoke(self,messages):
            raise ConnectionError('Injected provider transport failure')
    failed=await interpret(task,frames,{},True,FailedProvider())
    assert failed['interpretation_status']=='baseline_fallback' and failed['usage']['logical_calls']==1


def test_training_contract_rejects_label_leakage_and_undeclared_gates():
    with pytest.raises(ValueError):
        TrainingRequest(train_case_ids=['a','b'],development_case_ids=['c','d'],final_case_ids=['a','e'],idempotency_key='x')


def test_diagnosis_requires_observed_schema_and_authorized_semantic_evidence():
    task=fixture_task(uuid4());frames={'orders':pd.DataFrame({'order_id':['A'],'amount':['100']}),
        'refunds':pd.DataFrame({'order_id':['A'],'refund':['5']})}
    changed=task.model_copy(update={'units':'EUR','currency':'EUR'})
    units=diagnose(context(changed,frames),frames,definitions=fixture_definition(task))
    assert units.category=='unit_mismatch' and units.established
    assert units.evidence[0]['defined_units']=='USD'
    metric=task.metrics[0].model_copy(update={'aggregation':'mean'})
    changed=task.model_copy(update={'metrics':[metric]})
    assert diagnose(context(changed,frames),frames,definitions=fixture_definition(task)).category=='aggregation_mismatch'
    assert diagnose(context(task,frames),frames,definitions={}).category=='ambiguous_definition'
    missing={'orders':frames['orders'].drop(columns=['amount']),'refunds':frames['refunds']}
    schema=diagnose(context(task,missing),missing)
    assert schema.category=='stale_schema' and schema.evidence[0]['missing_columns']==['amount']
