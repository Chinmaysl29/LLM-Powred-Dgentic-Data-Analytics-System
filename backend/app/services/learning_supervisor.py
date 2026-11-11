"""Verified learning authority integrated with existing run, storage and job abstractions."""
from datetime import timedelta, timezone
import json
import time
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError

from backend.app.core.workspace_authorization import authorize_workspace, authorize_bound_dataset
from backend.app.models.analysis_run import AnalysisRun, AnalysisArtifact
from backend.app.models.background_job import DurableJob, utcnow
from backend.app.models.dataset import Dataset
from backend.app.models.learning import (BusinessDefinition, LearningAttempt, LearningAudit,
    LearningBundle, LearningControl, LearningFeedback, LearningLesson, LearningRevision,
    LearningRun, LearningVerification)
from backend.app.schemas.learning import (Budget, DefinitionRequest, LessonCandidate, Operation,
    Scope, StageResult, TaskSpec, Usage, LESSON_TRANSITIONS, transition)
from backend.app.services.learning_engine import (ENGINE_VERSION, RUNTIME_IDENTITY, digest, execute, infer_task,
    frame_hash, profile, schema_hash, scrub, verify_operation)


def error(status, code, message):
    raise HTTPException(status, detail={'code': code, 'message': message})


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def bind(db, actor, workspace, permission='read'):
    access = authorize_workspace(db, actor, workspace, permission)
    if db.bind.dialect.name == 'postgresql':
        db.execute(text("SELECT set_config('app.actor_id', :a, true), set_config('app.workspace_id', :w, true)"),
                   {'a': str(access.actor_id), 'w': str(access.workspace_id)})
    return access


def audit(db, access, action, entity_id, **summary):
    db.add(LearningAudit(workspace_id=access.workspace_id, actor_id=access.actor_id,
                         action=action, entity_id=entity_id, summary=summary))


def definitions(db, workspace):
    result = {}
    for row in db.scalars(select(BusinessDefinition).where(BusinessDefinition.workspace_id == workspace, BusinessDefinition.active.is_(True))):
        if row.content_hash != digest(row.content):
            continue
        try:
            DefinitionRequest.model_validate(row.content)
        except ValueError:
            continue
        result[f'{row.key}@{row.version}'] = row.content
    return result


def add_definition(db, access, request):
    content = request.model_dump(mode='json')
    old = db.scalar(select(BusinessDefinition).where(BusinessDefinition.workspace_id == access.workspace_id,
        BusinessDefinition.key == request.key, BusinessDefinition.version == request.version))
    if old:
        if old.content_hash != digest(content):
            error(409, 'IMMUTABLE_DEFINITION', 'Create a new version to change a business definition.')
        return old
    row = BusinessDefinition(workspace_id=access.workspace_id, key=request.key, version=request.version,
        actor_id=access.actor_id, content=content, content_hash=digest(content))
    db.add(row); db.flush()
    audit(db, access, 'definition_confirmed', row.id, reference=f'{row.key}@{row.version}')
    return row


def control(db, workspace):
    row = db.get(LearningControl, workspace)
    return {'mode': row.mode if row else 'disabled', 'active_bundle_id': row.active_bundle_id if row else None,
        'previous_bundle_id': row.previous_bundle_id if row else None,
        'rollout_percent': row.rollout_percent if row else 0, 'generation': row.generation if row else 0,
        'engine_version': ENGINE_VERSION, 'numeric_confidence': None,
        'confidence_reason': 'Numeric confidence unavailable: calibration evidence has not been collected.'}


def create_learning_run(db, access, run, task=None, budget=None):
    if task:
        if (task.workspace_id != access.workspace_id or task.objective != run.query or
            (task.datasets[0].dataset_id, task.datasets[0].version) != (run.dataset_id, run.version_number)):
            error(422, 'TASK_SCOPE_MISMATCH', 'Task must match the authorized run, query and dataset version.')
        from backend.app.models.dataset_version import DatasetVersion
        for ref in task.datasets[1:]:
            authorize_bound_dataset(db,access,ref.dataset_id)
            if not db.scalar(select(DatasetVersion.version_id).where(DatasetVersion.dataset_id==ref.dataset_id,DatasetVersion.version_number==ref.version)):
                error(404,'VERSION_NOT_FOUND','Relationship input version not found.')
    config = control(db, access.workspace_id)
    # Stable allocation does not depend on feedback/outcomes.
    selected = int(digest([str(access.actor_id), run.id])[:8], 16) % 100 < config['rollout_percent']
    mode = config['mode']
    if mode == 'limited' and not selected:
        mode = 'collection'
    row = LearningRun(id=run.id, workspace_id=access.workspace_id, owner_id=access.actor_id,
        task=task.model_dump(mode='json') if task else None, budget=(budget or Budget()).model_dump(mode='json'),
        mode=mode, bundle_id=config['active_bundle_id'])
    db.add(row); db.flush()
    return row


def lesson_eligible(db, lesson, task, signature, cutoff, allowed_states=('active',)):
    if not lesson or lesson.workspace_id != task.workspace_id or lesson.state not in allowed_states:
        return False
    now = utcnow()
    if aware(lesson.expires_at) <= now or aware(lesson.created_at) > aware(cutoff):
        return False
    if not lesson.verified_at or aware(lesson.verified_at) > aware(cutoff) or lesson.invalid_reason:
        return False
    if lesson.state == 'active':
        activation = db.scalar(select(LearningRevision.id).where(LearningRevision.lesson_id == lesson.id,
            LearningRevision.workspace_id == task.workspace_id, LearningRevision.number == lesson.revision,
            LearningRevision.state == 'active', LearningRevision.created_at <= cutoff))
        if not activation:
            return False
    if lesson.schema_hash != signature or lesson.content_hash != digest(lesson.content):
        return False
    try:
        parsed = LessonCandidate.model_validate(lesson.content)
    except ValueError:
        return False
    if parsed.type != 'technical' or parsed.scope.task_type != task.task_type or parsed.scope.workspace_id != task.workspace_id:
        return False
    if parsed.scope.schema_hash != signature or aware(parsed.expires_at) <= now:
        return False
    if parsed.scope.dataset_id and parsed.scope.dataset_id != task.datasets[0].dataset_id:
        return False
    if set(parsed.scope.definition_refs) != set(task.definition_refs):
        return False
    if task.metrics[0].column != parsed.correction.column:
        return False
    if not set(parsed.scope.definition_refs) <= set(definitions(db, task.workspace_id)):
        return False
    source = db.get(Dataset, lesson.source_dataset_id)
    source_run = db.get(LearningRun, lesson.source_run_id)
    if not source or source.status in {'deleted', 'archived', 'DELETED'} or not source_run or source_run.state != 'succeeded':
        return False
    verified = db.scalar(select(LearningVerification).where(LearningVerification.lesson_id == lesson.id,
        LearningVerification.workspace_id == task.workspace_id, LearningVerification.content_hash == lesson.content_hash,
        LearningVerification.passed.is_(True)))
    return verified is not None


def retrieve(db, task, signature, cutoff, snapshot=None, allowed_states=('active',)):
    query = select(LearningLesson).where(LearningLesson.workspace_id == task.workspace_id,
        LearningLesson.schema_hash == signature, LearningLesson.state.in_(allowed_states),
        LearningLesson.created_at <= cutoff).order_by(LearningLesson.created_at, LearningLesson.id).limit(100)
    candidates = db.scalars(query).all()
    refs = {r['id']: r for r in snapshot} if snapshot is not None else None
    selected, used = [], 0
    for row in candidates:
        if refs is not None and (row.id not in refs or refs[row.id]['content_hash'] != row.content_hash):
            continue
        if not lesson_eligible(db, row, task, signature, cutoff, allowed_states):
            continue
        # There is no free-form lesson prompt. Only validated operator metadata is loaded.
        payload = {'lesson_id': row.id, 'revision': row.revision, 'content_hash': row.content_hash,
                   'correction': row.content['correction'], 'conditions': row.content['conditions'],
                   'scope': row.content['scope'], 'exceptions': row.content['exceptions']}
        cost = len(json.dumps(payload).encode())
        if used + cost > 4096 or len(selected) >= 5:
            break
        selected.append(payload); used += cost
    # Contradictions fail closed. With the one approved operator, duplicate rules agree.
    actions = {}
    conflicts = set()
    for item in selected:
        key = item['correction']['column']
        if key in actions and actions[key] != item['correction']:
            conflicts.add(key)
        actions[key] = item['correction']
    return [r for r in selected if r['correction']['column'] not in conflicts]


def optional_memory(db, task, signature, cutoff, snapshot=None):
    """Authorization and mandatory evidence are outside this optional savepoint."""
    try:
        with db.begin_nested():
            return retrieve(db, task, signature, cutoff, snapshot), []
    except (SQLAlchemyError, ValueError, TypeError, KeyError):
        return [], ['Optional memory unavailable; validated baseline used.']


def prepare(db, access, run, frame):
    row = db.get(LearningRun, run.id)
    if row is None:
        row = create_learning_run(db, access, run)
    previous = db.scalars(select(LearningAttempt).where(LearningAttempt.workspace_id == access.workspace_id,
        LearningAttempt.run_id == run.id)).all()
    if any(a.evidence['versions'].get('policy_hash') != RUNTIME_IDENTITY['policy_hash'] for a in previous):
        error(409, 'RUN_POLICY_VERSION_CHANGED', 'Supervisor code changed during this run; start a new versioned run.')
    if row.started_at is None:
        row.started_at = utcnow()
    if row.state == 'queued':
        row.state = transition(row.state, 'running')
    if row.task is None:
        row.task = infer_task(access.workspace_id, run.dataset_id, run.version_number, run.query, frame).model_dump(mode='json')
    task = TaskSpec.model_validate(row.task)
    signature = schema_hash(frame)
    fingerprint = frame_hash(frame)
    if row.source_hash and row.source_hash != fingerprint:
        error(409, 'PINNED_SOURCE_CHANGED', 'Pinned input values changed during execution; create a new dataset version.')
    row.source_hash = fingerprint
    if row.schema_hash and row.schema_hash != signature:
        error(409, 'PINNED_SCHEMA_CHANGED', 'Pinned source schema changed during execution.')
    if row.schema_hash is None:
        row.schema_hash = signature
        # The release approves the supervisor policy. Ordinary tenant-local lessons
        # follow verification/applicability, without a global prompt/model release.
        # Every run still freezes its own compatible memory references and cutoff;
        # paired evaluations use an explicitly frozen bundle instead.
        lessons, degraded = optional_memory(db, task, signature, row.memory_cutoff) if row.mode in {'limited', 'shadow'} else ([], [])
        if degraded:
            audit(db, access, 'memory_degraded', row.id, limitations=degraded)
        row.lesson_snapshot = [{'id': l['lesson_id'], 'content_hash': l['content_hash'], 'revision': l['revision']} for l in lessons]
    return row, task


def record_attempt(db, access, run_id, stage, number, outcome, started_at, status=None, error_code=None):
    old = db.scalar(select(LearningAttempt).where(LearningAttempt.workspace_id == access.workspace_id,
        LearningAttempt.run_id == run_id, LearningAttempt.stage == stage, LearningAttempt.number == number))
    if old and old.evidence['status'] != 'running':
        return  # Completed attempt evidence survives explicit retries unchanged.
    attempt_id = old.id if old else str(uuid4())
    if old:
        started_at = old.evidence['started_at']
    evidence = StageResult(run_id=run_id, stage_id=f'{run_id}:{stage}', attempt_id=attempt_id,
        status=status or ('succeeded' if outcome.get('status') == 'verified' else 'waiting_for_input'),
        input_artifacts=[f'dataset:{r["dataset_id"]}@{r["version"]}' for r in outcome['task']['datasets']] if outcome.get('task') else [],
        output_artifacts=[] if status == 'running' else [f'analysis:{run_id}:stage:{stage}'], validations=outcome.get('validations', []),
        versions={'supervisor': ENGINE_VERSION, 'policy_hash':RUNTIME_IDENTITY['policy_hash'], 'task': digest(outcome.get('task'))}, started_at=started_at,
        finished_at=None if status == 'running' else utcnow(), usage=Usage.model_validate(outcome.get('usage') or dict(provider='none', calls=0,input_tokens=0,output_tokens=0,cost_usd=0)),
        error_category=error_code or outcome.get('error_code')).model_dump(mode='json')
    if old:
        old.evidence = evidence
    else:
        db.add(LearningAttempt(id=attempt_id, workspace_id=access.workspace_id, run_id=run_id,
                               stage=stage, number=number, evidence=evidence))


def supervisor_stage(db, access, run, frame, number, row, task, reserve_repair=None, repair_router=None, frames=None):
    """Returns the real persisted stage content; no provider response is trusted."""
    defs = definitions(db, access.workspace_id)
    if number == 1:
        from backend.app.services.learning_engine import task_checks
        if task.relationships:
            from backend.app.services.adaptive_skills import relationship_checks
            checks = relationship_checks(task,frames,defs)
        else:
            checks = task_checks(task, frame, defs)
        blocked = any(c['outcome'] != 'pass' for c in checks if c['severity'] == 'error')
        return {'task': row.task, 'validations': checks, 'assumptions': task.assumptions,
                'status': 'insufficient_evidence' if blocked else 'verified', 'error_code': 'TASK_CONTRACT_UNRESOLVED' if blocked else None}, blocked
    if number in {2, 3, 4}:
        return {'profile': profile(frame), 'task': row.task, 'status': 'verified',
                'scope': 'Data quality profile only; no business error, deduplication or causal conclusion asserted.'}, False
    if number == 5:
        from backend.app.services.learning_engine import task_checks
        # Resume deadline and budget are anchored to the original run, not delivery attempts.
        remaining = Budget.model_validate(row.budget).deadline_seconds - (utcnow() - aware(row.started_at)).total_seconds()
        lessons, degraded = optional_memory(db, task, row.schema_hash, row.memory_cutoff, snapshot=row.lesson_snapshot) if row.mode in {'limited','shadow'} else ([], [])
        # Recheck the active control on every application: rollback overrides frozen snapshots.
        current = control(db, access.workspace_id)
        apply = row.mode == 'limited' and current['mode'] == 'limited' and current['active_bundle_id'] == row.bundle_id
        def reserve(count, actions, action, input_hash):
            if reserve_repair:
                reserve_repair(count, actions, action, input_hash)
            row.repairs = count; row.actions = actions
        if task.relationships:
            from backend.app.services.adaptive_routing import relational_analysis
            result = relational_analysis(task,frames,defs,repair_router,Budget.model_validate(row.budget),row.repairs,row.actions,
                row.repair_reservations,time.monotonic()+remaining,reserve)
        else:
            result = execute(task, frame, defs, Budget.model_validate(row.budget), lessons if apply else [],
                row.repairs, row.actions, deadline=time.monotonic() + remaining, on_repair=reserve, replay_reservations=row.repair_reservations,repair_router=repair_router)
        if repair_router:
            result['decisions']=repair_router.records
        result['shadow_lessons'] = [l['lesson_id'] for l in lessons] if row.mode == 'shadow' else []
        result['limitations'].extend(degraded)
        row.outcome = result; row.plan = result['plan']; row.applied_lessons = result['applied_lessons']
        row.repairs = result['repairs']; row.actions = result['actions']; row.error_code = result['error_code']
        return result, result['status'] != 'verified'
    if not row.outcome or row.outcome['status'] != 'verified':
        error(409, 'UNVERIFIED_RESULT', 'A verified result is required for publication.')
    result = row.outcome
    if digest(result['answer']) != result['result_hash']:
        error(409, 'ARTIFACT_INTEGRITY_FAILED', 'Result integrity verification failed.')
    if number == 6:
        return {'task': row.task, 'status': 'verified', 'answer': result['answer'], 'result_hash': result['result_hash'],
                'scope': 'Chart, report JSON and narrative share this exact result version.'}, False
    return {'task': row.task, 'status': 'verified', 'claims': result['answer']['claims'],
            'result_hash': result['result_hash'], 'limitations': result['limitations'],
            'numeric_confidence': None, 'confidence_reason': result['confidence_reason']}, False


def enqueue_extraction(db, row):
    if row.mode == 'disabled':
        return
    key = f'extract:{row.id}'
    existing = db.scalar(select(DurableJob).where(DurableJob.workspace_id == row.workspace_id,
        DurableJob.kind == 'lesson_extract', DurableJob.idempotency_key == key))
    if not existing:
        db.add(DurableJob(workspace_id=row.workspace_id, owner_id=row.owner_id, kind='lesson_extract',
            idempotency_key=key, payload={'run_id': row.id}, retry_eligible=True))


def submit_feedback(db, access, run, request):
    from backend.app.models.workspace import Workspace
    db.scalar(select(Workspace.id).where(Workspace.id == access.workspace_id).with_for_update())
    learning = db.get(LearningRun, run.id)
    if not learning or control(db, access.workspace_id)['mode'] == 'disabled':
        error(409, 'COLLECTION_DISABLED', 'An authorized manager must enable collection before feedback is retained.')
    payload = request.model_dump(mode='json'); payload['comment'] = scrub(payload['comment'])
    old = db.scalar(select(LearningFeedback).where(LearningFeedback.workspace_id == access.workspace_id,
        LearningFeedback.actor_id == access.actor_id, LearningFeedback.idempotency_key == request.idempotency_key))
    if old:
        if old.run_id != run.id or old.payload != payload:
            error(409, 'IDEMPOTENCY_CONFLICT', 'Feedback key already represents another request.')
        return old
    if request.evidence_artifact:
        artifact = db.get(AnalysisArtifact, request.evidence_artifact)
        if not artifact or artifact.run_id != run.id:
            error(404, 'ARTIFACT_NOT_FOUND', 'Evidence artifact not found for this run.')
    row = LearningFeedback(workspace_id=access.workspace_id, actor_id=access.actor_id, run_id=run.id,
        idempotency_key=request.idempotency_key, payload=payload)
    db.add(row); db.flush()
    db.add(DurableJob(workspace_id=access.workspace_id, owner_id=access.actor_id, kind='lesson_extract',
        idempotency_key=f'feedback:{row.id}', payload={'run_id': run.id, 'feedback_id': row.id}, retry_eligible=True))
    return row


def append_revision(db, access, lesson, reason):
    db.add(LearningRevision(workspace_id=access.workspace_id, lesson_id=lesson.id, number=lesson.revision,
        state=lesson.state, content=lesson.content, content_hash=lesson.content_hash,
        actor_id=access.actor_id, reason=scrub(reason)))


async def execute_extraction_job(store, job):
    from backend.app.services.analysis_run_service import authorize_run, fence
    with store.sessions() as db, db.begin():
        fence(db, job)
        run = authorize_run(db, job['payload']['run_id'], job['owner_id'], 'write')
        access = bind(db, job['owner_id'], run.workspace_id, 'write')
        row = db.scalar(select(LearningRun).where(LearningRun.id == run.id).with_for_update())
        if not row or control(db, access.workspace_id)['mode'] == 'disabled':
            return {'status': 'skipped', 'reason': 'COLLECTION_DISABLED'}
        actions = []
        feedback = db.get(LearningFeedback, job['payload']['feedback_id']) if job['payload'].get('feedback_id') else None
        if feedback:
            if feedback.run_id != run.id or feedback.workspace_id != access.workspace_id:
                error(404, 'FEEDBACK_NOT_FOUND', 'Feedback not found.')
            if feedback.payload['category'] != 'calculation':
                return {'status': 'feedback_only', 'reason': 'This feedback category cannot establish a technical numeric correction; domain definitions and preferences require their own authorized contracts.'}
            if feedback.payload.get('correction'):
                actions = [feedback.payload['correction']]
        elif row.outcome and row.outcome['status'] == 'verified':
            actions = row.outcome['plan']['operations']
        ids = []
        for action in actions:
            # Only the allowlisted representation correction is extracted. No feedback prose or dataset values.
            action = Operation.model_validate(action).model_dump(mode='json')
            candidate = LessonCandidate(type='technical', conditions=['Canonical signed decimal text in the named numeric measure.', 'Exact schema and definition versions match.'],
                correction=action, exceptions=['Reject separators, currency symbols, exponents, leading zero ambiguity or nonfinite values.',
                    'Never impute missing values, delete duplicate-looking rows or change metric meaning.'],
                scope=Scope(workspace_id=access.workspace_id, schema_hash=row.schema_hash, definition_refs=row.task['definition_refs'], task_type='descriptive', dataset_id=None),
                provenance=[f'run:{run.id}', f'dataset:{run.dataset_id}@{run.version_number}'] + ([f'feedback:{feedback.id}'] if feedback else []),
                verification_evidence=[], state='candidate', expires_at=utcnow()+timedelta(days=90),
                invalidation_rules=['Source deletion or invalidation', 'Schema or definition mismatch', 'Revocation', 'Expiry'])
            content = candidate.model_dump(mode='json')
            # Stable even when expiry/provenance timestamps differ; rejected proposals stay deduplicated.
            key = digest([run.id, candidate.type, action, candidate.scope.model_dump(mode='json')])
            old = db.scalar(select(LearningLesson).where(LearningLesson.workspace_id == access.workspace_id, LearningLesson.dedup_key == key))
            if old:
                ids.append(old.id); continue
            lesson = LearningLesson(workspace_id=access.workspace_id, source_run_id=run.id, source_dataset_id=run.dataset_id,
                dedup_key=key, schema_hash=row.schema_hash, content=content, content_hash=digest(content), expires_at=candidate.expires_at)
            db.add(lesson); db.flush(); append_revision(db, access, lesson, 'Structured candidate; feedback is not proof.')
            ids.append(lesson.id)
            audit(db, access, 'candidate_created', lesson.id, source_run=run.id)
        return {'status': 'collected', 'lesson_ids': ids, 'note': 'Candidates require independent verification and authorized review.'}


async def execute_dataset_cleanup_job(store, job):
    """Tombstone-first deletion: durable, replay-safe physical cleanup."""
    import asyncio
    return await asyncio.to_thread(_cleanup_dataset, store, job)


def _cleanup_dataset(store, job):
    from backend.app.core.config import get_settings
    from backend.app.core.workspace_authorization import dataset_workspace_bindings
    from backend.app.services.analysis_run_service import fence
    from backend.app.services.storage_service import StorageService
    dataset_id = str(UUID(job['payload']['dataset_id']))
    with store.sessions() as db, db.begin():
        fence(db, job)
        access = bind(db, job['owner_id'], job['workspace_id'], 'write')
        row = db.scalar(select(Dataset).join(dataset_workspace_bindings,
            dataset_workspace_bindings.c.dataset_id == Dataset.dataset_id).where(Dataset.dataset_id == dataset_id,
            Dataset.owner_id == str(access.actor_id), dataset_workspace_bindings.c.workspace_id == access.workspace_id))
        if not row or row.status != 'deleted':
            error(404, 'DELETED_SOURCE_NOT_FOUND', 'Deleted source not found.')
        original = row.file_path
        file_type = row.file_type
    storage = StorageService(get_settings())
    try:
        storage.delete_dataset(dataset_id)
        if original:
            storage.delete_file(original)
    except OSError:
        raise ConnectionError('Source cleanup temporarily unavailable') from None
    # Supervisor lessons have no vector entries. Existing document vectors are
    # inaccessible after the authoritative tombstone; removal can be retried.
    if file_type in {'pdf','txt','text','md','markdown'}:
        try:
            from backend.app.services.rag_service import get_pipeline
            get_pipeline()._store.delete(document_id=dataset_id)
        except Exception:
            raise ConnectionError('Document vector cleanup temporarily unavailable') from None
    with store.sessions() as db, db.begin():
        fence(db, job)
        access = bind(db, job['owner_id'], job['workspace_id'], 'write')
        audit(db, access, 'source_physical_cleanup', dataset_id, status='complete')
    return {'dataset_id': dataset_id, 'status':'deleted'}


def review_lesson(db, access, lesson_id, request):
    lesson = db.scalar(select(LearningLesson).where(LearningLesson.id == lesson_id,
        LearningLesson.workspace_id == access.workspace_id).with_for_update())
    if not lesson:
        error(404, 'LESSON_NOT_FOUND', 'Lesson not found.')
    if lesson.state != request.expected_state:
        error(409, 'STALE_REVIEW', 'Lesson status changed; reload before reviewing.')
    target = {'verify':'verified', 'activate':'active', 'reject':'rejected', 'revoke':'revoked', 'expire':'expired'}[request.action]
    try:
        transition(lesson.state, target, LESSON_TRANSITIONS)
    except ValueError:
        error(409, 'ILLEGAL_TRANSITION', 'This lesson lifecycle transition is not permitted.')
    if target in {'verified', 'active'}:
        if aware(lesson.expires_at) <= utcnow() or lesson.invalid_reason:
            error(409, 'LESSON_INVALID', 'Expired or invalidated lesson cannot be verified or applied.')
        if lesson.content['type'] != 'technical':
            error(409, 'DOMAIN_CONFIRMATION_REQUIRED', 'Only supported technical corrections can be activated by this verifier.')
        source = db.get(LearningRun, lesson.source_run_id)
        dataset = db.get(Dataset, lesson.source_dataset_id)
        if not source or source.state != 'succeeded' or not dataset or dataset.status in {'deleted','archived','DELETED'}:
            error(409, 'SOURCE_NOT_VERIFIED', 'A successful source run and live source dataset are required.')
        if not set(lesson.content['scope']['definition_refs']) <= set(definitions(db, access.workspace_id)):
            error(409, 'DEFINITION_INVALID', 'A source definition has been invalidated.')
        if target == 'verified':
            if lesson.content['correction'] not in (source.plan or {}).get('operations', []):
                error(409, 'SOURCE_CORRECTION_NOT_VALIDATED', 'This proposed correction was not independently validated in the source run.')
            evidence = verify_operation(lesson.content['correction'])
            if not evidence['passed']:
                error(409, 'VERIFICATION_FAILED', 'Independent correction checks failed.')
            db.add(LearningVerification(workspace_id=access.workspace_id, lesson_id=lesson.id, content_hash=lesson.content_hash,
                verifier_version='scaled-integer-reference-v1', passed=True, evidence=evidence))
            lesson.verified_at = utcnow()
        else:
            proof = db.scalar(select(LearningVerification).where(LearningVerification.lesson_id == lesson.id,
                LearningVerification.workspace_id == access.workspace_id, LearningVerification.content_hash == lesson.content_hash,
                LearningVerification.passed.is_(True)))
            if not proof:
                error(409, 'VERIFICATION_REQUIRED', 'Independent verification must precede activation.')
    lesson.state = target; lesson.revision += 1
    if target in {'revoked','expired'}:
        lesson.invalid_reason = scrub(request.reason)[:200]
        disable_affected_release(db, access, lesson.id)
    append_revision(db, access, lesson, request.reason)
    audit(db, access, f'lesson_{target}', lesson.id, revision=lesson.revision, reason=scrub(request.reason))
    return lesson


def disable_affected_release(db, access, lesson_id):
    cfg = db.get(LearningControl, access.workspace_id)
    bundle = db.get(LearningBundle, cfg.active_bundle_id) if cfg and cfg.active_bundle_id else None
    if bundle and any(r['id'] == lesson_id for r in bundle.content['lessons']):
        cfg.mode = 'shadow'; cfg.rollout_percent = 0; cfg.generation += 1; cfg.updated_at = utcnow()
        audit(db, access, 'automatic_release_suspension', bundle.id, reason='Lesson invalidation overrides release snapshot.')


def suspend_policy(db, access, reason):
    cfg = db.scalar(select(LearningControl).where(LearningControl.workspace_id == access.workspace_id).with_for_update())
    if cfg and cfg.mode == 'limited':
        cfg.mode = 'shadow'; cfg.rollout_percent = 0; cfg.generation += 1; cfg.updated_at = utcnow()
        audit(db, access, 'mandatory_invariant_suspension', str(access.workspace_id), reason=reason)


def invalidate_source(db, access, dataset_id=None, definition_ref=None):
    from backend.app.services.adaptive_service import invalidate
    invalidate(db,access,dataset_id=dataset_id,definition_ref=definition_ref)
    lessons = db.scalars(select(LearningLesson).where(LearningLesson.workspace_id == access.workspace_id,
        LearningLesson.state.in_(['candidate','verified','active'])).with_for_update()).all()
    count = 0
    for lesson in lessons:
        if (dataset_id and lesson.source_dataset_id == dataset_id) or (definition_ref and definition_ref in lesson.content['scope']['definition_refs']):
            lesson.state = 'revoked'; lesson.invalid_reason = 'Authoritative source invalidated'; lesson.revision += 1
            append_revision(db, access, lesson, lesson.invalid_reason); disable_affected_release(db, access, lesson.id); count += 1
    audit(db, access, 'source_invalidation', dataset_id or 'definition', definition_ref=definition_ref, lessons=count)
    return count


def freeze_bundle(db, access):
    cutoff = utcnow()
    refs = []
    for row in db.scalars(select(LearningLesson).where(LearningLesson.workspace_id == access.workspace_id,
        LearningLesson.state == 'active', LearningLesson.expires_at > cutoff).order_by(LearningLesson.id)):
        if row.content_hash == digest(row.content):
            refs.append({'id': row.id, 'revision': row.revision, 'content_hash': row.content_hash})
    content = {'engine': ENGINE_VERSION, 'runtime_identity':RUNTIME_IDENTITY, 'lessons': refs, 'configuration': 'validated-baseline-v1', 'memory_cutoff': cutoff.isoformat()}
    bundle = LearningBundle(workspace_id=access.workspace_id, content=content, content_hash=digest(content))
    db.add(bundle); db.flush(); audit(db, access, 'bundle_frozen', bundle.id, content_hash=bundle.content_hash)
    return bundle


def learning_status(db, access, run):
    row = db.get(LearningRun, run.id)
    if not row:
        return {'run_id': run.id, 'state': 'unavailable', 'numeric_confidence': None}
    attempts = db.scalars(select(LearningAttempt).where(LearningAttempt.workspace_id == access.workspace_id,
        LearningAttempt.run_id == run.id).order_by(LearningAttempt.stage, LearningAttempt.number)).all()
    return {'run_id': run.id, 'state': row.state, 'mode': row.mode, 'bundle_id': row.bundle_id,
        'memory_cutoff': row.memory_cutoff, 'lesson_snapshot': row.lesson_snapshot,
        'task': row.task, 'plan': row.plan, 'outcome': row.outcome, 'repairs': row.repairs, 'budget': row.budget,
        'attempts': [a.evidence for a in attempts], 'error_code': row.error_code,
        'numeric_confidence': None, 'confidence_reason': 'Numeric confidence unavailable: independent calibration evidence is missing.'}
