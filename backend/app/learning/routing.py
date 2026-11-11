"""Tenant-scoped runtime router. Errors and abstention delegate to the original service."""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.core.config import get_settings
from backend.app.core.database_target import bind_database_schema
from backend.app.core.workspace_authorization import authorize_workspace, authorize_bound_dataset, dataset_workspace_bindings
from backend.app.models import DatasetVersion
from backend.app.learning.evidence import enabled
from backend.app.learning.features import extract, feature_version
from backend.app.learning.perceptron import AveragedPerceptron, Prediction
from backend.app.learning.release import active_version, read_version, approved
from backend.app.schemas.intent import IntentClassificationResponse


def read_prediction(actor_id: str | UUID, dataset_id: str | None, question: str,
                    version_number: int | None = None) -> tuple[Prediction, int] | None:
    if not enabled() or not actor_id or not dataset_id:
        return None
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
                return None
            access = authorize_workspace(db, actor_id, workspace)
            authorize_bound_dataset(db, access, dataset_id)
            for key, value in (("actor_id", access.actor_id), ("tenant_id", access.tenant_id)):
                db.execute(text("SELECT set_config(:key,:value,true)"), {"key": f"app.{key}", "value": str(value)})
            query = select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
            query = query.where(DatasetVersion.version_number == version_number) if version_number is not None else query.where(DatasetVersion.is_active.is_(True))
            dataset_version = db.scalar(query)
            if dataset_version is None:
                return None
            version = active_version(db, access.tenant_id)
            if not version:
                return None
            payload = read_version(db, access.tenant_id, version)
            if not approved(db, access.tenant_id, version, payload):
                return None
            snapshot = dataset_version.metadata_snapshot or {}
            schema = {key: snapshot[key] for key in ("columns", "dtypes") if key in snapshot}
            prediction = AveragedPerceptron.from_payload(payload, feature_version()).predict(extract(question, schema), allow_unknown=True)
            return None if prediction.abstained else (prediction, version)
    except Exception:
        return None
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass


class TenantIntentRouter:
    def __init__(self, service: Any, actor_id: str | UUID, version_number: int | None = None) -> None:
        self.service, self.actor_id, self.version_number = service, actor_id, version_number

    @property
    def registry(self):
        return self.service.registry

    async def classify(self, query: str, context: dict | None = None,
                       dataset_id: str | None = None) -> IntentClassificationResponse:
        if enabled():
            try:
                self.service.validate_query(query)
                result = await asyncio.wait_for(asyncio.to_thread(
                    read_prediction, self.actor_id, dataset_id, query, self.version_number), timeout=2.5)
                if result:
                    prediction, version = result
                    definition = self.registry.get(prediction.intent)
                    if definition:
                        return IntentClassificationResponse(intent=definition.name,
                            confidence=0.5,  # Compatibility field; margin is not a calibrated probability.
                            reasoning=f"Approved tenant router version {version}; margin {prediction.margin:.3f} (uncalibrated).",
                            required_agents=definition.required_agents)
            except Exception:
                pass
        return await self.service.classify(query=query, context=context, dataset_id=dataset_id)


def scoped_router(service: Any, actor_id: str | UUID | None, version_number: int | None = None) -> Any:
    if isinstance(service, TenantIntentRouter):
        return service if str(service.actor_id) == str(actor_id) else service.service
    # Offline promotion validates the deterministic fallback only. Existing LLM
    # deployments and custom classifiers keep their original path unchanged.
    from backend.app.services.intent_classification_service import IntentClassificationService
    if (not enabled() or not actor_id or not isinstance(service, IntentClassificationService)
            or service._llm is not None):
        return service
    return TenantIntentRouter(service, actor_id, version_number)
