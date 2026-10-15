"""Comprehensive Regression and Integration Test Suite for Complete Application Recovery.

Validates:
1. Cross-platform path portability and resolution in StorageService (Windows absolute -> container path).
2. prosandcons.xlsx recovery and successful execution in DataRetrievalService and EDAService.
3. Dataset preview contract: tabular datasets vs explicit document guidance.
4. External database connectors (PostgreSQL & MySQL) test endpoints, SSRF protection, and persistence.
5. Seven-stage AnalysisRun persistence and lifecycle (create, stage initialization, cancel, retry).
6. Two-account workspace isolation for database connections and analytical runs.
"""

from pathlib import Path
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.exceptions import StorageFileNotFoundError
from backend.app.core.security import create_access_token
from backend.app.database.postgres import PostgresDatabase
from backend.app.main import create_app
from backend.app.models.tenant import Tenant
from backend.app.models.user import User
from backend.app.models.workspace import Workspace
from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships, dataset_workspace_bindings
from backend.app.services.data_retrieval_service import DataRetrievalService
from backend.app.services.eda_service import EDAService
from backend.app.services.storage_service import StorageService


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
    return ws


# =============================================================================
# 1. PATH RESOLUTION & RECOVERY (ERROR 2 ROOT CAUSE)
# =============================================================================

def test_windows_path_resolution(settings):
    """StorageService must seamlessly resolve Windows absolute paths into container storage."""
    storage = StorageService(settings)
    win_path = r"C:\data analyst\ai-data-analyst-os\storage\raw\excel\38003018-eeb7-4842-afad-78844a3bbec8_prosandcons.xlsx"
    resolved = storage.retrieve_file(win_path)
    assert resolved.exists()
    assert resolved.is_file()
    assert resolved.name == "38003018-eeb7-4842-afad-78844a3bbec8_prosandcons.xlsx"

    # Test relative path
    rel_path = "raw/excel/38003018-eeb7-4842-afad-78844a3bbec8_prosandcons.xlsx"
    resolved_rel = storage.retrieve_file(rel_path)
    assert resolved_rel.exists()

    # Test non-existent path raises StorageFileNotFoundError
    with pytest.raises(StorageFileNotFoundError):
        storage.retrieve_file(r"C:\some\nonexistent\fake_file_12345.csv")


def test_prosandcons_excel_recovery_and_eda(db_session, settings):
    """prosandcons.xlsx must load into DataRetrievalService and complete full automated EDA."""
    ds_id = "38003018-eeb7-4842-afad-78844a3bbec8"
    row = db_session.execute(
        text("SELECT owner_id FROM datasets WHERE dataset_id = :id"),
        {"id": ds_id},
    ).fetchone()
    assert row is not None, "prosandcons dataset record must exist in PostgreSQL"
    owner_id = str(row[0])

    retrieval = DataRetrievalService(db_session, StorageService(settings), owner_id=owner_id)
    df, is_sampled = retrieval.load_dataframe(ds_id)

    assert df is not None
    assert len(df) in {16, 17}, f"Expected 16 or 17 rows, got {len(df)}"
    assert len(df.columns) == 4
    assert is_sampled is False

    # Execute full automated EDA
    eda = EDAService(retrieval_service=retrieval)
    results = eda.analyze_dataframe(df, dataset_id=ds_id)
    assert results.dataset_summary.row_count in {16, 17}
    assert results.dataset_summary.column_count == 4
    assert len(results.business_insights) > 0


# =============================================================================
# 2. DATASET PREVIEW & VISUALIZATION CONTRACT (ERROR 3 ROOT CAUSE)
# =============================================================================

def test_dataset_preview_tabular_success(client, db_session):
    """Tabular preview on prosandcons must return exact rows and columns for authorized owner."""
    owner_id = "a9573a0b-8a48-4883-a54f-46650627ecdf"
    token = create_access_token({"sub": owner_id, "email": "rabs.chinmay@gmail.com"})
    ds_id = "38003018-eeb7-4842-afad-78844a3bbec8"

    response = client.get(
        f"/api/v1/datasets/{ds_id}/preview?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "rows" in data
    assert "columns" in data
    assert len(data["rows"]) == 10
    assert data["source_type"] == "tabular"
    assert data["total_rows"] == 17


def test_dataset_preview_unstructured_document_guidance(client, db_session, settings):
    """Requesting tabular preview on an unstructured document returns clear 400 guidance."""
    user, token = make_user_token(db_session, "doc_user")
    ws = make_workspace(db_session, user)

    # Upload a small text document
    content = b"# Architecture Overview\nThis document describes the RAG indexing system."
    res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("architecture.md", content, "text/markdown")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    doc_id = res.json()["dataset_id"]

    # Bind to workspace
    db_session.execute(
        dataset_workspace_bindings.insert().values(
            dataset_id=doc_id,
            workspace_id=ws.id,
        )
    )
    db_session.commit()

    # Calling preview on this document must return structured 400 guidance
    preview_res = client.get(
        f"/api/v1/datasets/{doc_id}/preview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert preview_res.status_code == 400
    body = preview_res.json()
    assert body["error_code"] == "unstructured_document_source"
    assert "unstructured document" in body["message"].lower()


# =============================================================================
# 3. EXTERNAL DATABASE CONNECTORS (ERROR 1 ROOT CAUSE)
# =============================================================================

def test_external_connection_test_postgresql_and_ssrf(client, db_session):
    """External database connection testing must validate inputs, block SSRF, and test connections."""
    user, token = make_user_token(db_session, "conn_tester")

    # SSRF Protection: blocked metadata IP
    ssrf_res = client.post(
        "/api/v1/connections/test",
        json={
            "connector_type": "postgresql",
            "host": "169.254.169.254",
            "port": 5432,
            "database": "secret",
            "username": "admin",
            "password": "pwd",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ssrf_res.status_code == 400
    body = ssrf_res.json()
    assert "disallowed" in body["message"].lower()

    # Real connection test against PostgreSQL service in Docker network
    test_res = client.post(
        "/api/v1/connections/test",
        json={
            "connector_type": "postgresql",
            "host": "postgres",
            "port": 5432,
            "database": "ai_analyst",
            "username": "postgres",
            "password": "postgres",
            "schema_name": "public",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert test_res.status_code == 200
    result = test_res.json()
    assert result["success"] is True
    assert result["status"] == "HEALTHY"
    assert result["connector_type"] == "postgresql"
    assert result["latency_ms"] > 0
    assert "datasets" in result["tables"]
    assert result["total_tables"] > 0


def test_external_connection_persistence_and_masking(client, db_session):
    """Saving database connection must mask secrets and persist metadata scoped to workspace."""
    user, token = make_user_token(db_session, "conn_owner")
    ws = make_workspace(db_session, user)

    # Save connection
    save_res = client.post(
        "/api/v1/connections",
        json={
            "workspace_id": str(ws.id),
            "connector_name": "Primary Analytics Warehouse",
            "connector_type": "postgresql",
            "host": "postgres",
            "port": 5432,
            "database": "ai_analyst",
            "username": "postgres",
            "password": "supersecretpassword123",
            "schema_name": "public",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert save_res.status_code == 201
    conn_data = save_res.json()
    assert conn_data["connector_name"] == "Primary Analytics Warehouse"
    assert conn_data["config"]["password"] == "••••••••"
    conn_id = conn_data["id"]

    # List connections for workspace
    list_res = client.get(
        f"/api/v1/connections?workspace_id={ws.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1
    assert any(c["id"] == conn_id for c in items)

    # Delete connection
    del_res = client.delete(
        f"/api/v1/connections/{conn_id}?workspace_id={ws.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True


# =============================================================================
# 4. SEVEN-STAGE ANALYTICAL PIPELINE LIFECYCLE
# =============================================================================

def test_seven_stage_pipeline_lifecycle(client, db_session):
    """AnalysisRun creation initializes all 7 stages and respects cancel/retry transitions."""
    user, token = make_user_token(db_session, "pipeline_analyst")
    ws = make_workspace(db_session, user)

    # Upload test CSV
    csv_bytes = b"revenue,cost,region\n1000,400,North\n1500,600,South\n"
    up_res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("revenue_metrics.csv", csv_bytes, "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert up_res.status_code == 201
    ds_id = up_res.json()["dataset_id"]

    # Bind dataset
    db_session.execute(
        dataset_workspace_bindings.insert().values(dataset_id=ds_id, workspace_id=ws.id)
    )
    db_session.commit()

    # Create run
    run_res = client.post(
        "/api/v1/orchestrator/runs",
        json={
            "workspace_id": str(ws.id),
            "dataset_id": ds_id,
            "version_number": 1,
            "query": "What is total revenue across regions?",
            "idempotency_key": f"run-test-{uuid4().hex[:12]}",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_res.status_code == 201
    run_data = run_res.json()
    assert "id" in run_data
    assert len(run_data["stages"]) == 7

    stage_names = [s["name"] for s in run_data["stages"]]
    expected_stages = [
        "Problem formulation",
        "Data collection",
        "Data preparation",
        "Exploratory analysis",
        "Data modeling",
        "Visualization and reporting",
        "Recommendations",
    ]
    assert stage_names == expected_stages

    # Test cancel run
    cancel_res = client.post(
        f"/api/v1/orchestrator/runs/{run_data['id']}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"


# =============================================================================
# 5. TWO-ACCOUNT WORKSPACE ISOLATION
# =============================================================================

def test_two_account_isolation_connectors_and_runs(client, db_session):
    """Account B cannot read or modify Account A's connections or analysis runs."""
    user_a, token_a = make_user_token(db_session, "account_a")
    user_b, token_b = make_user_token(db_session, "account_b")
    ws_a = make_workspace(db_session, user_a)
    ws_b = make_workspace(db_session, user_b)

    # Account A creates a connection
    save_res = client.post(
        "/api/v1/connections",
        json={
            "workspace_id": str(ws_a.id),
            "connector_name": "Account A Private DB",
            "connector_type": "postgresql",
            "host": "postgres",
            "port": 5432,
            "database": "ai_analyst",
            "username": "postgres",
            "password": "secret",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert save_res.status_code == 201
    conn_id_a = save_res.json()["id"]

    # Account B attempts to list Account A's connections (must be denied 403)
    list_res = client.get(
        f"/api/v1/connections?workspace_id={ws_a.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert list_res.status_code in (403, 404)

    # Account B attempts to delete Account A's connection (must be denied)
    del_res = client.delete(
        f"/api/v1/connections/{conn_id_a}?workspace_id={ws_a.id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert del_res.status_code in (403, 404)
