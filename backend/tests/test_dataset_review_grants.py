"""Real restricted-role grants and two-person review; raw access stays private."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from sqlalchemy import select, text, update
from backend.tests.test_verified_learning_integration import environment
from backend.tests.test_dataplane_integration import case, call, finish, uploaded
from backend.tests.test_company_review import api, draft, query
from backend.app.core.security import create_access_token
from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships
from backend.app.models import User, Workspace
from backend.app.dataplane.records import artifacts, scoped
from backend.app.dataplane.reviewer import grants


def colleague(case, role='viewer'):
    env, account, *_ = case
    with env['admin']() as db, db.begin():
        workspace = db.get(Workspace, account['workspace'])
        user = User(id=uuid4(), email=f'{uuid4()}@review.synthetic.test', hashed_password='',
                    full_name='Synthetic peer reviewer', is_active=True, role='analyst')
        db.add(user)
        db.flush()
        db.execute(tenant_memberships.insert().values(tenant_id=workspace.tenant_id, user_id=user.id, role=role, active=True))
        db.execute(workspace_memberships.insert().values(workspace_id=workspace.id, user_id=user.id, role=role, active=True))
        token = create_access_token({'sub': str(user.id), 'email': user.email})
        return {'user': user.id, 'workspace': workspace.id, 'headers': {'Authorization': 'Bearer ' + token}}


def grant(case, snapshot, peer, revision=0):
    return api(case, 'PUT', f"review-grants/{snapshot['dataset_id']}/{peer['user']}", {
        'expected_revision': revision, 'expires_at': (datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),
        'reason': 'Explicit synthetic per-dataset reviewer grant'})


def grant_metadata(case, path, snapshot, peer=None):
    params = {'workspace_id': str(case[1]['workspace']), 'dataset_id': snapshot['dataset_id']}
    if peer:
        params['reviewer_id'] = str(peer['user'])
    response = case[0]['client'].get('/api/v1/dataplane/company/' + path,
        params=params, headers=case[1]['headers'])
    assert response.status_code == 200, response.text
    return response.json()


def approved_dictionary(case, snapshot, peer):
    row = api(case, 'POST', 'dictionary', draft(snapshot), 201)
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 0, 'action': 'review', 'reason': 'Request an independent review'})
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 1, 'action': 'approve', 'reason': 'Author cannot self-approve'}, 409)
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 1, 'action': 'approve', 'reason': 'Not yet granted'}, 404, peer)
    permission = grant(case, snapshot, peer)
    state = grant_metadata(case, 'review-grants/revision', snapshot, peer)
    assert state['revision'] == 1 and state['active'] is True
    assert grant_metadata(case, 'review-grants', snapshot)['items'][0]['reviewer_id'] == str(peer['user'])
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 1, 'action': 'approve', 'reason': 'Independent typed/schema/example review'}, actor=peer)
    return row, permission


def test_granted_peer_approves_definition_workflow_and_output_without_raw_access(case):
    snapshot = finish(case, uploaded(case))
    peer = colleague(case)
    row, permission = approved_dictionary(case, snapshot, peer)
    workflow = api(case, 'POST', 'workflows', {'name': 'Two-person synthetic report', 'purpose': 'Granted peer review',
        'query': query(row, snapshot), 'require_artifact_review': True}, 201)
    api(case, 'GET', 'reviews/' + workflow['id'], expected=404, actor=peer)  # Private draft.
    api(case, 'POST', 'artifacts/' + workflow['id'] + '/review', {'expected_revision': 0, 'action': 'review', 'reason': 'Submit exact manifest'})
    inbox = api(case, 'GET', 'reviews', actor=peer)
    assert [item['id'] for item in inbox['items']] == [workflow['id']]
    api(case, 'POST', 'artifacts/' + workflow['id'] + '/review', {'expected_revision': 1, 'action': 'approve', 'reason': 'Approve submitted manifest'}, actor=peer)
    assert api(case, 'GET', 'workflows')['items'][0]['review']['status'] == 'approved'
    api(case, 'POST', 'artifacts/' + workflow['id'] + '/review', {'expected_revision': 2, 'action': 'activate', 'reason': 'Review grant is not execution control'}, 403, peer)
    api(case, 'POST', 'artifacts/' + workflow['id'] + '/review', {'expected_revision': 2, 'action': 'activate', 'reason': 'Owner activates approved workflow'})
    result = finish(case, api(case, 'POST', 'workflows/' + workflow['id'] + '/run', {'idempotency_key': uuid4().hex}, 202))
    call(case, 'GET', 'evidence/' + result['id'] + '/report', expected=409)
    api(case, 'POST', 'artifacts/' + result['id'] + '/review', {'expected_revision': 0, 'action': 'review', 'reason': 'Submit actual result'})
    projected = api(case, 'GET', 'reviews/' + result['id'], actor=peer)
    assert projected['payload']['rows'] == [{'value': 24}]
    for private in ('sql', 'parameters', 'files', 'curated', 'report_artifact'):
        assert private not in projected['payload']
    api(case, 'POST', 'artifacts/' + result['id'] + '/review', {'expected_revision': 1, 'action': 'approve', 'reason': 'Independent result review'}, actor=peer)
    assert api(case, 'GET', 'workflows')['items'][0]['recent_runs'][0]['status'] == 'succeeded'
    assert call(case, 'GET', 'evidence/' + result['id'] + '/report').content.startswith(b'%PDF')
    for path in ('artifacts/' + snapshot['id'], 'artifacts/' + result['id'], 'evidence/' + result['id'] + '/report'):
        call(case, 'GET', path, expected=404, actor=peer)
    api(case, 'POST', 'query', query(row, snapshot), 403, peer)
    api(case, 'POST', 'workflows/' + workflow['id'] + '/run', {'idempotency_key': 'no-execution-grant'}, 403, peer)
    # Even the restricted app DB role sees no raw evidence through ordinary SELECT.
    with case[0]['api']() as db:
        access = scoped(db, peer['user'], peer['workspace'])
        assert db.execute(select(artifacts).where(artifacts.c.id == UUID(result['id']))).first() is None
        safe = db.scalar(text('SELECT company_review_artifact(CAST(:id AS uuid), NULL)'), {'id': result['id']})
        assert safe['payload']['rows'] == [{'value': 24}] and 'sql' not in safe['payload']
    api(case, 'POST', 'review-grants/' + permission['id'] + '/revoke', {'expected_revision': 1, 'reason': 'End review access'})
    api(case, 'GET', 'reviews/' + result['id'], expected=404, actor=peer)
    api(case, 'POST', 'artifacts/' + result['id'] + '/review', {'expected_revision': 2, 'action': 'approve', 'reason': 'Revoked grant'}, 404, peer)
    assert api(case, 'GET', 'evidence/' + result['id'])['review']['status'] == 'approved'  # Historical decision retained.
    assert api(case, 'GET', 'workflows')['items'][0]['recent_runs'][0]['status'] == 'succeeded'


def test_grants_reject_foreign_self_expired_and_cross_dataset_use(case):
    snapshot = finish(case, uploaded(case))
    peer = colleague(case)
    body = {'expected_revision': 0, 'expires_at': (datetime.now(timezone.utc)+timedelta(days=1)).isoformat(), 'reason': 'Synthetic isolation'}
    api(case, 'PUT', f"review-grants/{snapshot['dataset_id']}/{case[2]['user']}", body, 404)
    api(case, 'PUT', f"review-grants/{snapshot['dataset_id']}/{case[1]['user']}", body, 422)
    api(case, 'PUT', f"review-grants/{snapshot['dataset_id']}/{peer['user']}", {**body, 'expires_at': '2020-01-01T00:00:00Z'}, 422)
    permission = grant(case, snapshot, peer)
    api(case, 'PUT', f"review-grants/{snapshot['dataset_id']}/{peer['user']}", body, 409)
    other = finish(case, uploaded(case))
    definition = api(case, 'POST', 'dictionary', draft(other), 201)
    api(case, 'POST', 'dictionary/' + definition['id'] + '/review', {'expected_revision': 0, 'action': 'review', 'reason': 'Other dataset'})
    api(case, 'POST', 'dictionary/' + definition['id'] + '/review', {'expected_revision': 1, 'action': 'approve', 'reason': 'No grant on this dataset'}, 404, peer)
    with case[0]['admin']() as db, db.begin():
        db.execute(grants.update().where(grants.c.id == UUID(permission['id'])).values(expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)))
    assert api(case, 'GET', 'reviews', actor=peer)['items'] == []
    with case[0]['api']() as db, db.begin():
        scoped(db, peer['user'], peer['workspace'])
        assert db.execute(grants.update().where(grants.c.id == UUID(permission['id'])).values(active=True)).rowcount == 0


def test_membership_and_source_lifecycle_reauthorize_granted_review(case):
    from backend.app.models import Dataset
    snapshot = finish(case, uploaded(case))
    peer = colleague(case, 'analyst')
    row, permission = approved_dictionary(case, snapshot, peer)
    output = finish(case, api(case, 'POST', 'query', query(row, snapshot), 202))
    api(case, 'POST', f"artifacts/{output['id']}/review", {'expected_revision': 0, 'action': 'review', 'reason': 'Submitted result'})
    assert api(case, 'GET', 'reviews', actor=peer)['items'][0]['id'] == output['id']
    # Write membership alone cannot execute over another owner's source.
    api(case, 'POST', 'query', query(row, snapshot), 404, peer)
    with case[0]['admin']() as db, db.begin():
        db.execute(workspace_memberships.update().where(workspace_memberships.c.workspace_id == peer['workspace'],
            workspace_memberships.c.user_id == peer['user']).values(active=False))
    api(case, 'GET', 'reviews/' + output['id'], expected=404, actor=peer)
    with case[0]['admin']() as admin:
        tenant = str(admin.get(Workspace, peer['workspace']).tenant_id)
    with case[0]['api']() as db:
        # Even a stale previously authorized request context cannot use the SQL helper.
        for name, value in [('tenant_id', tenant),
                            ('workspace_id', str(peer['workspace'])), ('actor_id', str(peer['user']))]:
            db.execute(text('SELECT set_config(:key,:value,true)'), {'key': 'app.'+name, 'value': value})
        assert db.scalar(text('SELECT company_review_artifact(CAST(:id AS uuid),NULL)'), {'id': output['id']}) is None
    with case[0]['admin']() as db, db.begin():
        db.execute(workspace_memberships.update().where(workspace_memberships.c.workspace_id == peer['workspace'],
            workspace_memberships.c.user_id == peer['user']).values(active=True))
        db.execute(update(Dataset).where(Dataset.dataset_id == snapshot['dataset_id']).values(status='archived'))
    api(case, 'GET', 'reviews/' + output['id'], expected=404, actor=peer)
    assert api(case, 'GET', 'reviews', actor=peer)['items'] == []
    # Revocation remains possible while the source is archived.
    api(case, 'POST', 'review-grants/' + permission['id'] + '/revoke', {'expected_revision': 1, 'reason': 'Archived source'})
