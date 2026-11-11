"""Selection snapshots and scoped, source-bound release evidence."""
from dataclasses import asdict
from pathlib import Path
import hashlib
from sqlalchemy import select, func, cast, Text
from backend.app.learning.tables import learner_weights as weights
from backend.app.learning.selection_table import selection_events as events
from backend.app.learning.selection_models import KINDS, load_model
from backend.app.learning.column_store import scope_dict
from backend.app.learning.memory_contract import digest


def learner(kind):
    if kind not in KINDS:
        raise ValueError('Unsupported selection learner')
    return 'chart_selector' if kind == 'chart' else 'provider_bandit'


def fingerprint():
    directory = Path(__file__).parent
    names = ('selection_models.py', 'selection_contract.py', 'selection_store.py', 'selection_lifecycle.py',
        'selection_runtime.py', 'selection_provider.py', 'failure_memory.py')
    paths = [directory / name for name in names]
    paths += [directory.parent / 'llm/provider.py', directory.parent / 'services/intent_classification_service.py',
        directory.parent / 'services/natural_language_analytics.py', directory.parent / 'api/v1/routes/chat.py',
        directory.parent / 'api/v1/routes/intent.py']
    return hashlib.sha256(b''.join(path.read_bytes() for path in paths)).hexdigest()


def condition(tenant, kind):
    return (weights.c.tenant_id == tenant) & (weights.c.learner == learner(kind))


def validate(payload, kind):
    if (not isinstance(payload, dict) or set(payload) != {'format', 'kind', 'scope', 'manifest_digest', 'model'}
            or type(payload['format']) is not int or payload['format'] != 1 or payload['kind'] != kind
            or not isinstance(payload['scope'], dict) or set(payload['scope']) != {'tenant_id', 'workspace_id', 'actor_id', 'dataset_id', 'dataset_version', 'schema_hash'}
            or not isinstance(payload['manifest_digest'], str) or len(payload['manifest_digest']) != 64):
        raise ValueError('Invalid selection snapshot')
    load_model(kind, payload['model'])
    return payload


def read(db, tenant, kind, version):
    where = condition(tenant, kind) & (weights.c.version == version)
    size = db.scalar(select(func.octet_length(cast(weights.c.weights, Text))).where(where))
    if size is None or size > 100_000:
        raise ValueError('Missing/oversized selection snapshot')
    return validate(db.scalar(select(weights.c.weights).where(where)), kind)


def active(db, tenant, kind):
    return db.scalar(select(weights.c.version).where(condition(tenant, kind), weights.c.is_active.is_(True))) or 0


def attested(db, current, kind, version, payload, action):
    return db.scalar(select(events.c.id).where(events.c.tenant_id == current.tenant_id,
        events.c.workspace_id == current.workspace_id, events.c.actor_id == current.actor_id,
        events.c.dataset_id == current.dataset_id, events.c.dataset_version == current.dataset_version,
        events.c.schema_hash == current.schema_hash, events.c.kind == kind, events.c.version == version,
        events.c.action == action, events.c.model_digest == digest(payload), events.c.runtime_digest == fingerprint()).limit(1)) is not None


def event(db, current, kind, action, version, previous=0, payload=None, reviewer=None, detail=None):
    db.execute(events.insert().values(**asdict(current), kind=kind, action=action, version=version,
        previous_version=previous, model_digest=digest(payload) if payload else None,
        runtime_digest=fingerprint(), reviewer_id=reviewer, detail=detail or {}))
