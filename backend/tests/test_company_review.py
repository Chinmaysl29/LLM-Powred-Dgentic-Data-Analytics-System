"""Synthetic company flows over real PostgreSQL RLS, API and bounded children."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, update
from backend.tests.test_verified_learning_integration import environment, identity
from backend.tests.test_dataplane_integration import case, call, finish, uploaded
from backend.app.dataplane.company import comparison
from backend.app.dataplane.company_schedule import due_slot, schedule_workflows
from backend.app.dataplane.records import artifacts, scoped
from backend.app.models.background_job import DurableJob
from backend.app.core.workspace_authorization import tenant_memberships


def api(case, method, path, body=None, expected=200, actor=None):
    return call(case, method, 'company/' + path, body, expected, actor).json()


def draft(snapshot, key='source_amount', version=1, missing='exclude', rules=None, aggregation='sum'):
    return {'definition': {'key': key, 'version': version, 'owner': 'Synthetic owner',
        'source': 'Authorized synthetic snapshot', 'metric': {'column': 'amount', 'aggregation': aggregation,
            'missing': missing, 'definition_ref': None}, 'filters': [], 'units': 'USD', 'currency': 'USD',
        'examples': [{'values': [10, 10, 4] if missing == 'reject' else [10, 10, None, 4],
            'expected': {'sum': 24, 'mean': 8, 'count': 3, 'min': 4, 'max': 10}[aggregation]}]},
        'dataset_id': snapshot['dataset_id'], 'description': 'Total source amount', 'domain': 'synthetic',
        'aliases': [key + ' total'], 'grain': 'source transaction', 'timezone': 'UTC',
        'date_basis': 'No time filter; complete uploaded snapshot', 'exclusions': [],
        'effective_from': '2026-01-01', 'health_rules': rules or []}


def policy(case):
    return api(case, 'PUT', 'policy', {'allow_self_approval': True, 'expected_revision': 0,
                                      'reason': 'Explicit synthetic single-reviewer test policy'})


def reviewed(case, snapshot, **kwargs):
    row = api(case, 'POST', 'dictionary', draft(snapshot, **kwargs), 201)
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 0, 'action': 'review', 'reason': 'Review fixture'})
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 1, 'action': 'approve', 'reason': 'Approve fixture'})
    return row


def query(row, snapshot, dimensions=None):
    return {'definition_id': row['id'], 'snapshot_id': snapshot['id'], 'business_date': '2026-11-09',
            'plan': {'metric': row['key'], 'dimensions': dimensions or []}, 'idempotency_key': str(uuid4())}


def test_dictionary_approval_actual_result_evidence_and_revocation(case):
    snapshot = finish(case, uploaded(case))
    row = api(case, 'POST', 'dictionary', draft(snapshot), 201)
    api(case, 'POST', 'query', query(row, snapshot), 409)
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 0, 'action': 'review', 'reason': 'Ready'})
    # No assumed self-approval policy.
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 1, 'action': 'approve', 'reason': 'Ready'}, 409)
    policy(case)
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 1, 'action': 'approve', 'reason': 'Ready'})
    evidence = finish(case, api(case, 'POST', 'query', query(row, snapshot), 202))
    assert evidence['payload']['rows'] == [{'value': 24}]
    assert evidence['payload']['definition_id'] == row['id']
    assert evidence['payload']['source_version'] == snapshot['payload']['version_id']
    assert evidence['payload']['coverage'] == 'full'
    assert evidence['payload']['model']['provider'] == 'none'
    detail = api(case, 'GET', 'evidence/' + evidence['id'])
    assert detail['definition_context']['formula'] == 'sum(amount)'
    assert 'sql' not in detail and 'parameters' not in detail
    report = call(case, 'GET', f"evidence/{evidence['id']}/report")
    assert report.content.startswith(b'%PDF')
    assert report.headers['content-disposition'].endswith('.pdf"')
    pending = api(case, 'POST', 'query', query(row, snapshot), 202)
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 2, 'action': 'revoke', 'reason': 'Revoke synthetic definition'})
    api(case, 'POST', 'query', query(row, snapshot), 409)
    from backend.app.dataplane.worker import process_one
    from backend.app.dataplane.config import Limits
    process_one(case[0]['worker'], Limits(), 'revocation-test')
    assert call(case, 'GET', 'jobs/' + pending['id']).json()['status'] == 'FAILED'
    assert api(case, 'GET', 'evidence/' + evidence['id'])['current_definition_status'] == 'revoked'
    assert call(case, 'GET', 'artifacts/' + evidence['id']).json()['payload']['rows'] == [{'value': 24}]
    api(case, 'GET', 'dictionary/' + row['id'], expected=404, actor=case[2])
    api(case, 'GET', 'evidence/' + evidence['id'], expected=404, actor=case[2])


def test_scope_alias_conflicts_review_cas_and_unapproved_edits(case):
    snapshot = finish(case, uploaded(case))
    policy(case)
    first = reviewed(case, snapshot)
    second = api(case, 'POST', 'dictionary', draft(snapshot, version=2), 201)
    api(case, 'POST', f"dictionary/{second['id']}/review", {'expected_revision': 0, 'action': 'review', 'reason': 'New immutable draft'})
    api(case, 'POST', f"dictionary/{second['id']}/review", {'expected_revision': 1, 'action': 'approve', 'reason': 'Conflicting period'}, 409)
    api(case, 'POST', f"dictionary/{first['id']}/review", {'expected_revision': 1, 'action': 'revoke', 'reason': 'Stale'}, 409)
    assert finish(case, api(case, 'POST', 'query', query(first, snapshot), 202))['payload']['rows'] == [{'value': 24}]
    viewer = identity(case[0], role='viewer')
    api(case, 'POST', 'dictionary', draft(snapshot), expected=403, actor=viewer)
    # Identical names in another tenant remain independently valid.
    other_case = (case[0], case[2], case[1], case[3])
    other_snapshot = finish(other_case, uploaded(other_case))
    policy(other_case)
    other = reviewed(other_case, other_snapshot, aggregation='mean')
    assert other['key'] == first['key'] and other['id'] != first['id']
    assert finish(other_case, api(other_case, 'POST', 'query', query(other, other_snapshot), 202))['payload']['rows'] == [{'value': 8}]


def test_health_lineage_blocks_required_input_preserves_findings(case):
    snapshot = finish(case, uploaded(case))
    policy(case)
    strict = reviewed(case, snapshot, missing='reject', rules=[{'column': 'amount', 'check': 'not_null', 'severity': 'warning'}])
    job = api(case, 'POST', 'query', query(strict, snapshot), 202)
    from backend.app.dataplane.worker import process_one
    from backend.app.dataplane.config import Limits
    process_one(case[0]['worker'], Limits(), 'quality-gate')
    state = call(case, 'GET', 'jobs/' + job['id']).json()
    assert state['status'] == 'FAILED' and state['error_code'] == 'QUALITY_BLOCKED'
    incident = call(case, 'GET', 'artifacts/' + state['result']['incident_id']).json()
    assert incident['payload']['checks'][0]['observed'] == 1
    assert incident['payload']['checks'][0]['coverage'] == 'full'
    api(case, 'POST', 'artifacts/' + incident['id'] + '/review',
        {'expected_revision': 0, 'action': 'acknowledge', 'reason': 'Investigating'})
    api(case, 'POST', 'artifacts/' + incident['id'] + '/review',
        {'expected_revision': 1, 'action': 'resolve', 'reason': 'Acknowledgement is not a pass'}, 409)
    # A failing critical check on an unused text field does not block amount.
    unrelated = reviewed(case, snapshot, key='other_amount', rules=[{'column': 'region', 'check': 'unique', 'severity': 'critical'}])
    unrelated_result = finish(case, api(case, 'POST', 'query', query(unrelated, snapshot), 202))['payload']
    assert unrelated_result['validation_status'] == 'passed'
    assert unrelated_result['quality_checks'][0]['status'] == 'failed'
    assert unrelated_result['quality_checks'][0]['impact'] == 'unaffected'
    # A later check may discover a defect in the same immutable snapshot. Original
    # result evidence remains unchanged; unknown historical lineage is not guessed.
    from backend.app.dataplane.records import add_record
    with case[0]['api']() as db:
        access = scoped(db, case[1]['user'], case[1]['workspace'], 'write')
        legacy_id = add_record(db, access, 'evidence', {'rows': [{'value': 24}]},
            dataset_id=snapshot['dataset_id'], parent_id=UUID(snapshot['id']))
        db.commit()
    impacts = api(case, 'GET', 'incidents')['items'][0]['affected_outputs']
    assert next(item for item in impacts if item['id'] == legacy_id)['impact'] == 'unknown'
    proposal = finish(case, call(case, 'POST', 'snapshots/' + snapshot['id'] + '/cleaning',
        {'plan': {'operation': 'drop_nulls', 'columns': ['amount'], 'reason': 'Reviewed recovery fixture'}}, 202).json())
    recovery = finish(case, call(case, 'POST', f"proposals/{proposal['id']}/approve", {}, 202).json())
    finish(case, api(case, 'POST', 'query', query(strict, recovery), 202))
    resolved = api(case, 'POST', 'artifacts/' + incident['id'] + '/review',
        {'expected_revision': 1, 'action': 'resolve', 'reason': 'Full check passes on the reviewed replacement snapshot'})
    assert resolved['status'] == 'resolved' and resolved['recovery_evidence_id']
    assert call(case, 'GET', 'artifacts/' + incident['id']).json()['payload']['checks'][0]['status'] == 'failed'


def test_cleaning_preview_select_and_undo_preserve_history(case):
    snapshot = finish(case, uploaded(case))
    proposal = finish(case, call(case, 'POST', 'snapshots/' + snapshot['id'] + '/cleaning',
        {'plan': {'operation': 'drop_nulls', 'columns': ['amount'], 'reason': 'Synthetic explicit removal'}}, 202).json())
    assert proposal['payload']['preview_rows']['before'][2]['amount'] is None
    cleaned = finish(case, call(case, 'POST', f"proposals/{proposal['id']}/approve", {}, 202).json())
    body = {'expected_active_version_id': snapshot['payload']['version_id'],
            'target_snapshot_id': cleaned['id'], 'reason': 'Publish reviewed cleaned version'}
    selected = api(case, 'POST', 'versions/' + snapshot['dataset_id'] + '/select', body)
    assert selected['active_version_id'] == cleaned['payload']['version_id']
    api(case, 'POST', 'versions/' + snapshot['dataset_id'] + '/select', body, 409)
    api(case, 'POST', 'versions/' + snapshot['dataset_id'] + '/select', {
        'expected_active_version_id': cleaned['payload']['version_id'], 'target_snapshot_id': snapshot['id'], 'reason': 'Undo'})
    assert call(case, 'GET', 'artifacts/' + cleaned['id']).json()['payload']['row_count'] == 3
    assert call(case, 'GET', 'artifacts/' + snapshot['id']).json()['payload']['row_count'] == 4


def test_workflow_manual_review_binary_download_idempotency_and_schedule(case):
    snapshot = finish(case, uploaded(case))
    policy(case)
    row = reviewed(case, snapshot)
    workflow = api(case, 'POST', 'workflows', {'name': 'Synthetic recurring total', 'purpose': 'Test reusable approved workflow',
        'query': query(row, snapshot), 'require_artifact_review': True}, 201)
    for index, action in enumerate(('review', 'approve', 'activate')):
        api(case, 'POST', 'artifacts/' + workflow['id'] + '/review',
            {'expected_revision': index, 'action': action, 'reason': 'Synthetic workflow review'})
    path = 'workflows/' + workflow['id'] + '/run'
    job = api(case, 'POST', path, {'idempotency_key': 'manual-one'}, expected=202)
    assert api(case, 'POST', path, {'idempotency_key': 'manual-one'}, expected=202)['id'] == job['id']
    evidence = finish(case, job)
    assert evidence['payload']['rows'] == [{'value': 24}]
    call(case, 'GET', f"evidence/{evidence['id']}/report", expected=409)
    for index, action in enumerate(('review', 'approve')):
        api(case, 'POST', 'artifacts/' + evidence['id'] + '/review',
            {'expected_revision': index, 'action': action, 'reason': 'Review actual report output'})
    downloaded = call(case, 'GET', f"evidence/{evidence['id']}/report").content
    assert downloaded.startswith(b'%PDF')
    assert call(case, 'GET', f"evidence/{evidence['id']}/report").content == downloaded
    with case[0]['api']() as db:
        from backend.app.dataplane.records import get_record
        access = scoped(db, case[1]['user'], case[1]['workspace'])
        stored = get_record(db, access, evidence['id'], 'evidence')['payload']['report_artifact']
        assert stored['bytes'] == len(downloaded) and stored['content_type'] == 'application/pdf'
    configured = api(case, 'GET', 'workflows')['items'][0]['schedule']
    assert not configured.get('enabled', False)
    api(case, 'PUT', 'workflows/' + workflow['id'] + '/schedule',
        {'expected_revision': 0, 'enabled': True, 'timezone': 'UTC', 'hour': 9, 'minute': 0})
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    tomorrow = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
    # The shared synthetic database can contain more than one registry page.
    # Exercise the worker's real pagination contract on both deduplication passes.
    for _ in range(2):
        offset = 0
        for _ in range(100):
            offset = schedule_workflows(case[0]['worker'], tomorrow, offset=offset)
            if not offset:
                break
        else:
            raise AssertionError('Synthetic schedule registry exceeded 100 pages')
    with case[0]['admin']() as db:
        jobs = db.scalars(select(DurableJob).where(DurableJob.workspace_id == case[1]['workspace'],
            DurableJob.kind == 'dp_workflow')).all()
        assert len(jobs) == 2  # One manual and one deduplicated due slot.
    # Pause stops pending publication/execution after scheduling.
    api(case, 'POST', 'artifacts/' + workflow['id'] + '/review',
        {'expected_revision': 3, 'action': 'pause', 'reason': 'Pause before scheduled execution'})


def test_comparison_exports_and_foreign_source_authorization(case):
    snapshot = finish(case, uploaded(case))
    policy(case)
    row = reviewed(case, snapshot)
    first = finish(case, api(case, 'POST', 'query', query(row, snapshot, ['region']), 202))
    second = finish(case, api(case, 'POST', 'query', query(row, snapshot, ['region']), 202))
    result = api(case, 'POST', 'compare', {'previous_id': first['id'], 'current_id': second['id']}, 201)
    assert result['comparable'] and [r['absolute_change'] for r in result['rows']] == ['0', '0']
    response = call(case, 'GET', 'company/comparisons/' + result['id'] + '/download')
    assert response.headers['content-type'].startswith('application/json')
    assert response.json()['previous_id'] == first['id']
    api(case, 'POST', 'compare', {'previous_id': first['id'], 'current_id': second['id']}, 404, case[2])
    # Download reauthorizes both original datasets, not only the comparison artifact.
    with case[0]['admin']() as db, db.begin():
        db.execute(update(tenant_memberships).where(tenant_memberships.c.user_id == case[1]['user']).values(active=False))
    call(case, 'GET', 'company/comparisons/' + result['id'] + '/download', expected=404)


@pytest.mark.parametrize('old,new,delta,percent', [(1000, 800, '-200', '-20.000000'),
    (0, 8, '8', None), (-100, -80, '20', '20.000000'), (None, 8, None, None)])
def test_decimal_comparison_independent_expected_values(old, new, delta, percent):
    base = {'definition_id': 'v1', 'definition_hash': 'h', 'spec_hash': 's', 'validation_status': 'passed',
        'coverage': 'full', 'metric': {'aggregation': 'sum'}, 'plan': {'dimensions': []}, 'rows': [{'value': old}]}
    result = comparison(base, {**base, 'rows': [{'value': new}]})
    assert result['rows'][0]['absolute_change'] == delta
    assert result['rows'][0]['percentage_change'] == percent
    assert not comparison(base, {**base, 'definition_id': 'v2'})['comparable']


def test_schedule_dst_clock_and_malformed_contract():
    config = {'timezone': 'America/New_York', 'hour': 2, 'minute': 30}
    slot = due_slot(config, datetime(2026, 3, 8, 8, tzinfo=timezone.utc))
    assert slot == datetime(2026, 3, 7, 7, 30, tzinfo=timezone.utc)
    config['hour'] = 1
    slot = due_slot(config, datetime(2026, 11, 1, 8, tzinfo=timezone.utc))
    assert slot == datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)


def test_wrong_metric_examples_and_nonfinite_or_naive_windows_are_rejected():
    from fastapi import HTTPException
    from backend.app.dataplane.company import verify_examples
    from backend.app.dataplane.company_contracts import DictionaryDraft, TimeWindow
    body = draft({'dataset_id': str(uuid4())})
    body['definition']['examples'][0]['expected'] = 385  # Seeded false acceptance.
    with pytest.raises(HTTPException) as failure:
        verify_examples(DictionaryDraft.model_validate(body))
    assert failure.value.status_code == 409
    with pytest.raises(ValueError):
        TimeWindow(column='date', start='2026-01-01T00:00:00', end='2026-02-01T00:00:00')
    from backend.app.dataplane.api import public
    private = {'kind': 'evidence', 'payload': {'sql': 'SELECT ... WHERE email=?', 'parameters': ['private@example.test'],
        'plan': {'filters': [{'column': 'email', 'operator': 'eq', 'value': 'private@example.test'}]}}}
    rendered = public(private)
    assert 'private@example.test' not in str(rendered)
    assert private['payload']['plan']['filters'][0]['value'] == 'private@example.test'


def test_approved_dictionary_drives_existing_chat_and_revocation_abstains(case):
    from backend.app.dataplane.chat import route
    from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
    snapshot = finish(case, uploaded(case))
    policy(case)
    row = reviewed(case, snapshot)
    with case[0]['api']() as db:
        response = route(db, case[1]['user'], case[1]['workspace'], snapshot['dataset_id'], 1,
                         'sum amount by region', NaturalLanguageAnalyticsService())
    assert response['status'] == 'queued'
    evidence = finish(case, {'id': response['plan']['job_id']})
    assert evidence['payload']['definition_id'] == row['id']
    assert evidence['payload']['rows'] == [{'region': 'a', 'value': 20}, {'region': 'b', 'value': 4}]
    api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': 2, 'action': 'revoke', 'reason': 'Stop future use'})
    with case[0]['api']() as db:
        response = route(db, case[1]['user'], case[1]['workspace'], snapshot['dataset_id'], 1,
                         'sum amount by region', NaturalLanguageAnalyticsService())
    assert response['status'] == 'clarification_required'


def test_relative_workflow_pins_source_and_resolved_window_before_active_version_changes(case):
    from io import BytesIO
    import pyarrow as pa
    import pyarrow.parquet as pq
    from backend.app.dataplane.company_api import workflow_payload
    from backend.app.dataplane.service import enqueue
    values = [datetime(2026, 11, day, 12, tzinfo=timezone.utc) for day in (7, 7, 7, 8)]
    buffer = BytesIO()
    pq.write_table(pa.table({'date': values, 'amount': [10, None, 20, 5], 'region': ['a', 'a', 'b', 'b']}), buffer)
    upload = case[0]['client'].post('/api/v1/dataplane/upload',
        data={'workspace_id': str(case[1]['workspace']), 'idempotency_key': str(uuid4())},
        files={'file': ('synthetic-time.parquet', buffer.getvalue(), 'application/octet-stream')}, headers=case[1]['headers'])
    assert upload.status_code == 202, upload.text
    snapshot = finish(case, upload.json())
    policy(case)
    specification = draft(snapshot)
    specification['definition']['examples'] = [{'values': [10, 20, 5], 'expected': 35}]
    row = api(case, 'POST', 'dictionary', specification, 201)
    for revision, action in enumerate(('review', 'approve')):
        api(case, 'POST', f"dictionary/{row['id']}/review", {'expected_revision': revision, 'action': action, 'reason': 'Synthetic time fixture'})
    workflow = api(case, 'POST', 'workflows', {'name': 'Completed local day', 'purpose': 'Pinned manifest test',
        'query': query(row, snapshot), 'require_artifact_review': False, 'source_selection': 'active_at_start',
        'relative_window': {'column': 'date', 'completed_days': 1}}, 201)
    for revision, action in enumerate(('review', 'approve', 'activate')):
        api(case, 'POST', 'artifacts/' + workflow['id'] + '/review', {'expected_revision': revision, 'action': action, 'reason': 'Synthetic review'})
    proposal = finish(case, call(case, 'POST', 'snapshots/' + snapshot['id'] + '/cleaning',
        {'plan': {'operation': 'drop_nulls', 'columns': ['amount'], 'reason': 'Remove explicit missing value into a new version'}}, 202).json())
    cleaned = finish(case, call(case, 'POST', f"proposals/{proposal['id']}/approve", {}, 202).json())
    now = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)
    with case[0]['api']() as db:
        access = scoped(db, case[1]['user'], case[1]['workspace'], 'write')
        payload = workflow_payload(db, access, workflow['id'], now=now)
        assert payload['snapshot_id'] == snapshot['id']
        assert payload['time_window']['start'].startswith('2026-11-08')
        queued = enqueue(db, access, 'dp_workflow', 'controlled-window-' + uuid4().hex, payload)
    api(case, 'POST', 'versions/' + snapshot['dataset_id'] + '/select', {
        'expected_active_version_id': snapshot['payload']['version_id'], 'target_snapshot_id': cleaned['id'], 'reason': 'Concurrent later activation'})
    result = finish(case, {'id': str(queued['id'])})
    assert result['payload']['rows'] == [{'value': 5}]
    assert result['payload']['snapshot_id'] == snapshot['id']
    with case[0]['api']() as db:
        access = scoped(db, case[1]['user'], case[1]['workspace'], 'write')
        assert workflow_payload(db, access, workflow['id'], now=now)['snapshot_id'] == cleaned['id']


def test_additive_new_removed_contributions_reconcile_and_changed_window_is_rejected():
    base = {'definition_id': 'v1', 'definition_hash': 'h', 'spec_hash': 's', 'validation_status': 'passed',
        'coverage': 'full', 'metric': {'aggregation': 'sum'}, 'plan': {'dimensions': ['region']},
        'rows': [{'region': 'a', 'value': 100}, {'region': 'b', 'value': 200}]}
    after = {**base, 'rows': [{'region': 'a', 'value': 80}, {'region': 'c', 'value': 20}]}
    result = comparison(base, after)
    assert result['totals'] == {'previous': '300', 'current': '100', 'absolute_change': '-200'}
    assert sum(int(row['contribution']) for row in result['contributions']) == -200
    assert {row['entity'] for row in result['rows']} == {'matched', 'new', 'removed'}
    changed = {**after, 'time_window': {'column': 'date', 'start': '2026-11-01T00:00:00+00:00', 'end': '2026-11-02T00:00:00+00:00'}}
    assert not comparison(base, changed)['comparable']


def test_database_rejects_a_second_active_version_from_other_writers(case):
    from sqlalchemy.exc import IntegrityError
    from backend.app.models.dataset_version import DatasetVersion
    snapshot = finish(case, uploaded(case))
    with pytest.raises(IntegrityError):
        with case[0]['admin']() as db, db.begin():
            db.add(DatasetVersion(version_id=str(uuid4()), dataset_id=snapshot['dataset_id'], version_number=2,
                change_type='synthetic_conflicting_writer', storage_path='/synthetic/not-published',
                metadata_snapshot={}, quality_snapshot={}, is_active=True, created_by=str(case[1]['user'])))
            db.flush()


def test_legacy_version_creation_and_rollback_respect_the_database_guard(case):
    from backend.app.models.dataset_version import DatasetVersion
    from backend.app.repositories.dataset_version_repository import DatasetVersionRepository
    snapshot = finish(case, uploaded(case))
    with case[0]['admin']() as db:
        repository = DatasetVersionRepository(db)
        original = db.get(DatasetVersion, snapshot['payload']['version_id'])
        created = repository.create(DatasetVersion(version_id=str(uuid4()), dataset_id=snapshot['dataset_id'],
            version_number=2, parent_version_id=original.version_id, change_type='synthetic_legacy_version',
            storage_path=original.storage_path, metadata_snapshot={}, quality_snapshot={}, is_active=True,
            created_by=str(case[1]['user'])))
        assert repository.get_active_version(snapshot['dataset_id']).version_id == created.version_id
        restored = repository.set_active_version(snapshot['dataset_id'], 1)
        assert restored.version_id == original.version_id
        versions, _ = repository.get_versions(snapshot['dataset_id'])
        assert sum(v.is_active for v in versions) == 1


def test_workflow_report_render_failure_never_publishes_a_success(case, monkeypatch):
    from backend.app.dataplane.worker import process_one
    from backend.app.dataplane.config import Limits
    from backend.app.dataplane import reporting
    snapshot = finish(case, uploaded(case))
    policy(case)
    row = reviewed(case, snapshot)
    workflow = api(case, 'POST', 'workflows', {'name': 'Synthetic renderer failure', 'purpose': 'Failure publication guard',
        'query': query(row, snapshot), 'require_artifact_review': False}, 201)
    for revision, action in enumerate(('review', 'approve', 'activate')):
        api(case, 'POST', 'artifacts/' + workflow['id'] + '/review',
            {'expected_revision': revision, 'action': action, 'reason': 'Synthetic fault-injection fixture'})
    job = api(case, 'POST', 'workflows/' + workflow['id'] + '/run', {'idempotency_key': uuid4().hex}, 202)
    def failed_renderer(*args):
        raise RuntimeError('Synthetic report renderer failure')
    monkeypatch.setattr(reporting, 'render_pdf', failed_renderer)
    process_one(case[0]['worker'], Limits(), 'report-failure-test')
    assert call(case, 'GET', 'jobs/' + job['id']).json()['status'] == 'FAILED'
    with case[0]['admin']() as db:
        assert db.execute(select(artifacts.c.id).where(artifacts.c.job_id == UUID(job['id']))).first() is None
