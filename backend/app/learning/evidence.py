"""Best-effort, authorized hard-failure evidence; never alters an analytical result.

No exception strings, dataset rows, result values, prompts or credentials are
persisted. A failure is not a training label: truth remains NULL.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
import hashlib
import json
from typing import Any, AsyncIterator
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from backend.app.core.config import get_settings
from backend.app.core.database_target import bind_database_schema
from backend.app.core.workspace_authorization import (
    authorize_workspace, authorize_bound_dataset, dataset_workspace_bindings,
)
from backend.app.models import DatasetVersion
from backend.app.learning.tables import feedback_events

OPERATIONS = frozenset({"preview", "description", "sum", "average", "count", "min", "max", "top", "bottom", "trend"})
VALIDATION_ERRORS = frozenset({
    "The metric contains non-finite values.",
    "The date field contains missing or invalid dates. Resolve them before trend analysis.",
    "Exact analytics cannot run on an undeclared sample.",
})
ERROR_TYPES = frozenset({"execution_error", "empty_result", "validator_rejection"})


def enabled() -> bool:
    try:
        return get_settings().learning_enabled
    except Exception:
        return False


def result_failure(result: dict[str, Any]) -> str | None:
    plan = result.get("plan") or {}
    if any(error in VALIDATION_ERRORS for error in plan.get("validation_errors", []) if isinstance(error, str)):
        return "validator_rejection"
    if (result.get("status") == "complete" and plan.get("operation") in OPERATIONS
            and result.get("data") == []):
        return "empty_result"
    return None


def record_failure(*, actor_id: str, dataset_id: str | None, question: str,
                   error_type: str, version_number: int | None = None,
                   predicted: str | None = None, event_id: UUID | None = None,
                   source: str = "chat") -> bool:
    """Independent, bounded transaction; failures never poison the caller's session.

Tenant/workspace come from persisted dataset binding and active memberships,
never from a client-supplied tenant. Only schema names/types are read, then hashed.
    """
    if not enabled() or not dataset_id or error_type not in ERROR_TYPES:
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
            if version_number is not None:
                query = query.where(DatasetVersion.version_number == version_number)
            else:
                query = query.where(DatasetVersion.is_active.is_(True))
            version = db.scalar(query)
            snapshot = version.metadata_snapshot if version else {}
            schema = {key: snapshot[key] for key in ("columns", "dtypes") if key in snapshot}
            schema_hash = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest() if schema else None
            for key, value in (("actor_id", access.actor_id), ("workspace_id", access.workspace_id), ("tenant_id", access.tenant_id)):
                db.execute(text("SELECT set_config(:key, :value, true)"), {"key": f"app.{key}", "value": str(value)})
            values = dict(id=event_id or uuid4(), tenant_id=access.tenant_id,
                workspace_id=access.workspace_id, actor_id=access.actor_id,
                dataset_schema_hash=schema_hash, question=None,
                question_hash=hashlib.sha256(question.encode()).hexdigest(),
                features={"source": source if source in {"chat", "analysis_job"} else "unknown",
                          "error_type": error_type, "schema_available": schema_hash is not None,
                          "dataset_id": dataset_id, "dataset_version": version.version_number if version else None},
                predicted=predicted if predicted in OPERATIONS else None,
                truth=None, signal_type="hard_failure")
            db.execute(insert(feedback_events).values(**values).on_conflict_do_nothing(index_elements=["id"]))
        return True
    except Exception:
        # Do not log exception text: SQL/driver errors may contain private data.
        return False
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass


@dataclass
class Observation:
    result: dict[str, Any] | None = None
    live_intent: str | None = None


@asynccontextmanager
async def observe_chat(*, actor_id: str, dataset_id: str | None, question: str,
                       version_number: int | None) -> AsyncIterator[Observation]:
    observation = Observation()
    if not enabled():
        yield observation
        return
    error_type = None
    try:
        yield observation
    except Exception as exc:
        # Access denial / missing dataset is not a teacher signal.
        if getattr(exc, "status_code", None) not in {401, 403, 404}:
            error_type = "execution_error"
        raise
    finally:
        try:
            result = observation.result or {}
            error_type = error_type or result_failure(result)
            if error_type:
                plan = result.get("plan") or {}
                await asyncio.to_thread(record_failure, actor_id=actor_id, dataset_id=dataset_id,
                    question=question, version_number=plan.get("dataset_version") or version_number,
                    predicted=plan.get("operation"), error_type=error_type)
        except Exception:
            pass

        try:
            from backend.app.learning.shadow import observe_shadow
            plan = (observation.result or {}).get("plan") or {}
            await observe_shadow(actor_id=actor_id, dataset_id=dataset_id, question=question,
                live_intent=observation.live_intent, live_operation=plan.get("operation"),
                version_number=plan.get("dataset_version") or version_number)
        except Exception:
            pass


def record_job_failure(store: Any, job: dict, number: int, *, exception: bool) -> None:
    """Use run/stage/attempt identity to deduplicate worker delivery."""
    if not enabled():
        return
    try:
        from backend.app.services.analysis_run_service import authorize_run
        from backend.app.models.analysis_run import AnalysisStage
        from backend.app.models.learning import LearningRun
        with store.sessions() as db:
            run = authorize_run(db, job["payload"]["run_id"], job["owner_id"], "write")
            stage = db.scalar(select(AnalysisStage).where(AnalysisStage.run_id == run.id, AnalysisStage.number == number))
            learning = db.get(LearningRun, run.id)
            if not exception and (not learning or learning.error_code != "MANDATORY_VALIDATION_FAILED"):
                return
            record_failure(actor_id=str(job["owner_id"]), dataset_id=run.dataset_id,
                question=run.query, version_number=run.version_number,
                error_type="execution_error" if exception else "validator_rejection", source="analysis_job",
                event_id=uuid5(NAMESPACE_URL, f"perceptron:{run.id}:{number}:{stage.attempt if stage else 0}"))
    except Exception:
        pass
