"""Approved executable skills and evidence-based diagnosis; no generated code."""
from dataclasses import dataclass
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
import math
import re
import time
from typing import Any

import pandas as pd

from backend.app.schemas.adaptive import Diagnosis, ProblemContext, SkillManifest
from backend.app.schemas.learning import TaskSpec
from backend.app.services.learning_engine import (RUNTIME_IDENTITY, REGISTRY, aggregate, answer_object,
    check, digest, exact_decimal, frame_hash, profile, schema_hash, task_checks, transform,
    validate_join, validate_training_split, verify_operation)

FEATURE_VERSION='task-action-features-v1'
EMBEDDING_VERSION='unused-frozen-embeddings'
SOURCE_HASH=sha256(Path(__file__).read_bytes()).hexdigest()
FEATURES=['log_rows','log_columns','missing_fraction','canonical_fraction','high_precision_fraction',
    'max_fractional_places','duplicate_right_fraction','remaining_repairs','numeric_failure','join_failure',
    'method_exact','method_vector','method_preaggregate','method_direct','method_events','method_recipe']
RECIPE=['sum_refunds_by_order','validated_order_join','signed_subtract','aggregate_result','validate_result']
IMPLEMENTATIONS=['decimal_exact','decimal_vector_checked','refunds_per_order','unique_refund_join',
    'refund_event_count','join_cardinality_check','date_format_check','chart_result_check','approved_recipe']


def implementation_hash(key):
    return digest([key,SOURCE_HASH,RUNTIME_IDENTITY['policy_hash']])


def catalog(workspace):
    manifests=[]
    for key in IMPLEMENTATIONS:
        if key=='approved_recipe':
            continue
        manifests.append(SkillManifest(skill_id=key,version=1,implementation=key,
            implementation_hash=implementation_hash(key),inputs='ProblemContext+authorized-dataframes@1',
            outputs='SkillResult+ValidationResult@1',
            preconditions=['Active authenticated workspace','Pinned compatible schema and explicit task semantics',
                           'Approved implementation hash and sufficient remaining resources'],
            permitted_tools=RECIPE if key in {'refunds_per_order','unique_refund_join'} else [key],
            resource_limits={'max_rows':500000,'max_input_bytes':50000000,'max_seconds':30,'max_repairs':2},
            stages=[5],workspace_id=workspace,definition_refs=[],task_types=['descriptive'],
            tests=[f'isolated:{key}:v1'],lifecycle='active',source='repository_reviewed'))
    return manifests


def context(task,frames,source='explicit_contract',provider=None):
    return ProblemContext(task=task,schema_versions={key:schema_hash(frame) for key,frame in frames.items()},
        entities=list(frames),grain=task.grain,quality_findings={key:profile(frame) for key,frame in frames.items()},
        constraints=['Original data immutable','No SQL/generated code/network tools','At most two repairs total',
                     'Predictive tasks require separate leakage-controlled workflow'],
        acceptance_checks=task.success_criteria,interpretation_source=source,provider=provider,
        limitations=['Semantic definitions require an authorized owner.','No final-answer probability is inferred from routing.'])


def diagnose(ctx,frames,error_code=None,definitions=None):
    task=ctx.task;metric=task.metrics[0]
    evidence=[];category='unknown';established=False;observation=error_code or 'Task preflight'
    causes=[];checks=[]
    mapping={'TASK_CONTRACT_UNRESOLVED':'ambiguous_definition','SCHEMA_MISMATCH':'stale_schema',
        'MISSING_METRIC_VALUES':'missing_data','NONFINITE_METRIC':'numeric_representation',
        'DATE_OR_FILTER_INVALID':'invalid_query','REPAIR_BUDGET_EXHAUSTED':'budget_exhausted',
        'PROVIDER_UNAVAILABLE':'provider_failure','AUTHORIZATION_DENIED':'permission_denial',
        'MANDATORY_VALIDATION_FAILED':'integrity_failure'}
    if error_code in mapping:
        category=mapping[error_code];evidence=[{'safe_error_code':error_code}];established=True
    if task.ambiguity:
        category='ambiguous_definition';established=True;observation='Task declares unresolved material ambiguity'
        evidence=[{'ambiguity_count':len(task.ambiguity)}];checks=['Resolve the selected definition and grain with the current user.']
    elif task.relationships:
        rel=task.relationships[0];left=frames[rel.left_dataset_id];right=frames[rel.right_dataset_id]
        missing=[key for key,frame in [(rel.left_key,left),(rel.order_amount,left),(rel.right_key,right),(rel.refund_amount,right)] if key not in frame]
        if missing:
            category='stale_schema';established=True;observation='Required relationship columns are absent'
            evidence=[{'missing_columns':missing}]
        elif right[rel.right_key].duplicated().any():
            category='join_fan_out';established=True;observation='Refund input has multiple events per order'
            evidence=[{'orders':len(left),'refund_events':len(right),'repeated_right_keys':int(right[rel.right_key].duplicated().sum()),
                       'requested_grain':task.grain,'purpose':rel.purpose}]
            causes=['Joining order amounts directly to refund events repeats order measures.']
            checks=['Verify unique order keys','Reconcile per-order refund sums and source order totals',
                    'Preserve event rows when the task asks for refund-event counts']
    else:
        frame=next(iter(frames.values()))
        fields=set(task.dimensions+[f.column for f in task.filters])|({metric.column} if metric.column!='__records__' else set())
        if not fields<=set(frame):
            category='stale_schema';established=True;observation='Requested columns do not exist in pinned schema'
            evidence=[{'missing_columns':sorted(fields-set(frame))}]
        elif metric.column in frame and frame[metric.column].isna().any() and metric.missing=='reject':
            category='missing_data';established=True;observation='Missing metric observations require clarification'
            evidence=[{'missing':int(frame[metric.column].isna().sum())}]
        elif metric.column in frame and any(isinstance(v,str) for v in frame[metric.column].dropna()):
            category='numeric_representation';established=True;observation='Numeric contract has text representations'
            evidence=[{'dtype':str(frame[metric.column].dtype),'non_null':int(frame[metric.column].count())}]
            causes=['Values may be canonical decimal text or may contain unsupported units/separators.']
            checks=['Lossless decimal round-trip','Missingness preserved','No currency or unit inference']
    # Semantic mismatches require an explicit authorized reference, not a guess
    # from a column name. These take precedence over representation repairs.
    refs=(set(task.definition_refs)|({metric.definition_ref} if metric.definition_ref else set())) if definitions is not None else set()
    definitions=definitions or {}
    for ref in sorted(refs):
        definition=definitions.get(ref)
        if not definition:
            category='ambiguous_definition';established=True
            observation='Referenced business definition is unavailable'
            evidence=[{'definition_ref':ref}];causes=[]
            checks=['Select an active authorized definition before execution.']
            continue
        if task.units!=definition['units'] or task.currency!=definition['currency']:
            category='unit_mismatch';established=True;observation='Task units disagree with the selected business definition'
            evidence=[{'definition_ref':ref,'requested_units':task.units,'defined_units':definition['units'],
                       'requested_currency':task.currency,'defined_currency':definition['currency']}]
            causes=[];checks=['Confirm units with the definition owner; no implicit conversion is permitted.']
            break
        if metric.aggregation!=definition['metric']['aggregation']:
            category='aggregation_mismatch';established=True;observation='Task aggregation disagrees with the selected business definition'
            evidence=[{'definition_ref':ref,'requested_aggregation':metric.aggregation,
                       'defined_aggregation':definition['metric']['aggregation']}]
            causes=[];checks=['Resolve the metric aggregation before computing a result.']
            break
    if not checks:
        checks=['Run the category-specific code validator; a hypothesis is not proof.']
    return Diagnosis(observed_failure=observation,category=category,evidence=evidence,
        proposed_causes=causes,distinguishing_checks=checks,established=established)


def eligible(manifests,ctx,frames,diagnosis,remaining=2):
    if remaining<=0 or ctx.task.task_type!='descriptive' or ctx.task.ambiguity:
        return []
    result=[];task=ctx.task
    for item in manifests:
        try:
            skill=SkillManifest.model_validate(item)
        except ValueError:
            continue
        if skill.workspace_id!=task.workspace_id or skill.lifecycle!='active' or skill.implementation_hash!=implementation_hash(skill.implementation):
            continue
        if not set(skill.definition_refs)<=set(task.definition_refs) or 5 not in skill.stages:
            continue
        if any(len(frame)>skill.resource_limits['max_rows'] for frame in frames.values()):
            continue
        key=skill.implementation
        if key=='approved_recipe' and skill.recipe!=RECIPE:
            continue
        if key.startswith('decimal_'):
            if diagnosis.category!='numeric_representation' or task.relationships or task.metrics[0].column not in next(iter(frames.values())):
                continue
        elif key in {'refunds_per_order','unique_refund_join','approved_recipe','refund_event_count'}:
            if not task.relationships:
                continue
            rel=task.relationships[0]
            if key=='refund_event_count' and rel.purpose!='refund_event_count':
                continue
            if key!='refund_event_count' and rel.purpose!='order_net_revenue':
                continue
            right=frames[rel.right_dataset_id]
            if key=='unique_refund_join' and (rel.right_key not in right or right[rel.right_key].duplicated().any()):
                continue
        else:
            continue  # Validators are usable catalog tools, not numerical repair candidates.
        result.append(skill)
    return result


def feature_vector(ctx,skill,frames,diagnosis,remaining=2):
    primary=frames[ctx.task.datasets[0].dataset_id];metric=ctx.task.metrics[0]
    values=primary[metric.column].dropna().tolist() if metric.column in primary else []
    canonical=high=places=0
    for value in values:
        try:
            dec=exact_decimal(value);canonical+=1
            high+=int(len(dec.as_tuple().digits)>15)
            places=max(places,max(0,-dec.as_tuple().exponent))
        except (ValueError,InvalidOperation):
            pass
    duplicate=0
    if ctx.task.relationships:
        rel=ctx.task.relationships[0];right=frames[rel.right_dataset_id]
        if rel.right_key in right and len(right):
            duplicate=float(right[rel.right_key].duplicated().mean())
    method=skill.implementation
    return [math.log1p(len(primary)),math.log1p(len(primary.columns)),
        float(primary[metric.column].isna().mean()) if metric.column in primary and len(primary) else 0,
        canonical/max(1,len(values)),high/max(1,len(values)),places/8,duplicate,remaining/2,
        float(diagnosis.category=='numeric_representation'),float(diagnosis.category=='join_fan_out'),
        float(method=='decimal_exact'),float(method=='decimal_vector_checked'),float(method=='refunds_per_order'),
        float(method=='unique_refund_join'),float(method=='refund_event_count'),float(method=='approved_recipe')]


def baseline_score(skill,lessons=None):
    key=skill.implementation
    score={'decimal_exact':1,'decimal_vector_checked':.5,'refunds_per_order':1,'unique_refund_join':.9,
           'refund_event_count':1,'approved_recipe':.95}.get(key,0)
    if key=='decimal_exact' and lessons:
        score+=.1
    return score


@dataclass
class SkillResult:
    success: bool
    frame: pd.DataFrame | dict[str, Any] | None
    checks: list[dict]
    error: str | None
    latency_ms: float


def numeric_skill(skill,task,frame):
    started=time.perf_counter();column=task.metrics[0].column;before=frame_hash(frame)
    try:
        if skill.implementation=='decimal_exact':
            result=transform(frame,{'type':'exact_decimal_parse','column':column})
        elif skill.implementation=='decimal_vector_checked':
            result=frame.copy(deep=True)
            converted=pd.to_numeric(frame[column],errors='raise')
            result[column]=converted.map(lambda value:value if pd.isna(value) else Decimal(str(value)))
            if any(exact_decimal(a)!=b for a,b in zip(frame[column],result[column]) if not pd.isna(a)):
                raise ValueError('LOSSLESS_ROUNDTRIP_FAILED')
        else:
            raise ValueError('UNSUPPORTED_NUMERIC_SKILL')
        valid=len(result)==len(frame) and result.index.equals(frame.index) and frame_hash(frame)==before
        evidence=[check('skill_numeric_roundtrip',valid,'Every original decimal value, missing mask, row and index is preserved.')]
        return SkillResult(valid,result,evidence,None if valid else 'INVARIANT_FAILED',(time.perf_counter()-started)*1000)
    except (ValueError,TypeError,InvalidOperation,OverflowError):
        return SkillResult(False,None,[check('skill_numeric_roundtrip',False,'Approved numeric repair failed exact representation postconditions.')],
                           'NUMERIC_REPRESENTATION_REJECTED',(time.perf_counter()-started)*1000)


def relationship_checks(task,frames,definitions):
    rel=task.relationships[0];left=frames[rel.left_dataset_id];right=frames[rel.right_dataset_id]
    required={rel.left_key,rel.order_amount};right_required={rel.right_key,rel.refund_amount}
    checks=[check('relationship_schema',required<=set(left) and right_required<=set(right),'Explicit order/refund columns exist in both pinned inputs.')]
    if checks[0]['outcome']!='pass':
        return checks
    checks.append(check('order_key_unique',not left[rel.left_key].isna().any() and not left[rel.left_key].duplicated().any(),'Order identifier is complete and unique.'))
    checks.append(check('refund_key_complete',not right[rel.right_key].isna().any(),'Every refund identifies an order.'))
    checks.append(check('refund_references',set(right[rel.right_key])<=set(left[rel.left_key]),'No orphan refund keys are silently dropped.'))
    checks.append(check('relationship_grain_fields',set(task.dimensions)<=set(left) and rel.left_key!=rel.order_amount and rel.right_key!=rel.refund_amount,
                        'Declared order grouping fields exist and identifiers are distinct from amounts.'))
    checks.append(check('relationship_semantics',not task.filters and task.date_range is None and not task.ambiguity,
                        'This recipe supports explicit whole-input semantics without unresolved filter/date reinterpretation.'))
    # Verify the same metric/definition policy using only a declared output schema.
    output_columns={task.metrics[0].column:pd.Series(dtype=object),**{d:pd.Series(dtype=object) for d in task.dimensions}}
    checks.extend(task_checks(task,pd.DataFrame(output_columns),definitions))
    valid=(task.metrics[0].aggregation=='sum' and bool(task.metrics[0].definition_ref)) if rel.purpose=='order_net_revenue' else task.metrics[0].aggregation=='count' and not task.dimensions
    checks.append(check('requested_grain',valid,'Net revenue requires order-grain sum and a trusted definition; event count preserves refund events.'))
    return checks


def relational_skill(skill,task,frames,definitions):
    started=time.perf_counter();checks=relationship_checks(task,frames,definitions)
    if any(c['severity']=='error' and c['outcome']!='pass' for c in checks):
        return SkillResult(False,None,checks,'RELATIONSHIP_CONTRACT_UNRESOLVED',(time.perf_counter()-started)*1000)
    rel=task.relationships[0];left=frames[rel.left_dataset_id];right=frames[rel.right_dataset_id]
    before={k:frame_hash(v) for k,v in frames.items()}
    try:
        if rel.purpose=='refund_event_count':
            output=pd.DataFrame({'__records__':[1]*len(right)})
            reference=len(right)
        else:
            if skill.implementation=='unique_refund_join' and right[rel.right_key].duplicated().any():
                raise ValueError('JOIN_FAN_OUT')
            orders=left.copy(deep=True);refunds=right.copy(deep=True)
            orders[rel.order_amount]=orders[rel.order_amount].map(exact_decimal)
            refunds[rel.refund_amount]=refunds[rel.refund_amount].map(exact_decimal)
            if (refunds[rel.refund_amount]<0).any():
                raise ValueError('REFUND_SIGN_CONTRACT_UNRESOLVED')
            helper='_adaptive_refund_value'
            if helper in orders:
                raise ValueError('RESERVED_RELATIONSHIP_FIELD')
            if skill.implementation=='unique_refund_join':
                aggregated=refunds[[rel.right_key,rel.refund_amount]].rename(columns={rel.refund_amount:helper})
            else:
                aggregated=refunds.groupby(rel.right_key,dropna=False)[rel.refund_amount].sum().rename(helper).reset_index()
            aggregated=aggregated.rename(columns={rel.right_key:rel.left_key})
            checks.append(validate_join(orders,aggregated,[rel.left_key]))
            output=orders.merge(aggregated,on=rel.left_key,how='left',validate='one_to_one',sort=False)
            output.index=orders.index
            # A missing joined event is structural absence under the explicit
            # no-event contract; source refund amounts themselves cannot be null.
            output[task.metrics[0].column]=[amount-(Decimal(0) if pd.isna(refund) else refund)
                for amount,refund in zip(output[rel.order_amount],output[helper])]
            output=output.drop(columns=[helper])
            # Independent linear-time row iteration, no groupby or merged total.
            reference_refunds=defaultdict(lambda:Decimal(0))
            for record in right.to_dict('records'):
                reference_refunds[record[rel.right_key]]+=Decimal(str(record[rel.refund_amount]))
            expected=[]
            for record in left.to_dict('records'):
                refunded=reference_refunds[record[rel.left_key]]
                expected.append(Decimal(str(record[rel.order_amount]))-refunded)
            reference=sum(expected,Decimal(0))
            if list(output[task.metrics[0].column])!=expected:
                raise ValueError('ORDER_RECONCILIATION_FAILED')
        if task.dimensions and len(output[task.dimensions].drop_duplicates())>1000:
            raise ValueError('RESULT_LIMIT_EXCEEDED')
        rows=aggregate(task,output)
        answer=answer_object(task,rows,digest(before))
        checks.extend(REGISTRY.validate({'answer':answer,'task':task,'work':output,'raw':output,'raw_hash':frame_hash(output)}))
        total=sum((Decimal(str(r['value'])) for r in rows),Decimal(0))
        checks.append(check('independent_relationship_total',total==reference,'Independent order/refund iteration reconciles the final total.'))
        checks.append(check('both_raw_inputs_immutable',before=={k:frame_hash(v) for k,v in frames.items()},'Both source versions remain unchanged.'))
        passed=all(c['outcome']=='pass' for c in checks if c['severity']=='error')
        return SkillResult(passed,answer,checks,None if passed else 'INVARIANT_FAILED',(time.perf_counter()-started)*1000)
    except (ValueError,TypeError,InvalidOperation,KeyError):
        checks.append(check('relationship_execution',False,'Approved relationship recipe could not establish its contract.'))
        return SkillResult(False,None,checks,'RELATIONSHIP_VALIDATION_FAILED',(time.perf_counter()-started)*1000)


def fixture_task(workspace,left_id='orders',right_id='refunds',events=False):
    return TaskSpec(workspace_id=workspace,objective='Count refund events' if events else 'Net revenue',task_type='descriptive',
        datasets=[{'dataset_id':left_id,'version':1},{'dataset_id':right_id,'version':1}],
        metrics=[{'column':'__records__' if events else 'net_amount','aggregation':'count' if events else 'sum','missing':'reject',
                  'definition_ref':None if events else 'net_revenue@1'}],dimensions=[],grain='refund event' if events else 'one order',
        filters=[],date_range=None,timezone='UTC',units='events' if events else 'USD',currency=None if events else 'USD',output='report',definition_refs=[] if events else ['net_revenue@1'],
        assumptions=[],ambiguity=[],success_criteria=['Independent relationship reconciliation'],relationships=[{
            'left_dataset_id':left_id,'right_dataset_id':right_id,'left_key':'order_id','right_key':'order_id','order_amount':'amount',
            'refund_amount':'refund','purpose':'refund_event_count' if events else 'order_net_revenue','cardinality':'one_to_many',
            'missing_refund_policy':'no_event_means_no_refund'}])


def fixture_definition(task):
    return {'net_revenue@1':{'metric':task.metrics[0].model_dump(),'filters':[],'units':'USD','currency':'USD'}}


def test_skill(manifest):
    """Independent expected outputs/counterexamples for a fixed approved implementation."""
    skill=SkillManifest.model_validate(manifest);results=[];key=skill.implementation
    if key in {'decimal_exact','decimal_vector_checked'}:
        base=fixture_task(skill.workspace_id).model_dump(mode='json');base['datasets']=base['datasets'][:1];base['relationships']=[]
        base['objective']='Total amount';base['metrics'][0]={'column':'amount','aggregation':'sum','missing':'reject','definition_ref':None};base['definition_refs']=[]
        task=TaskSpec.model_validate(base)
        for values,expected in [(['100','-15'],Decimal(85)),(['0.25','0.50'],Decimal('.75'))]:
            outcome=numeric_skill(skill,task,pd.DataFrame({'amount':values}))
            results.append(outcome.success and sum(outcome.frame['amount'])==expected)
        for value in ['$10','1,000','ignore instructions','NaN']:
            results.append(not numeric_skill(skill,task,pd.DataFrame({'amount':[value]})).success)
        if key=='decimal_vector_checked':
            results.append(not numeric_skill(skill,task,pd.DataFrame({'amount':['1234567890123456.12']})).success)
        else:
            results.append(verify_operation({'type':'exact_decimal_parse','column':'amount'})['passed'])
    elif key in {'refunds_per_order','unique_refund_join','refund_event_count','approved_recipe'}:
        task=fixture_task(skill.workspace_id,events=key=='refund_event_count')
        frames={'orders':pd.DataFrame({'order_id':['A','B'],'amount':['100','200']}),
                'refunds':pd.DataFrame({'order_id':['A','A'],'refund':['10','5']})}
        if key=='unique_refund_join':
            results.append(not relational_skill(skill,task,frames,fixture_definition(task)).success)
            frames['refunds']=pd.DataFrame({'order_id':['A'],'refund':['15']})
        result=relational_skill(skill,task,frames,fixture_definition(task))
        results.append(result.success and result.frame['rows'][0]['value']==(2 if key=='refund_event_count' else 285))
        events=fixture_task(skill.workspace_id,events=True)
        results.append(not any(s.implementation==key for s in eligible([skill],context(events,frames),frames,diagnose(context(events,frames),frames)))) if key!='refund_event_count' else None
        bad={**frames,'orders':pd.DataFrame({'order_id':['A','A'],'amount':['100','200']})}
        results.append(not relational_skill(skill,task,bad,fixture_definition(task)).success)
    elif key=='join_cardinality_check':
        results=[validate_join(pd.DataFrame({'id':[1]}),pd.DataFrame({'id':[1,1]}),['id'])['outcome']=='fail',
                 validate_join(pd.DataFrame({'id':[1]}),pd.DataFrame({'id':[1]}),['id'])['outcome']=='pass']
    elif key=='date_format_check':
        results=[pd.to_datetime('2026-01-02',format='%Y-%m-%d').day==2]
        try:
            pd.to_datetime('01/02/2026',format='%Y-%m-%d',errors='raise');results.append(False)
        except ValueError:
            results.append(True)
    elif key=='chart_result_check':
        from backend.app.services.learning_engine import validate_claims
        task=fixture_task(skill.workspace_id);answer=answer_object(task,[{'value':285}],'fixture')
        results.append(validate_claims({'task':task,'answer':answer})['outcome']=='pass')
        answer['chart'][0]['value']=385
        results.append(validate_claims({'task':task,'answer':answer})['outcome']=='fail')
    return {'passed':bool(results) and all(results),'checks':len(results),'results':results,
            'source':'synthetic independent constants and rejection counterexamples','implementation_hash':skill.implementation_hash,
            'limitations':['These tests establish only this bounded skill contract, not production effectiveness.']}
