"""Schema-only learning with real isolated PostgreSQL and deterministic execution."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import select, update, text

from backend.tests.test_verified_learning_integration import environment, identity, dataset
from backend.app.core.config import get_settings
from backend.app.models import DatasetVersion
from backend.app.learning import column_lifecycle as lifecycle, column_runtime as runtime, column_store as store
from backend.app.learning.column_ranker import ColumnRanker, features
from backend.app.learning.column_contract import manifest, train, evaluate, schema_fields, eligible
from backend.app.learning.memory_contract import digest
from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService

SCHEMA = {'columns': ['region', 'amount', 'cost'], 'dtypes': {'region': 'object', 'amount': 'int64', 'cost': 'int64'}}
QUESTION = 'total receipts by region'


def reviewed_cases():
    cases = []
    def add(question, expected, split, group):
        cases.append(dict(question=question, expected=expected, split=split, group=group))
    operations = ['total', 'sum', 'average', 'minimum', 'maximum']
    for alias, target in [('receipts', 'amount'), ('expenses', 'cost')]:
        for operation in operations:
            add(f'{operation} {alias}', target, 'train', 'training-' + alias)
            add(f'{operation} {alias} by region', target, 'golden', 'grouped-' + alias)
            add(f'{operation} {target} by region', target, 'golden', 'explicit-' + alias)
    for i, operation in enumerate(operations):
        add(f'{operation} mystery', None, 'train', 'training-unknown')
        add(f'{operation} vapor', None, 'golden', 'unknown')
        add(f'{operation} receipts where region is west', None, 'golden', 'unsupported-filter')
    return {'format': 1, 'schema': deepcopy(SCHEMA), 'cases': cases}


@pytest.fixture
def case(environment, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), 'learning_enabled', True)
    account = identity(environment)
    ds = dataset(environment, account, tmp_path, 'region,amount,cost\na,100,10\na,1000,100\na,-20,2\na,100,10\n')
    with environment['admin']() as db, db.begin():
        db.execute(update(DatasetVersion).where(DatasetVersion.dataset_id == ds).values(metadata_snapshot=SCHEMA))
    return environment, account, ds, reviewed_cases()


def stage(case):
    env, account, ds, value = case
    return lifecycle.stage(env['admin'], account['user'], ds, 1, value, digest(value))['version']


def plan(case, question=QUESTION):
    _, _, ds, _ = case
    columns, numeric, dates, _ = schema_fields(SCHEMA)
    return replace(NaturalLanguageAnalyticsService().parse(question, columns, numeric, dates), dataset_id=ds, dataset_version=1)


def resolve(case, question=QUESTION, **kwargs):
    return runtime.resolve(case[1]['user'], question, SCHEMA, plan(case, question), **kwargs)


def promote(case, version, expected=0):
    env, account, ds, value = case
    return lifecycle.promote(env['admin'], account['user'], ds, 1, version, expected, value, digest(value))


def activate(case):
    version = stage(case)
    assert resolve(case).clarification_required  # Shadow must not apply the prediction.
    result = promote(case, version)
    assert result['promoted'], result
    return version


def test_numpy_training_and_disjoint_real_evaluator():
    value = reviewed_cases()
    model = train(value)
    assert np.isfinite(model.weights).all()
    assert model.predict(QUESTION, ['amount', 'cost'], SCHEMA['dtypes'])[0] == 'amount'
    assert model.predict(QUESTION, ['cost', 'amount'], SCHEMA['dtypes']) == model.predict(QUESTION, ['amount', 'cost'], SCHEMA['dtypes'])
    report = evaluate(value, model)
    assert report['passed'], report
    assert report['correct'] == report['cases'] == 30
    assert not evaluate(value, model, model)['passed']  # Ties cannot promote.
    assert ColumnRanker(model.snapshot(), sorted(model.vocabulary)).predict(QUESTION, ['amount', 'cost'], SCHEMA['dtypes'])[0] == 'amount'
    assert model.predict('total neverreviewed by region', ['amount', 'cost'], SCHEMA['dtypes'])[0] is None


@pytest.mark.parametrize('change', ['duplicate', 'group_overlap', 'invalid_target', 'no_abstention', 'too_small'])
def test_manifest_rejects_leakage_and_unreviewed_choices(change):
    value = reviewed_cases()
    if change == 'duplicate':
        value['cases'][-1]['question'] = value['cases'][0]['question']
    elif change == 'group_overlap':
        value['cases'][-1]['group'] = value['cases'][0]['group']
    elif change == 'invalid_target':
        value['cases'][-1]['expected'] = 'arbitrary formula'
    elif change == 'no_abstention':
        for row in value['cases']:
            row['expected'] = 'amount'
    else:
        value['cases'] = value['cases'][:10]
    with pytest.raises(ValueError):
        manifest(value)


def test_invalid_models_and_vectors():
    for weights in ([float('nan')] * 512, [1001] * 512, [False] * 512, [0] * 513):
        with pytest.raises(ValueError):
            ColumnRanker(weights)
    with pytest.raises(ValueError):
        features('x' * 2001, 'amount')
    with pytest.raises(ValueError):
        features('total receipts ' + 'please ' * 64 + 'unreviewed', 'amount')
    with pytest.raises(ValueError):
        ColumnRanker().update('total x', ['amount'], SCHEMA['dtypes'], 'forged')


def test_guard_preserves_explicit_ambiguous_filtered_and_context_requests(case):
    activate(case)
    for question in ('total amount by region', 'sum amount and cost', 'total receipts where region is west',
                     'average order value', 'total profit', 'monthly receipts', 'count records by region'):
        original = plan(case, question)
        assert runtime.resolve(case[1]['user'], question, SCHEMA, original) == original
    assert resolve(case, context=[{'content': 'total cost'}]) == plan(case)
    schema = {'columns': ['region', 'customer_id', 'event_date', 'flag', 'amount'],
        'dtypes': {'region': 'object', 'customer_id': 'int64', 'event_date': 'int64', 'flag': 'bool', 'amount': 'float64'}}
    assert schema_fields(schema)[3] == ['amount']


def test_shadow_promotion_rollback_and_private_evidence(case):
    env, account, ds, value = case
    version = stage(case)
    with pytest.raises(ValueError):
        promote(case, version)  # Cannot skip shadow.
    assert resolve(case) == plan(case)
    assert promote(case, version)['promoted']
    assert resolve(case).metric == 'amount'
    with env['admin']() as db:
        payload = store.read(db, lifecycle.access(db, account['user'], ds, 1).tenant_id, version)
        serialized = json.dumps(payload)
        assert QUESTION not in serialized and 'receipts' not in serialized and 'expenses' not in serialized
        rows = db.execute(select(store.events).where(store.events.c.dataset_id == ds)).mappings().all()
        assert {'stage', 'shadow', 'promote'} <= {r['action'] for r in rows}
        assert 'receipts' not in json.dumps([dict(r['detail']) for r in rows])
    lifecycle.rollback(env['admin'], account['user'], ds, 1, 0, version)
    assert resolve(case) == plan(case)
    lifecycle.rollback(env['admin'], account['user'], ds, 1, version, 0)
    assert resolve(case).metric == 'amount'


def test_flag_off_and_db_outage_return_original(case, monkeypatch):
    activate(case)
    monkeypatch.setattr(get_settings(), 'learning_enabled', False)
    monkeypatch.setattr(runtime, 'create_engine', lambda *a, **k: pytest.fail('Disabled resolver touched DB'))
    assert runtime.scoped_resolver(case[1]['user']) is None
    assert resolve(case) == plan(case)
    monkeypatch.setattr(get_settings(), 'learning_enabled', True)
    monkeypatch.setattr(runtime, 'create_engine', lambda *a, **k: (_ for _ in ()).throw(OSError('offline')))
    assert resolve(case) == plan(case)


def test_scope_version_schema_and_access_revocation(case, tmp_path):
    from backend.app.core.workspace_authorization import workspace_memberships
    env, account, ds, _ = case
    activate(case)
    outsider = identity(env)
    assert runtime.resolve(outsider['user'], QUESTION, SCHEMA, plan(case)) == plan(case)
    other = dataset(env, account, tmp_path)
    original = replace(plan(case), dataset_id=other)
    assert runtime.resolve(account['user'], QUESTION, SCHEMA, original) == original
    original = replace(plan(case), dataset_version=99)
    assert runtime.resolve(account['user'], QUESTION, SCHEMA, original) == original
    changed = deepcopy(SCHEMA); changed['dtypes']['amount'] = 'float64'
    assert runtime.resolve(account['user'], QUESTION, changed, plan(case)) == plan(case)
    with env['admin']() as db, db.begin():
        db.execute(workspace_memberships.update().where(workspace_memberships.c.user_id == account['user']).values(active=False))
    assert resolve(case) == plan(case)


def test_tampered_model_and_changed_source_fail_open(case, monkeypatch):
    env, account, ds, _ = case
    version = activate(case)
    with monkeypatch.context() as patch:
        patch.setattr(store, 'fingerprint', lambda: '0' * 64)
        assert resolve(case) == plan(case)
    with env['admin']() as db, db.begin():
        current = lifecycle.access(db, account['user'], ds, 1)
        payload = deepcopy(store.read(db, current.tenant_id, version))
        payload['weights'][0] += 1
        db.execute(store.weights.update().where(store.condition(current.tenant_id), store.weights.c.version == version).values(weights=payload))
    assert resolve(case) == plan(case)


def test_reviewer_and_runtime_role_cannot_forge_release(case):
    env, account, ds, value = case
    outsider = identity(env)
    for reviewer, factory in ((outsider['user'], env['admin']), (account['user'], env['api'])):
        with pytest.raises(Exception):
            lifecycle.stage(factory, reviewer, ds, 1, value, digest(value))
    version = stage(case)
    with env['api']() as db, db.begin():
        current = store.scope_dict(runtime.scope(db, account['user'], ds, 1))
        assert db.execute(store.events.update().where(store.events.c.dataset_id == ds).values(action='promote')).rowcount == 0
        assert db.execute(store.events.delete().where(store.events.c.dataset_id == ds)).rowcount == 0
    with pytest.raises(Exception):
        with env['api']() as db, db.begin():
            current = runtime.scope(db, account['user'], ds, 1)
            store.event(db, current, 'promote', version, reviewer=account['user'])


def test_manifest_changed_and_stale_version_refused(case):
    env, account, ds, value = case
    version = stage(case)
    resolve(case)
    changed = deepcopy(value); changed['cases'][-1]['question'] += ' please'
    with pytest.raises(ValueError):
        lifecycle.promote(env['admin'], account['user'], ds, 1, version, 0, changed, digest(changed))
    with pytest.raises(ValueError):
        promote(case, version, expected=99)
    with pytest.raises(ValueError):
        lifecycle.rollback(env['admin'], account['user'], ds, 1, version, 0)


def test_actual_chat_uses_deterministic_arithmetic_without_training(case, monkeypatch):
    env, account, ds, _ = case
    activate(case)
    monkeypatch.setattr(ColumnRanker, 'update', lambda *a, **k: pytest.fail('Request trained model'))
    response = env['client'].post('/api/v1/chat', headers=account['headers'], json={
        'message': QUESTION, 'dataset_id': ds, 'workspace_id': str(account['workspace'])})
    assert response.status_code == 200, response.text
    assert response.json()['plan']['metric'] == 'amount'
    assert response.json()['data'] == [{'region': 'a', 'amount': 1180}]
    assert response.json()['kpis']['total'] == 1180
    assert response.json()['chart']['points'] == [{'label': 'a', 'value': 1180.0}]


def test_cli_status_and_disable(case):
    _, account, ds, _ = case
    version = activate(case)
    script = Path(__file__).resolve().parents[2] / 'scripts/perceptron_columns.py'
    common = ['--reviewer-id', str(account['user']), '--dataset-id', ds, '--dataset-version', '1']
    result = subprocess.run([sys.executable, str(script), 'status', *common], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['active_version'] == version
    result = subprocess.run([sys.executable, str(script), 'rollback', *common, '--version', '0', '--expected-version', str(version)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert resolve(case) == plan(case)


def test_failed_evaluation_never_activates(case):
    env, account, ds, value = case
    value['cases'][1]['expected'] = 'cost'  # Deliberately conflicting reviewed golden label.
    version = stage(case)
    resolve(case)
    result = promote(case, version)
    assert not result['promoted'] and result['evaluation']['correct'] < result['evaluation']['cases']
    with env['admin']() as db:
        current = lifecycle.access(db, account['user'], ds, 1)
        assert store.active(db, current.tenant_id) == 0


def test_concurrent_staging_allocates_distinct_versions(case):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        versions = list(executor.map(lambda _: stage(case), range(2)))
    assert sorted(versions) == [1, 2]


@pytest.mark.parametrize('change', ['release', 'revocation'])
def test_changes_during_evaluation_block_activation(case, monkeypatch, change):
    from backend.app.core.workspace_authorization import workspace_memberships
    env, account, ds, _ = case
    version = stage(case); resolve(case)
    original = lifecycle.evaluate
    def changed(*args, **kwargs):
        report = original(*args, **kwargs)
        if change == 'release':
            lifecycle.rollback(env['admin'], account['user'], ds, 1, 0, 0)
        else:
            with env['admin']() as db, db.begin():
                db.execute(workspace_memberships.update().where(workspace_memberships.c.user_id == account['user']).values(active=False))
        return report
    monkeypatch.setattr(lifecycle, 'evaluate', changed)
    with pytest.raises(Exception):
        promote(case, version)
    with env['admin']() as db:
        assert not db.scalar(select(store.weights.c.is_active).where(store.weights.c.learner == store.LEARNER,
            store.weights.c.weights['scope']['dataset_id'].astext == ds))


def test_audit_failure_rolls_back_activation(case, monkeypatch):
    env, account, ds, _ = case
    version = stage(case); resolve(case)
    def broken(*args, **kwargs):
        raise RuntimeError('Synthetic audit storage failure')
    monkeypatch.setattr(lifecycle, 'event', broken)
    with pytest.raises(RuntimeError):
        promote(case, version)
    with env['admin']() as db:
        current = lifecycle.access(db, account['user'], ds, 1)
        assert store.active(db, current.tenant_id) == 0


def test_bounded_capacity_and_schema_mismatch_skip_selection(case):
    assert runtime._slots.acquire(blocking=False)
    assert runtime._slots.acquire(blocking=False)
    try:
        assert resolve(case) == plan(case)
    finally:
        runtime._slots.release(); runtime._slots.release()
    env, account, ds, value = case
    value['schema']['dtypes']['amount'] = 'float64'
    with pytest.raises(ValueError):
        lifecycle.stage(env['admin'], account['user'], ds, 1, value, digest(value))
