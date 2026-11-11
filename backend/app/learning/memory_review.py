"""Explicit human-reviewed corrections; SQL authority and retryable Chroma projection."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from backend.app.learning.evidence import ERROR_TYPES
from backend.app.learning.lifecycle import operator
from backend.app.learning.failure_memory import scope, verified_rows, validate_record
from backend.app.learning.memory_chroma import MemoryIndex
from backend.app.learning.memory_contract import correction, embedding, payload_digest, EMBEDDING_VERSION
from backend.app.learning.memory_table import failure_memory_links as links
from backend.app.learning.tables import feedback_events, mistakes

SessionFactory = Callable[[], Session]


def approve(factory: SessionFactory, reviewer_id: str | UUID, feedback_id: str | UUID,
            dataset_id: str, version_number: int, question: str, corrected_plan: dict) -> dict:
    plan, vector = correction(corrected_plan), embedding(question)
    with factory() as db, db.begin():
        db.execute(text("SET LOCAL lock_timeout='2s'"))
        db.execute(text("SET LOCAL statement_timeout='5s'"))
        feedback = db.execute(select(feedback_events).where(feedback_events.c.id == UUID(str(feedback_id))).with_for_update()).mappings().first()
        if not feedback:
            raise ValueError("Failure evidence unavailable")
        reviewer, _ = operator(db, reviewer_id, feedback["tenant_id"])
        current = scope(db, feedback["actor_id"], dataset_id, version_number)
        features = feedback["features"]
        if (feedback["signal_type"] != "hard_failure" or feedback["truth"] is not None
                or not isinstance(features, dict) or features.get("error_type") not in ERROR_TYPES
                or features.get("dataset_id") != dataset_id or features.get("dataset_version") != version_number
                or feedback["tenant_id"] != current.tenant_id or feedback["workspace_id"] != current.workspace_id
                or feedback["dataset_schema_hash"] != current.schema_hash
                or feedback["question_hash"] != hashlib.sha256(question.encode()).hexdigest()):
            raise ValueError("Failure provenance does not match reviewed correction")
        existing = db.execute(select(links).where(links.c.feedback_id == feedback["id"])).mappings().first()
        if existing:
            rows = verified_rows(db, current, [existing["mistake_id"]])
            if not existing["active"] or not rows or validate_record(rows[0])[0] != plan:
                raise ValueError("Correction already reviewed differently or revoked")
            mistake_id = existing["mistake_id"]
        else:
            mistake_id = uuid4()
            value = dict(id=mistake_id, tenant_id=current.tenant_id, workspace_id=current.workspace_id,
                actor_id=current.actor_id, dataset_schema_hash=current.schema_hash, question=None,
                question_hash=feedback["question_hash"], features={"embedding_version": EMBEDDING_VERSION, "embedding": vector},
                predicted=feedback["predicted"], truth=plan["intent"], signal_type="reviewed_hard_failure",
                error_type=features["error_type"], corrected_plan=plan)
            db.execute(mistakes.insert().values(**value))
            db.execute(links.insert().values(mistake_id=mistake_id, feedback_id=feedback["id"],
                tenant_id=current.tenant_id, workspace_id=current.workspace_id, actor_id=current.actor_id,
                reviewer_id=reviewer, dataset_id=dataset_id, dataset_version=version_number,
                schema_hash=current.schema_hash, payload_digest=payload_digest(value), active=True))
    # A failed projection leaves an approved SQL record that can be safely retried.
    try:
        indexed = reindex(factory, reviewer_id, mistake_id)
    except Exception:
        indexed = False  # SQL approval committed; report projection separately.
    return {"mistake_id": str(mistake_id), "approved": True, "indexed": indexed}


def reindex(factory: SessionFactory, reviewer_id: str | UUID, mistake_id: str | UUID) -> bool:
    with factory() as db, db.begin():
        link = db.execute(select(links).where(links.c.mistake_id == UUID(str(mistake_id)))).mappings().first()
        if not link:
            raise ValueError("Correction unavailable")
        operator(db, reviewer_id, link["tenant_id"])
        current = scope(db, link["actor_id"], link["dataset_id"], link["dataset_version"])
        rows = verified_rows(db, current, [link["mistake_id"]])
        if not rows:
            raise ValueError("Correction inactive or incompatible")
        plan, vector = validate_record(rows[0])
    try:
        with MemoryIndex() as index:
            index.upsert(current.tenant_id, link["mistake_id"], vector, current.filters(plan["intent"]))
        return True
    except Exception:
        return False


def revoke(factory: SessionFactory, reviewer_id: str | UUID, mistake_id: str | UUID) -> dict:
    with factory() as db, db.begin():
        db.execute(text("SET LOCAL lock_timeout='2s'"))
        link = db.execute(select(links).where(links.c.mistake_id == UUID(str(mistake_id))).with_for_update()).mappings().first()
        if not link:
            raise ValueError("Correction unavailable")
        reviewer, tenant = operator(db, reviewer_id, link["tenant_id"])
        if link["active"]:
            db.execute(links.update().where(links.c.mistake_id == link["mistake_id"]).values(
                active=False, revoked_at=datetime.now(timezone.utc), revoked_by=reviewer))
    removed = False
    try:
        with MemoryIndex() as index:
            index.remove(tenant, link["mistake_id"])
        removed = True
    except Exception:
        pass
    return {"mistake_id": str(link["mistake_id"]), "revoked": True, "index_removed": removed}
