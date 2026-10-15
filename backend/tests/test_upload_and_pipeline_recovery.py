"""Comprehensive Regression and Acceptance Test Suite for AI Data Analyst OS.

Validates:
1. Schema preflight verification (head revision, missing table detection, search path).
2. Universal upload format matrix (CSV, TSV, XLSX, JSON, JSONL, Parquet, PDF, TXT, MD).
3. Explicit DOCX rejection with actionable error messages.
4. Malformed/corrupted file and binary payload rejection.
5. Path traversal sanitization and checksum integrity.
6. Durable storage domain partitioning and PostgreSQL metadata persistence.
7. Two-account workspace authorization and tenant isolation.
8. Pipeline handoff (7-stage AnalysisRun vs RAG document indexing).
"""

import hashlib
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
from backend.app.database.schema_contract import inspect_schema
from backend.app.main import create_app
from backend.app.models.user import User
from backend.app.models.tenant import Tenant
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
# PHASE 1 & 7: SCHEMA PREFLIGHT TESTS
# ==============================================================================

def test_schema_preflight_compatible(db_engine):
    """Verify live database schema matches required head revision 009."""
    with db_engine.connect() as conn:
        result = inspect_schema(conn)
    assert result["compatible"] is True, f"Schema preflight failed: {result}"
    assert result["missing_tables"] == []
    assert result["missing_columns"] == {}
    assert result["revision_matches"] is True
    assert "009_analysis_runs" in result["actual_revisions"]


def test_schema_preflight_missing_table_detection(db_engine):
    """Verify preflight detects missing tables correctly without false positives."""
    from sqlalchemy import MetaData, Table, Column, Integer
    test_meta = MetaData()
    Table("non_existent_table_xyz", test_meta, Column("id", Integer, primary_key=True))
    with db_engine.connect() as conn:
        result = inspect_schema(conn, metadata=test_meta)
    assert result["compatible"] is False
    assert "non_existent_table_xyz" in result["missing_tables"]


def test_schema_preflight_missing_revision_detection(db_engine):
    """Verify preflight detects unapplied migrations correctly."""
    with db_engine.connect() as conn:
        result = inspect_schema(conn, expected_revisions=["999_unapplied_future_migration"])
    assert result["compatible"] is False
    assert result["revision_matches"] is False


def test_startup_readiness_endpoint(client):
    """Verify /health/ready returns status ready and schema healthy."""
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["critical_dependencies"]["schema"]["status"] == "healthy"
    assert data["critical_dependencies"]["postgresql"]["status"] == "healthy"


# ==============================================================================
# PHASE 2 & 7: UNIVERSAL UPLOAD FORMAT MATRIX & DOCX REJECTION
# ==============================================================================

def test_docx_explicit_rejection(client, db_session):
    """Microsoft Word (.docx) files must be explicitly rejected with a clear message."""
    _, token = make_user_token(db_session, "user_docx")
    fake_docx_content = b"PK\x03\x04\x14\x00Fake docx binary stream"
    files = {"file": ("document.docx", fake_docx_content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 415
    data = response.json()
    assert "explicitly unsupported" in data["message"].lower() or "unsupported" in data["message"].lower()
    assert "docx" in data["message"].lower()


def test_valid_csv_upload(client, db_session):
    """CSV upload must be parsed, profiled, quality-assessed, and stored durably."""
    user, token = make_user_token(db_session, "user_csv")
    csv_bytes = b"id,name,revenue,department\n1,Alpha,1000.5,Sales\n2,Beta,2500.0,Marketing\n3,Gamma,300.0,Engineering\n"
    files = {"file": ("revenue_report.csv", csv_bytes, "text/csv")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ready"
    assert data["file_type"] == "csv"
    assert data["row_count"] == 3
    assert data["column_count"] == 4
    assert Path(data["original_path"]).exists()
    assert Path(data["canonical_path"]).exists()


def test_valid_tsv_upload(client, db_session):
    """TSV upload must be parsed correctly using tab delimiters."""
    user, token = make_user_token(db_session, "user_tsv")
    tsv_bytes = b"id\tproduct\tprice\n101\tWidget A\t19.99\n102\tWidget B\t29.99\n"
    files = {"file": ("products.tsv", tsv_bytes, "text/tab-separated-values")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ready"
    assert data["file_type"] == "tsv"
    assert data["row_count"] == 2
    assert data["column_count"] == 3


def test_valid_xlsx_upload(client, db_session):
    """XLSX upload must be parsed into records and produce metadata."""
    user, token = make_user_token(db_session, "user_xlsx")
    buffer = io.BytesIO()
    df = pd.DataFrame({"quarter": ["Q1", "Q2", "Q3", "Q4"], "profit": [100, 150, 120, 210]})
    df.to_excel(buffer, index=False, engine="openpyxl")
    xlsx_bytes = buffer.getvalue()

    files = {"file": ("quarterly_profit.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ready"
    assert data["file_type"] == "xlsx"
    assert data["row_count"] == 4
    assert data["column_count"] == 2


def test_valid_json_upload(client, db_session):
    """JSON dataset upload must parse records array into canonical format."""
    user, token = make_user_token(db_session, "user_json")
    json_bytes = b'[{"country":"US","gdp":25000},{"country":"DE","gdp":4200},{"country":"JP","gdp":4100}]'
    files = {"file": ("gdp_data.json", json_bytes, "application/json")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ready"
    assert data["file_type"] == "json"
    assert data["row_count"] == 3


def test_valid_jsonl_upload(client, db_session):
    """JSONL / NDJSON lines must parse into records properly."""
    user, token = make_user_token(db_session, "user_jsonl")
    jsonl_bytes = b'{"timestamp":"2026-01-01T00:00:00","event":"click"}\n{"timestamp":"2026-01-01T00:01:00","event":"purchase"}\n'
    files = {"file": ("events.jsonl", jsonl_bytes, "application/x-ndjson")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ready"
    assert data["file_type"] == "jsonl"
    assert data["row_count"] == 2


def test_valid_parquet_upload(client, db_session):
    """Parquet dataset upload must parse columnar data accurately."""
    user, token = make_user_token(db_session, "user_parquet")
    buffer = io.BytesIO()
    df = pd.DataFrame({"sensor_id": [1, 2, 3], "temp": [21.5, 22.0, 21.8]})
    df.to_parquet(buffer, index=False)
    parquet_bytes = buffer.getvalue()

    files = {"file": ("sensors.parquet", parquet_bytes, "application/octet-stream")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "ready"
    assert data["file_type"] == "parquet"
    assert data["row_count"] == 3


def test_valid_pdf_upload(client, db_session):
    """PDF document upload must retain original bytes, SHA256 checksum, and status UPLOADED for RAG."""
    user, token = make_user_token(db_session, "user_pdf")
    # A minimal valid PDF structure
    minimal_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"
    )
    files = {"file": ("manual.pdf", minimal_pdf, "application/pdf")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["file_type"] == "pdf"
    assert data["indexing_status"] == "UPLOADED"
    assert data["content_hash"] == hashlib.sha256(minimal_pdf).hexdigest()
    assert Path(data["original_path"]).exists()


def test_valid_txt_upload(client, db_session):
    """Plain text document upload must be saved durably and prepared for document indexing."""
    user, token = make_user_token(db_session, "user_txt")
    txt_bytes = b"Enterprise Data Analytics Platform Architecture Specification.\nVersion 2.0."
    files = {"file": ("spec.txt", txt_bytes, "text/plain")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["file_type"] == "txt"
    assert data["indexing_status"] == "UPLOADED"
    assert Path(data["original_path"]).exists()


def test_valid_markdown_upload(client, db_session):
    """Markdown document upload must be preserved and prepared for document indexing."""
    user, token = make_user_token(db_session, "user_md")
    md_bytes = b"# Executive Summary\n\nQ3 showed a 25% increase in operational metrics across all teams."
    files = {"file": ("report.md", md_bytes, "text/markdown")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["file_type"] == "md"
    assert data["indexing_status"] == "UPLOADED"


# ==============================================================================
# SECURITY, MALFORMED CONTENT & TWO-ACCOUNT WORKSPACE ISOLATION
# ==============================================================================

def test_empty_file_rejection(client, db_session):
    """Empty files (0 bytes) must be rejected with 422 CorruptedFileError."""
    user, token = make_user_token(db_session, "user_empty")
    files = {"file": ("empty.csv", b"", "text/csv")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 422
    assert "empty" in response.json()["message"].lower()


def test_executable_payload_rejection(client, db_session):
    """Executable binaries disguised as CSV must be immediately rejected."""
    user, token = make_user_token(db_session, "user_exe")
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00Fake windows executable header"
    files = {"file": ("evil.csv", fake_exe, "text/csv")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 415
    assert "prohibited" in response.json()["message"].lower() or "unsupported" in response.json()["message"].lower()


def test_path_traversal_sanitization(client, db_session):
    """Path traversal filename must be sanitized to safe basename."""
    user, token = make_user_token(db_session, "user_traversal")
    csv_bytes = b"col1,col2\nval1,val2\n"
    files = {"file": ("../../../../etc/passwd.csv", csv_bytes, "text/csv")}
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/datasets/upload", files=files, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert ".." not in data["file_path"]
    assert "passwd.csv" in data["file_path"]


def test_two_account_workspace_isolation(client, db_session):
    """Account A uploads file; Account B is strictly denied access; Account B can upload own file."""
    user_a, token_a = make_user_token(db_session, "tenant_a")
    user_b, token_b = make_user_token(db_session, "tenant_b")

    ws_a = make_workspace(db_session, user_a)
    ws_b = make_workspace(db_session, user_b)

    # 1. Account A uploads dataset
    csv_a = b"user,secret_metric\nAlice,9999\n"
    res_a = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("tenant_a_data.csv", csv_a, "text/csv")},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert res_a.status_code == 201
    dataset_a_id = res_a.json()["dataset_id"]

    # 2. Account A binds dataset to Workspace A
    bind_res = client.post(
        f"/api/v1/datasets/{dataset_a_id}/workspace",
        json={"workspace_id": str(ws_a.id)},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert bind_res.status_code == 200

    # 3. Account B attempts to bind or read Account A's dataset -> DENIED
    forbidden_bind = client.post(
        f"/api/v1/datasets/{dataset_a_id}/workspace",
        json={"workspace_id": str(ws_b.id)},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert forbidden_bind.status_code in (403, 404)

    # 4. Account B attempts to trigger an AnalysisRun against Account A's dataset -> DENIED
    forbidden_run = client.post(
        "/api/v1/orchestrator/runs",
        json={
            "workspace_id": str(ws_b.id),
            "dataset_id": dataset_a_id,
            "query": "Show me secret metric",
            "idempotency_key": str(uuid4()),
        },
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert forbidden_run.status_code in (403, 404)

    # 5. Account B uploads and analyzes their own dataset -> SUCCEEDS
    csv_b = b"item,amount\nBook,45\n"
    res_b = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("tenant_b_data.csv", csv_b, "text/csv")},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_b.status_code == 201
    dataset_b_id = res_b.json()["dataset_id"]

    bind_b = client.post(
        f"/api/v1/datasets/{dataset_b_id}/workspace",
        json={"workspace_id": str(ws_b.id)},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert bind_b.status_code == 200


def test_pipeline_handoff_analysis_run(client, db_session):
    """Eligible structured dataset can initiate seven-stage AnalysisRun tracking."""
    user, token = make_user_token(db_session, "user_pipeline")
    ws = make_workspace(db_session, user)

    # Upload structured dataset
    csv_data = b"x,y\n1,10\n2,20\n3,30\n"
    res = client.post(
        "/api/v1/datasets/upload",
        files={"file": ("metrics.csv", csv_data, "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    dataset_id = res.json()["dataset_id"]

    # Bind to workspace
    client.post(
        f"/api/v1/datasets/{dataset_id}/workspace",
        json={"workspace_id": str(ws.id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Launch AnalysisRun
    idempotency_key = f"run-{uuid4()}"
    run_res = client.post(
        "/api/v1/orchestrator/runs",
        json={
            "workspace_id": str(ws.id),
            "dataset_id": dataset_id,
            "query": "Perform complete statistical analysis",
            "idempotency_key": idempotency_key,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_res.status_code == 201
    run_data = run_res.json()
    assert run_data["status"] in ("PENDING", "CREATED")
    assert run_data["dataset_id"] == dataset_id
    assert len(run_data["stages"]) == 7
