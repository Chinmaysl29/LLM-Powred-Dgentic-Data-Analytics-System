"""Enterprise AI Analytics Operating System API Routes for Phase 20.

Exposes REST gateways for:
- 20.1 Workspace Management
- 20.2 AI Memory Layer
- 20.3 Natural Language Dashboard Builder
- 20.4 Executive Report Studio
- 20.5 Data Storytelling Engine
- 20.6 Dashboard Templates Marketplace
- 20.7 Dataset Relationship Engine
- 20.8 Semantic Business Layer
- 20.9 KPI Knowledge Engine
- 20.10 Autonomous AI Analyst Mode
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, HTTPException, Query, Request
from pathlib import Path
from backend.app.core.workspace_authorization import identifier
from pydantic import BaseModel, Field
import pandas as pd

from backend.app.services.autonomous_ai_analyst import get_autonomous_ai_analyst
from backend.app.services.dashboard_builder_service import get_dashboard_builder_service
from backend.app.services.dashboard_marketplace_service import get_dashboard_marketplace_service
from backend.app.services.dataset_relationship_service import get_dataset_relationship_engine
from backend.app.services.data_storytelling_service import get_data_storytelling_engine
from backend.app.services.kpi_knowledge_engine import get_kpi_knowledge_engine
from backend.app.services.report_studio_service import get_report_studio_service
from backend.app.services.semantic_layer_service import get_semantic_business_layer
from backend.app.services.workspace_orchestration_service import get_workspace_orchestration_service
from backend.memory.ai_memory_layer import get_ai_memory_layer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/os", tags=["Enterprise AI Analytics OS (Phase 20)"])


def scoped_storage(request: Request, kind: str) -> Path:
    """Only the verified DB workspace selects storage; legacy roots stay quarantined."""
    access = request.state.workspace_access
    return Path('storage/authorized_workspaces') / str(access.workspace_id) / kind


# -----------------------------------------------------------------------------
# Pydantic Request Models
# -----------------------------------------------------------------------------

class WorkspaceCreateRequest(BaseModel):
    name: str
    description: str = ""
    owner_id: str = "admin-user"
    owner_email: str = "admin@enterprise.ai"
    tenant_id: str = "default-tenant"


class AddMemberRequest(BaseModel):
    user_id: str
    email: str
    role: str = "Analyst"


class ContextResolveRequest(BaseModel):
    query: str
    workspace_id: str = "default-ws"
    session_id: str = "default-session"


class DashboardGenerateRequest(BaseModel):
    prompt: str
    workspace_id: str = "default-ws"
    title: str | None = None
    data_records: list[dict[str, Any]] = Field(default_factory=list)


class ReportGenerateRequest(BaseModel):
    title: str
    report_type: str = "Executive Report"
    workspace_id: str = "default-ws"
    data_records: list[dict[str, Any]] = Field(default_factory=list)
    executive_summary: str | None = None


class StorytellingRequest(BaseModel):
    query: str
    data_records: list[dict[str, Any]] = Field(default_factory=list)


class ApplyTemplateRequest(BaseModel):
    workspace_id: str = "default-ws"
    data_records: list[dict[str, Any]] = Field(default_factory=list)


class RelationshipDiscoveryRequest(BaseModel):
    datasets: dict[str, list[dict[str, Any]]]


class SemanticResolveRequest(BaseModel):
    query: str
    columns: list[str]


class AnalystExecuteRequest(BaseModel):
    query: str
    workspace_id: str = "default-ws"
    session_id: str = "default-session"
    data_records: list[dict[str, Any]] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# 20.1 Workspace Management
# -----------------------------------------------------------------------------

@router.post("/workspaces")
def create_workspace(req: WorkspaceCreateRequest) -> dict[str, Any]:
    svc = get_workspace_orchestration_service()
    return svc.create_workspace(
        name=req.name,
        description=req.description,
        owner_id=req.owner_id,
        owner_email=req.owner_email,
        tenant_id=req.tenant_id,
    )


@router.get("/workspaces")
def list_workspaces(tenant_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    svc = get_workspace_orchestration_service()
    return svc.list_workspaces(tenant_id=tenant_id, status=status)


@router.get("/workspaces/{workspace_id}")
def get_workspace(workspace_id: str) -> dict[str, Any]:
    svc = get_workspace_orchestration_service()
    try:
        return svc.get_workspace(workspace_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")


@router.post("/workspaces/{workspace_id}/archive")
def archive_workspace(workspace_id: str) -> dict[str, Any]:
    svc = get_workspace_orchestration_service()
    try:
        return svc.archive_workspace(workspace_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str) -> dict[str, Any]:
    svc = get_workspace_orchestration_service()
    success = svc.delete_workspace(workspace_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")
    return {"status": "deleted", "workspace_id": workspace_id}


@router.post("/workspaces/{workspace_id}/members")
def add_workspace_member(workspace_id: str, req: AddMemberRequest) -> dict[str, Any]:
    svc = get_workspace_orchestration_service()
    try:
        return svc.add_member(workspace_id, user_id=req.user_id, email=req.email, role=req.role)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")


@router.get("/workspaces/{workspace_id}/resources")
def get_workspace_resources(workspace_id: str) -> dict[str, Any]:
    svc = get_workspace_orchestration_service()
    try:
        return svc.get_workspace_resources(workspace_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Workspace {workspace_id} not found")


# -----------------------------------------------------------------------------
# 20.2 AI Memory Layer
# -----------------------------------------------------------------------------

@router.post("/memory/resolve")
def resolve_contextual_query(req: ContextResolveRequest, request: Request) -> dict[str, Any]:
    from backend.memory.ai_memory_layer import AIMemoryLayer
    session_id = str(identifier(req.session_id))
    mem = AIMemoryLayer(storage_dir=scoped_storage(request, 'memory'))
    return mem.resolve_contextual_query(req.query, str(request.state.workspace_access.workspace_id), session_id)


@router.get("/memory/{workspace_id}/{session_id}")
def get_session_memory(workspace_id: str, session_id: str, request: Request) -> dict[str, Any]:
    from backend.memory.ai_memory_layer import AIMemoryLayer
    session_id = str(identifier(session_id))
    mem = AIMemoryLayer(storage_dir=scoped_storage(request, 'memory'))
    return mem._ensure_session(str(request.state.workspace_access.workspace_id), session_id)


# -----------------------------------------------------------------------------
# 20.3 Dashboard Builder
# -----------------------------------------------------------------------------

@router.post("/dashboards/generate")
def generate_dashboard(req: DashboardGenerateRequest, request: Request) -> dict[str, Any]:
    from backend.app.services.dashboard_builder_service import DashboardBuilderService
    if not req.data_records:
        raise HTTPException(422, 'Source records are required')
    svc = DashboardBuilderService(storage_dir=scoped_storage(request, 'dashboards'))
    df = pd.DataFrame(req.data_records) if req.data_records else pd.DataFrame({
        "order_date": pd.date_range("2025-01-01", periods=12, freq="ME").strftime("%Y-%m-%d"),

        "sales": [12000, 15000, 14000, 18000, 22000, 21000, 25000, 28000, 27000, 31000, 34000, 39000],
        "category": ["Computers", "Mobile", "Computers", "Audio", "Mobile", "Computers", "Audio", "Mobile", "Computers", "Audio", "Mobile", "Computers"],
    })
    return svc.create_dashboard_from_prompt(
        prompt=req.prompt,
        df=df,
        workspace_id=req.workspace_id,
        title=req.title,
    )


# -----------------------------------------------------------------------------
# 20.4 Executive Report Studio
# -----------------------------------------------------------------------------

@router.post("/reports/studio/generate")
def generate_executive_report(req: ReportGenerateRequest, request: Request) -> dict[str, Any]:
    from backend.app.services.report_studio_service import ReportStudioService
    if not req.data_records:
        raise HTTPException(422, 'Source records are required')
    svc = ReportStudioService(storage_dir=scoped_storage(request, 'reports'))
    df = pd.DataFrame(req.data_records) if req.data_records else pd.DataFrame({
        "revenue": [50000, 62000, 78000, 85000],
        "segment": ["Enterprise", "Mid-Market", "SMB", "Government"],
    })
    return svc.generate_report(
        title=req.title,
        report_type=req.report_type,
        df=df,
        workspace_id=req.workspace_id,
        executive_summary=req.executive_summary,
    )


@router.get("/reports/studio/history")
def list_report_history(request: Request, workspace_id: str | None = None) -> list[dict[str, Any]]:
    from backend.app.services.report_studio_service import ReportStudioService
    svc = ReportStudioService(storage_dir=scoped_storage(request, 'reports'))
    return svc.list_reports(workspace_id=str(request.state.workspace_access.workspace_id))


# -----------------------------------------------------------------------------
# 20.5 Data Storytelling Engine
# -----------------------------------------------------------------------------

@router.post("/storytelling/generate")
def generate_story(req: StorytellingRequest) -> dict[str, Any]:
    svc = get_data_storytelling_engine()
    df = pd.DataFrame(req.data_records) if req.data_records else pd.DataFrame({
        "revenue": [120000, 85000, 42000],
        "segment": ["Enterprise", "Mid-Market", "SMB"],
    })
    return svc.generate_story(query=req.query, df=df)


# -----------------------------------------------------------------------------
# 20.6 Dashboard Marketplace
# -----------------------------------------------------------------------------

@router.get("/marketplace/templates")
def list_marketplace_templates() -> list[dict[str, Any]]:
    svc = get_dashboard_marketplace_service()
    return svc.get_templates()


@router.post("/marketplace/templates/{template_id}/apply")
def apply_marketplace_template(template_id: str, req: ApplyTemplateRequest) -> dict[str, Any]:
    svc = get_dashboard_marketplace_service()
    df = pd.DataFrame(req.data_records) if req.data_records else pd.DataFrame({
        "order_date": ["2025-01-01", "2025-02-01", "2025-03-01"],
        "sales": [45000, 52000, 61000],
        "product": ["SaaS Cloud", "AI Copilot", "Database"],
        "rep": ["Alice", "Bob", "Charlie"],
    })
    try:
        return svc.apply_template_to_dataset(template_id, df, workspace_id=req.workspace_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Template {template_id} not found")


# -----------------------------------------------------------------------------
# 20.7 Dataset Relationship Engine
# -----------------------------------------------------------------------------

@router.post("/relationships/discover")
def discover_relationships(req: RelationshipDiscoveryRequest) -> dict[str, Any]:
    svc = get_dataset_relationship_engine()
    dfs = {name: pd.DataFrame(rows) for name, rows in req.datasets.items()}
    return svc.generate_schema_graph(dfs)


# -----------------------------------------------------------------------------
# 20.8 Semantic Business Layer
# -----------------------------------------------------------------------------

@router.get("/semantic/glossary")
def get_semantic_glossary() -> dict[str, Any]:
    svc = get_semantic_business_layer()
    return svc.glossary


@router.post("/semantic/resolve")
def resolve_query_columns(req: SemanticResolveRequest) -> dict[str, Any]:
    svc = get_semantic_business_layer()
    return svc.translate_query_terms_to_columns(req.query, req.columns)


# -----------------------------------------------------------------------------
# 20.9 KPI Knowledge Engine
# -----------------------------------------------------------------------------

@router.get("/kpis/catalog")
def get_kpi_catalog() -> list[dict[str, Any]]:
    svc = get_kpi_knowledge_engine()
    return svc.get_kpi_catalog()


# -----------------------------------------------------------------------------
# 20.10 Autonomous AI Analyst Mode
# -----------------------------------------------------------------------------

@router.post("/analyst/execute")
def execute_autonomous_analyst(req: AnalystExecuteRequest) -> dict[str, Any]:
    svc = get_autonomous_ai_analyst()
    df = pd.DataFrame(req.data_records) if req.data_records else pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=15, freq="ME").strftime("%Y-%m-%d"),

        "revenue": [12000, 14000, 16000, 15500, 18000, 21000, 24000, 23000, 27000, 31000, 30500, 35000, 38000, 42000, 45000],
        "cogs": [4800, 5600, 6400, 6200, 7200, 8400, 9600, 9200, 10800, 12400, 12200, 14000, 15200, 16800, 18000],
        "category": ["Enterprise", "Enterprise", "Mid-Market", "SMB", "Enterprise", "Enterprise", "Mid-Market", "SMB", "Enterprise", "Enterprise", "Mid-Market", "SMB", "Enterprise", "Enterprise", "Mid-Market"],
        "customer_id": [f"CUST-{i:03d}" for i in range(1, 16)],
    })
    return svc.execute(
        query=req.query,
        df=df,
        workspace_id=req.workspace_id,
        session_id=req.session_id,
    )


# -----------------------------------------------------------------------------
# Phase 21: Enterprise Launch Readiness & Portfolio Mode
# -----------------------------------------------------------------------------

@router.post("/portfolio/init")
def initialize_portfolio() -> dict[str, Any]:
    from backend.app.services.portfolio_mode_service import get_portfolio_mode_service
    svc = get_portfolio_mode_service()
    return svc.initialize_portfolio_mode()


@router.get("/demo/datasets")
def list_demo_datasets() -> dict[str, Any]:
    from backend.app.services.demo_dataset_service import get_demo_dataset_service
    svc = get_demo_dataset_service()
    manifest = svc.provision_all_demo_datasets()
    return {"status": "available", "datasets": manifest}


@router.get("/telemetry/summary")
def get_telemetry_summary() -> dict[str, Any]:
    from backend.app.services.usage_analytics_service import get_usage_analytics_service
    svc = get_usage_analytics_service()
    return svc.get_summary()


@router.post("/telemetry/event")
def record_telemetry_event(event_type: str = "query", intent: str = "sql", latency_ms: float = 120.0) -> dict[str, Any]:
    from backend.app.services.usage_analytics_service import get_usage_analytics_service
    svc = get_usage_analytics_service()
    if event_type == "query":
        svc.record_query(intent=intent, latency_ms=latency_ms)
    elif event_type == "upload":
        svc.record_dataset_upload()
    elif event_type == "dashboard":
        svc.record_dashboard_creation()
    elif event_type == "report":
        svc.record_report_generation()
    return {"status": "recorded", "event_type": event_type}

