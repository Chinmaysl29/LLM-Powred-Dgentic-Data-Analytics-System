"""Request-local batches for bounded company list pages; no authorization cache."""
from collections import defaultdict
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from backend.app.dataplane.records import artifacts, conditions
from backend.app.models.background_job import DurableJob
from backend.app.models.learning import BusinessDefinition


def latest_events(db, access, parents, kind='review'):
    identities = {UUID(str(parent)) for parent in parents}
    if not identities:
        return {}
    scope = [artifacts.c.tenant_id == access.tenant_id, artifacts.c.workspace_id == access.workspace_id]
    if kind != 'review':
        scope.append(artifacts.c.actor_id == access.actor_id)
    # Reviews can be authored by a granted peer. RLS still checks access to each
    # event; filtering to the caller would silently discard independent approvals.
    ordering = (artifacts.c.payload['revision'].as_integer().desc(), artifacts.c.id.desc()) if kind == 'review' else (artifacts.c.created_at.desc(), artifacts.c.id.desc())
    ranked = select(artifacts.c.parent_id, artifacts.c.payload,
        func.row_number().over(partition_by=artifacts.c.parent_id, order_by=ordering).label('position'))\
        .where(*scope, artifacts.c.kind == kind, artifacts.c.parent_id.in_(identities)).subquery()
    return {str(row.parent_id): row.payload for row in db.execute(
        select(ranked.c.parent_id, ranked.c.payload).where(ranked.c.position == 1))}


def workflow_runs(db, access, workflows):
    identities = {str(identity) for identity in workflows}
    grouped = defaultdict(list)
    if not identities:
        return grouped
    workflow_id = DurableJob.payload['workflow_id'].as_string()
    ranked = select(DurableJob.id, DurableJob.status, DurableJob.attempt, DurableJob.error_code,
        DurableJob.payload, DurableJob.result, workflow_id.label('workflow_id'),
        func.row_number().over(partition_by=workflow_id, order_by=DurableJob.created_at.desc()).label('position'))\
        .where(DurableJob.workspace_id == access.workspace_id, DurableJob.owner_id == access.actor_id,
            DurableJob.kind == 'dp_workflow', workflow_id.in_(identities)).subquery()
    # The limit is per workflow, not global to the page.
    for row in db.execute(select(ranked).where(ranked.c.position <= 10).order_by(ranked.c.position)).mappings():
        grouped[row['workflow_id']].append(row)
    return grouped


def output_lineage(db, access, datasets):
    identities = set(datasets)
    grouped = defaultdict(list)
    if not identities:
        return grouped
    dataset_scope = artifacts.c.dataset_id.in_(identities - {None})
    if None in identities:
        dataset_scope = or_(dataset_scope, artifacts.c.dataset_id.is_(None))
    # Only lineage/manifest JSON crosses the wire. Aggregate evidence rows and
    # execution details are neither needed nor hydrated by this endpoint.
    ranked = select(artifacts.c.id, artifacts.c.dataset_id, artifacts.c.kind,
        artifacts.c.payload['lineage'].label('lineage'), artifacts.c.payload['spec'].label('spec'),
        func.row_number().over(partition_by=artifacts.c.dataset_id,
            order_by=artifacts.c.created_at.desc()).label('position'))\
        .where(*conditions(access), dataset_scope, artifacts.c.kind.in_(['workflow', 'evidence'])).subquery()
    outputs = db.execute(select(ranked).where(ranked.c.position <= 100).order_by(ranked.c.position)).mappings().all()
    definition_ids = {row['spec']['query']['definition_id'] for row in outputs if row['kind'] == 'workflow'}
    definitions = dict(db.execute(select(BusinessDefinition.id, BusinessDefinition.content).where(
        BusinessDefinition.workspace_id == access.workspace_id, BusinessDefinition.id.in_(definition_ids))).all()) if definition_ids else {}
    for row in outputs:
        lineage = row['lineage']
        if row['kind'] == 'workflow':
            spec = row['spec']
            query = spec['query']
            definition = definitions.get(query['definition_id'])
            if definition is None:
                raise HTTPException(404, 'Definition not found')
            lineage = {'snapshot_id': query['snapshot_id'], 'fields': [definition['metric']['column'],
                *query['plan']['dimensions'], *(f['column'] for f in query['plan'].get('filters', [])),
                *(f['column'] for f in definition.get('filters', [])),
                *([query['time_window']['column']] if query.get('time_window') else []),
                *([spec['relative_window']['column']] if spec.get('relative_window') else [])]}
        grouped[row['dataset_id']].append({'id': row['id'], 'kind': row['kind'], 'lineage': lineage})
    return grouped
