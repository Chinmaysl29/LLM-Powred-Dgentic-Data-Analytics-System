"""Aggregate version 1 feature routes at one gateway boundary."""

from fastapi import APIRouter, Depends
from backend.app.core.security import get_current_user, require_dataset_access
from backend.app.core.workspace_authorization import require_os_workspace, deny_unverified_enterprise

from backend.app.api.v1.routes.auth import router as auth_router
from backend.app.api.v1.routes.datasets import router as datasets_router
from backend.app.api.v1.routes.eda import router as eda_router
from backend.app.api.v1.routes.health import router as health_router
from backend.app.api.v1.routes.intent import router as intent_router
from backend.app.api.v1.routes.orchestrator import router as orchestrator_router
from backend.app.api.v1.routes.planner import router as planner_router
from backend.app.api.v1.routes.retrieval import router as retrieval_router
from backend.app.api.v1.routes.statistics import router as statistics_router
from backend.app.api.v1.routes.validation import router as validation_router
from backend.app.api.v1.routes.executive_summary import router as summary_router
from backend.app.api.v1.routes.schema_reader import router as schema_router
from backend.app.api.v1.routes.sql_guardrails import router as sql_guardrails_router
from backend.app.api.v1.routes.document_loader import router as document_loader_router
from backend.app.api.v1.routes.rag import router as rag_router
from backend.app.api.v1.routes.forecasting import router as forecasting_router
from backend.app.api.v1.routes.operations import router as operations_router
from backend.app.api.v1.routes.enterprise import router as enterprise_router
from backend.app.api.v1.routes.workspaces import router as workspaces_router
from backend.app.api.v1.routes.autonomous import router as autonomous_router
from backend.app.api.v1.routes.audit import router as audit_router
from backend.app.api.v1.routes.chat import router as chat_router
from backend.app.api.v1.routes.monitoring import router as monitoring_router
from backend.app.api.v1.routes.lineage import router as lineage_router
from backend.app.api.v1.routes.enterprise_os import router as enterprise_os_router


router = APIRouter()
from backend.app.api.v1.routes.document_indexing import router as document_indexing_router
router.include_router(document_indexing_router, dependencies=[Depends(require_dataset_access)])
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(datasets_router, dependencies=[Depends(require_dataset_access)])
router.include_router(intent_router, dependencies=[Depends(get_current_user)])
router.include_router(orchestrator_router, dependencies=[Depends(require_dataset_access)])
router.include_router(planner_router, dependencies=[Depends(get_current_user)])
router.include_router(retrieval_router, dependencies=[Depends(require_dataset_access)])
router.include_router(eda_router, dependencies=[Depends(require_dataset_access)])
router.include_router(statistics_router, dependencies=[Depends(require_dataset_access)])
router.include_router(validation_router, dependencies=[Depends(get_current_user)])
router.include_router(summary_router, dependencies=[Depends(require_dataset_access)])
router.include_router(schema_router, dependencies=[Depends(get_current_user)])
router.include_router(sql_guardrails_router, dependencies=[Depends(get_current_user)])
router.include_router(document_loader_router, dependencies=[Depends(get_current_user)])
router.include_router(rag_router, dependencies=[Depends(get_current_user)])
router.include_router(forecasting_router, dependencies=[Depends(require_dataset_access)])
router.include_router(operations_router, dependencies=[Depends(get_current_user)])
router.include_router(enterprise_router, dependencies=[Depends(deny_unverified_enterprise)])
router.include_router(workspaces_router, dependencies=[Depends(get_current_user)])
router.include_router(autonomous_router, dependencies=[Depends(deny_unverified_enterprise)])
router.include_router(audit_router, dependencies=[Depends(get_current_user)])
router.include_router(chat_router, dependencies=[Depends(require_dataset_access)])
router.include_router(monitoring_router, dependencies=[Depends(get_current_user)])
router.include_router(lineage_router, dependencies=[Depends(require_dataset_access)])
router.include_router(enterprise_os_router, dependencies=[Depends(require_os_workspace)])
from backend.app.api.v1.routes.analysis_runs import router as analysis_runs_router
router.include_router(analysis_runs_router, dependencies=[Depends(get_current_user)])
from backend.app.api.v1.routes.connections import router as connections_router
router.include_router(connections_router, dependencies=[Depends(get_current_user)])
from backend.app.api.v1.routes.analysis_history import router as analysis_history_router
router.include_router(analysis_history_router, dependencies=[Depends(get_current_user)])


