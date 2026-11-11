"""Frozen paired comparisons. Gold labels stay outside executor context."""
from collections import Counter
from datetime import datetime
import math
import random
import time

from sqlalchemy import select

from backend.app.core.config import get_settings
from backend.app.core.workspace_authorization import authorize_bound_dataset
from backend.app.models.background_job import DurableJob, utcnow
from backend.app.models.learning import (LearningBundle, LearningCase, LearningControl,
                                         LearningEvaluation, LearningLesson)
from backend.app.schemas.learning import Budget, CaseRequest, EvaluationManifest, TaskSpec
from backend.app.services.data_retrieval_service import DataRetrievalService
from backend.app.services.storage_service import StorageService
from backend.app.services.learning_engine import RUNTIME_IDENTITY, digest, execute, same_rows, schema_hash
from backend.app.services.learning_supervisor import (audit, aware, bind, definitions,
                                                     error, lesson_eligible, retrieve)


def add_case(db, access, request):
    if request.task.workspace_id != access.workspace_id or request.task.datasets != [request.dataset_version]:
        error(422, 'CASE_SCOPE_MISMATCH', 'Case task and dataset version must match the authorized workspace.')
    authorize_bound_dataset(db, access, request.dataset_version.dataset_id)
    conflicting = db.scalar(select(LearningCase.id).where(LearningCase.workspace_id == access.workspace_id,
        LearningCase.scenario_group == request.scenario_group, LearningCase.split != request.split))
    if conflicting:
        error(409, 'SPLIT_CONTAMINATION', 'A scenario group cannot span development, calibration and final splits.')
    content = request.model_dump(mode='json')
    row = LearningCase(workspace_id=access.workspace_id, actor_id=access.actor_id,
        scenario_group=request.scenario_group, split=request.split, content=content, content_hash=digest(content))
    db.add(row); db.flush(); audit(db, access, 'evaluation_label_registered', row.id, split=row.split, source=request.label_source)
    return row


def validate_manifest(db, access, manifest):
    bundle = db.get(LearningBundle, manifest.candidate_bundle)
    if not bundle or bundle.workspace_id != access.workspace_id or bundle.content_hash != digest(bundle.content):
        error(404, 'BUNDLE_NOT_FOUND', 'Candidate bundle not found.')
    if bundle.content.get('runtime_identity') != RUNTIME_IDENTITY:
        error(409, 'POLICY_VERSION_MISMATCH', 'Candidate code or dependencies changed; freeze and evaluate the new version.')
    if aware(manifest.memory_cutoff) != datetime.fromisoformat(bundle.content['memory_cutoff']):
        error(422, 'CUTOFF_MISMATCH', 'Manifest must use the frozen bundle memory cutoff.')
    if len(set(manifest.case_ids)) != len(manifest.case_ids):
        error(422, 'DUPLICATE_EVALUATION_CASE', 'Evaluation cases must be unique.')
    cases = []
    declared = {(d.dataset_id, d.version) for d in manifest.dataset_versions}
    for case_id in manifest.case_ids:
        case = db.get(LearningCase, case_id)
        if not case or case.workspace_id != access.workspace_id or case.split != 'final':
            error(404, 'FINAL_CASE_NOT_FOUND', 'A final evaluation case was not found.')
        if case.content_hash != digest(case.content):
            error(409, 'CASE_INTEGRITY_FAILED', 'Evaluation case integrity check failed.')
        request = CaseRequest.model_validate(case.content)
        if (request.dataset_version.dataset_id, request.dataset_version.version) not in declared:
            error(422, 'DATASET_VERSION_NOT_DECLARED', 'Every case dataset version must be frozen in the manifest.')
        authorize_bound_dataset(db, access, request.dataset_version.dataset_id)
        cases.append(case)
    final_datasets = {case.content['dataset_version']['dataset_id'] for case in cases}
    for ref in bundle.content['lessons']:
        lesson = db.get(LearningLesson, ref['id'])
        if not lesson or lesson.workspace_id != access.workspace_id or lesson.content_hash != ref['content_hash']:
            error(409, 'BUNDLE_INVALIDATED', 'A frozen lesson is unavailable or changed.')
        if lesson.source_dataset_id in final_datasets:
            error(409, 'HELD_OUT_CONTAMINATION', 'Final dataset answers/feedback cannot contribute candidate lessons.')
        if lesson.state != 'active' or lesson.invalid_reason or aware(lesson.expires_at) <= utcnow():
            error(409, 'BUNDLE_INVALIDATED', 'A frozen lesson has been revoked, expired or invalidated.')
    return bundle, cases


def create_evaluation(db, access, request):
    from backend.app.models.workspace import Workspace
    db.scalar(select(Workspace.id).where(Workspace.id == access.workspace_id).with_for_update())
    old = db.scalar(select(LearningEvaluation).where(LearningEvaluation.workspace_id == access.workspace_id,
        LearningEvaluation.idempotency_key == request.idempotency_key))
    manifest = request.manifest.model_dump(mode='json')
    if old:
        if old.manifest != manifest or old.actor_id != access.actor_id:
            error(409, 'IDEMPOTENCY_CONFLICT', 'Evaluation key already represents another request.')
        return old
    previous = db.scalars(select(LearningEvaluation).where(LearningEvaluation.workspace_id == access.workspace_id)).all()
    for prior in previous:
        overlap = set(prior.manifest['case_ids']) & set(manifest['case_ids'])
        if overlap and (prior.manifest['gates'] != manifest['gates'] or prior.manifest['candidate_bundle'] != manifest['candidate_bundle']):
            error(409, 'FINAL_SET_ALREADY_EXPOSED', 'Use a new untouched final set for a changed candidate or release gates. Repeated identical frozen comparisons remain allowed.')
    bundle, cases = validate_manifest(db, access, request.manifest)
    job = DurableJob(workspace_id=access.workspace_id, owner_id=access.actor_id, kind='learning_eval',
        idempotency_key=request.idempotency_key, payload={}, retry_eligible=True)
    db.add(job); db.flush()
    row = LearningEvaluation(workspace_id=access.workspace_id, actor_id=access.actor_id, bundle_id=bundle.id,
        job_id=job.id, idempotency_key=request.idempotency_key, manifest=manifest)
    db.add(row); db.flush(); job.payload = {'evaluation_id': row.id}
    audit(db, access, 'evaluation_queued', row.id, manifest_hash=digest(manifest))
    return row


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered)-1, math.ceil(p * len(ordered))-1)] if ordered else None


def paired_interval(deltas):
    """Deterministic paired bootstrap; scenario groups, not paraphrases, are units."""
    if len(deltas) < 2:
        return None
    rng = random.Random(7219)
    samples = [sum(rng.choices(deltas, k=len(deltas))) / len(deltas) for _ in range(2000)]
    return [percentile(samples, .025), percentile(samples, .975)]


def summarize(pairs, manifest, trusted_groups):
    n = len(pairs)
    baseline = sum(p['baseline']['correct'] for p in pairs)
    candidate = sum(p['candidate']['correct'] for p in pairs)
    applications = sum(bool(p['candidate']['applied_lessons']) for p in pairs)
    useful = sum(not p['baseline']['correct'] and p['candidate']['correct'] and bool(p['candidate']['applied_lessons']) for p in pairs)
    harmful = sum(p['baseline']['correct'] and not p['candidate']['correct'] and bool(p['candidate']['applied_lessons']) for p in pairs)
    metrics = {}
    for name in ('baseline', 'candidate'):
        items = [p[name] for p in pairs]
        signatures = Counter(p['error_code'] for p in items if not p['correct'])
        repeats = sum(max(0, count-1) for count in signatures.values())
        metrics[name] = {'correct': sum(p['correct'] for p in items), 'total': n,
            'correctness': sum(p['correct'] for p in items)/n,
            'completed': sum(p['status'] == 'verified' for p in items),
            'abstained': sum(p['status'] == 'insufficient_evidence' for p in items),
            'unknown': sum(p['status'] == 'failed' for p in items),
            'repeated_errors': repeats, 'repeated_error_rate': repeats/n,
            'p50_latency_ms': percentile([p['latency_ms'] for p in items], .5),
            'p95_latency_ms': percentile([p['latency_ms'] for p in items], .95),
            'cost_usd': sum(p['cost_usd'] for p in items)}
    invariants = all(not (p[name]['status'] == 'verified' and not p[name]['correct']) for p in pairs for name in ('baseline','candidate'))
    gates = manifest.gates
    gate_results = {
        'mandatory_correctness_and_no_unsupported_verified_claim': invariants,
        'authorization_and_isolation': all(p['authorized'] for p in pairs),
        'no_forecasting_leakage': all(p['task_type'] == 'descriptive' for p in pairs),
        'minimum_independent_trusted_scenarios': trusted_groups >= gates.min_cases,
        'correctness_nonregression': (candidate-baseline)/n >= -gates.max_correctness_regression,
        'harmful_applications': harmful == 0,
        'latency_tolerance': metrics['candidate']['p95_latency_ms'] <= max(1, metrics['baseline']['p95_latency_ms']) * gates.max_p95_ratio,
        'cost_tolerance': metrics['candidate']['cost_usd'] - metrics['baseline']['cost_usd'] <= gates.max_cost_delta_usd,
        'measured_benefit': (candidate > baseline or metrics['candidate']['repeated_errors'] < metrics['baseline']['repeated_errors']) if gates.require_measured_benefit else True,
    }
    # Cluster paraphrases within a scenario before uncertainty estimation.
    grouped = {}
    for pair in pairs:
        grouped.setdefault(pair['scenario_group'], []).append(int(pair['candidate']['correct'])-int(pair['baseline']['correct']))
    interval = paired_interval([sum(v)/len(v) for v in grouped.values()])
    return {'sample_size': n, 'independent_scenario_groups': len(grouped), 'trusted_final_groups': trusted_groups,
        'metrics': metrics, 'correctness_delta': (candidate-baseline)/n, 'paired_bootstrap_95_interval': interval,
        'applications': applications, 'useful_applications': useful, 'harmful_applications': harmful,
        'gates': gate_results, 'release_eligible': all(gate_results.values()), 'pairs': pairs,
        'numeric_confidence': None, 'calibration': {'available': False, 'sample_size': 0,
            'brier_score': None, 'reliability_bins': [], 'error_coverage': [],
            'reason': 'No independently labeled calibrator fitting and untouched calibration-test datasets.'},
        'denominators': {'correctness': 'All declared paired cases, including failures and unknowns.',
            'repeated_error_rate': 'Repeated failing error-code occurrences after the first / all cases.',
            'applications': 'Cases with at least one eligible correction used.',
            'latency': 'Executor only; includes validation and repair, excludes queue delay and data load.',
            'useful_harmful': 'Paired correctness change among cases with applied memory.'},
        'limitations': ['Small/synthetic pilots do not establish production accuracy gains.',
            'Both arms use identical validators, approved corrections, data, tools and code.',
            'No provider nondeterminism in this deterministic executor; cost is zero provider usage, not infrastructure cost.',
            'Definition and trusted-label quality remain domain assertions.',
            'No model weights were trained.']}


async def execute_evaluation_job(store, job):
    import asyncio
    return await asyncio.to_thread(_execute_evaluation, store, job)


def _execute_evaluation(store, job):
    from backend.app.services.analysis_run_service import fence
    evaluation_id = job['payload']['evaluation_id']
    try:
        with store.sessions() as db, db.begin():
            fence(db, job)
            access = bind(db, job['owner_id'], job['workspace_id'], 'manage')
            row = db.get(LearningEvaluation, evaluation_id)
            if not row or row.workspace_id != access.workspace_id or row.actor_id != access.actor_id:
                error(404, 'EVALUATION_NOT_FOUND', 'Evaluation not found.')
            if row.state == 'succeeded':
                return {'evaluation_id': row.id, 'status': 'succeeded'}
            manifest = EvaluationManifest.model_validate(row.manifest)
            validate_manifest(db, access, manifest)
            row.state = 'running'
        pairs = []
        trusted = set()
        for index, case_id in enumerate(manifest.case_ids):
            store.heartbeat(job['id'], job['lease_token'])
            with store.sessions() as db:
                access = bind(db, job['owner_id'], job['workspace_id'], 'manage')
                bundle, cases = validate_manifest(db, access, manifest)
                case = next(c for c in cases if c.id == case_id)
                task = TaskSpec.model_validate(case.content['task'])
                dataset = case.content['dataset_version']
                loader = DataRetrievalService(db, StorageService(get_settings()), owner_id=str(access.actor_id))
                frame, sampled = loader.load_dataframe(dataset['dataset_id'], dataset['version'], sample_size=0, preserve_representation=True)
                if sampled:
                    raise ValueError('EVALUATION_REQUIRES_FULL_DATA')
                defs = definitions(db, access.workspace_id)
                lessons = retrieve(db, task, schema_hash(frame), manifest.memory_cutoff, snapshot=bundle.content['lessons'])
                # Only task, inputs and approved memory reach execution. Gold labels below are grader-only.
                results = {}
                names = ('baseline','candidate') if index % 2 == 0 else ('candidate','baseline')
                for name in names:
                    started = time.perf_counter()
                    try:
                        result = execute(task, frame, defs, manifest.budget, lessons if name == 'candidate' else [])
                    except Exception:
                        result = {'status': 'failed', 'error_code': 'EXECUTOR_FAILED', 'answer': None,
                            'latency_ms': (time.perf_counter()-started)*1000, 'usage': {'cost_usd':0},
                            'applied_lessons':[], 'result_hash':None}
                    expected_status = case.content['expected_status']
                    correct = result['status'] == expected_status
                    if expected_status == 'verified':
                        correct = correct and bool(result['answer']) and same_rows(result['answer']['rows'], case.content['expected_rows'])
                    results[name] = {'status': result['status'], 'correct': bool(correct),
                        'error_code': result['error_code'], 'latency_ms': result['latency_ms'],
                        'cost_usd': result['usage']['cost_usd'], 'applied_lessons': result['applied_lessons'],
                        'result_hash': result['result_hash']}
                if case.content['label_source'] == 'domain_reviewed':
                    trusted.add(case.scenario_group)
                pairs.append({'case_id': case.id, 'case_hash': case.content_hash, 'scenario_group': case.scenario_group,
                    'task_type': task.task_type, 'authorized': True, **results})
        result = summarize(pairs, manifest, len(trusted))
        with store.sessions() as db, db.begin():
            fence(db, job)
            access = bind(db, job['owner_id'], job['workspace_id'], 'manage')
            validate_manifest(db, access, manifest)  # Revocation overrides frozen evaluation memory.
            row = db.get(LearningEvaluation, evaluation_id)
            row.state = 'succeeded'; row.result = result
            audit(db, access, 'evaluation_completed', row.id, release_eligible=result['release_eligible'])
        return {'evaluation_id': evaluation_id, 'status': 'succeeded'}
    except Exception:
        from backend.jobs.persistence import LostLeaseError
        try:
            with store.sessions() as db, db.begin():
                fence(db, job)
                bind(db, job['owner_id'], job['workspace_id'], 'manage')
                row = db.get(LearningEvaluation, evaluation_id)
                if row and row.state != 'succeeded':
                    row.state = 'failed'; row.result = {'error_code': 'EVALUATION_FAILED', 'release_eligible': False}
        except (LostLeaseError, Exception):
            pass
        raise


def release(db, access, evaluation_id, generation, percent):
    row = db.get(LearningEvaluation, evaluation_id)
    if not row or row.workspace_id != access.workspace_id or row.state != 'succeeded' or not row.result.get('release_eligible'):
        error(409, 'RELEASE_GATES_NOT_PASSED', 'A completed evaluation must pass all declared release gates.')
    manifest = EvaluationManifest.model_validate(row.manifest)
    bundle, cases = validate_manifest(db, access, manifest)
    cfg = db.scalar(select(LearningControl).where(LearningControl.workspace_id == access.workspace_id).with_for_update())
    if not cfg or cfg.generation != generation:
        error(409, 'CONTROL_VERSION_CONFLICT', 'Reload feature controls before releasing.')
    cfg.previous_bundle_id = cfg.active_bundle_id; cfg.active_bundle_id = bundle.id
    cfg.mode = 'limited'; cfg.rollout_percent = percent; cfg.generation += 1
    cfg.actor_id = access.actor_id; cfg.updated_at = utcnow()
    audit(db, access, 'limited_release', bundle.id, evaluation_id=row.id, rollout_percent=percent)
    return cfg
