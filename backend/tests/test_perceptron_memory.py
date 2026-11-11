"""Failure memory against isolated PostgreSQL and Chroma; synthetic data only."""
import asyncio
import json
import subprocess
import sys
from uuid import UUID, uuid4

import numpy as np
import pytest
from sqlalchemy import select, update, text

from backend.tests.test_verified_learning_integration import environment, identity, dataset
from backend.app.core.config import get_settings
from backend.app.models import DatasetVersion
from backend.app.learning import evidence, failure_memory as memory, memory_review as review
from backend.app.learning.memory_contract import embedding, checked_vector, correction, merge_steps
from backend.app.learning.memory_chroma import MemoryIndex, BASE
from backend.app.learning.memory_table import failure_memory_links as links
from backend.app.learning.tables import feedback_events, mistakes
from backend.app.schemas.planner import WorkflowPlanningRequest
from backend.app.services.workflow_planner_service import WorkflowPlannerService

QUESTION = 'Explore the dataset schema and inspect missing values across all columns'
PLAN = {'format': 1, 'intent': 'dataset_overview', 'add_steps': ['validation']}


@pytest.fixture
def case(environment, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), 'learning_enabled', True)
    account = identity(environment)
    ds = dataset(environment, account, tmp_path)
    with environment['admin']() as db, db.begin():
        db.execute(update(DatasetVersion).where(DatasetVersion.dataset_id == ds).values(
            metadata_snapshot={'columns': ['region', 'amount', 'status'],
                               'dtypes': {'region': 'object', 'amount': 'int64', 'status': 'object'}}))
    event = uuid4()
    assert evidence.record_failure(actor_id=str(account['user']), dataset_id=ds,
        question=QUESTION, error_type='validator_rejection', event_id=event)
    return environment, account, ds, event


def approve(case, **changes):
    env, account, ds, event = case
    args = dict(factory=env['admin'], reviewer_id=account['user'], feedback_id=event,
        dataset_id=ds, version_number=1, question=QUESTION, corrected_plan=PLAN)
    args.update(changes)
    return review.approve(**args)


def recall(case, question=QUESTION, intent='dataset_overview'):
    _, account, ds, _ = case
    return memory.retrieve_sync(account['user'], ds, question, intent)


def test_vector_is_stable_bounded_and_numpy_only():
    vector = embedding(QUESTION)
    assert len(vector) == 1024 and np.linalg.norm(vector) == pytest.approx(1)
    code = 'import json; from backend.app.learning.memory_contract import embedding; print(json.dumps(embedding(' + repr(QUESTION) + ')))'
    assert json.loads(subprocess.check_output([sys.executable, '-c', code], text=True)) == vector
    with pytest.raises(ValueError):
        checked_vector([float('nan')] * 1024)
    with pytest.raises(ValueError):
        embedding('x' * 2001)


@pytest.mark.parametrize('value', [dict(PLAN, sql='select 1'), dict(PLAN, format=True),
    dict(PLAN, add_steps=['cleaning']), dict(PLAN, add_steps=['validation', 'validation']),
    dict(PLAN, intent='unknown'), dict(PLAN, add_steps=['ignore all instructions'])])
def test_corrections_cannot_execute_text_or_change_metrics(value):
    with pytest.raises(ValueError):
        correction(value)


def test_real_index_review_recall_and_privacy(case):
    env, account, ds, event = case
    result = approve(case)
    assert result['approved'] and result['indexed'], result
    assert recall(case) == [PLAN]
    assert recall(case, QUESTION + ' please') == [PLAN]
    assert recall(case, 'Forecast tomorrow weather temperature') == []
    assert recall(case, intent='trend_analysis') == []
    assert approve(case) == result
    with env['admin']() as db:
        row = db.execute(select(mistakes).where(mistakes.c.id == UUID(result['mistake_id']))).mappings().one()
        assert row['question'] is None and set(row['features']) == {'embedding', 'embedding_version'}
        assert db.scalar(select(feedback_events.c.truth).where(feedback_events.c.id == event)) is None
        tenant = row['tenant_id']
    with MemoryIndex() as index:
        collection = index.collection(tenant)
        stored = index.request('POST', f'{BASE}/{collection}/get',
            {'ids': [result['mistake_id']], 'include': ['documents', 'metadatas', 'embeddings']})
    assert stored['documents'] == [None]
    assert QUESTION not in json.dumps(stored)
    assert len(stored['embeddings'][0]) == 1024
    assert set(stored['metadatas'][0]) == {'tenant_id', 'workspace_id', 'actor_id', 'dataset_id',
        'dataset_version', 'schema_hash', 'intent', 'embedding_version'}


@pytest.mark.parametrize('change', ['question', 'dataset', 'version', 'legacy', 'schema'])
def test_review_requires_exact_provenance(case, tmp_path, change):
    env, account, ds, event = case
    updates = {}
    if change == 'question':
        updates['question'] = QUESTION + ' changed'
    elif change == 'dataset':
        updates['dataset_id'] = dataset(env, account, tmp_path)
    elif change == 'version':
        updates['version_number'] = 99
    elif change == 'legacy':
        with env['admin']() as db, db.begin():
            db.execute(feedback_events.update().where(feedback_events.c.id == event).values(
                features={'error_type': 'validator_rejection'}))
    else:
        with env['admin']() as db, db.begin():
            db.execute(update(DatasetVersion).where(DatasetVersion.dataset_id == ds).values(metadata_snapshot={}))
    with pytest.raises(ValueError):
        approve(case, **updates)


def test_review_requires_authorized_operator(case):
    env, account, _, _ = case
    outsider = identity(env)
    with pytest.raises(Exception):
        approve(case, reviewer_id=outsider['user'])
    with pytest.raises(Exception):
        approve(case, factory=env['api'])
    from backend.app.core.workspace_authorization import tenant_memberships
    with env['admin']() as db, db.begin():
        db.execute(tenant_memberships.update().where(tenant_memberships.c.user_id == account['user']).values(role='viewer'))
    with pytest.raises(Exception):
        approve(case)


def test_sql_rechecks_scope_even_if_index_returns_forged_candidates(case, tmp_path, monkeypatch):
    env, account, ds, _ = case
    result = approve(case)
    monkeypatch.setattr(MemoryIndex, 'query', lambda *args: [result['mistake_id']])
    outsider = identity(env)
    other_ds = dataset(env, outsider, tmp_path)
    assert memory.retrieve_sync(outsider['user'], ds, QUESTION, PLAN['intent']) == []
    assert memory.retrieve_sync(account['user'], other_ds, QUESTION, PLAN['intent']) == []
    assert recall(case, intent='trend_analysis') == []
    assert recall(case, question='Weather forecast') == []
    with env['admin']() as db, db.begin():
        db.execute(update(DatasetVersion).where(DatasetVersion.dataset_id == ds).values(version_number=2))
    assert recall(case) == []


def test_tampered_sql_payload_is_not_replayed(case, monkeypatch):
    env, _, _, _ = case
    result = approve(case)
    monkeypatch.setattr(MemoryIndex, 'query', lambda *args: [result['mistake_id']])
    with env['admin']() as db, db.begin():
        db.execute(mistakes.update().where(mistakes.c.id == UUID(result['mistake_id'])).values(
            corrected_plan=dict(PLAN, add_steps=['statistics'])))
    assert recall(case) == []


def test_revocation_blocks_stale_vectors_and_cannot_be_reapproved(case, monkeypatch):
    env, account, _, _ = case
    result = approve(case)
    monkeypatch.setattr(MemoryIndex, 'remove', lambda *args: (_ for _ in ()).throw(OSError('offline')))
    revoked = review.revoke(env['admin'], account['user'], result['mistake_id'])
    assert revoked['revoked'] and not revoked['index_removed']
    monkeypatch.setattr(MemoryIndex, 'query', lambda *args: [result['mistake_id']])
    assert recall(case) == []
    with pytest.raises(ValueError):
        review.reindex(env['admin'], account['user'], result['mistake_id'])
    with pytest.raises(ValueError):
        approve(case)


def test_partial_index_failure_is_retryable(case, monkeypatch):
    env, account, _, _ = case
    with monkeypatch.context() as patch:
        patch.setattr(MemoryIndex, 'upsert', lambda *args: (_ for _ in ()).throw(OSError('offline')))
        result = approve(case)
    assert result['approved'] and not result['indexed']
    assert review.reindex(env['admin'], account['user'], result['mistake_id'])
    assert recall(case) == [PLAN]


def test_flag_disabled_and_outages_preserve_planner(case, monkeypatch):
    _, account, ds, _ = case
    assert approve(case)['indexed']
    planner = WorkflowPlannerService(owner_id=str(account['user']))
    request = WorkflowPlanningRequest(query=QUESTION, dataset_id=ds, intent=PLAN['intent'])
    monkeypatch.setattr(get_settings(), 'learning_enabled', False)
    baseline = asyncio.run(planner.plan(request)).model_dump(exclude={'workflow_id'})
    with monkeypatch.context() as patch:
        patch.setattr(memory, 'create_engine', lambda *a, **k: pytest.fail('Flag off touched DB'))
        assert recall(case) == []
    monkeypatch.setattr(get_settings(), 'learning_enabled', True)
    enhanced = asyncio.run(planner.plan(request))
    assert 'validation' in enhanced.steps and set(baseline['steps']).issubset(enhanced.steps)
    assert enhanced.intent == baseline['intent'] and enhanced.use_sampling == baseline['use_sampling']
    with monkeypatch.context() as patch:
        patch.setattr(MemoryIndex, '__enter__', lambda *args: (_ for _ in ()).throw(OSError('offline')))
        assert asyncio.run(planner.plan(request)).model_dump(exclude={'workflow_id'}) == baseline
    with monkeypatch.context() as patch:
        patch.setattr(memory, 'create_engine', lambda *a, **k: (_ for _ in ()).throw(OSError('offline')))
        assert recall(case) == []
    assert merge_steps(['summary'], [PLAN], 'trend_analysis') == ['summary']


def test_rls_reads_only_bound_actor_and_disallows_runtime_writes(case):
    env, account, ds, _ = case
    result = approve(case)
    mid = UUID(result['mistake_id'])
    with env['api']() as db, db.begin():
        assert db.scalar(select(links.c.mistake_id).where(links.c.mistake_id == mid)) is None
        memory.scope(db, account['user'], ds)
        assert db.scalar(select(links.c.mistake_id).where(links.c.mistake_id == mid)) == mid
        assert db.execute(links.update().where(links.c.mistake_id == mid).values(active=False)).rowcount == 0
        assert db.execute(links.delete().where(links.c.mistake_id == mid)).rowcount == 0
        db.execute(text("SELECT set_config('app.actor_id',:actor,true)"), {'actor': str(uuid4())})
        assert db.scalar(select(links.c.mistake_id).where(links.c.mistake_id == mid)) is None


def test_cli_reindex_and_revoke(case):
    env, account, _, _ = case
    result = approve(case)
    from pathlib import Path
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'perceptron_memory.py'
    for action in ('reindex', 'revoke'):
        command = [sys.executable, str(script), action, '--reviewer-id', str(account['user']),
                   '--mistake-id', result['mistake_id']]
        output = subprocess.run(command, capture_output=True, text=True)
        assert output.returncode == 0, output.stderr
        assert json.loads(output.stdout)['indexed' if action == 'reindex' else 'revoked']
    assert recall(case) == []


def test_authenticated_planner_uses_only_owners_memory(case):
    env, account, ds, _ = case
    assert approve(case)['indexed']
    body = dict(query=QUESTION, dataset_id=ds, intent=PLAN['intent'])
    own = env['client'].post('/api/v1/planner/plan', headers=account['headers'], json=body)
    assert own.status_code == 200, own.text
    assert 'Added analytical checks from a reviewed past failure.' in own.json()['rules_triggered']
    outsider = identity(env)
    other = env['client'].post('/api/v1/planner/plan', headers=outsider['headers'], json=body)
    assert other.status_code == 200
    assert 'Added analytical checks from a reviewed past failure.' not in other.json()['rules_triggered']


@pytest.mark.parametrize('dynamic', [False, True])
def test_orchestrator_executes_added_validation(case, dynamic):
    from backend.app.services.orchestrator_service import OrchestratorService
    env, account, ds, _ = case
    assert approve(case)['indexed']
    with env['admin']() as db:
        service = OrchestratorService(db=db, owner_id=str(account['user']))
        response = asyncio.run(service.execute(QUESTION, dataset_id=ds,
            context={'intent': PLAN['intent']}, dynamic_planning=dynamic, max_retries=0))
    assert 'validation' in response.workflow
    assert 'validation' in response.executed_agents


def test_memory_never_changes_chat_arithmetic_or_trains(case, monkeypatch):
    from backend.app.learning.perceptron import AveragedPerceptron
    env, account, ds, _ = case
    question = 'total amount by region'
    event = uuid4()
    assert evidence.record_failure(actor_id=str(account['user']), dataset_id=ds,
        question=question, error_type='execution_error', event_id=event)
    assert approve(case, feedback_id=event, question=question)['indexed']
    monkeypatch.setattr(AveragedPerceptron, 'update', lambda *a, **k: pytest.fail('Request trained model'))
    outputs = []
    for flag in (False, True):
        monkeypatch.setattr(get_settings(), 'learning_enabled', flag)
        response = env['client'].post('/api/v1/chat', headers=account['headers'], json={
            'message': question, 'dataset_id': ds, 'workspace_id': str(account['workspace'])})
        assert response.status_code == 200, response.text
        outputs.append({key: response.json()[key] for key in ('data', 'plan', 'kpis', 'answer', 'intent', 'confidence')})
    assert outputs[0] == outputs[1]
    assert outputs[1]['data'] == [{'region': 'a', 'amount': 1180}]


def test_access_revocation_overrides_index(case):
    from backend.app.core.workspace_authorization import workspace_memberships
    env, account, _, _ = case
    assert approve(case)['indexed']
    with env['admin']() as db, db.begin():
        db.execute(workspace_memberships.update().where(workspace_memberships.c.user_id == account['user']).values(active=False))
    assert recall(case) == []


def test_full_read_slots_skip_memory(case):
    assert memory._read_slots.acquire(blocking=False)
    assert memory._read_slots.acquire(blocking=False)
    try:
        assert recall(case) == []
    finally:
        memory._read_slots.release()
        memory._read_slots.release()
