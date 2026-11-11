"""Eligible-first routing, with shadow decisions and action-specific evidence."""
from datetime import datetime, timezone
import time
from uuid import uuid4

from backend.app.schemas.adaptive import DecisionRecord
from backend.app.services.adaptive_skills import (FEATURE_VERSION, baseline_score, context, diagnose,
    eligible, feature_vector, numeric_skill, relational_skill)
from backend.app.services.adaptive_selector import JsonScorer
from backend.app.services.learning_engine import digest


class RepairRouter:
    def __init__(self,task,frames,manifests,mode='collection',bundle=None,model_id=None,
                 before_decision=None,after_outcome=None,recheck=None,lessons=None):
        self.task=task;self.frames=frames;self.manifests=manifests;self.mode=mode
        self.bundle=bundle;self.model_id=model_id;self.before_decision=before_decision
        self.after_outcome=after_outcome;self.recheck=recheck;self.lessons=lessons or []
        self.records=[];self.outcomes=[];self.current={}

    def choose(self,frames=None,remaining=2,actions=None):
        frames=frames or self.frames
        ctx=context(self.task,frames);diagnosis=diagnose(ctx,frames)
        manifests=self.manifests;model_allowed=True;fallback=None
        if self.recheck:
            manifests,model_allowed=self.recheck()
        candidates=eligible(manifests,ctx,frames,diagnosis,remaining)
        # Callers pass actual action hashes separately; this list is a local guard
        # against selecting the same implementation twice for one failure.
        tried={r['selected_implementation_hash'] for r in self.records}
        candidates=[s for s in candidates if s.implementation_hash not in tried]
        if not candidates:
            return None
        features={s.skill_id:feature_vector(ctx,s,frames,diagnosis,remaining) for s in candidates}
        scores={s.skill_id:baseline_score(s,self.lessons) for s in candidates};shadow={};selector='rules-memory-v1'
        scorer=None
        if self.mode in {'shadow','active'}:
            if self.bundle and model_allowed:
                try:
                    scorer=JsonScorer(self.bundle)
                    learned={s.skill_id:scorer.score(ctx,s,features[s.skill_id])['score'] for s in candidates}
                    if self.mode=='shadow':
                        shadow=learned
                    else:
                        scores=learned;selector=scorer.name
                except (ValueError,KeyError,TypeError,OverflowError):
                    fallback='MODEL_INCOMPATIBLE_OR_COLD_START'
            else:
                fallback='MODEL_UNAVAILABLE_OR_POLICY_CHANGED'
        chosen=sorted(candidates,key=lambda s:(-scores[s.skill_id],s.skill_id))[0]
        record=DecisionRecord(context_version=ctx.version,feature_version=FEATURE_VERSION,
            context_hash=digest(ctx.model_dump(mode='json')),
            eligible_candidates=[{'skill_id':s.skill_id,'version':s.version,'implementation_hash':s.implementation_hash} for s in candidates],
            selected_skill=chosen.skill_id,selected_version=chosen.version,selector=selector,model_id=self.model_id,
            scores=scores,shadow_scores=shadow,fallback_reason=fallback,decided_at=datetime.now(timezone.utc),
            remaining_repairs=remaining,selection_probability=1.0)
        payload=record.model_dump(mode='json');payload['diagnosis']=diagnosis.model_dump(mode='json')
        payload['selected_implementation_hash']=chosen.implementation_hash
        payload['source_hash']=digest({k:ctx.quality_findings[k]['source_hash'] for k in frames})
        decision_id=self.before_decision(payload,features) if self.before_decision else str(uuid4())
        payload['id']=decision_id;self.records.append(payload);self.current[decision_id]=(chosen,frames)
        return chosen,payload

    def perform(self,choice,frame=None,definitions=None):
        skill,record=choice
        if self.recheck:
            current,model_allowed=self.recheck()
            if not any(s.skill_id==skill.skill_id and s.version==skill.version and s.implementation_hash==skill.implementation_hash for s in current):
                raise PermissionError('Selected skill revoked before execution')
            if not record['selector'].startswith('rules-memory') and not model_allowed:
                raise ValueError('SELECTOR_POLICY_CHANGED_BEFORE_EXECUTION')
        if skill.implementation.startswith('decimal_'):
            result=numeric_skill(skill,self.task,frame)
        else:
            result=relational_skill(skill,self.task,self.frames,definitions or {})
        outcome={'decision_id':record['id'],'action_id':skill.skill_id,'action_version':skill.version,
            'result':'success' if result.success else 'failure',
            'label_status':'positive' if result.success else 'negative',
            'label_policy':'independent-action-postconditions-v1','evidence':result.checks,
            'failure_category':None if result.success else record['diagnosis']['category'],
            'usage':{'provider':'none','cost_usd':0,'latency_ms':result.latency_ms},
            'parent_run_id':None,'source_kind':'live'}
        if self.after_outcome:
            self.after_outcome(record,outcome)
        self.outcomes.append(outcome)
        return result


def relational_analysis(task,frames,definitions,router,budget,repairs_used=0,actions=None,reservations=None,
                        deadline=None,on_repair=None):
    from backend.app.services.learning_engine import ENGINE_VERSION, RUNTIME_IDENTITY, profile
    started=time.perf_counter();actions=list(actions or []);attempts=[]
    deadline=deadline or time.monotonic()+budget.deadline_seconds
    while (repairs_used<budget.max_repairs or reservations) and time.monotonic()<deadline:
        choice=router.choose(remaining=max(1,budget.max_repairs-repairs_used),actions=actions)
        if choice is None:
            break
        skill,decision=choice;action={'type':'relationship_recipe','skill_id':skill.skill_id,'version':skill.version}
        key=digest(action);source_hash=digest({k:profile(v)['source_hash'] for k,v in frames.items()})
        replay=next((r for r in (reservations or []) if r['action_hash']==key and r['input_hash']==source_hash),None)
        if key in actions and not replay:
            break
        if not replay:
            repairs_used+=1;actions.append(key)
            if on_repair:
                on_repair(repairs_used,actions,action,source_hash)
        result=router.perform(choice,definitions=definitions)
        attempts.append({'number':repairs_used,'skill_id':skill.skill_id,'version':skill.version,
            'decision_id':decision['id'],'outcome':'succeeded' if result.success else 'failed','checks':result.checks})
        if result.success:
            return {'status':'verified','error_code':None,'validations':result.checks,'profile':profile(frames[task.datasets[0].dataset_id]),
                'task':task.model_dump(mode='json'),'plan':{'operations':[],'relationship_recipe':skill.skill_id,
                    'input_versions':[r.model_dump() for r in task.datasets],'lineage':[f'{r.dataset_id}@{r.version}' for r in task.datasets]},
                'answer':result.frame,'result_hash':digest(result.frame),'repairs':repairs_used,'actions':actions,
                'applied_lessons':[],'repair_attempts':attempts,'runtime_identity':RUNTIME_IDENTITY,
                'latency_ms':(time.perf_counter()-started)*1000,'usage':{'provider':'none','calls':0,'input_tokens':0,'output_tokens':0,'cost_usd':0},
                'numeric_confidence':None,'confidence_reason':'Numeric confidence unavailable; routing scores are not answer confidence.',
                'limitations':['The trusted order/refund grain and sign conventions define this descriptive calculation.',
                               'Skill addition is a capability improvement, not evidence of learned selector improvement.']}
    return {'status':'insufficient_evidence','error_code':'REPAIR_BUDGET_EXHAUSTED' if repairs_used>=budget.max_repairs else 'NO_ELIGIBLE_REPAIR',
        'validations':attempts[-1]['checks'] if attempts else [],'profile':profile(frames[task.datasets[0].dataset_id]),
        'task':task.model_dump(mode='json'),'plan':{'operations':[]},'answer':None,'result_hash':None,
        'repairs':repairs_used,'actions':actions,'applied_lessons':[],'repair_attempts':attempts,'numeric_confidence':None,
        'latency_ms':(time.perf_counter()-started)*1000,'usage':{'provider':'none','calls':0,'input_tokens':0,'output_tokens':0,'cost_usd':0},
        'confidence_reason':'Numeric confidence unavailable.','limitations':['No unverified join answer was published.']}
