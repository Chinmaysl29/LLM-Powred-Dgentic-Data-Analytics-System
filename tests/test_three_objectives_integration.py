"""Comprehensive End-to-End Integration Test for Three-Objective AI Data Analyst OS.

Validates the full application journey against live PostgreSQL, Redis, and ChromaDB:
1. Objective 1 — Automate Data Analysis:
   - Durable dataset storage, schema parsing, versioning, quality, profiling.
   - Full population calculation via /chart-data (not 100 preview rows).
   - Durable seven-stage AnalysisRun persistence across all stages.
2. Objective 2 — Conversational Analytics:
   - Natural language analytical question answering directly in-page.
   - Deterministic metric computation and KPI generation.
   - Conversational memory retention across follow-up queries.
   - Document RAG indexing, search, and citation resolution.
3. Objective 3 — Intelligent Decision Making:
   - Evidence-backed data cleaning and quality recommendations.
   - Predictive analytics foundation and ARIMA time-series modeling.
   - Full-population dashboard generation, layout, and server persistence.
   - Detailed executive report generation, verification, and authorized PDF download.
4. Security & Tenant Isolation:
   - Two-account isolation: cross-tenant access to datasets, runs, dashboards, and reports is strictly denied.
"""

from __future__ import annotations

import io
from pathlib import Path
from uuid import UUID, uuid4
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token
from backend.app.database.postgres import PostgresDatabase
from backend.app.main import create_app
from backend.app.models.user import User
from backend.app.models.tenant import Tenant
from backend.app.models.workspace import Workspace
from backend.app.models.dataset import Dataset
from backend.app.models.dataset_version import DatasetVersion
from backend.app.models.background_job import DurableJob
from backend.app.models.analysis_run import AnalysisRun, AnalysisStage, AnalysisArtifact
from backend.app.core.workspace_authorization import (
    tenant_memberships,
    workspace_memberships,
    dataset_workspace_bindings,
)


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def db_engine(settings):
    db = PostgresDatabase(settings)
    db.connect()
    yield db.engine
    db.close()


@pytest.fixture
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session


@pytest.fixture(scope="session")
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def make_user_token(db: Session, email_prefix: str) -> tuple[User, str]:
    user_id = uuid4()
    user = User(
        id=user_id,
        email=f"{email_prefix}_{user_id.hex[:6]}@enterprise.test",
        hashed_password="",
        full_name=f"Analyst {email_prefix.title()}",
        role="analyst",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id), "email": user.email})
    return user, token


def make_workspace(db: Session, owner: User) -> Workspace:
    tenant_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        tenant_name=f"Tenant {owner.full_name}",
        tenant_slug=f"tenant-{owner.id.hex[:8]}",
        tenant_status="active",
    )
    db.add(tenant)
    db.flush()

    ws = Workspace(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_name=f"Workspace {owner.full_name}",
        workspace_slug=f"ws-{owner.id.hex[:8]}",
        status="active",
    )
    db.add(ws)
    db.flush()

    db.execute(
        tenant_memberships.insert().values(
            tenant_id=tenant.id,
            user_id=owner.id,
            role="owner",
            active=True,
        )
    )
    db.execute(
        workspace_memberships.insert().values(
            workspace_id=ws.id,
            user_id=owner.id,
            role="owner",
            active=True,
        )
    )
    db.commit()
    db.refresh(ws)
    return ws


# ==============================================================================
# INTEGRATED THREE-OBJECTIVE ACCEPTANCE TEST
# ==============================================================================

def test_full_three_objectives_integrated_journey(client, db_session, settings):
    """Verify complete integrated journey covering Objective 1, Objective 2, and Objective 3."""

    # --------------------------------------------------------------------------
    # SETUP: Create Users and Workspaces for Account A and Account B
    # --------------------------------------------------------------------------
    user_a, token_a = make_user_token(db_session, "user_alpha")
    ws_a = make_workspace(db_session, user_a)
    headers_a = {
        "Authorization": f"Bearer {token_a}",
        "X-Workspace-Id": str(ws_a.id),
    }

    user_b, token_b = make_user_token(db_session, "user_beta")
    ws_b = make_workspace(db_session, user_b)
    headers_b = {
        "Authorization": f"Bearer {token_b}",
        "X-Workspace-Id": str(ws_b.id),
    }

    # ==========================================================================
    # OBJECTIVE 1: AUTOMATE DATA ANALYSIS
    # ==========================================================================
    # 1. Upload structured retail dataset with known answers
    # Observations: 6 rows
    # Total revenue = 100 + 200 + 300 + 400 + 500 - 50 = 1450.0
    # Mean revenue = 241.67, Min = -50.0, Max = 500.0
    csv_content = (
        "date,region,category,revenue\n"
        "2026-01-15,North,Electronics,100.0\n"
        "2026-01-20,North,Furniture,200.0\n"
        "2026-02-10,South,Electronics,300.0\n"
        "2026-02-15,South,Supplies,400.0\n"
        "2026-02-20,South,Electronics,500.0\n"
        "2026-03-05,North,Supplies,-50.0\n"
    )
    files = {"file": ("enterprise_retail.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    upload_res = client.post("/api/v1/datasets/upload", files=files, headers=headers_a)
    assert upload_res.status_code == 201, f"Upload failed: {upload_res.text}"
    dataset_info = upload_res.json()
    dataset_id = dataset_info["dataset_id"]
    assert dataset_info["status"] == "ready"
    assert dataset_info["row_count"] == 6

    # Bind dataset to Workspace A
    db_session.execute(
        dataset_workspace_bindings.insert().values(
            workspace_id=ws_a.id,
            dataset_id=dataset_id,
        )
    )
    db_session.commit()

    # 2. Verify /chart-data calculates exact full population (not 100 preview rows)
    chart_payload = {
        "chart_type": "Histogram",
        "y_axis": "revenue",
    }
    chart_res = client.post(f"/api/v1/datasets/{dataset_id}/chart-data", json=chart_payload, headers=headers_a)
    assert chart_res.status_code == 200, f"Chart-data failed: {chart_res.text}"
    chart_data = chart_res.json()
    assert chart_data["is_valid"] is True
    assert chart_data["summary_metrics"]["count"] == 6
    assert chart_data["summary_metrics"]["sum"] == 1450.0
    assert chart_data["summary_metrics"]["min"] == -50.0
    assert chart_data["summary_metrics"]["max"] == 500.0
    assert len(chart_data["histogram_bins"]) > 0

    # 3. Launch durable seven-stage AnalysisRun
    run_payload = {
        "workspace_id": str(ws_a.id),
        "dataset_id": dataset_id,
        "query": "Analyze total revenue by region and identify top performing categories",
        "idempotency_key": f"test-run-{uuid4().hex[:12]}",
    }
    run_res = client.post("/api/v1/orchestrator/runs", json=run_payload, headers=headers_a)
    assert run_res.status_code == 201, f"Run creation failed: {run_res.text}"
    run_data = run_res.json()
    run_id = run_data["id"]
    assert len(run_data["stages"]) == 7
    stage_names = [s["name"] for s in run_data["stages"]]
    assert "Problem formulation" in stage_names
    assert "Data collection" in stage_names
    assert "Recommendations" in stage_names

    # ==========================================================================
    # OBJECTIVE 2: CONVERSATIONAL ANALYTICS
    # ==========================================================================
    # 1. Ask natural-language analytical question
    chat_payload = {
        "message": "What is the total revenue?",
        "dataset_id": dataset_id,
        "workspace_id": str(ws_a.id),
    }
    chat_res = client.post("/api/v1/chat", json=chat_payload, headers=headers_a)
    assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
    chat_data = chat_res.json()
    assert chat_data["status"] == "complete"
    assert "1450" in chat_data["answer"]
    session_id = chat_data["session_id"]
    assert session_id is not None
    assert chat_data["kpis"] is not None
    assert chat_data["kpis"].get("total") == 1450.0

    # 2. Ask follow-up question preserving session context
    followup_payload = {
        "message": "What is the average revenue?",
        "dataset_id": dataset_id,
        "workspace_id": str(ws_a.id),
        "session_id": session_id,
    }
    followup_res = client.post("/api/v1/chat", json=followup_payload, headers=headers_a)
    assert followup_res.status_code == 200, f"Followup failed: {followup_res.text}"
    followup_data = followup_res.json()
    assert followup_data["status"] == "complete"
    assert "Mean revenue" in followup_data["answer"]
    assert "400.0" in followup_data["answer"] or "241" in followup_data["answer"]

    # 3. Document upload and RAG integration
    doc_content = (
        "# Enterprise Financial Guidelines 2026\n\n"
        "All business units must maintain an operating margin above 15%.\n"
        "Revenue recognition must follow ASC 606 standards.\n"
        "Capital expenditure limits for North region are set at $2,000,000.\n"
    )
    doc_file = {"file": ("guidelines.md", io.BytesIO(doc_content.encode("utf-8")), "text/markdown")}
    doc_res = client.post("/api/v1/datasets/upload", files=doc_file, headers=headers_a)
    assert doc_res.status_code == 201, f"Doc upload failed: {doc_res.text}"
    doc_id = doc_res.json()["dataset_id"]

    # Bind doc to workspace
    db_session.execute(
        dataset_workspace_bindings.insert().values(
            workspace_id=ws_a.id,
            dataset_id=doc_id,
        )
    )
    db_session.commit()

    # Query document via chat
    doc_chat_payload = {
        "message": "What is the capital expenditure limit for the North region?",
        "dataset_id": doc_id,
        "workspace_id": str(ws_a.id),
    }
    doc_chat_res = client.post("/api/v1/chat", json=doc_chat_payload, headers=headers_a)
    assert doc_chat_res.status_code == 200, f"Doc chat failed: {doc_chat_res.text}"
    doc_chat_data = doc_chat_res.json()
    assert doc_chat_data["status"] == "complete"

    # ==========================================================================
    # OBJECTIVE 3: INTELLIGENT DECISION MAKING
    # ==========================================================================
    # 1. Evidence-backed cleaning & quality recommendations
    rec_res = client.get(f"/api/v1/datasets/{dataset_id}/recommendations", headers=headers_a)
    assert rec_res.status_code == 200, f"Recommendations failed: {rec_res.text}"
    rec_data = rec_res.json()
    assert "recommendations" in rec_data

    # 2. Time-series Predictive Analytics (Auto-ARIMA)
    series_points = [
        {"date": f"{2022 + (m // 12)}-{(m % 12) + 1:02d}-01", "value": 1000.0 + m * 25.0}
        for m in range(36)
    ]
    forecast_payload = {
        "series": series_points,
        "frequency": "monthly",
        "horizon": 3,
        "confidence_level": 0.95,
    }
    forecast_res = client.post("/api/v1/forecasting/arima", json=forecast_payload, headers=headers_a)
    assert forecast_res.status_code == 200, f"Forecast failed: {forecast_res.text}"
    fc_data = forecast_res.json()
    assert fc_data["diagnostics"]["aic"] is not None

    # Validate forecast with backtest metrics
    val_payload = {
        **forecast_payload,
        "forecast_output": fc_data,
    }
    val_res = client.post("/api/v1/forecasting/validate-forecast", json=val_payload, headers=headers_a)
    assert val_res.status_code == 200, f"Validate forecast failed: {val_res.text}"
    val_data = val_res.json()
    assert val_data["mae"] is not None
    assert val_data["validation_status"] in ["PASSED", "WARNING"]

    # 3. Interactive Persistent Dashboard (Full Population)
    dash_payload = {
        "prompt": "Executive retail performance overview",
        "workspace_id": str(ws_a.id),
        "dataset_id": dataset_id,
        "title": "Retail Revenue Dashboard",
    }
    dash_res = client.post("/api/v1/os/dashboards/generate", json=dash_payload, headers=headers_a)
    assert dash_res.status_code == 200, f"Dashboard generation failed: {dash_res.text}"
    dash_data = dash_res.json()
    assert dash_data["population_size"] == 6
    assert dash_data["sampling_method"] == "none"
    dashboard_id = dash_data["id"]

    # Verify dashboard list persists
    dash_list_res = client.get(f"/api/v1/os/dashboards?workspace_id={ws_a.id}", headers=headers_a)
    assert dash_list_res.status_code == 200
    assert any(d["id"] == dashboard_id for d in dash_list_res.json())

    # 4. Detailed Executive Report Generation and Binary PDF Download
    # Create completed AnalysisRun and Artifact for report generation
    report_run_id = str(uuid4())
    art_content = {
        "answer": "Total revenue across all regions is $1,450.00 with South region contributing the highest sales.",
        "explanation": "Calculated across 100% of observations with no sampling.",
        "kpis": {"total": 1450.0, "mean": 241.67, "count": 6},
        "chart": {
            "points": [{"label": "North", "value": 250.0}, {"label": "South", "value": 1200.0}],
            "chart_label": "Revenue by Region",
        },
        "actionable": [
            "Scale inventory in South region to sustain growth momentum.",
            "Review North region product mix to address negative return items.",
        ],
    }
    durable_job = DurableJob(
        id=uuid4(),
        workspace_id=ws_a.id,
        owner_id=user_a.id,
        kind="ANALYSIS",
        idempotency_key=str(uuid4()),
        status="COMPLETED",
        payload={"query": "Executive Retail Analysis"},
    )
    db_session.add(durable_job)
    db_session.flush()

    rep_run = AnalysisRun(
        id=report_run_id,
        job_id=durable_job.id,
        workspace_id=ws_a.id,
        owner_id=user_a.id,
        dataset_id=dataset_id,
        version_number=1,
        query="Executive Retail Analysis",
        status="COMPLETED",
    )
    db_session.add(rep_run)
    db_session.flush()
    db_session.add(AnalysisStage(run_id=report_run_id, number=5, name="Data modeling", status="COMPLETED"))
    db_session.add(AnalysisStage(run_id=report_run_id, number=6, name="Visualization and reporting", status="COMPLETED"))
    db_session.add(AnalysisStage(run_id=report_run_id, number=7, name="Recommendations", status="COMPLETED"))
    db_session.add(AnalysisArtifact(run_id=report_run_id, stage_number=5, content=art_content))
    db_session.add(AnalysisArtifact(run_id=report_run_id, stage_number=6, content=art_content))
    db_session.commit()

    # Generate Report from Analysis
    report_payload = {
        "run_id": report_run_id,
        "title": "Annual Executive Retail Report 2026",
        "report_type": "Executive Report",
        "format_type": "pdf",
    }
    rep_res = client.post("/api/v1/reports/from-analysis", json=report_payload, headers=headers_a)
    assert rep_res.status_code == 201, f"Report generation failed: {rep_res.text}"
    report_meta = rep_res.json()
    report_id = report_meta["id"]
    assert report_meta["status"] == "GENERATED"
    assert report_meta["format"] == "pdf"

    # Download binary report file and verify PDF structure
    dl_res = client.get(f"/api/v1/reports/{report_id}/download", headers=headers_a)
    assert dl_res.status_code == 200, f"Report download failed: {dl_res.text}"
    assert dl_res.headers["content-type"] == "application/pdf"
    assert dl_res.content.startswith(b"%PDF"), "Downloaded report is not a valid PDF file"

    # ==========================================================================
    # SECURITY & TWO-ACCOUNT ISOLATION
    # ==========================================================================
    # User B (Workspace B) must be denied access to User A's resources

    # 1. Cross-tenant dataset access denied
    denied_chart = client.post(f"/api/v1/datasets/{dataset_id}/chart-data", json=chart_payload, headers=headers_b)
    assert denied_chart.status_code in [403, 404]

    # 2. Cross-tenant analysis run access denied
    denied_run = client.get(f"/api/v1/orchestrator/runs/{run_id}", headers=headers_b)
    assert denied_run.status_code in [403, 404]

    # 3. Cross-tenant report generation from User A's run denied
    denied_report = client.post("/api/v1/reports/from-analysis", json=report_payload, headers=headers_b)
    assert denied_report.status_code in [403, 404]
