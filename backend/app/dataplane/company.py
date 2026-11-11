"""Company review built on canonical definitions, audit and dataplane artifacts."""
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select

from backend.app.core.workspace_authorization import authorize_bound_dataset
from backend.app.dataplane.company_contracts import DictionaryDraft, CompanyQuery, WorkflowDraft
from backend.app.dataplane.contracts import Metric, QueryPlan, Filter
from backend.app.dataplane.records import artifacts, conditions, get_record, add_record
from backend.app.dataplane.storage import fingerprint
from backend.app.models.background_job import DurableJob
from backend.app.models.learning import BusinessDefinition, LearningAudit
from backend.app.services.learning_engine import digest
from backend.app.services.learning_supervisor import audit, invalidate_source


def fail(message, status=409):
    raise HTTPException(status, message)


def policy(db, access):
    row = db.scalar(select(LearningAudit).where(LearningAudit.workspace_id == access.workspace_id,
        LearningAudit.action == 'company_policy').order_by(LearningAudit.created_at.desc(), LearningAudit.id.desc()).limit(1))
    return row.summary if row else {'revision': 0, 'allow_self_approval': None}


def approval_allowed(db, access, author):
    if str(author) == str(access.actor_id) and policy(db, access).get('allow_self_approval') is not True:
        fail('Self-approval requires an explicit company policy. Use a separate authorized reviewer or configure the policy.')


def definition(db, access, identity, lock=False):
    query = select(BusinessDefinition).where(BusinessDefinition.id == str(identity),
        BusinessDefinition.workspace_id == access.workspace_id)
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        fail('Definition not found', 404)
    return row


def eligible(db, access, identity, business_date, lock=False):
    row = definition(db, access, identity, lock)
    gov = row.governance
    if gov.get('status') != 'approved' or not row.active:
        fail('An eligible approved company definition is required')
    spec = DictionaryDraft.model_validate(gov['spec'])
    if row.content_hash != digest(row.content) or gov['spec_hash'] != fingerprint(gov['spec']):
        fail('Definition integrity check failed')
    day = date.fromisoformat(str(business_date))
    if day < spec.effective_from or (spec.effective_to and day >= spec.effective_to):
        fail('Definition is not effective for the selected business date')
    authorize_bound_dataset(db, access, spec.dataset_id)
    return row, spec


def create_definition(db, access, body: DictionaryDraft):
    authorize_bound_dataset(db, access, body.dataset_id)
    # Serialize key/version creation without a database-wide or long-running lock.
    from sqlalchemy import text
    key = int(fingerprint([str(access.workspace_id), body.definition.key])[:15], 16)
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
    if db.scalar(select(BusinessDefinition.id).where(BusinessDefinition.workspace_id == access.workspace_id,
        BusinessDefinition.key == body.definition.key, BusinessDefinition.version == body.definition.version)):
        fail('Definition version exists; create a new immutable version')
    content = body.definition.model_dump(mode='json')
    spec = body.model_dump(mode='json')
    row = BusinessDefinition(workspace_id=access.workspace_id, key=body.definition.key,
        version=body.definition.version, actor_id=access.actor_id, content=content,
        content_hash=digest(content), active=False,
        governance={'status': 'draft', 'revision': 0, 'spec': spec, 'spec_hash': fingerprint(spec)})
    db.add(row)
    db.flush()
    audit(db, access, 'dictionary_draft', row.id, content_hash=row.content_hash)
    return row


def dictionary_json(row):
    return {'id': row.id, 'key': row.key, 'version': row.version, 'owner_id': str(row.actor_id),
        'status': row.governance.get('status', 'historical_unreviewed'),
        'revision': row.governance.get('revision', 0), 'content': row.content,
        'spec': row.governance.get('spec'), 'content_hash': row.content_hash}


def review_definition(db, access, identity, body):
    row = definition(db, access, identity, True)
    gov = dict(row.governance)
    from backend.app.dataplane.reviewer import require_review, owns, source_for_review
    dataset_id = gov.get('spec', {}).get('dataset_id')
    if not dataset_id:
        fail('Historical definition lacks a reviewed dataset scope')
    peer = require_review(db, access, dataset_id)
    if peer and body.action != 'approve':
        fail('A reviewer grant permits approval of submitted definitions only', 403)
    if not peer and body.action in {'revoke', 'supersede'} and access.role not in {'admin', 'owner'}:
        fail('Definition revocation requires source-owner manage permission', 403)
    if gov.get('revision', 0) != body.expected_revision:
        fail('Definition changed; reload before reviewing')
    state = gov.get('status', 'historical_unreviewed')
    transitions = {'review': ('draft', 'review'), 'approve': ('review', 'approved'),
                   'revoke': ('approved', 'revoked'), 'supersede': ('approved', 'superseded')}
    if body.action not in transitions or state != transitions[body.action][0]:
        fail('Invalid definition lifecycle transition')
    if body.action == 'approve':
        if owns(db, access, dataset_id) and access.role not in {'admin', 'owner'}:
            fail('Source authors require an independent granted reviewer', 403)
        approval_allowed(db, access, row.actor_id)
        spec = DictionaryDraft.model_validate(gov['spec'])
        # Key-level lock prevents concurrent approvals of overlapping versions.
        from sqlalchemy import text
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'),
                   {'key': int(fingerprint([str(access.workspace_id), row.key])[:15], 16)})
        for other in db.scalars(select(BusinessDefinition).where(BusinessDefinition.workspace_id == access.workspace_id,
            BusinessDefinition.active.is_(True), BusinessDefinition.id != row.id)):
            raw = other.governance.get('spec')
            if not raw or other.governance.get('status') != 'approved':
                continue
            prior = DictionaryDraft.model_validate(raw)
            labels = {row.key.casefold(), *(a.casefold() for a in spec.aliases)}
            old_labels = {other.key.casefold(), *(a.casefold() for a in prior.aliases)}
            overlaps = spec.effective_from < (prior.effective_to or date.max) and prior.effective_from < (spec.effective_to or date.max)
            if (spec.dataset_id, spec.domain) == (prior.dataset_id, prior.domain) and labels & old_labels and overlaps:
                fail('Conflicting approved definition or alias overlaps this effective period; supersede it explicitly')
        # Validate typed semantics against an actual immutable snapshot before release.
        snapshot = source_for_review(db, access, spec.dataset_id)
        metric, filters = execution_definition(row, spec)
        from backend.app.dataplane.semantic import compile_plan
        try:
            compile_plan(QueryPlan(metric=metric.name, filters=filters), metric, snapshot['payload']['schema'])
        except ValueError as error:
            fail(str(error), 422)
        if any(rule.column not in snapshot['payload']['schema'] for rule in spec.health_rules):
            fail('Health rule references an unknown field', 422)
        verify_examples(spec)
        gov['release_check'] = {'validator': 'typed-source-schema-and-decimal-examples-v1',
            'snapshot_id': str(snapshot['id']), 'status': 'passed', 'example_count': len(spec.definition.examples)}
    gov.update(status=transitions[body.action][1], revision=body.expected_revision + 1,
               reviewed_by=str(access.actor_id), reviewed_at=datetime.now(timezone.utc).isoformat())
    row.governance = gov
    row.active = gov['status'] == 'approved'
    if not row.active:
        invalidate_source(db, access, definition_ref=f'{row.key}@{row.version}')
    audit(db, access, 'dictionary_' + gov['status'], row.id, revision=gov['revision'], reason=body.reason)
    return row


def verify_examples(spec):
    """Independent small fixture oracle; company examples must declare their values."""
    aggregation = spec.definition.metric.aggregation
    for example in spec.definition.examples:
        values = example.get('values')
        if not isinstance(values, list) or len(values) > 1000 or 'expected' not in example:
            fail('Each reviewed example requires a bounded values array and expected result', 422)
        if any(v is None for v in values) and spec.definition.metric.missing == 'reject':
            fail('Example contains missing values rejected by this definition', 422)
        try:
            numbers = [Decimal(str(v)) for v in values if v is not None]
            if any(not v.is_finite() for v in numbers):
                raise ValueError()
            if aggregation == 'count':
                result = Decimal(len(numbers))
            elif not numbers:
                result = None
            elif aggregation in {'sum', 'mean'}:
                result = sum(numbers, Decimal(0))
                if aggregation == 'mean':
                    result /= len(numbers)
            else:
                result = (min if aggregation == 'min' else max)(numbers)
            expected = Decimal(str(example['expected'])) if example['expected'] is not None else None
            if result != expected:
                fail('Independent reviewed example calculation does not match its expected result')
        except (ArithmeticError, ValueError, TypeError):
            fail('Example values must be finite numbers or explicit nulls', 422)


def execution_definition(row, spec):
    base = spec.definition
    metric = Metric(name=row.key, column=base.metric.column,
        aggregation='avg' if base.metric.aggregation == 'mean' else base.metric.aggregation,
        description=spec.description, unit=base.units, grain=spec.grain)
    filters = [Filter(column=f.column, operator=f.operator, value=f.value) for f in base.filters]
    return metric, filters


def query_payload(db, access, body: CompanyQuery):
    row, spec = eligible(db, access, body.definition_id, body.business_date)
    snapshot = get_record(db, access, body.snapshot_id, 'snapshot')
    if snapshot['dataset_id'] != spec.dataset_id:
        fail('Definition and snapshot dataset differ', 422)
    metric, filters = execution_definition(row, spec)
    window = None
    if body.time_window:
        window = body.time_window.model_dump(mode='json')
        dtype = snapshot['payload']['schema'].get(body.time_window.column, '').upper()
        if 'TIMESTAMPTZ' not in dtype and 'TIMESTAMP WITH TIME ZONE' not in dtype and not (dtype.startswith('TIMESTAMP[') and 'TZ=' in dtype):
            fail('Time windows require a timezone-aware timestamp source field; convert ambiguous source dates through an approved ingestion process', 422)
        filters.extend([Filter(column=body.time_window.column, operator='gte', value=window['start']),
                        Filter(column=body.time_window.column, operator='lt', value=window['end'])])
    plan = body.plan.model_copy(update={'filters': [*filters, *body.plan.filters]})
    # Revalidate combined bounds; model_copy alone does not enforce validators.
    plan = QueryPlan.model_validate(plan.model_dump())
    from backend.app.dataplane.semantic import compile_plan
    try:
        compile_plan(plan, metric, snapshot['payload']['schema'])
    except ValueError as error:
        fail(str(error), 422)
    return {'dataset_id': spec.dataset_id, 'snapshot_id': str(snapshot['id']),
        'definition_id': row.id, 'definition_hash': row.content_hash,
        'spec_hash': row.governance['spec_hash'], 'business_date': str(body.business_date),
        'time_window': window,
        'company_metric': metric.model_dump(), 'plan': plan.model_dump(mode='json')}


def current_event(db, access, parent, kind='review'):
    scope = (artifacts.c.tenant_id == access.tenant_id, artifacts.c.workspace_id == access.workspace_id)
    if kind != 'review':
        scope = (*scope, artifacts.c.actor_id == access.actor_id)
    ordering = (artifacts.c.payload['revision'].as_integer().desc(), artifacts.c.id.desc()) if kind == 'review' else (artifacts.c.created_at.desc(), artifacts.c.id.desc())
    row = db.execute(select(artifacts).where(*scope, artifacts.c.kind == kind,
        artifacts.c.parent_id == UUID(str(parent))).order_by(*ordering).limit(1)).mappings().first()
    return dict(row['payload']) if row else {'revision': 0, 'status': 'draft'}


def lock_artifact(db, access, identity, kind):
    row = get_record(db, access, identity, kind)
    db.execute(select(artifacts.c.id).where(*conditions(access), artifacts.c.id == row['id']).with_for_update())
    return row


def review_artifact(db, access, identity, body):
    from backend.app.dataplane.reviewer import record_for_review, require_review, lock_review
    lock_review(db, access, identity)
    row = record_for_review(db, access, identity)
    if row['kind'] not in {'workflow', 'evidence', 'incident'}:
        fail('This artifact does not support review', 422)
    peer = require_review(db, access, row['dataset_id'])
    if peer and body.action != 'approve':
        fail('A reviewer grant permits approval of submitted artifacts only', 403)
    if not peer:
        # Keep lifecycle changes serialized with worker publication, which locks
        # the canonical artifact row before its final state check.
        lock_artifact(db, access, identity, row['kind'])
        if body.action not in {'review', 'approve'} and access.role not in {'admin', 'owner'}:
            fail('Artifact lifecycle control requires source-owner manage permission', 403)
    state = current_event(db, access, identity)
    if state['revision'] != body.expected_revision:
        fail('Review changed; reload before retrying')
    transitions = {'review': {'draft': 'review'}, 'approve': {'review': 'approved'},
        'activate': {'approved': 'active', 'paused': 'active'}, 'pause': {'active': 'paused'},
        'retire': {'draft': 'retired', 'approved': 'retired', 'active': 'retired', 'paused': 'retired'},
        'revoke': {'approved': 'revoked', 'active': 'revoked'},
        'acknowledge': {'draft': 'acknowledged'}, 'resolve': {'acknowledged': 'resolved'}}
    target = transitions.get(body.action, {}).get(state['status'])
    if not target:
        fail('Invalid artifact lifecycle transition')
    if body.action == 'approve':
        if not peer and access.role not in {'admin', 'owner'}:
            fail('Source authors require an independent granted reviewer', 403)
        approval_allowed(db, access, row['actor_id'])
    if row['kind'] == 'workflow' and body.action in {'approve', 'activate'}:
        if peer:
            validate_shared_workflow(db, access, row)
        else:
            from backend.app.dataplane.company_api import workflow_payload
            workflow_payload(db, access, identity, require_active=False)
    if row['kind'] == 'evidence':
        if body.action not in {'review', 'approve', 'revoke'}:
            fail('Report artifacts support review, approval and revocation only')
        if row['payload'].get('validation_status') != 'passed':
            fail('Only validated company results can be approved')
        if body.action == 'approve':
            canonical = definition(db, access, row['payload'].get('definition_id'))
            if not canonical.active or canonical.governance.get('status') != 'approved':
                fail('The output definition is no longer approved')
    if row['kind'] == 'incident' and body.action not in {'acknowledge', 'resolve'}:
        fail('Incidents support acknowledgement and evidence-based resolution only')
    if row['kind'] == 'incident' and body.action == 'resolve':
        latest = db.execute(select(artifacts).where(*conditions(access), artifacts.c.kind == 'evidence',
            artifacts.c.dataset_id == row['dataset_id'], artifacts.c.created_at > row['created_at'],
            artifacts.c.payload['definition_id'].as_string() == row['payload']['definition_id'])
            .order_by(artifacts.c.created_at.desc()).limit(1)).mappings().first()
        if not latest or latest['payload'].get('validation_status') != 'passed':
            fail('A subsequent passing full-snapshot recheck with this definition is required; acknowledgement is not recovery')
    result = {'status': target, 'revision': state['revision'] + 1, 'reason': body.reason,
              'reviewed_by': str(access.actor_id)}
    if row['kind'] == 'incident' and body.action == 'resolve':
        result['recovery_evidence_id'] = str(latest['id'])
    if peer:
        db.execute(artifacts.insert().values(id=uuid4(), tenant_id=access.tenant_id,
            workspace_id=access.workspace_id, actor_id=access.actor_id, dataset_id=row['dataset_id'],
            parent_id=UUID(str(row['id'])), kind='review', payload=result))
    else:
        add_record(db, access, 'review', result, dataset_id=row['dataset_id'], parent_id=row['id'])
    audit(db, access, row['kind'] + '_' + target, str(identity), revision=result['revision'])
    return result


def validate_shared_workflow(db, access, row):
    """Validate the permitted projection; execution later rechecks the full manifest as owner."""
    from backend.app.dataplane.reviewer import shared_record
    spec = WorkflowDraft.model_validate(row['payload']['spec'])
    canonical = definition(db, access, spec.query.definition_id)
    if not canonical.active or canonical.governance.get('status') != 'approved':
        fail('Workflow definition is no longer approved')
    dictionary = DictionaryDraft.model_validate(canonical.governance['spec'])
    if dictionary.dataset_id != row['dataset_id']:
        fail('Workflow definition dataset mismatch', 422)
    day = spec.query.business_date
    if day < dictionary.effective_from or (dictionary.effective_to and day >= dictionary.effective_to):
        fail('Workflow definition is outside its effective dates')
    snapshot = shared_record(db, access, spec.query.snapshot_id, row['dataset_id'])
    metric, filters = execution_definition(canonical, dictionary)
    # The immutable manifest was fully validated on creation. A peer sees masked
    # literals, so recompile canonical semantics and dimensions rather than try
    # to treat a redaction marker as a number/date. Owner activation and every
    # execution revalidate the original complete manifest.
    plan = QueryPlan.model_validate({**spec.query.plan.model_dump(),
        'filters': [item.model_dump() for item in filters]})
    from backend.app.dataplane.semantic import compile_plan
    try:
        compile_plan(plan, metric, snapshot['payload']['schema'])
        if any(item.column not in snapshot['payload']['schema'] for item in spec.query.plan.filters):
            raise ValueError('Workflow filter field is missing')
        if spec.relative_window and spec.relative_window.column not in snapshot['payload']['schema']:
            raise ValueError('Relative period field is missing')
    except ValueError as error:
        fail(str(error), 422)


def comparison(previous, current):
    """Exact persisted aggregate comparison; missing is never coerced to zero."""
    mismatches = []
    for key in ('definition_id', 'definition_hash', 'spec_hash'):
        if previous.get(key) != current.get(key) or previous.get(key) is None:
            mismatches.append(key)
    def normalized_filters(evidence):
        filters = evidence.get('plan', {}).get('filters', [])
        window = evidence.get('time_window')
        if not window:
            return filters
        automatic = [{'column': window['column'], 'operator': 'gte', 'value': window['start']},
                     {'column': window['column'], 'operator': 'lt', 'value': window['end']}]
        return [f for f in filters if f not in automatic]
    for key in ('metric', 'dimensions', 'filters'):
        # Metric is a typed object outside plan; compare all declared semantics.
        a = previous.get('metric') if key == 'metric' else normalized_filters(previous) if key == 'filters' else previous.get('plan', {}).get(key)
        b = current.get('metric') if key == 'metric' else normalized_filters(current) if key == 'filters' else current.get('plan', {}).get(key)
        if a != b:
            mismatches.append(key)
    def duration(evidence):
        window = evidence.get('time_window')
        if not window:
            return None
        return (window['column'], (datetime.fromisoformat(window['end']) - datetime.fromisoformat(window['start'])).total_seconds())
    if duration(previous) != duration(current):
        mismatches.append('time_window_length_or_basis')
    for key in ('timezone', 'currency', 'grain', 'date_basis', 'exclusions', 'missing'):
        if previous.get('definition_context', {}).get(key) != current.get('definition_context', {}).get(key):
            mismatches.append(key)
    for key in ('validation_status', 'coverage'):
        if previous.get(key) != current.get(key) or previous.get(key) is None:
            mismatches.append(key)
    # Different transformations are a calculation change, not a business delta.
    if previous.get('transformation') != current.get('transformation'):
        mismatches.append('transformation')
    dimensions = current.get('plan', {}).get('dimensions', [])
    def indexed(evidence):
        rows = {}
        for row in evidence.get('rows', []):
            key = tuple(row.get(d) for d in dimensions)
            if key in rows:
                raise ValueError('Duplicate comparison grain')
            rows[key] = row.get('value')
        return rows
    old, new = indexed(previous), indexed(current)
    values = []
    with localcontext() as context:
        context.prec = 38
        for key in sorted(set(old) | set(new), key=str):
            a, b = old.get(key), new.get(key)
            change = percentage = None
            if not mismatches and key in old and key in new and a is not None and b is not None:
                a, b = Decimal(str(a)), Decimal(str(b))
                if not a.is_finite() or not b.is_finite():
                    raise ValueError('Non-finite comparison input')
                change = str(b - a)
                percentage = str(((b-a)/abs(a)*100).quantize(Decimal('0.000001'))) if a else None
            values.append({'dimensions': dict(zip(dimensions, key)), 'previous': old.get(key), 'current': new.get(key),
                'entity': 'new' if key not in old else 'removed' if key not in new else 'matched',
                'absolute_change': change, 'percentage_change': percentage})
    additive = current.get('metric', {}).get('aggregation') in {'sum', 'count'}
    complete = not mismatches and all((r['previous'] is not None or r['entity'] == 'new') and
        (r['current'] is not None or r['entity'] == 'removed') for r in values)
    contributions, totals = None, None
    if additive and complete:
        contributions = []
        with localcontext() as context:
            context.prec = 38
            for row in values:
                before = Decimal(0) if row['entity'] == 'new' else Decimal(str(row['previous']))
                after = Decimal(0) if row['entity'] == 'removed' else Decimal(str(row['current']))
                contributions.append({'dimensions': row['dimensions'], 'entity': row['entity'], 'contribution': str(after-before)})
            before_total = sum((Decimal(str(r['previous'])) for r in values if r['entity'] != 'new'), Decimal(0))
            after_total = sum((Decimal(str(r['current'])) for r in values if r['entity'] != 'removed'), Decimal(0))
            delta = after_total-before_total
            if sum((Decimal(r['contribution']) for r in contributions), Decimal(0)) != delta:
                raise ValueError('Dimension contributions do not reconcile')
            totals = {'previous': str(before_total), 'current': str(after_total), 'absolute_change': str(delta)}
    percent_unit = current.get('definition_context', {}).get('units', '').lower() in {'percent', '%', 'percentage'}
    return {'comparable': not mismatches, 'mismatches': mismatches, 'rows': values,
        'absolute_change_unit': 'percentage points' if percent_unit else current.get('metric', {}).get('unit', 'source units'),
        'percentage_denominator': 'absolute previous value; zero is undefined; missing is not zero',
        'precision': 'decimal arithmetic, 38 significant digits; percentage rounded to 6 decimal places (half even)',
        'contributions': contributions, 'totals': totals,
        'contribution_note': 'Additive contributions reconcile to total change; new/removed groups represent absent activity in a complete aggregate, while null values remain unknown' if additive and complete else 'Attribution unavailable for non-additive, missing or incompatible values',
        'source_changed': previous.get('snapshot_hash') != current.get('snapshot_hash'),
        'quality_changed': [{k: v for k, v in c.items() if k != 'collected_at'} for c in previous.get('quality_checks', [])] !=
                           [{k: v for k, v in c.items() if k != 'collected_at'} for c in current.get('quality_checks', [])],
        'system_changed': previous.get('engine_version') != current.get('engine_version'),
        'causality': 'Observed differences are associations; no cause is established.'}
