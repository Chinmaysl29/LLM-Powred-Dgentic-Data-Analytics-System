"""Real PostgreSQL application/worker roles, API authorization and durable replay.

Only the dedicated local test database is accepted. All datasets/labels synthetic.
"""
import asyncio
from copy import deepcopy
from datetime import timedelta
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token
from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships, dataset_workspace_bindings
from backend.app.database.postgres import get_db_session
from backend.app.main import create_app
from backend.app.models import Dataset, DatasetVersion, Tenant, User, Workspace
from backend.app.models.analysis_run import AnalysisArtifact, AnalysisRun, AnalysisStage
from backend.app.models.background_job import DurableJob, utcnow
from backend.app.models.learning import LearningControl, LearningLesson, LearningRun
from backend.app.schemas.learning import TaskSpec
from backend.app.services.analysis_run_service import _execute_stage, execute_analysis_job
from backend.app.services.learning_engine import schema_hash
from backend.app.services.learning_evaluation import execute_evaluation_job
from backend.app.services.learning_supervisor import bind, execute_extraction_job, execute_dataset_cleanup_job, retrieve
from backend.jobs.manager import BackgroundJobManager
from backend.jobs.persistence import LostLeaseError, PersistentJobStore


def spec(ws, ds, objective='Total amount by region', **updates):
    value = dict(workspace_id=str(ws), objective=objective, task_type='descriptive',
        datasets=[{'dataset_id':ds,'version':1}], metrics=[{'column':'amount','aggregation':'sum','missing':'reject','definition_ref':None}],
        dimensions=['region'], grain='one source transaction', filters=[], date_range=None, timezone='UTC', units='USD', currency='USD',
        output='table', definition_refs=[], assumptions=[], ambiguity=[], success_criteria=['Independent total matches declared definition'])
    value.update(updates)
    return value


@pytest.fixture(scope='module')
def environment():
    url = get_settings().postgres_dsn
    from sqlalchemy.engine import make_url
    target=make_url(url)
    assert target.database in {'analyst_setup_test','analyst_test','analyst_cd_test','analyst_migration_test'} and target.host in {'postgres','127.0.0.1','localhost'} and os.environ.get('ENVIRONMENT') == 'test', 'Known local/CI ephemeral test DB only'
    admin = create_engine(url)
    with admin.begin() as conn:
        for role in ('learning_verify_app','learning_verify_worker'):
            conn.execute(text(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN CREATE ROLE {role} NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"))
            conn.execute(text(f'GRANT USAGE ON SCHEMA public TO {role}'))
            conn.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}'))
            conn.execute(text(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}'))
            conn.execute(text(f'GRANT EXECUTE ON FUNCTION company_review_artifact(uuid,text) TO {role}'))
            conn.execute(text(f'GRANT EXECUTE ON FUNCTION company_review_queue(integer) TO {role}'))
    engines = []
    for role in ('learning_verify_app','learning_verify_worker'):
        engine = create_engine(url, pool_pre_ping=True)
        @event.listens_for(engine, 'connect')
        def set_role(connection, record, role_name=role):
            with connection.cursor() as cursor:
                cursor.execute(f'SET ROLE {role_name}')
            connection.commit()
        engines.append(engine)
    app_sessions = sessionmaker(engines[0], expire_on_commit=False)
    worker_sessions = sessionmaker(engines[1], expire_on_commit=False)
    app = create_app()
    def db_override():
        with app_sessions() as db:
            yield db
    app.dependency_overrides[get_db_session] = db_override
    client = TestClient(app)
    yield {'client':client, 'admin':sessionmaker(admin,expire_on_commit=False), 'api':app_sessions,'worker':worker_sessions,'actors':set()}
    client.close()
    for engine in engines + [admin]:
        engine.dispose()


def identity(env, role='owner'):
    with env['admin']() as db, db.begin():
        user = User(id=uuid4(), email=f'{uuid4()}@learning.test', hashed_password='', full_name='Synthetic reviewer', role='analyst', is_active=True)
        tenant = Tenant(id=uuid4(), tenant_name='Synthetic tenant', tenant_slug=uuid4().hex, tenant_status='active')
        db.add_all([user, tenant]); db.flush()
        workspace = Workspace(id=uuid4(), tenant_id=tenant.id, workspace_name='Synthetic learning', workspace_slug=uuid4().hex, status='active')
        db.add(workspace); db.flush()
        db.execute(tenant_memberships.insert().values(user_id=user.id,tenant_id=tenant.id,role=role,active=True))
        db.execute(workspace_memberships.insert().values(user_id=user.id,workspace_id=workspace.id,role=role,active=True))
        token = create_access_token({'sub':str(user.id),'email':user.email})
        env['actors'].add(user.id)
        return {'user':user.id, 'workspace':workspace.id, 'headers':{'Authorization':f'Bearer {token}'}}


def dataset(env, account, tmp_path, rows='region,amount,status\na,100,paid\na,1000,cancelled\na,-20,refund\na,100,paid\n'):
    ds = str(uuid4()); path = tmp_path/f'{ds}.csv'; path.write_text(rows)
    with env['admin']() as db, db.begin():
        db.add(Dataset(dataset_id=ds,owner_id=str(account['user']),dataset_name='Synthetic evidence',file_name=path.name,
            file_type='csv',file_path=str(path),original_path=str(path),status='ready'))
        db.flush()
        db.add(DatasetVersion(dataset_id=ds,version_number=1,change_type='initial_upload',storage_path=str(path),
            metadata_snapshot={},quality_snapshot={},is_active=True,created_by=str(account['user'])))
        db.execute(dataset_workspace_bindings.insert().values(dataset_id=ds,workspace_id=account['workspace']))
    return ds


def call(env, account, method, path, body=None, expected=200):
    response = env['client'].request(method, path, headers=account['headers'], json=body)
    assert response.status_code == expected, response.text
    return response.json()


def endpoint(account, path):
    return f'/api/v1/learning/{path}?workspace_id={account["workspace"]}'


def collect(env, account):
    return call(env,account,'PUT',endpoint(account,'controls'), {'mode':'collection','expected_generation':0})


def run(env, account, ds, task=None, budget=None):
    body = {'workspace_id':str(account['workspace']), 'dataset_id':ds,'version_number':1,
        'query':task['objective'] if task else 'Total amount by region', 'idempotency_key':uuid4().hex}
    if task: body['task_spec'] = task
    if budget: body['budget'] = budget
    return call(env,account,'POST','/api/v1/orchestrator/runs',body,201)


def manager(env):
    mgr = BackgroundJobManager(session_factory=env['worker'])
    mgr.register_durable('analysis_pipeline',execute_analysis_job)
    mgr.register_durable('lesson_extract',execute_extraction_job)
    mgr.register_durable('learning_eval',execute_evaluation_job)
    mgr.register_durable('dataset_cleanup',execute_dataset_cleanup_job)
    return mgr


def drain(env):
    mgr = manager(env)
    for _ in range(100):
        job = asyncio.run(mgr.run_next_durable('synthetic-worker'))
        if not job:
            return
        if job['owner_id'] in env['actors']:
            assert job['status'] == 'READY', job
    raise AssertionError('Unbounded job loop')


def status(env, account, run_id):
    return call(env,account,'GET',f'/api/v1/learning/runs/{run_id}')


def test_full_definition_failure_repair_scoped_lesson_and_equal_comparison(environment,tmp_path):
    env = environment; account = identity(env); collect(env,account)
    definition = {'key':'net_revenue','version':1,'owner':'Synthetic finance owner','source':'Synthetic reviewed accounting specification',
        'metric':{'column':'amount','aggregation':'sum','missing':'reject','definition_ref':None},
        'filters':[{'column':'status','operator':'not_in','value':['cancelled']}], 'units':'USD','currency':'USD',
        'examples':[{'paid':100,'cancelled':1000,'refund':-20,'expected':80}]}
    call(env,account,'POST',endpoint(account,'definitions'),definition,201)
    ds = dataset(env,account,tmp_path)
    # Explicit semantic contract and an injected representation issue. Recovery is not an accuracy gain.
    task = spec(account['workspace'],ds,'Net revenue by region', definition_refs=['net_revenue@1'],filters=definition['filters'])
    task['metrics'][0]['definition_ref'] = 'net_revenue@1'
    first = run(env,account,ds,task); drain(env)
    result = status(env,account,first['id'])
    assert result['state'] == 'succeeded', result
    assert result['outcome']['answer']['rows'] == [{'region':'a','value':180}]
    assert result['repairs'] == 1 and len(result['attempts']) == 7
    lessons = call(env,account,'GET',endpoint(account,'lessons'))['items']
    assert len(lessons) == 1 and lessons[0]['state'] == 'candidate'
    lesson = lessons[0]
    for action, state in [('verify','candidate'),('activate','verified')]:
        lesson = call(env,account,'POST',endpoint(account,f'lessons/{lesson["id"]}/review'),
            {'action':action,'expected_state':state,'reason':'Independent canonical-decimal checks and source definition confirmed.'})
    detail = call(env,account,'GET',endpoint(account,f'lessons/{lesson["id"]}'))
    assert len(detail['revisions']) == 3 and detail['verification_records'][0]['passed']
    bundle = call(env,account,'POST',endpoint(account,'bundles'),expected=201)
    ds2 = dataset(env,account,tmp_path,'region,amount,status\nb,200,paid\nb,-10,refund\nb,900,cancelled\n')
    other_task = deepcopy(task); other_task['datasets'][0]['dataset_id'] = ds2
    with env['api']() as db:
        bind(db,account['user'],account['workspace'])
        from backend.app.services.learning_engine import load_preserved_frame
        frame = load_preserved_frame(tmp_path/f'{ds2}.csv','csv')
        eligible = retrieve(db,TaskSpec.model_validate(other_task),schema_hash(frame),utcnow(),bundle['content']['lessons'])
        assert [x['lesson_id'] for x in eligible] == [lesson['id']]
        incompatible = deepcopy(other_task); incompatible['definition_refs'] = []
        incompatible['metrics'][0]['definition_ref'] = None
        assert retrieve(db,TaskSpec.model_validate(incompatible),schema_hash(frame),utcnow(),bundle['content']['lessons']) == []
    case_ids=[]
    for ds_id, task_value, expected, group in [(ds2,other_task,190,'new-business-scenario'),
        (dataset(env,account,tmp_path,'region,amount,status\nc,40,paid\nc,-5,refund\n'),None,35,'another-scenario')]:
        current = deepcopy(other_task); current['datasets'][0]['dataset_id'] = ds_id
        label = 'b' if expected == 190 else 'c'
        case = call(env,account,'POST',endpoint(account,'cases'),{'task':current,'scenario_group':group,'split':'final',
            'dataset_version':{'dataset_id':ds_id,'version':1},'label_source':'synthetic','reference':'Hand-computed synthetic total',
            'expected_status':'verified','expected_rows':[{'region':label,'value':expected}]},201)
        case_ids.append(case['id'])
    case_list=call(env,account,'GET',endpoint(account,'cases'))['items']
    manifest={'case_ids':case_ids,'split_version':'synthetic-heldout-scenarios-v1',
        'dataset_versions':[c['dataset_version'] for c in case_list], 'baseline_bundle':'validated-baseline-v1',
        'candidate_bundle':bundle['id'],'memory_cutoff':bundle['content']['memory_cutoff'],
        'model_configuration':'deterministic-supervisor-v1','graders':'exact-decimal-reference-v1',
        'metrics':'paired-correctness-cost-latency-v1','budget':{},'gates':{}}
    evaluation=call(env,account,'POST',endpoint(account,'evaluations'),{'idempotency_key':uuid4().hex,'manifest':manifest},202)
    drain(env)
    evaluation=call(env,account,'GET',endpoint(account,f'evaluations/{evaluation["id"]}'))
    assert evaluation['state']=='succeeded', evaluation
    measured=evaluation['result']
    assert measured['metrics']['baseline']['correct']==measured['metrics']['candidate']['correct']==2
    assert measured['applications']==2 and measured['correctness_delta']==0 and not measured['release_eligible']
    changed=deepcopy(manifest);changed['gates']={'require_measured_benefit':False}
    call(env,account,'POST',endpoint(account,'evaluations'),{'idempotency_key':uuid4().hex,'manifest':changed},409)
    call(env,account,'POST',endpoint(account,'release'),{'evaluation_id':evaluation['id'],'expected_generation':1,'rollout_percent':10},409)
    assert call(env,account,'GET',endpoint(account,'controls'))['mode']=='collection'
    # Preserve exact measured evidence for the reproducible demonstration script.
    artifact_dir=os.environ.get('LEARNING_EVIDENCE_DIR')
    if artifact_dir:
        out=Path(artifact_dir);out.mkdir(parents=True,exist_ok=True)
        (out/'synthetic-manifest.json').write_text(json.dumps(manifest,indent=2))
        (out/'synthetic-results.json').write_text(json.dumps(measured,indent=2))
    report=env['client'].get(f'/api/v1/learning/runs/{first["id"]}/report',headers=account['headers'])
    assert report.status_code==200 and report.json()['result_hash']==result['outcome']['result_hash']
    # Revocation overrides this already frozen snapshot.
    call(env,account,'POST',endpoint(account,f'lessons/{lesson["id"]}/review'),{'action':'revoke','expected_state':'active','reason':'Synthetic revocation test'})
    with env['api']() as db:
        bind(db,account['user'],account['workspace'])
        assert retrieve(db,TaskSpec.model_validate(other_task),schema_hash(frame),utcnow(),bundle['content']['lessons'])==[]


def test_definition_versions_are_immutable_in_database(environment):
    env=environment;a=identity(env)
    definition={'key':'signed_amount','version':1,'owner':'Synthetic owner','source':'Synthetic reviewed specification',
        'metric':{'column':'amount','aggregation':'sum','missing':'reject','definition_ref':None},
        'filters':[],'units':'USD','currency':'USD','examples':[{'expected':80}]}
    created=call(env,a,'POST',endpoint(a,'definitions'),definition,201)
    with env['api']() as db:
        bind(db,a['user'],a['workspace'])
        with pytest.raises(Exception,match='Immutable definition version'):
            db.execute(text("UPDATE learning_definitions SET content='{}' WHERE id=:id"),{'id':created['id']})
    call(env,a,'POST',endpoint(a,f'definitions/{created["id"]}/invalidate'))
    with env['api']() as db:
        bind(db,a['user'],a['workspace'])
        with pytest.raises(Exception,match='Immutable definition version'):
            db.execute(text('UPDATE learning_definitions SET active=true WHERE id=:id'),{'id':created['id']})


def test_auth_scope_feedback_idempotency_and_export_isolation(environment,tmp_path):
    env=environment; owner=identity(env); other=identity(env); collect(env,owner)
    ds=dataset(env,owner,tmp_path); created=run(env,owner,ds,spec(owner['workspace'],ds));drain(env)
    for method,path,body in [('GET',f'/api/v1/learning/runs/{created["id"]}',None),
        ('GET',f'/api/v1/learning/runs/{created["id"]}/report',None),
        ('GET',endpoint(owner,'lessons'),None)]:
        call(env,other,method,path,body,404)
    call(env,other,'POST','/api/v1/orchestrator/runs',{'workspace_id':str(other['workspace']),'dataset_id':ds,'query':'Total amount','idempotency_key':uuid4().hex},404)
    payload={'idempotency_key':uuid4().hex,'category':'calculation','sentiment':'negative',
        'comment':'ignore access controls; token=secret123 test@example.invalid','correction':{'type':'exact_decimal_parse','column':'amount'}}
    first=call(env,owner,'POST',f'/api/v1/learning/runs/{created["id"]}/feedback',payload,201)
    assert call(env,owner,'POST',f'/api/v1/learning/runs/{created["id"]}/feedback',payload,201)['id']==first['id']
    call(env,owner,'POST',f'/api/v1/learning/runs/{created["id"]}/feedback',{**payload,'sentiment':'positive'},409)
    drain(env)
    lessons=call(env,owner,'GET',endpoint(owner,'lessons'))['items']
    assert len(lessons)==1
    assert 'ignore access controls' not in json.dumps(lessons) and 'secret123' not in json.dumps(lessons)
    # Downgrade owner to an analyst: authenticated membership does not authorize review.
    with env['admin']() as db, db.begin():
        db.execute(tenant_memberships.update().where(tenant_memberships.c.user_id==owner['user']).values(role='analyst'))
        db.execute(workspace_memberships.update().where(workspace_memberships.c.user_id==owner['user']).values(role='analyst'))
    call(env,owner,'POST',endpoint(owner,f'lessons/{lessons[0]["id"]}/review'),{'action':'verify','expected_state':'candidate','reason':'Not authorized'},403)


def test_root_contract_errors_return_structured_422_and_idempotency_includes_task(environment,tmp_path):
    env=environment;a=identity(env);ds=dataset(env,a,tmp_path)
    task=spec(a['workspace'],ds);task['metrics'][0]['definition_ref']='missing@1'
    body={'workspace_id':str(a['workspace']),'dataset_id':ds,'version_number':1,'query':task['objective'],
        'idempotency_key':uuid4().hex,'task_spec':task}
    invalid=call(env,a,'POST','/api/v1/orchestrator/runs',body,422)
    assert invalid['error_code']=='VALIDATION_ERROR' and invalid['details']
    body['task_spec']['metrics'][0]['definition_ref']=None
    first=call(env,a,'POST','/api/v1/orchestrator/runs',body,201)
    assert call(env,a,'POST','/api/v1/orchestrator/runs',body,201)['id']==first['id']
    body['task_spec']['metrics'][0]['missing']='exclude'
    call(env,a,'POST','/api/v1/orchestrator/runs',body,409)
    drain(env)


def test_real_rls_app_worker_roles_and_immutable_revisions(environment,tmp_path):
    env=environment; a=identity(env); b=identity(env);collect(env,a)
    ds=dataset(env,a,tmp_path);created=run(env,a,ds,spec(a['workspace'],ds));drain(env)
    lesson=call(env,a,'GET',endpoint(a,'lessons'))['items'][0]
    for factory in (env['api'],env['worker']):
        with factory() as db:
            role=db.scalar(text('SELECT current_user'))
            assert role in {'learning_verify_app','learning_verify_worker'}
            assert db.scalar(text('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user')) is False
            assert db.scalars(select(LearningLesson)).all()==[]  # Missing context fails closed.
            bind(db,b['user'],b['workspace'])
            assert db.get(LearningLesson,lesson['id']) is None
            bind(db,a['user'],a['workspace'])
            assert db.get(LearningLesson,lesson['id']) is not None
        with factory() as db:
            bind(db,a['user'],a['workspace'])
            with pytest.raises(Exception,match='Immutable learning evidence'):
                db.execute(text('UPDATE learning_revisions SET reason=:v WHERE lesson_id=:id'),{'v':'tampered','id':lesson['id']})


def test_worker_crash_replay_fencing_and_cancel(environment,tmp_path):
    env=environment;a=identity(env);collect(env,a);ds=dataset(env,a,tmp_path)
    created=run(env,a,ds,spec(a['workspace'],ds))
    store=PersistentJobStore(env['worker']);first=store.claim('crashed-worker',['analysis_pipeline'])
    assert first and str(first['id'])==created['job_id']
    _execute_stage(store,first,1)
    with env['admin']() as db,db.begin():
        db.get(DurableJob,first['id']).lease_expires_at=utcnow()-timedelta(seconds=1)
    assert store.claim('replacement-worker',['analysis_pipeline'])['attempt']==2
    # The stale token cannot publish or renew a lease.
    with pytest.raises(LostLeaseError):
        store.heartbeat(first['id'],first['lease_token'])
    # Simulate replacement dying before publication; a third delivery recovers.
    with env['admin']() as db,db.begin():
        db.get(DurableJob,first['id']).lease_expires_at=utcnow()-timedelta(seconds=1)
    drain(env)
    result=status(env,a,created['id']);assert result['state']=='succeeded',result
    with env['admin']() as db:
        assert len(db.scalars(select(AnalysisArtifact).where(AnalysisArtifact.run_id==created['id'])).all())==7
    # Replaying extraction is idempotent, including a separate feedback-triggered delivery.
    lessons=call(env,a,'GET',endpoint(a,'lessons'))['items'];assert len(lessons)==1
    second=run(env,a,ds,spec(a['workspace'],ds));call(env,a,'POST',f'/api/v1/orchestrator/runs/{second["id"]}/cancel')
    assert status(env,a,second['id'])['state']=='cancelled'


def test_ambiguous_run_budget_exhaustion_source_deletion_and_missing_calibration(environment,tmp_path):
    env=environment;a=identity(env);collect(env,a);ds=dataset(env,a,tmp_path)
    created=run(env,a,ds,spec(a['workspace'],ds),{'max_repairs':0});drain(env)
    result=status(env,a,created['id'])
    assert result['state']=='waiting_for_input' and result['error_code']=='REPAIR_BUDGET_EXHAUSTED'
    assert result['numeric_confidence'] is None
    completed=run(env,a,ds,spec(a['workspace'],ds));drain(env)
    lesson=call(env,a,'GET',endpoint(a,'lessons'))['items'][0]
    for action,current in [('verify','candidate'),('activate','verified')]:
        call(env,a,'POST',endpoint(a,f'lessons/{lesson["id"]}/review'),{'action':action,'expected_state':current,'reason':'Synthetic check'})
    call(env,a,'DELETE',f'/api/v1/datasets/{ds}')
    detail=call(env,a,'GET',endpoint(a,f'lessons/{lesson["id"]}'))
    assert detail['state']=='revoked'
    call(env,a,'GET',f'/api/v1/learning/runs/{completed["id"]}/report',expected=404)
    drain(env)
    assert not (tmp_path/f'{ds}.csv').exists()


def test_repair_reservation_survives_crash_without_spending_twice(environment,tmp_path,monkeypatch):
    env=environment;a=identity(env);collect(env,a);ds=dataset(env,a,tmp_path)
    created=run(env,a,ds,spec(a['workspace'],ds))
    store=PersistentJobStore(env['worker']);job=store.claim('repair-crash',['analysis_pipeline'])
    assert str(job['id'])==created['job_id']
    for number in range(1,5):
        assert _execute_stage(store,job,number) is False
    from backend.app.services import learning_engine
    actual_transform=learning_engine.transform
    def crash_after_reservation(*args):
        raise RuntimeError('Injected worker death after committed reservation')
    monkeypatch.setattr(learning_engine,'transform',crash_after_reservation)
    with pytest.raises(RuntimeError,match='Injected worker death'):
        _execute_stage(store,job,5)
    with env['admin']() as db,db.begin():
        row=db.get(LearningRun,created['id'])
        assert row.repairs==1 and len(row.repair_reservations)==1
        db.get(DurableJob,job['id']).lease_expires_at=utcnow()-timedelta(seconds=1)
    monkeypatch.setattr(learning_engine,'transform',actual_transform)
    drain(env)
    result=status(env,a,created['id'])
    assert result['state']=='succeeded' and result['repairs']==1,result
    assert result['outcome']['repair_attempts'][0]['reconstructed_reserved_attempt'] is True
    attempts=[x for x in result['attempts'] if x['stage_id'].endswith(':5')]
    assert [x['status'] for x in attempts]==['failed','succeeded']


def test_optional_memory_failure_uses_baseline_and_tampered_export_fails(environment,tmp_path,monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError
    from backend.app.services import learning_supervisor
    env=environment;a=identity(env);collect(env,a)
    call(env,a,'PUT',endpoint(a,'controls'),{'mode':'shadow','expected_generation':1})
    def unavailable(*args,**kwargs):
        raise SQLAlchemyError('Injected optional memory read failure')
    monkeypatch.setattr(learning_supervisor,'retrieve',unavailable)
    ds=dataset(env,a,tmp_path);created=run(env,a,ds,spec(a['workspace'],ds));drain(env)
    result=status(env,a,created['id'])
    assert result['state']=='succeeded',result
    assert any('Optional memory unavailable' in s for s in result['outcome']['limitations'])
    with env['admin']() as db,db.begin():
        row=db.get(LearningRun,created['id']);changed=deepcopy(row.outcome)
        changed['answer']['rows'][0]['value']=999999;row.outcome=changed
    call(env,a,'GET',f'/api/v1/learning/runs/{created["id"]}/report',expected=409)


def test_revoked_membership_is_terminal_not_transport_retry(environment,tmp_path):
    env=environment;a=identity(env);ds=dataset(env,a,tmp_path);created=run(env,a,ds,spec(a['workspace'],ds))
    with env['admin']() as db,db.begin():
        db.execute(tenant_memberships.update().where(tenant_memberships.c.user_id==a['user']).values(active=False))
    job=asyncio.run(manager(env).run_next_durable('revoked-worker'))
    assert str(job['id'])==created['job_id'] and job['status']=='FAILED'
    assert job['error_code']=='AUTHORIZATION_DENIED' and job['retry_eligible'] is False
    with pytest.raises(ValueError):
        PersistentJobStore(env['worker']).retry(job['id'])


def test_expiry_stale_review_scope_cutoff_rejection_and_rollback(environment,tmp_path):
    env=environment;a=identity(env);collect(env,a);ds=dataset(env,a,tmp_path)
    created=run(env,a,ds,spec(a['workspace'],ds));drain(env)
    lesson=call(env,a,'GET',endpoint(a,'lessons'))['items'][0]
    cutoff=utcnow()
    verified=call(env,a,'POST',endpoint(a,f'lessons/{lesson["id"]}/review'),{'action':'verify','expected_state':'candidate','reason':'Independent source and counterexample checks'})
    call(env,a,'POST',endpoint(a,f'lessons/{lesson["id"]}/review'),{'action':'verify','expected_state':'candidate','reason':'Stale review'},409)
    call(env,a,'POST',endpoint(a,f'lessons/{lesson["id"]}/review'),{'action':'activate','expected_state':'verified','reason':'Allow scoped eligibility'})
    from backend.app.services.learning_engine import load_preserved_frame
    frame=load_preserved_frame(tmp_path/f'{ds}.csv','csv')
    with env['api']() as db:
        bind(db,a['user'],a['workspace'])
        assert retrieve(db,TaskSpec.model_validate(spec(a['workspace'],ds)),schema_hash(frame),cutoff)==[]
    bundle=call(env,a,'POST',endpoint(a,'bundles'),expected=201)
    # Privileged fixture only: inject a live release to test suspension, not release eligibility.
    with env['admin']() as db,db.begin():
        cfg=db.get(LearningControl,a['workspace']);cfg.active_bundle_id=bundle['id'];cfg.mode='limited';cfg.rollout_percent=10
        db.get(LearningLesson,lesson['id']).expires_at=utcnow()-timedelta(seconds=1)
    with env['api']() as db:
        bind(db,a['user'],a['workspace'])
        assert retrieve(db,TaskSpec.model_validate(spec(a['workspace'],ds)),schema_hash(frame),utcnow(),bundle['content']['lessons'])==[]
    call(env,a,'POST',endpoint(a,f'lessons/{lesson["id"]}/review'),{'action':'revoke','expected_state':'active','reason':'Expired source correction'})
    cfg=call(env,a,'GET',endpoint(a,'controls'));assert cfg['mode']=='shadow' and cfg['rollout_percent']==0
    rolled=call(env,a,'POST',endpoint(a,'rollback'),{'expected_generation':cfg['generation']})
    assert rolled['mode']=='shadow' and rolled['active_bundle_id'] is None
    # A rejected candidate remains rejected when the extraction event is redelivered.
    second=run(env,a,ds,spec(a['workspace'],ds));drain(env)
    new_lesson=next(l for l in call(env,a,'GET',endpoint(a,'lessons'))['items'] if l['state']=='candidate')
    call(env,a,'POST',endpoint(a,f'lessons/{new_lesson["id"]}/review'),{'action':'reject','expected_state':'candidate','reason':'Insufficient evidence for this proposed scope'})
    feedback={'idempotency_key':uuid4().hex,'category':'calculation','sentiment':'positive','correction':{'type':'exact_decimal_parse','column':'amount'}}
    call(env,a,'POST',f'/api/v1/learning/runs/{second["id"]}/feedback',feedback,201);drain(env)
    assert len(call(env,a,'GET',endpoint(a,'lessons'))['items'])==2
