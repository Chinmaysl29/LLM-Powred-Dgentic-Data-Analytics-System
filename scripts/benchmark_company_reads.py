"""Repeatable list-read benchmark against the isolated real PG/RLS/API stack.

Synthetic metadata cardinality, not an analytics compute or production load test.
No credentials or SQL parameter values are written to benchmark artifacts.
"""
import argparse
from datetime import datetime, timedelta, timezone
import gc
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import sys
import threading
import time
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def configure():
    from sqlalchemy.engine import make_url
    target = make_url(os.environ.get('DATABASE_URL', ''))
    if target.database != 'analyst_setup_test' or target.host != 'postgres' or os.environ.get('ENVIRONMENT') != 'test':
        raise SystemExit('Only the existing isolated synthetic test database is permitted')
    for key in ('GROQ_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY', 'LANGSMITH_API_KEY'):
        os.environ.pop(key, None)
    os.environ.update(DATAPLANE_ENABLED='true', BACKGROUND_WORKER_ENABLED='false')
    from backend.app.core.config import Settings, get_settings
    Settings.model_config = {**Settings.model_config, 'env_file': None}
    get_settings.cache_clear()


def seed(env, destination):
    from backend.tests.test_verified_learning_integration import identity
    from backend.app.models import Workspace, Dataset
    from backend.app.models.background_job import DurableJob
    from backend.app.models.learning import BusinessDefinition
    from backend.app.core.workspace_authorization import dataset_workspace_bindings
    from backend.app.dataplane.records import artifacts
    account = identity(env)
    dataset_id, definition_id, snapshot_id = str(uuid4()), str(uuid4()), uuid4()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows, workflow_ids, evidence_ids = [], [], []
    with env['admin']() as db, db.begin():
        tenant = db.get(Workspace, account['workspace']).tenant_id
        db.add(Dataset(dataset_id=dataset_id, owner_id=str(account['user']), dataset_name='Synthetic list-performance metadata',
            file_name='metadata-only.csv', file_type='csv', file_path='/synthetic/no-source-read', status='ready'))
        db.flush()
        db.execute(dataset_workspace_bindings.insert().values(dataset_id=dataset_id, workspace_id=account['workspace']))
        db.add(BusinessDefinition(id=definition_id, workspace_id=account['workspace'], actor_id=account['user'],
            key='synthetic_read_total', version=1, active=True, content_hash='a'*64,
            content={'metric': {'column': 'amount', 'aggregation': 'sum'}, 'filters': [], 'units': 'USD'}, governance={}))
        def record(kind, payload, parent=None, identity=None):
            rid = identity or uuid4()
            rows.append(dict(id=rid, tenant_id=tenant, workspace_id=account['workspace'], actor_id=account['user'],
                dataset_id=dataset_id, parent_id=parent, kind=kind, payload=payload,
                created_at=start+timedelta(seconds=len(rows))))
            return rid
        record('snapshot', {'row_count': 4, 'schema': {'amount': 'int64', 'region': 'string'},
            'version_id': str(uuid4()), 'fixture': 'synthetic metadata only'}, identity=snapshot_id)
        for index in range(20):
            workflow = record('workflow', {'version': 1, 'spec': {'name': f'Synthetic report {index:02}',
                'purpose': 'List-cardinality benchmark only', 'require_artifact_review': True,
                'query': {'definition_id': definition_id, 'snapshot_id': str(snapshot_id),
                    'plan': {'metric': 'synthetic_read_total', 'dimensions': [], 'filters': []}}}})
            workflow_ids.append(str(workflow))
            record('review', {'revision': 1, 'status': 'review'}, workflow)
            record('review', {'revision': 2, 'status': 'approved'}, workflow)
            record('schedule', {'revision': 1, 'enabled': False, 'status': 'disabled'}, workflow)
            for attempt in range(3):
                output = record('evidence', {'contract_version': 1, 'validation_status': 'passed', 'coverage': 'full',
                    'rows': [{'region': f'g{n}', 'value': n} for n in range(100)],
                    'lineage': {'snapshot_id': str(snapshot_id), 'fields': ['amount']},
                    'definition_id': definition_id, 'query_hash': 'b'*64, 'result_hash': 'c'*64,
                    'sql': 'PRIVATE_SENTINEL', 'parameters': ['PRIVATE_SENTINEL']}, snapshot_id)
                evidence_ids.append(str(output))
                record('review', {'revision': 1, 'status': 'review'}, output)
                if attempt == 2:
                    record('review', {'revision': 2, 'status': 'approved'}, output)
                db.add(DurableJob(owner_id=account['user'], workspace_id=account['workspace'], kind='dp_workflow',
                    idempotency_key=uuid4().hex, status='READY', attempt=1,
                    payload={'workflow_id': str(workflow), 'dataset_id': dataset_id, 'require_artifact_review': True},
                    result={'artifact_id': str(output)}, created_at=start+timedelta(seconds=index*10+attempt)))
        for n in range(10):
            record('incident', {'definition_id': definition_id, 'snapshot_id': str(snapshot_id), 'coverage': 'full',
                'checks': [{'field': 'amount' if n%2 == 0 else 'unused', 'status': 'failed'}]}, snapshot_id)
        db.flush()
        db.execute(artifacts.insert(), rows)
    saved = {key: str(account[key]) for key in ('user', 'workspace')}
    saved.update(dataset_id=dataset_id, definition_id=definition_id, snapshot_id=str(snapshot_id),
                 workflows=workflow_ids, outputs=evidence_ids)
    destination.write_text(json.dumps(saved))
    return saved


def account_from(saved):
    from backend.app.core.security import create_access_token
    return {'user': UUID(saved['user']), 'workspace': UUID(saved['workspace']),
            'headers': {'Authorization': 'Bearer ' + create_access_token({'sub': saved['user']})}}


def verify(path, value):
    if path == 'company/workflows':
        assert len(value['items']) == 20
        assert all(item['review']['status'] == 'approved' and item['schedule']['enabled'] is False for item in value['items'])
        for item in value['items']:
            assert [run['status'] for run in item['recent_runs']] == ['succeeded', 'awaiting_review', 'awaiting_review']
    elif path == 'company/incidents':
        assert len(value['items']) == 10
        for item in value['items']:
            assert len(item['affected_outputs']) == 80
            expected = 'directly_affected' if item['checks'][0]['field'] == 'amount' else 'unaffected'
            assert all(output['impact'] == expected for output in item['affected_outputs'])
    else:
        assert len(value['records']) == 50 and len(value['jobs']) == 30 and value['next_offset'] == 50
        assert 'PRIVATE_SENTINEL' not in json.dumps(value)


def measure(env, saved, path, samples):
    import psutil
    from sqlalchemy import event
    engine = env['api'].kw['bind']
    account = account_from(saved)
    captured = []
    def before(conn, cursor, statement, parameters, context, many):
        context._perf_start = time.perf_counter()
    def after(conn, cursor, statement, parameters, context, many):
        captured.append((time.perf_counter()-context._perf_start)*1000)
    event.listen(engine, 'before_cursor_execute', before)
    event.listen(engine, 'after_cursor_execute', after)
    def request():
        response = env['client'].get('/api/v1/dataplane/'+path, params={'workspace_id': saved['workspace']}, headers=account['headers'])
        assert response.status_code == 200, response.text
        value = response.json()
        verify(path, value)
        return value
    try:
        for _ in range(5):
            request()
        gc.collect()
        process = psutil.Process()
        rss = [process.memory_info().rss]
        stop = threading.Event()
        def sample_memory():
            while not stop.wait(.01):
                rss.append(process.memory_info().rss)
        watcher = threading.Thread(target=sample_memory, daemon=True)
        watcher.start()
        times, queries, database_ms = [], [], []
        cpu_started = time.process_time()
        for _ in range(samples):
            captured.clear()
            started = time.perf_counter()
            value = request()
            times.append((time.perf_counter()-started)*1000)
            queries.append(len(captured))
            database_ms.append(sum(captured))
        cpu_seconds = time.process_time()-cpu_started
        stop.set(); watcher.join()
        ordered = sorted(times)
        quantile = lambda q: ordered[max(0, math.ceil(q*len(ordered))-1)]
        return {'samples': samples, 'warmups': 5, 'latency_ms': {'p50': quantile(.5), 'p95': quantile(.95), 'p99': quantile(.99)},
            'request_ms': times, 'sql_queries_per_request': queries, 'sql_duration_ms': database_ms,
            'sequential_requests_per_second': samples/(sum(times)/1000), 'client_process_cpu_seconds': cpu_seconds,
            'client_process_peak_rss_bytes': max(rss), 'response': value,
            'response_sha256': hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()}
    finally:
        if 'stop' in locals():
            stop.set()
            watcher.join()
        event.remove(engine, 'before_cursor_execute', before)
        event.remove(engine, 'after_cursor_execute', after)


def explain_reads(env, saved):
    """Inspect actual bounded statements under the same restricted role and scope."""
    from sqlalchemy import event
    from backend.app.dataplane.records import scoped
    account = account_from(saved)
    engine = env['api'].kw['bind']
    queries = []
    def capture(conn, cursor, statement, parameters, context, many):
        if 'row_number()' in statement:
            queries.append((statement, parameters))
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        for endpoint in ('company/workflows', 'company/incidents'):
            response = env['client'].get('/api/v1/dataplane/'+endpoint,
                params={'workspace_id': saved['workspace']}, headers=account['headers'])
            assert response.status_code == 200
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    plans = []
    with env['api']() as db:
        scoped(db, account['user'], account['workspace'])
        for statement, parameters in queries:
            plan = db.connection().exec_driver_sql('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+statement, parameters).scalar()
            plans.append(plan)
    return plans


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--fixture', default='/verification/optimization-workload.json')
    parser.add_argument('--samples', type=int, default=25)
    parser.add_argument('--explain', action='store_true')
    args = parser.parse_args()
    if not 5 <= args.samples <= 200:
        raise SystemExit('Use 5 to 200 bounded samples')
    configure()
    from backend.tests.test_verified_learning_integration import environment
    fixture = environment.__wrapped__()
    env = next(fixture)
    try:
        path = Path(args.fixture)
        saved = json.loads(path.read_text()) if path.exists() else seed(env, path)
        result = {'scope': 'Synthetic list metadata; restricted PG app role; FastAPI TestClient; sequential ASGI requests (no network latency)',
            'workload': {'workflows': 20, 'completed_runs_per_workflow': 3, 'incidents': 10, 'outputs_per_dataset': 80},
            'platform': {'python': platform.python_version(), 'logical_cpus': os.cpu_count()},
            'versions': {name: importlib.metadata.version(name) for name in ('fastapi', 'SQLAlchemy', 'psycopg')},
            'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
                ROOT/'backend/app/dataplane/api.py', ROOT/'backend/app/dataplane/company_api.py', ROOT/'backend/app/dataplane/company.py',
                ROOT/'backend/app/core/security.py', ROOT/'backend/app/core/workspace_authorization.py', ROOT/'backend/app/dataplane/read_models.py')},
            'endpoints': {}}
        for endpoint in ('dashboard', 'company/workflows', 'company/incidents'):
            result['endpoints'][endpoint] = measure(env, saved, endpoint, args.samples)
            print(json.dumps({'endpoint': endpoint, **{key: result['endpoints'][endpoint][key] for key in ('latency_ms', 'sql_queries_per_request')}}), flush=True)
        if args.explain:
            result['query_plans'] = explain_reads(env, saved)
        Path(args.output).write_text(json.dumps(result, indent=2))
    finally:
        try:
            next(fixture)
        except StopIteration:
            pass


if __name__ == '__main__':
    main()
