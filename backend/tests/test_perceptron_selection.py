"""Real isolated SQL, deterministic chart execution, and mocked provider transports."""
import asyncio
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import SecretStr
from sqlalchemy import select, update
from backend.tests.test_verified_learning_integration import environment, identity, dataset
from backend.app.core.config import get_settings
from backend.app.models import DatasetVersion
from backend.app.learning import selection_lifecycle as lifecycle, selection_runtime as runtime, selection_store as store
from backend.app.learning.selection_contract import manifest, train, evaluate
from backend.app.learning.selection_models import ChartPolicy, ProviderBandit, chart_options, outcome
from backend.app.learning.selection_provider import scoped_classifier
from backend.app.learning.memory_contract import digest
from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
from backend.app.services.intent_classification_service import IntentClassificationService
from backend.app.llm.provider import LLMProvider

SCHEMA = {'columns': ['date', 'amount'], 'dtypes': {'date': 'object', 'amount': 'int64'}}
CONTEXT = {'temporal': True, 'points': 3, 'dimensions': 1, 'ranking': False, 'explicit': False}
MODELS = {'groq': 'groq-reviewed-v1', 'gemini': 'gemini-reviewed-v1'}


def reviewed_cases(kind):
    cases = []
    for split, count in (('train', 10), ('golden', 30)):
        for i in range(count):
            row = {'id': f'{split}-{i}', 'group': f'{split}-scenario-{i}', 'split': split}
            if kind == 'chart':
                context = {**CONTEXT, 'temporal': i % 2 == 0, 'points': i + 2,
                    'ranking': i % 7 == 6, 'explicit': i % 7 == 5}
                row.update(context=context, expected='line' if len(chart_options(context)) == 2 else 'bar')
            else:
                row['outcomes'] = {'groq': {'correct': True, 'latency_ms': 9000 + i, 'cost_usd': .008},
                    'gemini': {'correct': True, 'latency_ms': 1000 + i, 'cost_usd': .001}}
            cases.append(row)
    return {'format': 1, 'kind': kind, 'models': MODELS if kind == 'provider' else {}, 'cases': cases}


def fixture_case(environment, tmp_path, monkeypatch, kind):
    monkeypatch.setattr(get_settings(), 'learning_enabled', True)
    account = identity(environment)
    ds = dataset(environment, account, tmp_path, 'date,amount\n2025-01-01,10\n2025-02-01,-5\n2025-04-01,20\n')
    with environment['admin']() as db, db.begin():
        db.execute(update(DatasetVersion).where(DatasetVersion.dataset_id == ds).values(metadata_snapshot=SCHEMA))
    return environment, account, ds, reviewed_cases(kind)


@pytest.fixture
def case(environment, tmp_path, monkeypatch):
    return fixture_case(environment, tmp_path, monkeypatch, 'chart')


@pytest.fixture
def provider_case(environment, tmp_path, monkeypatch):
    return fixture_case(environment, tmp_path, monkeypatch, 'provider')


def stage(case):
    env, account, ds, value = case
    return lifecycle.stage(env['admin'], account['user'], ds, 1, value['kind'], value, digest(value))['version']


def decide(case):
    _, account, ds, value = case
    return runtime.decide(account['user'], ds, 1, value['kind'], CONTEXT if value['kind'] == 'chart' else list(MODELS))


def promote(case, version, expected=0):
    env, account, ds, value = case
    return lifecycle.promote(env['admin'], account['user'], ds, 1, value['kind'], version, expected, value, digest(value))


def activate(case):
    version = stage(case)
    assert decide(case) is None
    result = promote(case, version)
    assert result['promoted'], result
    return version


@pytest.mark.parametrize('kind', ['chart', 'provider'])
def test_real_reviewed_evaluator_and_no_tie_promotion(kind):
    value = reviewed_cases(kind); model = train(value)
    report = evaluate(value, model)
    assert report['passed'] and report['all_correct'] and report['cases'] == 30, report
    assert not evaluate(value, model, model)['passed']
    if kind == 'provider':
        bandit = ProviderBandit(model)
        assert bandit.probabilities() == pytest.approx({'groq': .025, 'gemini': .975})
        assert bandit.choose(np.random.default_rng(42)) in MODELS
    else:
        assert ChartPolicy(model).predict(CONTEXT) == 'line'


@pytest.mark.parametrize('change', ['leak', 'duplicate', 'unsafe_chart', 'unknown_arm', 'missing_cost', 'nonfinite'])
def test_review_contract_rejects_unsafe_or_unpaired_evidence(change):
    value = reviewed_cases('chart' if change in ('leak', 'duplicate', 'unsafe_chart') else 'provider')
    if change == 'leak':
        value['cases'][-1]['group'] = value['cases'][0]['group']
    elif change == 'duplicate':
        value['cases'][-1]['id'] = value['cases'][0]['id']
    elif change == 'unsafe_chart':
        value['cases'][1]['expected'] = 'line'
    elif change == 'unknown_arm':
        value['models'] = {'unknown': 'x', 'gemini': 'y'}
    elif change == 'missing_cost':
        value['cases'][0]['outcomes']['groq']['cost_usd'] = None
    else:
        value['cases'][0]['outcomes']['groq']['latency_ms'] = float('inf')
    with pytest.raises(ValueError):
        manifest(value)


def test_exploration_excludes_failed_and_untried_arms():
    model = train(reviewed_cases('provider'))
    model['arms']['gemini']['correct'] -= 1
    assert ProviderBandit(model).probabilities() == {'groq': 1.0}
    model['arms']['groq'] = {'count': 0, 'correct': 0, 'reward': 0}
    assert ProviderBandit(model).choose() is None
    with pytest.raises(ValueError):
        ChartPolicy([[float('nan')] * 6] * 2)
    with pytest.raises(ValueError):
        outcome({'correct': 1, 'latency_ms': 0, 'cost_usd': 0})


def test_shadow_required_and_chart_rollback(case):
    env, account, ds, _ = case
    version = stage(case)
    with pytest.raises(ValueError):
        promote(case, version)
    assert decide(case) is None
    assert promote(case, version)['promoted']
    assert decide(case)['choice'] == 'line'
    lifecycle.rollback(env['admin'], account['user'], ds, 1, 'chart', 0, version)
    assert decide(case) is None
    lifecycle.rollback(env['admin'], account['user'], ds, 1, 'chart', version, 0)
    assert decide(case)['choice'] == 'line'


def test_chart_chat_changes_only_type_and_never_trains(case, monkeypatch):
    env, account, ds, _ = case
    activate(case)
    monkeypatch.setattr(ChartPolicy, 'update', lambda *a, **k: pytest.fail('Request trained policy'))
    outputs = []
    for flag in (False, True):
        monkeypatch.setattr(get_settings(), 'learning_enabled', flag)
        response = env['client'].post('/api/v1/chat', headers=account['headers'], json={
            'message': 'monthly amount', 'dataset_id': ds, 'workspace_id': str(account['workspace'])})
        assert response.status_code == 200, response.text
        outputs.append({key: response.json()[key] for key in ('data', 'plan', 'kpis', 'answer', 'chart')})
    assert outputs[0]['chart']['chart_type'] == 'bar' and outputs[1]['chart']['chart_type'] == 'line'
    outputs[1]['chart']['chart_type'] = 'bar'
    assert outputs[0] == outputs[1]
    assert outputs[1]['chart']['points'] == [{'label': '2025-01', 'value': 10.0}, {'label': '2025-02', 'value': -5.0}, {'label': '2025-04', 'value': 20.0}]


def test_chart_rejects_inconsistent_or_unordered_series(case):
    import pandas as pd
    frame = pd.DataFrame({'date': ['2025-01-01', '2025-02-01'], 'amount': [10, -5]})
    result = asyncio.run(NaturalLanguageAnalyticsService().analyze('monthly amount', dataframe=frame,
        dataset_id=case[2], dataset_version=1))
    assert runtime.chart_context('monthly amount', result)['temporal']
    assert runtime.chart_context('monthly amount line chart', result)['explicit']
    for change in ('value', 'order', 'label', 'multigroup'):
        modified = deepcopy(result)
        if change == 'value':
            modified['chart']['points'][0]['value'] = 999
        elif change == 'order':
            modified['chart']['points'].reverse(); modified['data'].reverse()
        elif change == 'label':
            modified['chart']['points'][0]['label'] = '2025-99'; modified['data'][0]['date'] = '2025-99'
        else:
            modified['plan']['dimensions'] = ['category']
        context = runtime.chart_context('monthly amount', modified)
        assert context is None or not context['temporal']


def test_disabled_missing_scope_and_outage_fallback(case, monkeypatch):
    monkeypatch.setattr(get_settings(), 'learning_enabled', False)
    monkeypatch.setattr(runtime, 'create_engine', lambda *a, **k: pytest.fail('Flag off touched DB'))
    assert decide(case) is None
    monkeypatch.setattr(get_settings(), 'learning_enabled', True)
    monkeypatch.setattr(runtime, 'create_engine', lambda *a, **k: (_ for _ in ()).throw(OSError('offline')))
    assert decide(case) is None


def test_scope_revocation_and_integrity(case, monkeypatch):
    from backend.app.core.workspace_authorization import workspace_memberships
    env, account, ds, _ = case
    version = activate(case)
    outsider = identity(env)
    assert runtime.decide(outsider['user'], ds, 1, 'chart', CONTEXT) is None
    assert runtime.decide(account['user'], ds, 99, 'chart', CONTEXT) is None
    with monkeypatch.context() as patch:
        patch.setattr(store, 'fingerprint', lambda: '0' * 64)
        assert decide(case) is None
    with env['admin']() as db, db.begin():
        db.execute(workspace_memberships.update().where(workspace_memberships.c.user_id == account['user']).values(active=False))
    assert decide(case) is None


def test_runtime_roles_cannot_release_or_modify_audit(case):
    env, account, ds, value = case
    with pytest.raises(Exception):
        lifecycle.stage(env['api'], account['user'], ds, 1, 'chart', value, digest(value))
    outsider = identity(env)
    with pytest.raises(Exception):
        lifecycle.stage(env['admin'], outsider['user'], ds, 1, 'chart', value, digest(value))
    stage(case)
    with env['api']() as db, db.begin():
        current = runtime.scope(db, account['user'], ds, 1)
        assert db.execute(store.events.update().where(store.events.c.dataset_id == ds).values(action='promote')).rowcount == 0
        assert db.execute(store.events.delete().where(store.events.c.dataset_id == ds)).rowcount == 0
    with pytest.raises(Exception):
        with env['api']() as db, db.begin():
            current = runtime.scope(db, account['user'], ds, 1)
            store.event(db, current, 'chart', 'promote', 1, reviewer=account['user'])


def fake_provider(case, monkeypatch, failures=(), mismatch=False):
    settings = get_settings()
    monkeypatch.setattr(settings, 'groq_api_key', SecretStr('synthetic-not-a-key'))
    monkeypatch.setattr(settings, 'gemini_api_key', SecretStr('synthetic-not-a-key'))
    monkeypatch.setattr(settings, 'openai_api_key', None)
    monkeypatch.setattr(ProviderBandit, 'choose', lambda self, rng=None: 'gemini')
    calls = []
    class Model:
        def __init__(self, name):
            self.name = name; self.model_name = MODELS[name]; self.model = 'changed-model' if mismatch else MODELS[name]
        async def ainvoke(self, messages):
            calls.append((self.name, [(type(m).__name__, m.content) for m in messages]))
            if self.name in failures:
                if 'invalid' in failures:
                    raise ValueError('Synthetic invalid input')
                raise RuntimeError('Synthetic transport unavailable')
            return SimpleNamespace(content='{"intent":"eda_analysis","confidence":0.9,"reasoning":"Synthetic validated response"}')
    monkeypatch.setattr(LLMProvider, '_init_groq', lambda self: Model('groq'))
    monkeypatch.setattr(LLMProvider, '_init_gemini', lambda self: Model('gemini'))
    monkeypatch.setattr(LLMProvider, '_init_openai', lambda self: pytest.fail('Unconfigured provider attempted'))
    base = LLMProvider(settings)
    service = IntentClassificationService(llm=base)
    scoped = scoped_classifier(service, str(case[1]['user']), case[2], 1)
    return base, scoped, calls


def test_provider_order_fallback_prompts_and_no_shared_mutation(provider_case, monkeypatch):
    activate(provider_case)
    base, service, calls = fake_provider(provider_case, monkeypatch, failures=('gemini',))
    answer = asyncio.run(service.classify('perform exploratory analysis', dataset_id=provider_case[2]))
    assert answer.intent == 'eda_analysis'
    assert [name for name, _ in calls] == ['gemini', 'groq']
    assert calls[0][1] == calls[1][1]
    assert base._chat_model is None and base._provider_name == 'none'
    monkeypatch.setattr(ProviderBandit, 'update', lambda *a, **k: pytest.fail('Unreviewed success trained bandit'))
    asyncio.run(service.classify('perform exploratory analysis', dataset_id=provider_case[2]))


def test_model_identity_drift_retains_original_provider_order(provider_case, monkeypatch):
    activate(provider_case)
    _, service, calls = fake_provider(provider_case, monkeypatch, mismatch=True)
    asyncio.run(service.classify('perform exploratory analysis', dataset_id=provider_case[2]))
    assert [name for name, _ in calls] == ['groq']
    assert runtime.decide(provider_case[1]['user'], provider_case[2], 1, 'provider', ['groq']) is None


def test_provider_flag_off_and_single_configured_arm_keep_service(provider_case, monkeypatch):
    base, service, _ = fake_provider(provider_case, monkeypatch)
    original = IntentClassificationService(llm=base)
    monkeypatch.setattr(get_settings(), 'learning_enabled', False)
    assert scoped_classifier(original, provider_case[1]['user'], provider_case[2]) is original
    monkeypatch.setattr(get_settings(), 'learning_enabled', True)
    monkeypatch.setattr(get_settings(), 'gemini_api_key', None)
    assert scoped_classifier(original, provider_case[1]['user'], provider_case[2]) is original


def test_quality_regression_in_any_exploration_arm_blocks_promotion(provider_case):
    provider_case[3]['cases'][-1]['outcomes']['groq']['correct'] = False
    version = stage(provider_case); decide(provider_case)
    result = promote(provider_case, version)
    assert not result['promoted'] and not result['evaluation']['all_correct']


def test_cli_status_and_disable(case):
    _, account, ds, _ = case
    version = activate(case)
    script = Path(__file__).resolve().parents[2] / 'scripts/perceptron_selection.py'
    common = ['--kind', 'chart', '--reviewer-id', str(account['user']), '--dataset-id', ds, '--dataset-version', '1']
    for command, extra in [('status', []), ('rollback', ['--version', '0', '--expected-version', str(version)])]:
        result = subprocess.run([sys.executable, str(script), command, *common, *extra], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['active_version' if command == 'status' else 'rolled_back']
    assert decide(case) is None


def test_authenticated_intent_endpoint_uses_scoped_provider(provider_case, monkeypatch):
    env, account, ds, _ = provider_case
    activate(provider_case)
    _, _, calls = fake_provider(provider_case, monkeypatch)
    response = env['client'].post('/api/v1/intent/classify', headers=account['headers'], json={
        'query': 'perform exploratory analysis', 'dataset_id': ds})
    assert response.status_code == 200, response.text
    assert response.json()['intent'] == 'eda_analysis'
    assert [name for name, _ in calls] == ['gemini']


def test_invalid_provider_input_is_not_retried(provider_case, monkeypatch):
    activate(provider_case)
    _, service, calls = fake_provider(provider_case, monkeypatch, failures=('gemini', 'invalid'))
    with pytest.raises(ValueError):
        asyncio.run(service._llm.chat('invalid synthetic input'))
    assert [name for name, _ in calls] == ['gemini']


def test_concurrent_stages_are_versioned_independently(case):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        versions = list(executor.map(lambda _: stage(case), range(2)))
    assert sorted(versions) == [1, 2]


def test_release_changes_during_evaluation_block_promotion(case, monkeypatch):
    env, account, ds, _ = case
    version = stage(case); decide(case)
    original = lifecycle.evaluate
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        lifecycle.rollback(env['admin'], account['user'], ds, 1, 'chart', 0, 0)
        return result
    monkeypatch.setattr(lifecycle, 'evaluate', changed)
    with pytest.raises(ValueError):
        promote(case, version)
    assert decide(case) is None


def test_audit_failure_rolls_back_activation(case, monkeypatch):
    env, account, ds, _ = case
    version = stage(case); decide(case)
    def broken(*args, **kwargs):
        raise RuntimeError('Synthetic audit failure')
    monkeypatch.setattr(store, 'event', broken)
    with pytest.raises(RuntimeError):
        promote(case, version)
    with env['admin']() as db:
        current = lifecycle.access(db, account['user'], ds, 1)
        assert store.active(db, current.tenant_id, 'chart') == 0


def test_payload_tampering_and_changed_manifest_are_rejected(case):
    env, account, ds, value = case
    version = activate(case)
    with env['admin']() as db, db.begin():
        current = lifecycle.access(db, account['user'], ds, 1)
        payload = deepcopy(store.read(db, current.tenant_id, 'chart', version))
        payload['model'][0][0] += 1
        db.execute(store.weights.update().where(store.condition(current.tenant_id, 'chart')).values(weights=payload))
    assert decide(case) is None
    value['cases'][0]['group'] += '-changed'
    with pytest.raises(ValueError):
        lifecycle.stage(env['admin'], account['user'], ds, 1, 'chart', value, '0' * 64)
