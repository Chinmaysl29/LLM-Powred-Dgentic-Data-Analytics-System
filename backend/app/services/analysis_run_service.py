"""Durable seven-stage execution supervised by deterministic verified evidence."""
import asyncio
import json
from datetime import timezone

from sqlalchemy import select

from backend.app.models.analysis_run import AnalysisRun, AnalysisStage, AnalysisArtifact, AnalysisEvent
from backend.app.models.background_job import DurableJob, utcnow
from backend.app.models.learning import LearningRun
from backend.app.core.workspace_authorization import authorize_workspace, authorize_bound_dataset
from backend.app.services.data_retrieval_service import DataRetrievalService
from backend.app.services.storage_service import StorageService
from backend.app.core.config import get_settings
from backend.jobs.persistence import LostLeaseError
from backend.app.learning.evidence import record_job_failure

STAGES = ['Problem formulation', 'Data collection', 'Data preparation', 'Exploratory analysis', 'Data modeling', 'Visualization and reporting', 'Recommendations']


def authorize_run(db, run_id, actor, permission='read'):
    run = db.get(AnalysisRun, str(run_id))
    from fastapi import HTTPException
    if run is None or str(run.owner_id) != str(actor):
        raise HTTPException(404, 'Run not found')
    access = authorize_workspace(db, actor, run.workspace_id, permission)
    authorize_bound_dataset(db, access, run.dataset_id)
    from backend.app.services.learning_supervisor import bind
    bind(db,actor,run.workspace_id,permission)
    learning=db.get(LearningRun,run.id)
    if learning and learning.task:
        for ref in learning.task['datasets'][1:]:
            authorize_bound_dataset(db,access,ref['dataset_id'])
    return run


def snapshot(db, run):
    job = db.get(DurableJob, run.job_id)
    return dict(id=run.id, workspace_id=str(run.workspace_id), dataset_id=run.dataset_id,
        version_number=run.version_number, query=run.query,
        status='CANCELLED' if job.status == 'CANCELLED' else run.status,
        job_id=str(run.job_id), job_status=job.status,
        stages=[dict(number=s.number, name=s.name, status=s.status, attempt=s.attempt, error=s.error)
                for s in db.scalars(select(AnalysisStage).where(AnalysisStage.run_id == run.id).order_by(AnalysisStage.number))],
        artifacts=[dict(id=a.id, stage_number=a.stage_number, content=a.content)
                for a in db.scalars(select(AnalysisArtifact).where(AnalysisArtifact.run_id == run.id).order_by(AnalysisArtifact.stage_number))])


def fence(db, job):
    row = db.scalar(select(DurableJob).where(DurableJob.id == job['id']).with_for_update())
    expiry = row.lease_expires_at if row else None
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if not row or row.status != 'RUNNING' or row.lease_token != job['lease_token'] or not expiry or expiry <= utcnow():
        raise LostLeaseError('Analysis lease lost')


def _execute_stage(store, job, number):
    from backend.app.services.learning_supervisor import (bind, prepare, record_attempt,
        supervisor_stage, enqueue_extraction, control, optional_memory, create_learning_run, suspend_policy)
    run_id = job['payload']['run_id']
    with store.sessions() as db, db.begin():
        fence(db, job)
        run = authorize_run(db, run_id, job['owner_id'], 'write')
        access = bind(db, job['owner_id'], run.workspace_id, 'write')
        stage = db.scalar(select(AnalysisStage).where(AnalysisStage.run_id == run_id, AnalysisStage.number == number))
        if stage.status == 'COMPLETED':
            return False
        if number > 1:
            previous = db.scalar(select(AnalysisStage).where(AnalysisStage.run_id == run_id, AnalysisStage.number == number-1))
            if previous.status != 'COMPLETED':
                raise RuntimeError('Stage dependency incomplete')
        stage.status = 'RUNNING'; stage.attempt += 1; stage.error = None; run.status = 'RUNNING'
        attempt = stage.attempt
        db.add(AnalysisEvent(run_id=run_id, stage_number=number, status='RUNNING'))
        started = utcnow()
        learning = db.get(LearningRun, run_id)
        if learning is None:
            learning = create_learning_run(db, access, run)
        if attempt > 1:
            record_attempt(db, access, run_id, number, attempt-1, {'task': learning.task}, started,
                status='failed', error_code='WORKER_LEASE_EXPIRED_OR_RETRY')
        record_attempt(db, access, run_id, number, attempt, {'task': learning.task}, started, status='running')
    # Calculation is outside the lease-row transaction so heartbeats/cancellation proceed.
    with store.sessions() as db, db.begin():
        run = authorize_run(db, run_id, job['owner_id'], 'write')
        access = bind(db, job['owner_id'], run.workspace_id, 'write')
        retrieval = DataRetrievalService(db, StorageService(get_settings()), owner_id=str(job['owner_id']))
        frame, sampled = retrieval.load_dataframe(run.dataset_id, run.version_number, sample_size=0, preserve_representation=True)
        if sampled:
            raise ValueError('EXACT_ANALYSIS_REQUIRES_FULL_DATA')
        learning, task = prepare(db, access, run, frame)
        from backend.app.services.adaptive_service import prepare_context
        adaptive_snapshot, frames = prepare_context(db,access,run,learning,frame)
        if adaptive_snapshot is not None:
            db.expunge(adaptive_snapshot)  # Preserve pinned values across expire-on-commit session factories.
        # Persist interpretation/snapshot/start time before execution effects.
    def reserve_repair(count, actions, action, input_hash):
        with store.sessions() as db, db.begin():
            fence(db, job)
            run = authorize_run(db, run_id, job['owner_id'], 'write')
            bind(db, job['owner_id'], run.workspace_id, 'write')
            row = db.scalar(select(LearningRun).where(LearningRun.id == run_id).with_for_update())
            if count > row.budget['max_repairs'] or count != row.repairs + 1:
                raise ValueError('REPAIR_BUDGET_EXHAUSTED')
            row.repairs = count; row.actions = list(actions)
            from backend.app.services.learning_engine import digest
            row.repair_reservations = [*row.repair_reservations, {'action_hash': actions[-1], 'action': action, 'input_hash': input_hash}]
    with store.sessions() as db:
        run = authorize_run(db, run_id, job['owner_id'], 'write')
        access = bind(db, job['owner_id'], run.workspace_id, 'write')
        learning = db.get(LearningRun, run_id)
        from backend.app.services.adaptive_service import run_router
        repair_router=run_router(store,job,run_id,task,frames,adaptive_snapshot) if adaptive_snapshot else None
        content, blocked = supervisor_stage(db, access, run, frame, number, learning, task, reserve_repair,repair_router,frames)
        # Only the fenced publication below commits computed effects.
        outcome = learning.outcome if number == 5 else None
        encoded = json.dumps(content, allow_nan=False, default=str)
        if len(encoded.encode()) > 2_000_000:
            raise ValueError('Stage evidence exceeds supported response limit')
        content = json.loads(encoded)
    with store.sessions() as db, db.begin():
        fence(db, job)
        run = authorize_run(db, run_id, job['owner_id'], 'write')
        access = bind(db, job['owner_id'], run.workspace_id, 'write')
        learning = db.get(LearningRun, run_id)
        stage = db.scalar(select(AnalysisStage).where(AnalysisStage.run_id == run_id, AnalysisStage.number == number))
        if number == 5:
            current = control(db, run.workspace_id)
            eligible, degraded = optional_memory(db, task, learning.schema_hash, learning.memory_cutoff, snapshot=learning.lesson_snapshot)
            outcome['limitations'].extend(degraded)
            allowed = {l['lesson_id'] for l in eligible} if current['mode'] == 'limited' and current['active_bundle_id'] == learning.bundle_id else set()
            outcome['applied_lessons'] = [l for l in outcome['applied_lessons'] if l in allowed]
            learning.outcome = outcome; learning.plan = outcome['plan']; learning.applied_lessons = outcome['applied_lessons']
            learning.error_code = outcome['error_code']
            if outcome['error_code'] == 'MANDATORY_VALIDATION_FAILED':
                suspend_policy(db, access, outcome['error_code'])
            content = outcome
        content['provenance'] = dict(run_id=run_id, dataset_id=run.dataset_id, version_number=run.version_number, sampled=False)
        old = db.scalar(select(AnalysisArtifact).where(AnalysisArtifact.run_id == run_id, AnalysisArtifact.stage_number == number))
        if old:
            raise LostLeaseError('Stage already published')
        db.add(AnalysisArtifact(run_id=run_id, stage_number=number, content=content))
        stage.status = 'BLOCKED' if blocked else 'COMPLETED'
        run.status = 'BLOCKED' if blocked else ('COMPLETED' if number == 7 else 'RUNNING')
        if blocked:
            learning.state = 'waiting_for_input'; learning.error_code = content.get('error_code', 'CLARIFICATION_REQUIRED')
            learning.finished_at = utcnow()
        elif number == 7:
            learning.state = 'succeeded'; learning.finished_at = utcnow(); enqueue_extraction(db, learning)
            from backend.app.services.adaptive_service import queue_gap
            queue_gap(db,access,run_id)
        record_attempt(db, access, run_id, number, attempt, content, started)
        db.add(AnalysisEvent(run_id=run_id, stage_number=number, status=stage.status))
    return blocked


async def execute_analysis_job(store, job):
    """At-least-once computation, fenced atomic effects using the durable worker."""
    run_id = job['payload']['run_id']
    for number in range(1, 8):
        try:
            blocked = await asyncio.to_thread(_execute_stage, store, job, number)
            if blocked:
                await asyncio.to_thread(record_job_failure, store, job, number, exception=False)
                return {'run_id': run_id, 'status': 'BLOCKED'}
        except LostLeaseError:
            raise
        except Exception as exc:
            await asyncio.to_thread(record_job_failure, store, job, number, exception=True)
            from fastapi import HTTPException
            try:
                with store.sessions() as db, db.begin():
                    fence(db, job)
                    run = authorize_run(db, run_id, job['owner_id'], 'write')
                    from backend.app.services.learning_supervisor import bind, record_attempt, suspend_policy
                    access = bind(db, job['owner_id'], run.workspace_id, 'write')
                    stage = db.scalar(select(AnalysisStage).where(AnalysisStage.run_id == run_id, AnalysisStage.number == number))
                    stage.status = 'FAILED'; stage.error = 'STAGE_EXECUTION_FAILED'; run.status = 'FAILED'
                    learning = db.get(LearningRun, run_id)
                    if learning:
                        learning.state = 'failed'; learning.error_code = 'STAGE_EXECUTION_FAILED'; learning.finished_at = utcnow()
                        record_attempt(db, access, run_id, number, stage.attempt, {'task': learning.task}, utcnow(),
                            status='failed', error_code='STAGE_EXECUTION_FAILED')
                    if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) and exc.detail.get('code') == 'ARTIFACT_INTEGRITY_FAILED':
                        suspend_policy(db, access, 'ARTIFACT_INTEGRITY_FAILED')
                    db.add(AnalysisEvent(run_id=run_id, stage_number=number, status='FAILED'))
            except HTTPException:
                pass  # Revoked access must not create new tenant evidence.
            raise exc
    return {'run_id': run_id, 'status': 'COMPLETED'}
