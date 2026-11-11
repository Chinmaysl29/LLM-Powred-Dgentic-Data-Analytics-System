"""Observe the live router. Never return a shadow decision to an execution path."""
from __future__ import annotations

import asyncio
import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import create_engine, select, text, func, cast, Text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.core.config import get_settings
from backend.app.core.database_target import bind_database_schema
from backend.app.core.workspace_authorization import (
    authorize_workspace, authorize_bound_dataset, dataset_workspace_bindings,
)
from backend.app.models import DatasetVersion
from backend.app.learning.tables import learner_weights
from backend.app.learning.shadow_table import shadow_predictions
from backend.app.learning.evidence import enabled, OPERATIONS
from backend.app.learning.features import extract, bootstrap_prior, feature_version
from backend.app.learning.perceptron import AveragedPerceptron, LABELS


def _digest(value: object) -> str:
    # Keep schema signatures compatible with Phase 1 hard-failure evidence.
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def record_shadow(*, actor_id: str, dataset_id: str | None, question: str,
                  live_intent: str | None = None, live_operation: str | None = None,
                  version_number: int | None = None, source: str = "chat",
                  event_id: UUID | None = None) -> bool:
    if not enabled() or not dataset_id:
        return False
    engine = None
    try:
        settings = get_settings()
        engine = create_engine(settings.postgres_dsn, poolclass=NullPool, hide_parameters=True,
                               connect_args={"connect_timeout": 2})
        bind_database_schema(engine, settings.database_schema)
        with Session(engine) as db, db.begin():
            db.execute(text("SET LOCAL statement_timeout='300ms'"))
            db.execute(text("SET LOCAL lock_timeout='100ms'"))
            workspace = db.scalar(select(dataset_workspace_bindings.c.workspace_id).where(
                dataset_workspace_bindings.c.dataset_id == dataset_id))
            if workspace is None:
                return False
            access = authorize_workspace(db, actor_id, workspace)
            authorize_bound_dataset(db, access, dataset_id)
            query = select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
            query = query.where(DatasetVersion.version_number == version_number) if version_number is not None else query.where(DatasetVersion.is_active.is_(True))
            version = db.scalar(query)
            if version is None:
                return False
            snapshot = version.metadata_snapshot or {}
            schema = {key: snapshot[key] for key in ("columns", "dtypes") if key in snapshot}
            features = extract(question, schema)
            for key, value in (("actor_id", access.actor_id), ("workspace_id", access.workspace_id), ("tenant_id", access.tenant_id)):
                db.execute(text("SELECT set_config(:key, :value, true)"), {"key": f"app.{key}", "value": str(value)})
            # Pin one tenant-local inactive candidate; no global or active-row writes.
            row = db.execute(select(learner_weights.c.id, learner_weights.c.version,
                func.octet_length(cast(learner_weights.c.weights, Text)).label("size")).where(
                learner_weights.c.tenant_id == access.tenant_id,
                learner_weights.c.learner == "intent_router", learner_weights.c.is_active.is_(False)
            ).order_by(learner_weights.c.version.desc()).limit(1)).mappings().first()
            model = bootstrap_prior()
            model_source, model_version, rejected_version = "bootstrap", None, None
            if row:
                try:
                    if row["size"] > 1_000_000:
                        raise ValueError("Oversized candidate")
                    payload = db.scalar(select(learner_weights.c.weights).where(
                        learner_weights.c.id == row["id"], learner_weights.c.tenant_id == access.tenant_id))
                    model = AveragedPerceptron.from_payload(payload, feature_version())
                    model_source, model_version = "tenant_candidate", row["version"]
                except (ValueError, TypeError, OverflowError):
                    model_source, rejected_version = "invalid_candidate_fallback", row["version"]
            prediction = model.predict(features)
            route = "canonical" if live_intent in LABELS else live_intent if live_intent in {"analytics", "rag_search"} else "unresolved"
            from sqlalchemy.dialects.postgresql import insert
            db.execute(insert(shadow_predictions).values(
                id=event_id or uuid4(), tenant_id=access.tenant_id, workspace_id=access.workspace_id,
                actor_id=access.actor_id, dataset_id=dataset_id, dataset_version=version.version_number,
                dataset_schema_hash=_digest(schema) if schema else None,
                question_hash=hashlib.sha256(question.encode()).hexdigest(), feature_version=feature_version(),
                features=[[int(index), float(features[index])] for index in features.nonzero()[0]],
                source=source if source in {"chat", "intent_api"} else "chat", live_route=route,
                live_intent=live_intent if live_intent in LABELS else None,
                live_operation=live_operation if live_operation in OPERATIONS else None,
                shadow_intent=prediction.intent, candidate_intent=prediction.candidate,
                margin=prediction.margin, abstained=prediction.abstained,
                model_source=model_source, model_version=model_version, rejected_version=rejected_version,
                model_digest=_digest(model.to_payload(feature_version()))
            ).on_conflict_do_nothing(index_elements=["id"]))
        return True
    except Exception:
        return False  # Never log raw questions, driver details, or dataset values.
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass


async def observe_shadow(**kwargs) -> None:
    if not enabled():
        return
    try:
        await asyncio.to_thread(record_shadow, **kwargs)
    except Exception:
        pass
