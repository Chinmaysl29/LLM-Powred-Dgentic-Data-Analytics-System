"""Real PG/RLS list contracts, per-parent bounds and fresh authorization."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import event, select, update

from backend.tests.test_verified_learning_integration import environment, identity
from backend.app.core.workspace_authorization import authorized_bound_dataset_ids, dataset_workspace_bindings
from backend.app.dataplane.records import artifacts, scoped
from backend.app.dataplane.read_models import latest_events, output_lineage
from backend.app.dataplane.company import current_event
from backend.app.models import Dataset, Workspace
from backend.app.models.background_job import DurableJob
from scripts.benchmark_company_reads import seed, account_from, verify


@pytest.fixture
def read_case(environment, tmp_path, monkeypatch):
    monkeypatch.setenv('DATAPLANE_ENABLED', 'true')
    saved = seed(environment, tmp_path/'fixture.json')
    return environment, saved, account_from(saved)


def request(case, endpoint, **params):
    env, saved, account = case
    return env['client'].get('/api/v1/dataplane/'+endpoint,
        params={'workspace_id': saved['workspace'], **params}, headers=account['headers'])


def test_page_contracts_and_constant_query_budgets(read_case):
    env, saved, account = read_case
    statements = []
    engine = env['api'].kw['bind']
    def capture(conn, cursor, sql, parameters, context, many):
        statements.append(sql)
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        for endpoint, budget in [('dashboard', 11), ('company/workflows', 12), ('company/incidents', 13)]:
            statements.clear()
            response = request(read_case, endpoint)
            assert response.status_code == 200, response.text
            verify(endpoint, response.json())
            assert len(statements) <= budget
            response = request(read_case, endpoint, offset=10000)
            assert response.status_code == 200
            assert response.json().get('items', response.json().get('records')) == []
        assert request(read_case, 'dashboard').headers['cache-control'] == 'private, no-store'
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    outsider = identity(env)
    response = env['client'].get('/api/v1/dataplane/company/workflows',
        params={'workspace_id': saved['workspace']}, headers=outsider['headers'])
    assert response.status_code == 404


def test_ten_runs_per_workflow_preserve_order_and_owner_scope(read_case):
    env, saved, account = read_case
    outsider = identity(env)
    expected = {}
    with env['admin']() as db, db.begin():
        for workflow in saved['workflows'][:2]:
            expected[workflow] = []
            for n in range(12):
                job = DurableJob(id=uuid4(), owner_id=account['user'], workspace_id=account['workspace'],
                    kind='dp_workflow', idempotency_key=uuid4().hex, status='FAILED', attempt=n,
                    payload={'workflow_id': workflow, 'schedule_slot': str(n)}, result={},
                    created_at=datetime(2026, 2, 1, tzinfo=timezone.utc)+timedelta(seconds=n))
                db.add(job)
                expected[workflow].insert(0, str(job.id))
            # An unrelated owner can never contribute a run, even with a forged workflow ID.
            db.add(DurableJob(owner_id=outsider['user'], workspace_id=account['workspace'],
                kind='dp_workflow', idempotency_key=uuid4().hex, status='FAILED',
                payload={'workflow_id': workflow}, result={}))
    result = request(read_case, 'company/workflows')
    assert result.status_code == 200, result.text
    for row in result.json()['items']:
        if row['id'] in expected:
            assert [run['id'] for run in row['recent_runs']] == expected[row['id']][:10]
            assert [run['schedule_slot'] for run in row['recent_runs']] == [str(n) for n in range(11, 1, -1)]
        else:
            assert len(row['recent_runs']) == 3


def test_lineage_limit_is_per_dataset_and_unknown_is_preserved(read_case):
    env, saved, account = read_case
    second = str(uuid4())
    unknown = uuid4()
    with env['admin']() as db, db.begin():
        tenant = db.get(Workspace, account['workspace']).tenant_id
        db.add(Dataset(dataset_id=second, owner_id=str(account['user']), dataset_name='Other synthetic metadata',
            file_name='none.csv', file_type='csv', file_path='/synthetic/no-source-read', status='ready'))
        db.flush()
        db.execute(dataset_workspace_bindings.insert().values(dataset_id=second, workspace_id=account['workspace']))
        values = []
        for dataset in [saved['dataset_id'], second]:
            for n in range(105):
                values.append(dict(id=unknown if dataset == second and n == 104 else uuid4(),
                    tenant_id=tenant, workspace_id=account['workspace'], actor_id=account['user'],
                    dataset_id=dataset, kind='evidence', payload={} if n == 104 else {'lineage': {'snapshot_id': saved['snapshot_id'], 'fields': ['amount']}},
                    created_at=datetime(2026, 3, 1, tzinfo=timezone.utc)+timedelta(seconds=n)))
        db.execute(artifacts.insert(), values)
    with env['api']() as db:
        access = scoped(db, account['user'], account['workspace'])
        result = output_lineage(db, access, [saved['dataset_id'], second])
        assert len(result[saved['dataset_id']]) == len(result[second]) == 100
        assert result[second][0]['id'] == unknown and result[second][0]['lineage'] is None
    response = request(read_case, 'company/incidents')
    assert response.status_code == 200, response.text
    assert all(len(row['affected_outputs']) == 100 and row['affected_outputs'][0]['impact'] == 'unknown' for row in response.json()['items'])


def test_batch_dataset_checks_reauthorize_lifecycle_owner_and_binding(read_case):
    env, saved, account = read_case
    outsider = identity(env)
    for factory in [env['api'], env['admin']]:
        with factory() as db:
            access = scoped(db, account['user'], account['workspace'])
            assert authorized_bound_dataset_ids(db, access, [saved['dataset_id'], str(uuid4())]) == {saved['dataset_id']}
    for status in ['archived', 'deleted', 'purged']:
        with env['admin']() as db, db.begin():
            db.execute(update(Dataset).where(Dataset.dataset_id == saved['dataset_id']).values(status=status))
        with env['admin']() as db:
            access = scoped(db, account['user'], account['workspace'])
            assert authorized_bound_dataset_ids(db, access, [saved['dataset_id']]) == set()
        assert request(read_case, 'dashboard').json()['records'] == []
        incidents = request(read_case, 'company/incidents')
        assert incidents.status_code == 404 or (incidents.status_code == 200 and incidents.json()['items'] == [])
    with env['admin']() as db, db.begin():
        db.execute(update(Dataset).where(Dataset.dataset_id == saved['dataset_id']).values(status='ready', owner_id=str(outsider['user'])))
    with env['admin']() as db:
        access = scoped(db, account['user'], account['workspace'])
        assert authorized_bound_dataset_ids(db, access, [saved['dataset_id']]) == set()
    with env['admin']() as db, db.begin():
        db.execute(update(Dataset).where(Dataset.dataset_id == saved['dataset_id']).values(owner_id=str(account['user'])))
        db.execute(dataset_workspace_bindings.update().where(dataset_workspace_bindings.c.dataset_id == saved['dataset_id']).values(workspace_id=outsider['workspace']))
    with env['admin']() as db:
        access = scoped(db, account['user'], account['workspace'])
        assert authorized_bound_dataset_ids(db, access, [saved['dataset_id']]) == set()
    with pytest.raises(HTTPException) as error:
        authorized_bound_dataset_ids(None, access, [saved['dataset_id']])
    assert error.value.status_code == 503


def test_event_batches_match_revision_and_timestamp_ordering(read_case):
    env, saved, account = read_case
    parent = UUID(saved['workflows'][0])
    with env['admin']() as db, db.begin():
        tenant = db.get(Workspace, account['workspace']).tenant_id
        # Newer creation time must not win over the canonical review revision.
        db.execute(artifacts.insert().values(id=uuid4(), tenant_id=tenant, workspace_id=account['workspace'],
            actor_id=account['user'], dataset_id=saved['dataset_id'], parent_id=parent, kind='review',
            payload={'revision': 0, 'status': 'draft'}, created_at=datetime.now(timezone.utc)))
    with env['api']() as db:
        access = scoped(db, account['user'], account['workspace'])
        for kind in ['review', 'schedule']:
            batch = latest_events(db, access, saved['workflows'], kind)
            assert batch == {parent: current_event(db, access, parent, kind) for parent in saved['workflows']}
        assert latest_events(db, access, []) == {}
        assert latest_events(db, access, [uuid4()]) == {}


def test_workflow_page_bounds_and_missing_definition_fail_closed(read_case):
    env, saved, account = read_case
    with env['admin']() as db, db.begin():
        original = db.execute(select(artifacts).where(artifacts.c.id == UUID(saved['workflows'][0]))).mappings().one()
        rows = []
        for n in range(35):
            rows.append({**dict(original), 'id': uuid4(),
                'created_at': datetime(2026, 4, 1, tzinfo=timezone.utc)+timedelta(seconds=n)})
        db.execute(artifacts.insert(), rows)
    first = request(read_case, 'company/workflows').json()
    second = request(read_case, 'company/workflows', offset=50).json()
    assert len(first['items']) == 50 and first['next_offset'] == 50
    assert len(second['items']) == 5 and second['next_offset'] is None
    assert not {row['id'] for row in first['items']} & {row['id'] for row in second['items']}
    with env['admin']() as db, db.begin():
        from copy import deepcopy
        invalid = deepcopy(dict(original))
        invalid.update(id=uuid4(), created_at=datetime.now(timezone.utc))
        invalid['payload']['spec']['query']['definition_id'] = str(uuid4())
        db.execute(artifacts.insert().values(**invalid))
    response = request(read_case, 'company/incidents')
    assert response.status_code == 404 and response.json()['message'] == 'Definition not found'
