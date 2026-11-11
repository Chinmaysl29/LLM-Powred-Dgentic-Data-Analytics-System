"""Fail-open recall. Postgres is authoritative; Chroma supplies candidate IDs only."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import BoundedSemaphore
from uuid import UUID

from sqlalchemy import create_engine, select, text, func, cast, Text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.core.config import get_settings
from backend.app.core.database_target import bind_database_schema
from backend.app.core.workspace_authorization import authorize_workspace, authorize_bound_dataset, dataset_workspace_bindings, workspace_memberships
from backend.app.models import DatasetVersion
from backend.app.learning.evidence import enabled
from backend.app.learning.memory_chroma import MemoryIndex
from backend.app.learning.memory_contract import correction, embedding, checked_vector, digest, payload_digest, EMBEDDING_VERSION, MIN_SIMILARITY
from backend.app.learning.memory_table import failure_memory_links as links
from backend.app.learning.tables import mistakes
from backend.app.learning.perceptron import LABELS

_read_slots = BoundedSemaphore(2)


@dataclass(frozen=True)
class MemoryScope:
    tenant_id: UUID
    workspace_id: UUID
    actor_id: UUID
    dataset_id: str
    dataset_version: int
    schema_hash: str

    def filters(self, intent: str) -> dict:
        return {"tenant_id": str(self.tenant_id), "workspace_id": str(self.workspace_id),
            "actor_id": str(self.actor_id), "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version, "schema_hash": self.schema_hash,
            "intent": intent, "embedding_version": EMBEDDING_VERSION}


def scope(db: Session, actor_id: str | UUID, dataset_id: str, version_number: int | None = None) -> MemoryScope:
    workspace = db.scalar(select(dataset_workspace_bindings.c.workspace_id).where(
        dataset_workspace_bindings.c.dataset_id == dataset_id))
    if workspace is None:
        raise ValueError("Dataset is unbound")
    access = authorize_workspace(db, actor_id, workspace)
    authorize_bound_dataset(db, access, dataset_id)
    # Match the memory table's stricter policy even with an operator connection:
    # tenant administrators also need a current workspace membership for recall.
    if db.scalar(select(workspace_memberships.c.user_id).where(
            workspace_memberships.c.user_id == access.actor_id,
            workspace_memberships.c.workspace_id == access.workspace_id,
            workspace_memberships.c.active.is_(True))) is None:
        raise ValueError("Failure memory workspace membership unavailable")
    query = select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
    query = query.where(DatasetVersion.version_number == version_number) if version_number is not None else query.where(DatasetVersion.is_active.is_(True))
    version = db.scalar(query)
    if version is None:
        raise ValueError("Dataset version unavailable")
    snapshot = version.metadata_snapshot or {}
    schema = {key: snapshot[key] for key in ("columns", "dtypes") if key in snapshot}
    columns, dtypes = schema.get("columns"), schema.get("dtypes")
    if (not isinstance(columns, list) or not 1 <= len(columns) <= 200 or not isinstance(dtypes, dict)
            or any(not isinstance(c, str) or len(c) > 256 or c not in dtypes for c in columns)
            or any(not isinstance(dtypes[c], str) for c in columns)):
        raise ValueError("Reliable schema unavailable")
    for key, value in (("tenant_id", access.tenant_id), ("workspace_id", access.workspace_id), ("actor_id", access.actor_id)):
        db.execute(text("SELECT set_config(:key,:value,true)"), {"key": f"app.{key}", "value": str(value)})
    return MemoryScope(access.tenant_id, access.workspace_id, access.actor_id,
                       dataset_id, version.version_number, digest(schema))


def verified_rows(db: Session, current: MemoryScope, ids: list[UUID]):
    return db.execute(select(mistakes, links.c.payload_digest.label("review_digest"), links.c.feedback_id)
        .join(links, links.c.mistake_id == mistakes.c.id).where(
            links.c.mistake_id.in_(ids[:20]), links.c.active.is_(True),
            links.c.tenant_id == current.tenant_id, links.c.workspace_id == current.workspace_id,
            links.c.actor_id == current.actor_id, links.c.dataset_id == current.dataset_id,
            links.c.dataset_version == current.dataset_version, links.c.schema_hash == current.schema_hash,
            mistakes.c.tenant_id == links.c.tenant_id, mistakes.c.workspace_id == links.c.workspace_id,
            mistakes.c.actor_id == links.c.actor_id, mistakes.c.dataset_schema_hash == links.c.schema_hash,
            func.octet_length(cast(mistakes.c.features, Text)) <= 100_000,
            func.octet_length(cast(mistakes.c.corrected_plan, Text)) <= 4096)).mappings().all()


def validate_record(row) -> tuple[dict, list[float]]:
    plan = correction(row["corrected_plan"])
    features = row["features"]
    if (row["question"] is not None or row["signal_type"] != "reviewed_hard_failure"
            or row["truth"] != plan["intent"] or not isinstance(features, dict)
            or set(features) != {"embedding_version", "embedding"}
            or features["embedding_version"] != EMBEDDING_VERSION
            or payload_digest(row) != row["review_digest"]):
        raise ValueError("Unverified correction payload")
    checked_vector(features["embedding"])
    return plan, features["embedding"]


def retrieve_sync(actor_id: str | UUID, dataset_id: str, question: str, intent: str) -> list[dict]:
    if not enabled() or not actor_id or not dataset_id or intent not in LABELS or intent == "unknown":
        return []
    if not _read_slots.acquire(blocking=False):
        return []
    engine = None
    try:
        vector = embedding(question)
        settings = get_settings()
        engine = create_engine(settings.postgres_dsn, poolclass=NullPool, hide_parameters=True,
                               connect_args={"connect_timeout": 2})
        bind_database_schema(engine, settings.database_schema)
        with Session(engine) as db, db.begin():
            db.execute(text("SET LOCAL statement_timeout='300ms'"))
            db.execute(text("SET LOCAL lock_timeout='100ms'"))
            current = scope(db, actor_id, dataset_id)
        # No database transaction is held across the network call.
        with MemoryIndex() as index:
            ids = index.query(current.tenant_id, vector, current.filters(intent))
        if not ids:
            return []
        with Session(engine) as db, db.begin():
            db.execute(text("SET LOCAL statement_timeout='300ms'"))
            db.execute(text("SET LOCAL lock_timeout='100ms'"))
            if scope(db, actor_id, dataset_id) != current:
                return []
            rows = verified_rows(db, current, [UUID(value) for value in ids[:20]])
            matches = []
            for row in rows:
                try:
                    plan, stored = validate_record(row)
                    score = float(checked_vector(vector) @ checked_vector(stored))
                    if plan["intent"] == intent and score >= MIN_SIMILARITY:
                        matches.append((score, str(row["id"]), plan))
                except (ValueError, TypeError, KeyError):
                    continue
        matches.sort(key=lambda match: (-match[0], match[1]))
        return [match[2] for match in matches[:3]]
    except Exception:
        return []
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass
        _read_slots.release()


async def recall(actor_id: str | UUID | None, dataset_id: str | None, question: str, intent: str) -> list[dict]:
    if not enabled() or not actor_id or not dataset_id:
        return []
    try:
        return await asyncio.wait_for(asyncio.to_thread(retrieve_sync, actor_id, dataset_id, question, intent), timeout=2.5)
    except Exception:
        return []
