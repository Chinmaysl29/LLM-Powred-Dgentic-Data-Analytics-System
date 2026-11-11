"""Bounded schema-only resolver, shadow first and fail-open to original parsing."""
from threading import BoundedSemaphore
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.core.config import get_settings
from backend.app.core.database_target import bind_database_schema
from backend.app.learning.evidence import enabled
from backend.app.learning.failure_memory import scope
from backend.app.learning.column_ranker import ColumnRanker, question_hash
from backend.app.learning.column_contract import schema_fields, eligible, apply_choice
from backend.app.learning.column_store import weights, condition, read, active, attested, event, scope_dict
from backend.app.learning.memory_contract import digest

_slots = BoundedSemaphore(2)


def resolve(actor_id, question, schema, plan, context=None):
    if not enabled() or not actor_id or not plan.dataset_id or not plan.dataset_version:
        return plan
    engine = None
    acquired = False
    try:
        if not eligible(question, schema, plan, context):
            return plan
        acquired = _slots.acquire(blocking=False)
        if not acquired:
            return plan
        _, _, _, candidates = schema_fields(schema)
        settings = get_settings()
        engine = create_engine(settings.postgres_dsn, poolclass=NullPool, hide_parameters=True,
            connect_args={'connect_timeout': 2})
        bind_database_schema(engine, settings.database_schema)
        with Session(engine) as db, db.begin():
            db.execute(text("SET LOCAL statement_timeout='300ms'"))
            db.execute(text("SET LOCAL lock_timeout='100ms'"))
            current = scope(db, actor_id, plan.dataset_id, plan.dataset_version)
            if current.schema_hash != digest(schema):
                return plan
            live_version = active(db, current.tenant_id)
            staged = db.scalar(select(func.max(weights.c.version)).where(condition(current.tenant_id), weights.c.is_active.is_(False)))
            chosen = None
            for version in dict.fromkeys(v for v in (staged, live_version) if v):
                payload = read(db, current.tenant_id, version)
                if payload['scope'] != scope_dict(current) or not attested(db, current, version, payload, 'stage'):
                    continue
                prediction, margin = ColumnRanker(payload['weights'], payload['vocabulary']).predict(question, candidates, schema['dtypes'])
                event(db, current, 'shadow', version, live_version, payload, detail={
                    'question_hash': question_hash(question), 'choice_hash': digest(prediction) if prediction else None,
                    'margin': margin, 'abstained': prediction is None})
                if version == live_version and attested(db, current, version, payload, 'promote'):
                    chosen = prediction
            return apply_choice(plan, chosen, candidates)
    except Exception:
        return plan
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass
        if acquired:
            _slots.release()


def scoped_resolver(actor_id):
    if not enabled() or not actor_id:
        return None
    return lambda question, schema, plan, context: resolve(actor_id, question, schema, plan, context)
