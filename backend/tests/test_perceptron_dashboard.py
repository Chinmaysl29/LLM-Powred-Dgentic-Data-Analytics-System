"""Actual scoped GETs against PostgreSQL, with synthetic reporting evidence only."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import json

import pytest
from sqlalchemy import event, select, text, update
from backend.tests.test_verified_learning_integration import environment, identity, dataset
from backend.app.core.config import get_settings
from backend.app.core.workspace_authorization import workspace_memberships, tenant_memberships
from backend.app.database.postgres import get_db_session
from backend.app.learning import dashboard as reporting
from backend.app.learning.tables import learner_weights, feedback_events
from backend.app.learning.shadow_table import shadow_predictions
from backend.app.learning.release_table import router_releases
from backend.app.learning.selection_table import selection_events
from backend.app.learning.column_table import resolver_events
from backend.app.models import Workspace, Dataset


def url(account, suffix=''):
    return f'/api/v1/perceptron/dashboard?workspace_id={account["workspace"]}{suffix}'


def seed(env, account, ds):
    now = datetime.now(timezone.utc) - timedelta(seconds=1)
    with env['admin']() as db, db.begin():
        tenant = db.scalar(select(Workspace.tenant_id).where(Workspace.id == account['workspace']))
        scope = dict(tenant_id=tenant, workspace_id=account['workspace'], actor_id=account['user'])
        for days, error in [(1, 'execution_error'), (2, 'execution_error'), (3, 'empty_result'), (40, 'validator_rejection')]:
            db.execute(feedback_events.insert().values(**scope, id=uuid4(), question=None, question_hash='a'*64,
                features={'dataset_id': ds, 'error_type': error}, signal_type='hard_failure', created_at=now-timedelta(days=days)))
        for abstain, live, predicted in [(False,'sum','sum'),(False,'sum','count'),(True,'sum','sum'),(False,None,'sum')]:
            db.execute(shadow_predictions.insert().values(**scope, id=uuid4(), dataset_id=ds, dataset_version=1,
                question_hash='a'*64, feature_version='v1', features={}, source='chat', live_route='analytics',
                live_intent=live, shadow_intent=predicted, candidate_intent=predicted, margin=1,
                abstained=abstain, model_source='tenant_candidate', model_version=1, model_digest='a'*64, created_at=now))
        full_scope = {**{k:str(v) for k,v in scope.items()}, 'dataset_id':ds, 'dataset_version':1, 'schema_hash':'a'*64}
        for learner in reporting.LEARNERS:
            db.execute(learner_weights.insert().values(id=uuid4(), tenant_id=tenant, learner=learner,
                version=1, weights={'scope':full_scope,'private':'DO_NOT_EXPOSE'}, is_active=False, created_at=now))
        db.execute(router_releases.insert().values(tenant_id=tenant, actor_id=account['user'], action='promote',
            version=1, previous_version=0, runtime_digest='a'*64, created_at=now,
            evidence={'manifest_digest':'a'*64,'gate':{'passed':True,'intent_count':34,'candidate_correct':34},'private':'DO_NOT_EXPOSE'}))
        common = dict(**scope, dataset_id=ds, dataset_version=1, schema_hash='a'*64, action='promote',
            version=1, previous_version=0, runtime_digest='a'*64, created_at=now)
        db.execute(resolver_events.insert().values(**common, detail={'manifest_digest':'b'*64,'cases':30,'correct':30,'passed':True}))
        for kind, score in [('chart',30),('provider',27)]:
            db.execute(selection_events.insert().values(**common, kind=kind,
                detail={'manifest_digest':'c'*64,'cases':30,'candidate_score':score,'all_correct':True,'passed':True}))
    return tenant


@pytest.fixture
def case(environment, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), 'learning_enabled', True)
    account = identity(environment); ds = dataset(environment, account, tmp_path)
    tenant = seed(environment, account, ds)
    return environment, account, ds, tenant


def read(case, suffix=''):
    env, account, *_ = case
    response = env['client'].get(url(account, suffix), headers=account['headers'])
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'private, no-store'
    return response.json()


def test_actual_dashboard_counts_accuracy_not_agreement_and_no_payloads(case):
    value = read(case)
    assert value['top_mistakes'] == [{'error_type':'execution_error','count':2},{'error_type':'empty_result','count':1}]
    assert value['shadow'] == dict(observations=4,abstentions=1,compared=2,agreements=1,agreement_rate=.5)
    assert len(value['evaluations']) == 4 and all(row['accuracy']==1 for row in value['evaluations'])
    provider = next(row for row in value['evaluations'] if row['learner']=='provider_bandit')
    assert provider['mean_reward'] == .9 and provider['correct'] == 30
    assert len(value['versions']) == 4
    assert 'DO_NOT_EXPOSE' not in json.dumps(value)
    assert all(set(row)=={'learner','version','selected','created_at'} for row in value['versions'])
    assert sum(row['count'] for row in read(case,'&days=90')['top_mistakes']) == 4


def test_flag_off_skips_learning_tables(case, monkeypatch):
    env, account, *_ = case
    monkeypatch.setattr(get_settings(), 'learning_enabled', False)
    engine = env['api'].kw['bind']; statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany): statements.append(statement.lower())
    event.listen(engine,'before_cursor_execute',capture)
    try: value=read(case)
    finally: event.remove(engine,'before_cursor_execute',capture)
    assert not value['enabled'] and not value['versions'] and not value['evaluations']
    assert not any('from '+name in sql for sql in statements for name in ('learner_weights','feedback_events','shadow_predictions','selection_events'))


@pytest.mark.parametrize('query',['&days=0','&days=91','&offset=-1','&offset=10001','&limit=0','&limit=101'])
def test_query_bounds(case, query):
    env, account, *_ = case
    assert env['client'].get(url(account,query),headers=account['headers']).status_code==422


def test_requires_auth_and_has_no_write_method(case):
    env, account, *_ = case
    assert env['client'].get(url(account)).status_code in (401,403)
    for method in ('post','put','patch','delete'):
        assert getattr(env['client'],method)(url(account),headers=account['headers']).status_code==405


def test_tenant_and_actor_isolation_even_with_privileged_connection(case, tmp_path):
    env, account, ds, tenant = case
    other=identity(env); other_ds=dataset(env,other,tmp_path);seed(env,other,other_ds)
    assert env['client'].get(url(account),headers=other['headers']).status_code==404
    # A different member of the same workspace sees tenant router metadata only.
    with env['admin']() as db, db.begin():
        db.execute(tenant_memberships.insert().values(tenant_id=tenant,user_id=other['user'],role='viewer',active=True))
        db.execute(workspace_memberships.insert().values(workspace_id=account['workspace'],user_id=other['user'],role='viewer',active=True))
    for factory in (env['api'],env['admin']):
        def override():
            with factory() as db: yield db
        original=env['client'].app.dependency_overrides[get_db_session]
        env['client'].app.dependency_overrides[get_db_session]=override
        try:
            response=env['client'].get(url(account),headers=other['headers'])
            assert response.status_code==200,response.text
            value=response.json()
            assert value['top_mistakes']==[] and value['shadow']['observations']==0
            assert [r['learner'] for r in value['versions']]==['intent_router']
            assert [r['learner'] for r in value['evaluations']]==['intent_router']
        finally: env['client'].app.dependency_overrides[get_db_session]=original


def test_revoked_membership_and_archived_dataset(case):
    env, account, ds, _ = case
    with env['admin']() as db, db.begin(): db.execute(update(Dataset).where(Dataset.dataset_id==ds).values(status='archived'))
    value=read(case)
    assert value['top_mistakes']==[] and value['shadow']['observations']==0
    assert len(value['versions'])==len(value['evaluations'])==1
    with env['admin']() as db, db.begin():
        db.execute(workspace_memberships.update().where(workspace_memberships.c.workspace_id==account['workspace']).values(active=False))
    assert env['client'].get(url(account),headers=account['headers']).status_code==404


def test_pagination_has_no_duplicates(case):
    first=read(case,'&limit=2');second=read(case,'&limit=2&offset=2')
    assert first['next_offset']==2 and second['next_offset'] is None
    assert len({r['learner'] for r in first['versions']+second['versions']})==4


def test_database_enforces_read_only_and_returns_sanitized_error(case, monkeypatch):
    env, account, *_=case
    def attempt_write(db,*args):
        assert db.scalar(text('SHOW transaction_read_only'))=='on'
        db.execute(feedback_events.delete())
    monkeypatch.setattr(reporting,'collect',attempt_write)
    response=env['client'].get(url(account),headers=account['headers'])
    assert response.status_code==503 and 'DELETE' not in response.text and 'postgres' not in response.text


@pytest.mark.parametrize('bad',[None,{}, {'manifest_digest':'a'*64,'cases':30,'correct':29,'passed':True},
    {'manifest_digest':'a'*64,'cases':0,'correct':0,'passed':True},
    {'manifest_digest':'a'*64,'cases':30,'correct':True,'passed':True}])
def test_malformed_reports_are_not_accuracy(bad):
    assert reporting.report_metrics('column_metric_resolver',bad) is None


def test_invalid_report_omitted_not_zero_accuracy(case):
    env,account,ds,tenant=case
    with env['admin']() as db,db.begin():
        db.execute(selection_events.update().where(selection_events.c.tenant_id==tenant).values(detail={'passed':True}))
    value=read(case)
    assert value['omitted_evaluations']==2 and len(value['evaluations'])==2


def test_empty_evidence_has_no_fabricated_accuracy(environment,monkeypatch):
    monkeypatch.setattr(get_settings(),'learning_enabled',True)
    account=identity(environment)
    value=read((environment,account))
    assert value['evaluations']==value['versions']==value['top_mistakes']==[]
    assert value['shadow']['agreement_rate'] is None


def test_evaluation_limit_is_explicit(case):
    env,account,_,tenant=case
    with env['admin']() as db,db.begin():
        db.execute(router_releases.insert(),[dict(tenant_id=tenant,actor_id=account['user'],action='promote',
            version=n+2,previous_version=0,runtime_digest='a'*64,
            evidence={'manifest_digest':'a'*64,'gate':{'passed':True,'intent_count':34,'candidate_correct':34}}) for n in range(101)])
    value=read(case)
    assert value['evaluations_truncated']
    assert len([r for r in value['evaluations'] if r['learner']=='intent_router'])==100


def test_missing_database_dependency_returns_unavailable(case):
    env,account,*_=case
    original=env['client'].app.dependency_overrides[get_db_session]
    env['client'].app.dependency_overrides[get_db_session]=lambda:None
    try:
        response=env['client'].get(url(account),headers=account['headers'])
        assert response.status_code==503,response.text
    finally: env['client'].app.dependency_overrides[get_db_session]=original
