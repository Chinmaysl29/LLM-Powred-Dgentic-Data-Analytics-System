"""Authenticated, workspace-scoped supervisor APIs. Capabilities enforced server-side."""
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import get_current_user
from backend.app.database.postgres import get_db_session
from backend.app.models.background_job import DurableJob, utcnow
from backend.app.models.learning import (BusinessDefinition, LearningAudit, LearningBundle,
    LearningCase, LearningControl, LearningEvaluation, LearningLesson, LearningRevision,
    LearningRun, LearningVerification)
from backend.app.schemas.learning import (CaseRequest, Contract, DefinitionRequest,
    EvaluationRequest, FeedbackRequest, ReviewRequest, LessonVersion)
from backend.app.services.analysis_run_service import authorize_run
from backend.app.services.learning_engine import digest
from backend.app.services.learning_evaluation import add_case, create_evaluation, release
from backend.app.services.learning_supervisor import (add_definition, audit, bind, control,
    error, freeze_bundle, invalidate_source, learning_status, review_lesson, submit_feedback)

router = APIRouter(prefix='/learning', tags=['Verified Learning Supervisor'])


def lesson_json(row):
    version = LessonVersion.model_validate({**row.content, 'state': row.state, 'lesson_id': row.id,
        'revision': row.revision, 'content_hash': row.content_hash}).model_dump(mode='json')
    return {'id': row.id, 'workspace_id': str(row.workspace_id), 'state': row.state,
        'revision': row.revision, 'content': row.content, 'version': version, 'content_hash': row.content_hash,
        'created_at': row.created_at, 'verified_at': row.verified_at, 'expires_at': row.expires_at,
        'invalid_reason': row.invalid_reason}


def evaluation_json(db, row):
    job = db.get(DurableJob, row.job_id)
    return {'id': row.id, 'state': row.state, 'manifest': row.manifest, 'result': row.result,
        'job_status': job.status, 'error_code': job.error_code, 'created_at': row.created_at}


@router.get('/controls')
def get_controls(workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = bind(db, user.id, workspace_id)
    return {**control(db, workspace_id), 'can_review': access.role in {'admin','owner'}}


class ControlRequest(Contract):
    mode: Literal['disabled', 'collection', 'shadow']
    expected_generation: int = Field(ge=0)


@router.put('/controls')
def update_controls(workspace_id: UUID, body: ControlRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = bind(db, user.id, workspace_id, 'manage')
    # Lock the workspace to serialize first creation as well as later updates.
    from backend.app.models.workspace import Workspace
    db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    cfg = db.get(LearningControl, workspace_id)
    if (cfg.generation if cfg else 0) != body.expected_generation:
        error(409, 'CONTROL_VERSION_CONFLICT', 'Feature controls changed; reload before saving.')
    if not cfg:
        cfg = LearningControl(workspace_id=workspace_id, actor_id=access.actor_id)
        db.add(cfg); db.flush()
    cfg.mode = body.mode; cfg.rollout_percent = 0; cfg.generation += 1; cfg.updated_at = utcnow(); cfg.actor_id = access.actor_id
    audit(db, access, 'mode_changed', str(workspace_id), mode=body.mode, generation=cfg.generation)
    db.commit()
    bind(db, user.id, workspace_id)
    return control(db, workspace_id)


@router.get('/runs')
def list_runs(workspace_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
              db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    bind(db, user.id, workspace_id)
    items = db.scalars(select(LearningRun).where(LearningRun.workspace_id == workspace_id,
        LearningRun.owner_id == user.id).order_by(LearningRun.memory_cutoff.desc()).offset(offset).limit(limit+1)).all()
    return {'items': [{'id': r.id, 'state': r.state, 'mode': r.mode, 'task': r.task, 'error_code': r.error_code} for r in items[:limit]],
            'next_offset': offset+limit if len(items) > limit else None}


@router.get('/runs/{run_id}')
def run_status(run_id: str, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    run = authorize_run(db, run_id, user.id)
    access = bind(db, user.id, run.workspace_id)
    return learning_status(db, access, run)


@router.post('/runs/{run_id}/feedback', status_code=201)
def feedback(run_id: str, body: FeedbackRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    run = authorize_run(db, run_id, user.id, 'write')
    access = bind(db, user.id, run.workspace_id, 'write')
    row = submit_feedback(db, access, run, body)
    result = {'id': row.id, 'status': 'feedback_saved', 'note': 'Feedback is not a verified numeric label.'}
    db.commit(); return result


@router.get('/runs/{run_id}/report')
def download_report(run_id: str, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    run = authorize_run(db, run_id, user.id)
    bind(db, user.id, run.workspace_id)
    row = db.get(LearningRun, run.id)
    if not row or row.state != 'succeeded' or not row.outcome or row.outcome['status'] != 'verified':
        error(409, 'VERIFIED_REPORT_UNAVAILABLE', 'A fully completed verified run is required for this export.')
    answer = row.outcome['answer']
    if digest(answer) != row.outcome['result_hash']:
        error(409, 'ARTIFACT_INTEGRITY_FAILED', 'Report integrity check failed.')
    payload = {'run_id': run.id, 'task': row.task, 'answer': answer, 'result_hash': row.outcome['result_hash'],
        'runtime_identity': row.outcome.get('runtime_identity'), 'memory_cutoff':row.memory_cutoff.isoformat(),
        'lesson_snapshot':row.lesson_snapshot, 'applied_lessons':row.applied_lessons,
        'validations': row.outcome['validations'], 'limitations': row.outcome['limitations'], 'numeric_confidence': None}
    return Response(json.dumps(payload, allow_nan=False, sort_keys=True), media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="verified-analysis-{UUID(run.id)}.json"',
                 'ETag': f'"{row.outcome["result_hash"]}"', 'Cache-Control': 'private, no-store'})


@router.get('/lessons')
def list_lessons(workspace_id: UUID, state: str | None = None, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    bind(db, user.id, workspace_id)
    query = select(LearningLesson).where(LearningLesson.workspace_id == workspace_id)
    if state:
        query = query.where(LearningLesson.state == state)
    items = db.scalars(query.order_by(LearningLesson.created_at.desc(), LearningLesson.id).offset(offset).limit(limit+1)).all()
    return {'items': [lesson_json(r) for r in items[:limit]], 'next_offset': offset+limit if len(items)>limit else None}


@router.get('/lessons/{lesson_id}')
def lesson_detail(lesson_id: str, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    bind(db, user.id, workspace_id)
    row = db.scalar(select(LearningLesson).where(LearningLesson.id == lesson_id, LearningLesson.workspace_id == workspace_id))
    if not row:
        error(404, 'LESSON_NOT_FOUND', 'Lesson not found.')
    result = {**lesson_json(row), 'revisions': [{'number': r.number, 'state': r.state, 'reason': r.reason, 'content_hash': r.content_hash}
        for r in db.scalars(select(LearningRevision).where(LearningRevision.lesson_id == lesson_id,
            LearningRevision.workspace_id == workspace_id).order_by(LearningRevision.number))],
        'verification_records': [{'id': v.id, 'passed': v.passed, 'evidence': v.evidence}
        for v in db.scalars(select(LearningVerification).where(LearningVerification.lesson_id == lesson_id,
            LearningVerification.workspace_id == workspace_id))]}
    result['version']['verification_evidence'] = [f'verification:{v["id"]}' for v in result['verification_records']]
    return result


@router.post('/lessons/{lesson_id}/review')
def review(lesson_id: str, workspace_id: UUID, body: ReviewRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = bind(db, user.id, workspace_id, 'manage')
    row = review_lesson(db, access, lesson_id, body)
    result = {**lesson_json(row), 'message': 'Verified lesson saved.' if row.state == 'verified' else f'Lesson {row.state}.'}
    db.commit(); return result


@router.get('/definitions')
def list_definitions(workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    bind(db, user.id, workspace_id)
    return [{'id': r.id, 'reference': f'{r.key}@{r.version}', 'active': r.active, 'content': r.content}
        for r in db.scalars(select(BusinessDefinition).where(BusinessDefinition.workspace_id == workspace_id).order_by(BusinessDefinition.key, BusinessDefinition.version).limit(100))]


@router.post('/definitions', status_code=201)
def create_definition(workspace_id: UUID, body: DefinitionRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = bind(db, user.id, workspace_id, 'manage')
    row = add_definition(db, access, body)
    result = {'id': row.id, 'reference': f'{row.key}@{row.version}', 'content_hash': row.content_hash}
    db.commit(); return result


@router.post('/definitions/{definition_id}/invalidate')
def invalidate_definition(definition_id: str, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = bind(db, user.id, workspace_id, 'manage')
    row = db.get(BusinessDefinition, definition_id)
    if not row or row.workspace_id != workspace_id:
        error(404, 'DEFINITION_NOT_FOUND', 'Definition not found.')
    row.active = False
    count = invalidate_source(db, access, definition_ref=f'{row.key}@{row.version}')
    db.commit(); return {'invalidated_lessons': count}


@router.post('/bundles', status_code=201)
def create_bundle(workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = bind(db, user.id, workspace_id, 'manage')
    row = freeze_bundle(db, access)
    result = {'id': row.id, 'content_hash': row.content_hash, 'content': row.content}
    db.commit(); return result


@router.get('/bundles')
def list_bundles(workspace_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    bind(db, user.id, workspace_id, 'manage')
    rows = db.scalars(select(LearningBundle).where(LearningBundle.workspace_id == workspace_id)
        .order_by(LearningBundle.created_at.desc()).offset(offset).limit(limit+1)).all()
    return {'items': [{'id': r.id, 'content_hash': r.content_hash, 'content': r.content} for r in rows[:limit]],
            'next_offset': offset+limit if len(rows)>limit else None}


@router.post('/cases', status_code=201)
def create_case(workspace_id: UUID, body: CaseRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = bind(db, user.id, workspace_id, 'manage')
    row = add_case(db, access, body)
    result = {'id': row.id, 'content_hash': row.content_hash, 'split': row.split}
    db.commit(); return result


@router.get('/cases')
def list_cases(workspace_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
               db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    bind(db, user.id, workspace_id, 'manage')
    rows = db.scalars(select(LearningCase).where(LearningCase.workspace_id == workspace_id)
        .order_by(LearningCase.created_at.desc()).offset(offset).limit(limit+1)).all()
    # Labels never returned on runtime analysis endpoints.
    return {'items': [{'id': r.id, 'split': r.split, 'scenario_group': r.scenario_group, 'content_hash': r.content_hash,
                       'dataset_version': r.content['dataset_version'], 'label_source': r.content['label_source']} for r in rows[:limit]],
            'next_offset': offset+limit if len(rows)>limit else None}


@router.post('/evaluations', status_code=202)
def queue_evaluation(workspace_id: UUID, body: EvaluationRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = bind(db, user.id, workspace_id, 'manage')
    row = create_evaluation(db, access, body)
    result = evaluation_json(db, row)
    db.commit(); return result


@router.get('/evaluations')
def list_evaluations(workspace_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                     db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    bind(db, user.id, workspace_id, 'manage')
    rows = db.scalars(select(LearningEvaluation).where(LearningEvaluation.workspace_id == workspace_id)
        .order_by(LearningEvaluation.created_at.desc()).offset(offset).limit(limit+1)).all()
    return {'items': [evaluation_json(db, r) for r in rows[:limit]], 'next_offset': offset+limit if len(rows)>limit else None}


@router.get('/evaluations/{evaluation_id}')
def get_evaluation(evaluation_id: str, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    bind(db, user.id, workspace_id, 'manage')
    row = db.get(LearningEvaluation, evaluation_id)
    if not row or row.workspace_id != workspace_id:
        error(404, 'EVALUATION_NOT_FOUND', 'Evaluation not found.')
    return evaluation_json(db, row)


class ReleaseRequest(Contract):
    evaluation_id: str
    expected_generation: int = Field(ge=0)
    rollout_percent: int = Field(ge=1, le=10)


@router.post('/release')
def create_release(workspace_id: UUID, body: ReleaseRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = bind(db, user.id, workspace_id, 'manage')
    release(db, access, body.evaluation_id, body.expected_generation, body.rollout_percent)
    db.commit(); bind(db, user.id, workspace_id)
    return control(db, workspace_id)


class RollbackRequest(Contract):
    expected_generation: int = Field(ge=0)


@router.post('/rollback')
def rollback(workspace_id: UUID, body: RollbackRequest, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = bind(db, user.id, workspace_id, 'manage')
    cfg = db.scalar(select(LearningControl).where(LearningControl.workspace_id == workspace_id).with_for_update())
    if not cfg or cfg.generation != body.expected_generation:
        error(409, 'CONTROL_VERSION_CONFLICT', 'Reload controls before rollback.')
    cfg.mode = 'shadow'; cfg.rollout_percent = 0; cfg.generation += 1; cfg.updated_at = utcnow()
    cfg.active_bundle_id, cfg.previous_bundle_id = cfg.previous_bundle_id, cfg.active_bundle_id
    audit(db, access, 'rollback_to_baseline', str(workspace_id), active_bundle_id=cfg.active_bundle_id)
    db.commit(); bind(db, user.id, workspace_id)
    return control(db, workspace_id)


@router.get('/monitor')
def monitor(workspace_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
            db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    bind(db, user.id, workspace_id, 'manage')
    rows = db.scalars(select(LearningAudit).where(LearningAudit.workspace_id == workspace_id)
        .order_by(LearningAudit.created_at.desc()).offset(offset).limit(limit+1)).all()
    jobs = db.scalars(select(DurableJob).where(DurableJob.workspace_id == workspace_id,
        DurableJob.kind.in_(['lesson_extract','learning_eval','dataset_cleanup']), DurableJob.status == 'FAILED').limit(50)).all()
    return {'items': [{'id': r.id, 'action': r.action, 'entity_id': r.entity_id, 'summary': r.summary, 'at': r.created_at} for r in rows[:limit]],
            'next_offset': offset+limit if len(rows)>limit else None,
            'failed_jobs': [{'id': str(j.id), 'kind': j.kind, 'attempt': j.attempt, 'error_code': j.error_code} for j in jobs]}
