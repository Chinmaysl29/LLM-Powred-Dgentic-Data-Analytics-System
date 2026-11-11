"""Read-only, bounded reporting of persisted evidence; never runs a learner."""
from datetime import datetime, timedelta, timezone
import math
import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.app.core.workspace_authorization import (
    authorize_workspace, dataset_workspace_bindings, workspace_memberships,
)
from backend.app.learning.evidence import enabled, ERROR_TYPES
from backend.app.learning.tables import feedback_events, learner_weights
from backend.app.learning.shadow_table import shadow_predictions
from backend.app.learning.release_table import router_releases
from backend.app.learning.column_table import resolver_events
from backend.app.learning.selection_table import selection_events
from backend.app.models import Dataset

LEARNERS = ('intent_router', 'column_metric_resolver', 'chart_selector', 'provider_bandit')
EVALUATION_LIMIT = 100


def report_metrics(learner: str, report: object) -> dict | None:
    """Expose only checked scalar summaries, never report payloads or case text."""
    if not isinstance(report, dict) or not re.fullmatch(r'[a-f0-9]{64}', str(report.get('manifest_digest', ''))):
        return None
    detail = report.get('gate') if learner == 'intent_router' else report
    if not isinstance(detail, dict) or detail.get('passed') is not True:
        return None
    count = detail.get('intent_count') if learner == 'intent_router' else detail.get('cases')
    if type(count) is not int or not 1 <= count <= 10000:
        return None
    reward = None
    if learner == 'intent_router':
        correct = detail.get('candidate_correct')
    elif learner == 'column_metric_resolver':
        correct = detail.get('correct')
    elif learner == 'chart_selector':
        correct = detail.get('candidate_score')
    else:
        if detail.get('all_correct') is not True:
            return None
        correct = count
        score = detail.get('candidate_score')
        if type(score) not in (int, float) or not math.isfinite(score) or not -.2 * count <= score <= count:
            return None
        reward = score / count
    if (type(correct) not in (int, float) or not math.isfinite(correct)
            or correct != int(correct) or correct != count):
        return None
    return {'cases': count, 'correct': int(correct), 'accuracy': correct / count,
            'mean_reward': reward, 'manifest_digest': report['manifest_digest']}


def owned_datasets(access):
    return select(Dataset.dataset_id).join(dataset_workspace_bindings,
        dataset_workspace_bindings.c.dataset_id == Dataset.dataset_id).where(
        Dataset.owner_id == str(access.actor_id), Dataset.status.not_in(['deleted', 'archived', 'purged']),
        dataset_workspace_bindings.c.workspace_id == access.workspace_id)


def scoped(table, access, dataset_column):
    return and_(table.c.tenant_id == access.tenant_id, table.c.workspace_id == access.workspace_id,
        table.c.actor_id == access.actor_id, dataset_column.in_(owned_datasets(access)))


def collect(db: Session, access, days: int, offset: int, limit: int, now: datetime) -> dict:
    cutoff = now - timedelta(days=days)
    result = {'enabled': enabled(), 'workspace_id': str(access.workspace_id), 'days': days,
        'since': cutoff.isoformat(), 'as_of': now.isoformat(), 'top_mistakes': [],
        'shadow': {'observations': 0, 'abstentions': 0, 'compared': 0, 'agreements': 0, 'agreement_rate': None},
        'evaluations': [], 'evaluations_truncated': False, 'omitted_evaluations': 0,
        'versions': [], 'next_offset': None}
    if not result['enabled']:
        return result
    period = lambda table: and_(table.c.created_at >= cutoff, table.c.created_at <= now)
    f = feedback_events
    error = case((f.c.features['error_type'].astext.in_(sorted(ERROR_TYPES)),
                  f.c.features['error_type'].astext), else_='other')
    failures = db.execute(select(error.label('error_type'), func.count().label('count')).where(
        scoped(f, access, f.c.features['dataset_id'].astext), period(f), f.c.signal_type == 'hard_failure'
    ).group_by(error).order_by(func.count().desc(), error)).mappings()
    result['top_mistakes'] = [dict(row) for row in failures]
    s = shadow_predictions
    compared = and_(s.c.abstained.is_(False), s.c.live_intent.is_not(None))
    row = db.execute(select(func.count().label('observations'),
        func.count().filter(s.c.abstained.is_(True)).label('abstentions'),
        func.count().filter(compared).label('compared'),
        func.count().filter(compared, s.c.shadow_intent == s.c.live_intent).label('agreements')
    ).where(scoped(s, access, s.c.dataset_id), period(s))).mappings().one()
    result['shadow'] = {**row, 'agreement_rate': row['agreements'] / row['compared'] if row['compared'] else None}

    # Tenant-wide router versions have no dataset scope. All other versions must
    # match this actor, workspace and an owned, currently accessible dataset.
    w = learner_weights
    weight_scope = w.c.weights['scope']
    visible = or_(w.c.learner == 'intent_router', and_(
        weight_scope['workspace_id'].astext == str(access.workspace_id),
        weight_scope['actor_id'].astext == str(access.actor_id),
        weight_scope['tenant_id'].astext == str(access.tenant_id),
        weight_scope['dataset_id'].astext.in_(owned_datasets(access))))
    versions = db.execute(select(w.c.learner, w.c.version, w.c.is_active.label('selected'), w.c.created_at)
        .where(w.c.tenant_id == access.tenant_id, w.c.learner.in_(LEARNERS), visible)
        .order_by(w.c.created_at.desc(), w.c.id.desc()).offset(offset).limit(limit + 1)).mappings().all()
    result['versions'] = [dict(row) for row in versions[:limit]]
    result['next_offset'] = offset + limit if len(versions) > limit and offset + limit <= 10000 else None

    # Each query has a hard row limit and selects scalar report fields only.
    sources = [(router_releases, 'intent_router', router_releases.c.evidence,
                router_releases.c.tenant_id == access.tenant_id),
               (resolver_events, 'column_metric_resolver', resolver_events.c.detail,
                scoped(resolver_events, access, resolver_events.c.dataset_id)),
               (selection_events, None, selection_events.c.detail,
                scoped(selection_events, access, selection_events.c.dataset_id))]
    for table, learner, detail, where in sources:
        fields = ('manifest_digest', 'gate') if learner == 'intent_router' else (
            'manifest_digest', 'cases', 'correct', 'candidate_score', 'all_correct', 'passed')
        columns = [table.c.id, table.c.version, table.c.created_at]
        if learner is None:
            columns.append(table.c.kind)
        columns += [detail[key].label(key) for key in fields]
        rows = db.execute(select(*columns).where(where, table.c.action == 'promote', period(table))
            .order_by(table.c.created_at.desc(), table.c.id.desc()).limit(EVALUATION_LIMIT + 1)).mappings().all()
        result['evaluations_truncated'] |= len(rows) > EVALUATION_LIMIT
        for row in rows[:EVALUATION_LIMIT]:
            name = learner or ('chart_selector' if row['kind'] == 'chart' else 'provider_bandit')
            metrics = report_metrics(name, {key: row[key] for key in fields})
            if metrics is None:
                result['omitted_evaluations'] += 1
                continue
            result['evaluations'].append({'learner': name, 'version': row['version'],
                'created_at': row['created_at'], **metrics})
    result['evaluations'].sort(key=lambda row: (row['created_at'], row['learner'], row['version']))
    return result


def dashboard(bind, actor: UUID, workspace: UUID, days: int, offset: int, limit: int) -> dict:
    """Separate read-only transaction protects even a privileged live connection."""
    try:
        with Session(bind) as db, db.begin():
            db.execute(text('SET TRANSACTION READ ONLY'))
            db.execute(text("SET LOCAL statement_timeout='1500ms'"))
            db.execute(text("SET LOCAL lock_timeout='100ms'"))
            access = authorize_workspace(db, actor, workspace)
            if db.scalar(select(workspace_memberships.c.user_id).where(
                    workspace_memberships.c.workspace_id == access.workspace_id,
                    workspace_memberships.c.user_id == access.actor_id,
                    workspace_memberships.c.active.is_(True))) is None:
                raise HTTPException(404, 'Resource not found')
            for key, value in (('actor_id', access.actor_id), ('workspace_id', access.workspace_id), ('tenant_id', access.tenant_id)):
                db.execute(text('SELECT set_config(:key,:value,true)'), {'key': f'app.{key}', 'value': str(value)})
            return collect(db, access, days, offset, limit, datetime.now(timezone.utc))
    except SQLAlchemyError:
        raise HTTPException(503, 'Learning dashboard is temporarily unavailable') from None
