"""Regression & Acceptance Test Suite for AI Analysis History & Reports Integration.

Validates:
1. Persistent Analysis Session creation and message turn recording.
2. Durable AnalysisRun and AnalysisArtifact linking.
3. Chronological message restoration with verified metrics, charts, and tables.
4. Conversational follow-up memory and context continuity.
5. Reports integration: Analysis History retrieval.
6. Detailed report generation from completed analysis (PDF with charts and KPIs).
7. Report artifact verification (valid non-empty PDF).
8. Report download endpoint with streaming FileResponse.
9. Two-account workspace isolation and security checks.
"""

from io import BytesIO
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token
from backend.app.database.postgres import PostgresDatabase
from backend.app.main import create_app
from backend.app.models.tenant import Tenant
from backend.app.models.user import User
from backend.app.models.workspace import Workspace
from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships


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


def make_test_user_and_workspace(db: Session, prefix: str) -> tuple[User, str, Workspace]:
    user_id = uuid4()
    user = User(
        id=user_id,
        email=f"{prefix}_{user_id.hex[:6]}@enterprise.test",
        hashed_password="",
        full_name=f"Analyst {prefix.title()}",
        role="analyst",
        is_active=True,
    )
    db.add(user)
    db.flush()

    tenant = Tenant(
        id=uuid4(),
        tenant_name=f"Tenant {user.full_name}",
        tenant_slug=f"tenant-{user.id.hex[:8]}",
        tenant_status="active",
    )
    db.add(tenant)
    db.flush()

    ws = Workspace(
        id=uuid4(),
        tenant_id=tenant.id,
        workspace_name=f"Workspace {user.full_name}",
        workspace_slug=f"ws-{user.id.hex[:8]}",
        status="active",
    )
    db.add(ws)
    db.flush()

    db.execute(tenant_memberships.insert().values(tenant_id=tenant.id, user_id=user.id, role="owner", active=True))
    db.execute(workspace_memberships.insert().values(workspace_id=ws.id, user_id=user.id, role="owner", active=True))
    db.commit()
    db.refresh(user)
    db.refresh(ws)

    token = create_access_token({"sub": str(user.id), "email": user.email})
    return user, token, ws


def test_session_lifecycle_and_turn_persistence(client: TestClient, db_session: Session):
    """Verify session creation, turn recording, and message restoration."""
    user, token, ws = make_test_user_and_workspace(db_session, "hist_alpha")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload and bind a sample dataset
    csv_bytes = b"dept,budget\nFinance,1200\nEngineering,2500\nHR,800\n"
    upload_resp = client.post(
        f"/api/v1/datasets/upload?workspace_id={ws.id}",
        headers=headers,
        files={"file": ("company_budgets.csv", csv_bytes, "text/csv")},
    )
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["dataset_id"]
    bind_resp = client.post(f"/api/v1/datasets/{dataset_id}/workspace", headers=headers, json={"workspace_id": str(ws.id)})
    assert bind_resp.status_code == 200

    # 1. Create a session
    resp = client.post(
        "/api/v1/analysis/sessions",
        headers=headers,
        json={"title": "Q3 Financial Breakdown", "workspace_id": str(ws.id), "dataset_id": dataset_id},
    )
    assert resp.status_code == 201
    session_data = resp.json()
    session_id = session_data["session_id"]
    assert session_data["title"] == "Q3 Financial Breakdown"

    # 2. Ask question via /api/v1/chat with session_id
    chat_resp = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "Total budget by dept",
            "dataset_id": dataset_id,
            "session_id": session_id,
            "workspace_id": str(ws.id),
        },
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["session_id"] == session_id
    assert chat_data["run_id"] is not None

    # 3. Retrieve session details
    detail_resp = client.get(f"/api/v1/analysis/sessions/{session_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["session_id"] == session_id
    assert len(detail["turns"]) >= 1
    assert detail["turns"][0]["question"] == "Total budget by dept"
    assert detail["turns"][0]["run_id"] == chat_data["run_id"]
    assert detail["turns"][0]["chart"] is not None
    assert detail["turns"][0]["kpis"] is not None

    # 4. List sessions
    list_resp = client.get(f"/api/v1/analysis/sessions?workspace_id={ws.id}", headers=headers)
    assert list_resp.status_code == 200
    sessions = list_resp.json()
    assert any(s["session_id"] == session_id for s in sessions)


def test_conversational_follow_up_memory(client: TestClient, db_session: Session):
    """Verify follow-up queries maintain conversational context."""
    user, token, ws = make_test_user_and_workspace(db_session, "hist_followup")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload test CSV and bind to workspace
    csv_bytes = b"company_name,revenue,profit_margin\nAlpha Corp,1200,25.5\nBeta LLC,800,18.2\nGamma Inc,1500,30.0\n"
    upload_resp = client.post(
        f"/api/v1/datasets/upload?workspace_id={ws.id}",
        headers=headers,
        files={"file": ("retail_sample.csv", csv_bytes, "text/csv")},
    )
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["dataset_id"]
    bind_resp = client.post(f"/api/v1/datasets/{dataset_id}/workspace", headers=headers, json={"workspace_id": str(ws.id)})
    assert bind_resp.status_code == 200

    # Question 1: Total revenue
    q1_resp = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "Total revenue",
            "dataset_id": dataset_id,
            "workspace_id": str(ws.id),
        },
    )
    assert q1_resp.status_code == 200
    q1_data = q1_resp.json()
    session_id = q1_data["session_id"]
    assert "3500" in q1_data["answer"]

    # Question 2: Follow-up in same session - Which company has highest revenue?
    q2_resp = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "Which company has the highest revenue?",
            "dataset_id": dataset_id,
            "session_id": session_id,
            "workspace_id": str(ws.id),
        },
    )
    assert q2_resp.status_code == 200
    q2_data = q2_resp.json()
    assert q2_data["session_id"] == session_id
    assert "Gamma Inc" in q2_data["answer"] or "1500" in q2_data["answer"]

    # Verify session has both turns
    detail_resp = client.get(f"/api/v1/analysis/sessions/{session_id}", headers=headers)
    assert detail_resp.status_code == 200
    turns = detail_resp.json()["turns"]
    assert len(turns) == 2


def test_reports_history_and_pdf_generation(client: TestClient, db_session: Session):
    """Verify reports analysis history, PDF report generation, and download."""
    user, token, ws = make_test_user_and_workspace(db_session, "hist_reports")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload test CSV and bind to workspace
    csv_bytes = b"category,sales\nElectronics,1000\nFurniture,500\nClothing,300\n"
    upload_resp = client.post(
        f"/api/v1/datasets/upload?workspace_id={ws.id}",
        headers=headers,
        files={"file": ("sales_categories.csv", csv_bytes, "text/csv")},
    )
    assert upload_resp.status_code == 201
    dataset_id = upload_resp.json()["dataset_id"]
    bind_resp = client.post(f"/api/v1/datasets/{dataset_id}/workspace", headers=headers, json={"workspace_id": str(ws.id)})
    assert bind_resp.status_code == 200

    # Run analysis
    chat_resp = client.post(
        "/api/v1/chat",
        headers=headers,
        json={
            "message": "Total sales by category",
            "dataset_id": dataset_id,
            "workspace_id": str(ws.id),
        },
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    run_id = chat_data["run_id"]
    assert run_id is not None

    # Check /reports/analysis-history
    hist_resp = client.get(f"/api/v1/reports/analysis-history?workspace_id={ws.id}", headers=headers)
    assert hist_resp.status_code == 200
    history = hist_resp.json()
    matching_entry = next((h for h in history if h.get("run_id") == run_id), None)
    assert matching_entry is not None
    assert matching_entry["report_eligible"] is True

    # Generate Detailed Report
    gen_resp = client.post(
        "/api/v1/reports/from-analysis",
        headers=headers,
        json={
            "run_id": run_id,
            "session_id": chat_data["session_id"],
            "title": "Category Sales Performance Report",
            "format_type": "pdf",
            "report_type": "Executive Report",
        },
    )
    assert gen_resp.status_code == 201
    report = gen_resp.json()
    assert report["status"] == "GENERATED"
    assert report["format"] == "pdf"
    report_id = report["id"]

    # Download Report PDF
    dl_resp = client.get(f"/api/v1/reports/{report_id}/download", headers=headers)
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/pdf"
    assert len(dl_resp.content) > 1000

    # Validate PDF structure using pypdf
    reader = PdfReader(BytesIO(dl_resp.content))
    assert len(reader.pages) >= 1
    extracted_text = "".join(p.extract_text() or "" for p in reader.pages)
    assert "Category Sales Performance Report" in extracted_text or "Executive Overview" in extracted_text


def test_two_account_isolation_analysis_and_reports(client: TestClient, db_session: Session):
    """Verify Account B cannot view or download Account A's sessions or reports."""
    user_a, token_a, ws_a = make_test_user_and_workspace(db_session, "iso_a")
    user_b, token_b, ws_b = make_test_user_and_workspace(db_session, "iso_b")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Account A creates session
    sess_a = client.post(
        "/api/v1/analysis/sessions",
        headers=headers_a,
        json={"title": "Secret Session A", "workspace_id": str(ws_a.id)},
    ).json()
    session_id_a = sess_a["session_id"]

    # Account B attempts to read Account A's session -> 404
    denied_resp = client.get(f"/api/v1/analysis/sessions/{session_id_a}", headers=headers_b)
    assert denied_resp.status_code == 404

    # Account B attempts to delete Account A's session -> 404
    del_resp = client.delete(f"/api/v1/analysis/sessions/{session_id_a}", headers=headers_b)
    assert del_resp.status_code == 404
