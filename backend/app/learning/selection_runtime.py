"""Authorized fail-open policy reads; charts preserve every original point/value."""
import asyncio
from datetime import datetime
import math
import re
from threading import BoundedSemaphore
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from backend.app.core.config import get_settings
from backend.app.core.database_target import bind_database_schema
from backend.app.learning.evidence import enabled
from backend.app.learning.failure_memory import scope
from backend.app.learning import selection_store as store
from backend.app.learning.selection_models import PROVIDERS, load_model

_slots = BoundedSemaphore(2)


def decide(actor, dataset_id, dataset_version, kind, context):
    if not enabled() or not actor or not dataset_id or not _slots.acquire(blocking=False):
        return None
    engine = None
    try:
        settings = get_settings()
        engine = create_engine(settings.postgres_dsn, poolclass=NullPool, hide_parameters=True, connect_args={'connect_timeout': 2})
        bind_database_schema(engine, settings.database_schema)
        with Session(engine) as db, db.begin():
            db.execute(text("SET LOCAL statement_timeout='300ms'")); db.execute(text("SET LOCAL lock_timeout='100ms'"))
            current = scope(db, actor, dataset_id, dataset_version)
            active = store.active(db, current.tenant_id, kind)
            candidate = db.scalar(select(func.max(store.weights.c.version)).where(store.condition(current.tenant_id, kind), store.weights.c.is_active.is_(False)))
            selected = None
            for version in dict.fromkeys(v for v in (candidate, active) if v):
                payload = store.read(db, current.tenant_id, kind, version)
                if payload['scope'] != store.scope_dict(current) or not store.attested(db, current, kind, version, payload, 'stage'):
                    continue
                model = load_model(kind, payload['model'])
                if kind == 'chart':
                    choice = model.predict(context)
                else:
                    if [p for p in PROVIDERS if p in model.models] != context:
                        continue  # Changed configured arm set requires reevaluation.
                    choice = model.choose()
                store.event(db, current, kind, 'shadow', version, active, payload, detail={'choice': choice})
                if version == active and store.attested(db, current, kind, version, payload, 'promote'):
                    selected = {'choice': choice, 'model': payload['model']}
            return selected
    except Exception:
        return None
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass
        _slots.release()


async def decision(actor, dataset_id, dataset_version, kind, context):
    if not enabled() or not actor or not dataset_id:
        return None
    try:
        return await asyncio.wait_for(asyncio.to_thread(decide, actor, dataset_id, dataset_version, kind, context), timeout=2.5)
    except Exception:
        return None


def chart_context(question, result):
    chart, plan = result.get('chart'), result.get('plan')
    if result.get('status') != 'complete' or not isinstance(chart, dict) or not isinstance(plan, dict) or chart.get('chart_type') != 'bar':
        return None
    points, rows = chart.get('points'), result.get('data')
    if not isinstance(points, list) or not 1 <= len(points) <= 50 or not isinstance(rows, list) or len(rows) != len(points):
        return None
    x, y = chart.get('x_field'), chart.get('y_field')
    for point, row in zip(points, rows):
        if (not isinstance(point, dict) or not isinstance(row, dict) or type(point.get('value')) not in (int, float)
                or not math.isfinite(point['value']) or str(row.get(x)) != point.get('label') or row.get(y) != point['value']):
            return None
    temporal = plan.get('operation') == 'trend' and x == plan.get('date_field') and not plan.get('dimensions')
    if temporal:
        labels = [point['label'] for point in points]
        try:
            dates = [datetime.strptime(label, '%Y-%m') for label in labels]
        except (ValueError, TypeError):
            return None
        if dates != sorted(set(dates)):
            return None
    dimensions = len(plan.get('dimensions') or []) + int(plan.get('operation') == 'trend')
    if not 1 <= dimensions <= 4:
        return None
    return {'temporal': bool(temporal), 'points': len(points), 'dimensions': dimensions,
        'ranking': plan.get('operation') in ('top', 'bottom'),
        'explicit': bool(re.search(r'\b(bar|line|area|pie|scatter|heatmap|waterfall|funnel|treemap)\b', question, re.I))}


async def select_chart(actor, question, result):
    if not enabled():
        return result
    try:
        context = chart_context(question, result)
        if context is None or context['explicit']:
            return result
        plan = result['plan']
        answer = await decision(actor, plan.get('dataset_id'), plan.get('dataset_version'), 'chart', context)
        if answer and answer['choice'] == 'line' and context['temporal'] and context['points'] >= 2:
            return {**result, 'chart': {**result['chart'], 'chart_type': 'line'}}
    except Exception:
        pass
    return result
