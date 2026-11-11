"""Scoped resolver snapshots and release attestations; existing weights table reused."""
from dataclasses import asdict
from pathlib import Path
import hashlib
from uuid import UUID
from sqlalchemy import select, func, cast, Text

from backend.app.learning.column_ranker import ColumnRanker, FEATURE_VERSION
from backend.app.learning.column_table import resolver_events as events
from backend.app.learning.memory_contract import digest
from backend.app.learning.tables import learner_weights as weights

LEARNER = 'column_metric_resolver'


def fingerprint():
    directory = Path(__file__).parent
    paths = [directory / name for name in ('column_ranker.py', 'column_contract.py', 'column_store.py',
        'column_runtime.py', 'column_lifecycle.py', 'failure_memory.py')]
    paths += [directory.parent / 'services/natural_language_analytics.py', directory.parent / 'api/v1/routes/chat.py']
    return hashlib.sha256(b''.join(path.read_bytes() for path in paths)).hexdigest()


def scope_dict(scope):
    return {key: str(value) if isinstance(value, UUID) else value for key, value in asdict(scope).items()}


def validate(payload):
    if (not isinstance(payload, dict) or set(payload) != {'format', 'feature_version', 'scope', 'manifest_digest', 'weights', 'vocabulary'}
            or type(payload['format']) is not int or payload['format'] != 1 or payload['feature_version'] != FEATURE_VERSION
            or not isinstance(payload['scope'], dict) or set(payload['scope']) != {'tenant_id', 'workspace_id', 'actor_id', 'dataset_id', 'dataset_version', 'schema_hash'}
            or not isinstance(payload['manifest_digest'], str) or len(payload['manifest_digest']) != 64):
        raise ValueError('Invalid resolver snapshot')
    ColumnRanker(payload['weights'], payload['vocabulary'])
    return payload


def condition(tenant):
    return (weights.c.tenant_id == tenant) & (weights.c.learner == LEARNER)


def read(db, tenant, version):
    where = condition(tenant) & (weights.c.version == version)
    size = db.scalar(select(func.octet_length(cast(weights.c.weights, Text))).where(where))
    if size is None or size > 100_000:
        raise ValueError('Missing/oversized resolver snapshot')
    return validate(db.scalar(select(weights.c.weights).where(where)))


def active(db, tenant):
    return db.scalar(select(weights.c.version).where(condition(tenant), weights.c.is_active.is_(True))) or 0


def attested(db, current, version, payload, action):
    return db.scalar(select(events.c.id).where(events.c.tenant_id == current.tenant_id,
        events.c.workspace_id == current.workspace_id, events.c.actor_id == current.actor_id,
        events.c.dataset_id == current.dataset_id, events.c.dataset_version == current.dataset_version,
        events.c.schema_hash == current.schema_hash, events.c.version == version, events.c.action == action,
        events.c.model_digest == digest(payload), events.c.runtime_digest == fingerprint()).limit(1)) is not None


def event(db, current, action, version, previous=0, payload=None, reviewer=None, detail=None):
    db.execute(events.insert().values(**asdict(current), action=action, version=version, previous_version=previous,
        model_digest=digest(payload) if payload else None, runtime_digest=fingerprint(), reviewer_id=reviewer, detail=detail or {}))
