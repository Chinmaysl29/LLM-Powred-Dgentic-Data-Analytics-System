"""Authenticated company review and immutable report flows."""
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Response, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.core.security import get_current_user
from backend.app.database.postgres import get_db_session
from backend.app.dataplane.api import enabled, job_view
from backend.app.dataplane.records import scoped, artifacts, conditions, get_record, add_record
from backend.app.dataplane.read_models import latest_events, workflow_runs, output_lineage
from backend.app.core.workspace_authorization import authorized_bound_dataset_ids
from backend.app.dataplane.company_contracts import (DictionaryDraft, Review, Policy, CompanyQuery,
    WorkflowDraft, Schedule, SwitchVersion, Compare, RunWorkflow)
from backend.app.dataplane import company as service
from backend.app.dataplane.service import enqueue
from backend.app.dataplane.storage import fingerprint, scope_root, confined
from backend.app.models.learning import BusinessDefinition, LearningAudit
from backend.app.models.background_job import DurableJob
from backend.app.models.dataset import Dataset
from backend.app.models.dataset_version import DatasetVersion
from backend.app.services.learning_supervisor import audit

router = APIRouter(prefix='/dataplane/company', tags=['Company review'], dependencies=[Depends(enabled)])


@router.get('/incidents')
def incidents(workspace_id: UUID, offset: int = Query(0, ge=0, le=100000),
              db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id)
    rows = db.execute(select(artifacts).where(*conditions(access), artifacts.c.kind == 'incident')
        .order_by(artifacts.c.created_at.desc()).offset(offset).limit(51)).mappings().all()
    page = rows[:50]
    datasets = {row['dataset_id'] for row in page if row['dataset_id']}
    if datasets - authorized_bound_dataset_ids(db, access, datasets):
        service.fail('Resource not found', 404)
    outputs_by_dataset = output_lineage(db, access, {row['dataset_id'] for row in page})
    reviews = latest_events(db, access, [row['id'] for row in page])
    items = []
    for row in page:
        fields = {c['field'] for c in row['payload']['checks'] if c['status'] != 'passed'}
        affected = []
        for output in outputs_by_dataset[row['dataset_id']]:
            lineage = output['lineage']
            impact = 'unknown'
            if lineage:
                if str(lineage.get('snapshot_id')) != str(row['parent_id']):
                    impact = 'unaffected'
                elif 'fields' not in lineage:
                    impact = 'unknown'
                elif fields & set(lineage.get('fields', [])):
                    impact = 'directly_affected'
                else:
                    impact = 'unaffected'
            affected.append({'id': str(output['id']), 'kind': output['kind'], 'impact': impact,
                'path': [str(row['parent_id']), *sorted(fields), str(output['id'])] if impact == 'directly_affected' else [],
                'reason': 'Historical field lineage is incomplete' if impact == 'unknown' else 'Immutable snapshot and required-field lineage'})
        items.append({'id': str(row['id']), **row['payload'], 'review': reviews.get(str(row['id']), {'revision': 0, 'status': 'draft'}),
                      'affected_outputs': affected, 'impact_limit': 'Latest 100 outputs for this dataset; earlier outputs not assessed'})
    return {'items': items, 'next_offset': offset + 50 if len(rows) > 50 else None}


@router.get('/policy')
def get_policy(workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id)
    return {**service.policy(db, access), 'role': access.role}


@router.put('/policy')
def set_policy(workspace_id: UUID, body: Policy, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    from sqlalchemy import text
    access = scoped(db, user.id, workspace_id, 'manage')
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': int(workspace_id.hex[:15], 16)})
    old = service.policy(db, access)
    if old['revision'] != body.expected_revision:
        service.fail('Policy changed; reload before saving')
    value = {'revision': old['revision'] + 1, 'allow_self_approval': body.allow_self_approval, 'reason': body.reason}
    audit(db, access, 'company_policy', str(workspace_id), **value)
    db.commit()
    return value


@router.get('/dictionary')
def dictionary(workspace_id: UUID, search: str = Query('', max_length=100), offset: int = Query(0, ge=0, le=100000),
               db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    scoped(db, user.id, workspace_id)
    query = select(BusinessDefinition).where(BusinessDefinition.workspace_id == workspace_id)
    if search:
        # Parameterized search includes aliases; selection still uses canonical IDs.
        from sqlalchemy import cast, String, or_
        term = '%' + search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        query = query.where(or_(BusinessDefinition.key.ilike(term, escape='\\'),
                                cast(BusinessDefinition.governance, String).ilike(term, escape='\\')))
    rows = db.scalars(query.order_by(BusinessDefinition.key, BusinessDefinition.version.desc()).offset(offset).limit(51)).all()
    return {'items': [service.dictionary_json(row) for row in rows[:50]], 'next_offset': offset+50 if len(rows)>50 else None}


@router.post('/dictionary', status_code=201)
def create_dictionary(body: DictionaryDraft, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    row = service.create_definition(db, scoped(db, user.id, workspace_id, 'write'), body)
    value = service.dictionary_json(row)
    db.commit()
    return value


@router.get('/dictionary/{identity}')
def dictionary_detail(identity: str, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id)
    row = service.definition(db, access, identity)
    history = db.scalars(select(LearningAudit).where(LearningAudit.workspace_id == workspace_id,
        LearningAudit.entity_id == identity).order_by(LearningAudit.created_at, LearningAudit.id).limit(100)).all()
    uses = db.execute(select(artifacts.c.id, artifacts.c.kind).where(*conditions(access),
        artifacts.c.payload['definition_id'].as_string() == identity).limit(100)).mappings().all()
    return {**service.dictionary_json(row), 'history': [{'action': r.action, 'at': r.created_at,
        'actor': str(r.actor_id), 'summary': r.summary} for r in history],
        'used_by': [{'id': str(r['id']), 'kind': r['kind']} for r in uses]}


@router.post('/dictionary/{identity}/review')
def dictionary_review(identity: str, body: Review, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'read')
    value = service.dictionary_json(service.review_definition(db, access, identity, body))
    db.commit()
    return value


@router.post('/query', status_code=202)
def query(body: CompanyQuery, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'write')
    payload = service.query_payload(db, access, body)
    try:
        return job_view(enqueue(db, access, 'dp_query', body.idempotency_key, payload))
    except ValueError as error:
        service.fail(str(error))


@router.get('/evidence/{identity}')
def calculation(identity: UUID, workspace_id: UUID, technical: bool = False,
                db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'manage' if technical else 'read')
    row = get_record(db, access, identity, 'evidence')
    value = row['payload']
    current = None
    if value.get('definition_id'):
        current = service.dictionary_json(service.definition(db, access, value['definition_id']))['status']
    # No file paths, physical scan plans, raw parameter values or private rows.
    safe = {k: v for k, v in value.items() if k not in {'sql', 'parameters', 'estimate', 'curated', 'report_artifact', 'plan'}}
    if safe.get('definition_context'):
        safe['definition_context'] = {k: v for k, v in safe['definition_context'].items() if k != 'source'}
    safe['plan'] = {**value.get('plan', {}), 'filters': [{**f, 'value': '[redacted]'} for f in value.get('plan', {}).get('filters', [])]}
    safe['current_definition_status'] = current
    safe['review'] = service.current_event(db, access, identity)
    safe['historical_notice'] = None if value.get('contract_version') else 'Calculation evidence unavailable for this historical report.'
    if technical:
        # Even administrators see a parameterized query with redacted literals.
        safe['technical'] = {'sql': value.get('sql'), 'parameters': ['[redacted]'] * len(value.get('parameters', []))}
    return Response(json.dumps(safe, default=str, allow_nan=False), media_type='application/json',
                    headers={'Cache-Control': 'private, no-store'})


@router.post('/compare', status_code=201)
def compare(body: Compare, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'write')
    before = get_record(db, access, body.previous_id, 'evidence')
    after = get_record(db, access, body.current_id, 'evidence')
    value = {**service.comparison(before['payload'], after['payload']),
             'previous_id': str(body.previous_id), 'current_id': str(body.current_id)}
    identity = add_record(db, access, 'comparison', value, dataset_id=after['dataset_id'], parent_id=after['id'])
    db.commit()
    return {'id': identity, **value}


@router.get('/comparisons/{identity}/download')
def comparison_download(identity: UUID, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id)
    row = get_record(db, access, identity, 'comparison')
    for key in ('previous_id', 'current_id'):
        get_record(db, access, row['payload'][key], 'evidence')
    return Response(json.dumps(row['payload'], allow_nan=False, indent=2), media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="comparison-{identity}.json"', 'Cache-Control': 'private, no-store'})


@router.post('/versions/{dataset_id}/select')
def switch(dataset_id: str, body: SwitchVersion, workspace_id: UUID,
           db: Session = Depends(get_db_session), user=Depends(get_current_user), limits=Depends(enabled)):
    from backend.app.core.workspace_authorization import authorize_bound_dataset
    access = scoped(db, user.id, workspace_id, 'manage')
    authorize_bound_dataset(db, access, dataset_id)
    target = get_record(db, access, body.target_snapshot_id, 'snapshot')
    if target['dataset_id'] != dataset_id:
        service.fail('Target snapshot belongs to another dataset', 422)
    dataset = db.scalar(select(Dataset).where(Dataset.dataset_id == dataset_id).with_for_update())
    active = db.scalar(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id, DatasetVersion.is_active.is_(True)))
    if active is None or active.version_id != body.expected_active_version_id:
        service.fail('Active version changed; reload and choose the version again')
    version = db.get(DatasetVersion, target['payload']['version_id'])
    if not version or version.dataset_id != dataset_id:
        service.fail('Retained dataset version is unavailable', 410)
    root = scope_root(limits.root, access.tenant_id, access.workspace_id, access.actor_id)
    try:
        for entry in target['payload']['files']:
            confined(root, entry['path'])
    except (ValueError, FileNotFoundError):
        service.fail('Snapshot files are no longer retained; restore the backup first', 410)
    previous = active.version_id
    now = datetime.now(timezone.utc)
    db.execute(update(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id, DatasetVersion.is_active.is_(True)).values(is_active=False, deactivated_at=now))
    db.flush()
    db.execute(update(DatasetVersion).where(DatasetVersion.version_id == version.version_id).values(is_active=True, activated_at=now))
    dataset.last_active_version_id = version.version_id
    dataset.row_count = target['payload']['row_count']
    dataset.column_count = len(target['payload']['schema'])
    identity = add_record(db, access, 'version_change', {'previous_version_id': previous,
        'active_version_id': version.version_id, 'reason': body.reason,
        'dependent_reports': 'Historical reports remain pinned; rerun to use the newly selected version'},
        dataset_id=dataset_id, parent_id=target['id'])
    audit(db, access, 'dataset_version_selected', dataset_id, previous_version=previous, version=version.version_id)
    db.commit()
    return {'id': identity, 'active_version_id': version.version_id}


@router.get('/versions/{dataset_id}')
def versions(dataset_id: str, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    from backend.app.core.workspace_authorization import authorize_bound_dataset
    access = scoped(db, user.id, workspace_id)
    authorize_bound_dataset(db, access, dataset_id)
    rows = db.scalars(select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.version_number.desc()).limit(100)).all()
    return [{'id': r.version_id, 'number': r.version_number, 'active': r.is_active, 'change': r.change_type} for r in rows]


@router.post('/workflows', status_code=201)
def workflow(body: WorkflowDraft, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'write')
    payload = service.query_payload(db, access, body.query)
    version = 1
    if body.previous_version_id:
        old = get_record(db, access, body.previous_version_id, 'workflow')
        if old['dataset_id'] != payload['dataset_id']:
            service.fail('Workflow versions must keep the same authorized dataset', 422)
        version = old['payload']['version'] + 1
    value = {'spec': body.model_dump(mode='json'), 'spec_hash': fingerprint(body.model_dump(mode='json')),
        'definition_id': body.query.definition_id, 'version': version, 'created_at': datetime.now(timezone.utc).isoformat()}
    identity = add_record(db, access, 'workflow', value, dataset_id=payload['dataset_id'], parent_id=body.previous_version_id)
    audit(db, access, 'workflow_draft', identity, version=version)
    db.commit()
    return {'id': identity, **value}


@router.get('/workflows')
def workflows(workspace_id: UUID, offset: int = Query(0, ge=0, le=100000),
              db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id)
    rows = db.execute(select(artifacts).where(*conditions(access), artifacts.c.kind == 'workflow')
        .order_by(artifacts.c.created_at.desc()).offset(offset).limit(51)).mappings().all()
    page = rows[:50]
    jobs_by_workflow = workflow_runs(db, access, [row['id'] for row in page])
    parents = [row['id'] for row in page]
    output_ids = [job['result']['artifact_id'] for jobs in jobs_by_workflow.values() for job in jobs if job['status'] == 'READY']
    reviews = latest_events(db, access, [*parents, *output_ids])
    schedules = latest_events(db, access, parents, 'schedule')
    default_event = {'revision': 0, 'status': 'draft'}
    items = []
    for row in rows[:50]:
        runs = []
        for job in jobs_by_workflow[str(row['id'])]:
            state = job['status'].lower()
            if job['status'] == 'READY':
                output_review = reviews.get(job['result']['artifact_id'], default_event)
                state = 'awaiting_review' if job['payload'].get('require_artifact_review') and output_review['status'] != 'approved' else 'succeeded'
            runs.append({'id': str(job['id']), 'status': state, 'attempt': job['attempt'], 'error_code': job['error_code'],
                'schedule_slot': job['payload'].get('schedule_slot'), 'schedule_policy': job['payload'].get('schedule_policy'),
                'result': job['result']})
        items.append({'id': str(row['id']), **row['payload'], 'review': reviews.get(str(row['id']), default_event),
            'schedule': schedules.get(str(row['id']), default_event), 'recent_runs': runs})
    return {'items': items, 'next_offset': offset+50 if len(rows)>50 else None}


@router.post('/artifacts/{identity}/review')
def review(identity: UUID, body: Review, workspace_id: UUID, db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'read')
    value = service.review_artifact(db, access, identity, body)
    db.commit()
    return value


def workflow_payload(db, access, identity, pinned=None, now=None, require_active=True):
    row = get_record(db, access, identity, 'workflow')
    if require_active and service.current_event(db, access, identity)['status'] != 'active':
        service.fail('Workflow must be approved and active')
    spec = WorkflowDraft.model_validate(row['payload']['spec'])
    if fingerprint(row['payload']['spec']) != row['payload']['spec_hash']:
        service.fail('Workflow manifest integrity check failed')
    query = spec.query
    if pinned is not None:
        query = CompanyQuery.model_validate({**query.model_dump(), 'snapshot_id': pinned['snapshot_id'],
            'business_date': pinned['business_date'], 'time_window': pinned.get('time_window')})
    else:
        if spec.source_selection == 'active_at_start':
            original = get_record(db, access, spec.query.snapshot_id, 'snapshot')
            active = db.scalar(select(DatasetVersion.version_id).where(DatasetVersion.dataset_id == original['dataset_id'],
                DatasetVersion.is_active.is_(True)))
            snapshot = db.execute(select(artifacts.c.id).where(*conditions(access), artifacts.c.kind == 'snapshot',
                artifacts.c.dataset_id == original['dataset_id'], artifacts.c.payload['version_id'].as_string() == active)
                .order_by(artifacts.c.created_at.desc()).limit(1)).scalar()
            if not snapshot:
                service.fail('Active dataset version has no retained immutable snapshot')
            query = query.model_copy(update={'snapshot_id': snapshot})
        if spec.relative_window:
            from datetime import timedelta
            from zoneinfo import ZoneInfo
            from backend.app.dataplane.company_contracts import TimeWindow
            definition = service.definition(db, access, query.definition_id)
            zone = ZoneInfo(definition.governance['spec']['timezone'])
            local = (now or datetime.now(timezone.utc)).astimezone(zone)
            end = local.replace(hour=0, minute=0, second=0, microsecond=0, fold=0)
            start = end - timedelta(days=spec.relative_window.completed_days)
            for boundary in (start, end):
                if boundary.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != boundary.replace(tzinfo=None):
                    service.fail('Relative period has a nonexistent local boundary; configure an explicit absolute window')
            query = query.model_copy(update={'business_date': local.date(), 'time_window': TimeWindow(
                column=spec.relative_window.column, start=start, end=end)})
    payload = service.query_payload(db, access, query)
    payload.update(workflow_id=str(identity), workflow_hash=row['payload']['spec_hash'],
        require_artifact_review=spec.require_artifact_review, workflow_version=row['payload']['version'],
        resource_limits=spec.resources.model_dump())
    return payload


@router.post('/workflows/{identity}/run', status_code=202)
def run_workflow(identity: UUID, body: RunWorkflow, workspace_id: UUID,
                 db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'write')
    key = 'workflow:' + str(identity) + ':' + body.idempotency_key
    get_record(db, access, identity, 'workflow')
    old = db.scalar(select(DurableJob).where(DurableJob.workspace_id == workspace_id, DurableJob.owner_id == user.id,
        DurableJob.kind == 'dp_workflow', DurableJob.idempotency_key == key))
    if old:
        from backend.jobs.persistence import PersistentJobStore
        return job_view(PersistentJobStore.snapshot(old))
    payload = workflow_payload(db, access, identity)
    payload['run_started_at'] = None  # Resolved once at worker claim, not on request retries.
    try:
        return job_view(enqueue(db, access, 'dp_workflow', key, payload))
    except ValueError as error:
        service.fail(str(error))


@router.put('/workflows/{identity}/schedule')
def schedule(identity: UUID, body: Schedule, workspace_id: UUID,
             db: Session = Depends(get_db_session), user=Depends(get_current_user)):
    access = scoped(db, user.id, workspace_id, 'manage')
    row = service.lock_artifact(db, access, identity, 'workflow')
    old = service.current_event(db, access, identity, 'schedule')
    if old['revision'] != body.expected_revision:
        service.fail('Schedule changed; reload before saving')
    if body.enabled:
        workflow_payload(db, access, identity)
        prior = db.scalar(select(DurableJob.id).where(DurableJob.owner_id == access.actor_id,
            DurableJob.workspace_id == workspace_id, DurableJob.kind == 'dp_workflow', DurableJob.status == 'READY',
            DurableJob.payload['workflow_id'].as_string() == str(identity)).limit(1))
        if not prior:
            service.fail('Complete a manual workflow run before enabling its schedule')
    value = {**body.model_dump(), 'revision': old['revision'] + 1, 'configured_at': datetime.now(timezone.utc).isoformat()}
    add_record(db, access, 'schedule', value, dataset_id=row['dataset_id'], parent_id=row['id'])
    audit(db, access, 'workflow_schedule_changed', str(identity), enabled=body.enabled, revision=value['revision'])
    db.commit()
    return value
