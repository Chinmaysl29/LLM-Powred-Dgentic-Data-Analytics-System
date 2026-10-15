"""Comprehensive Verification and Acceptance Test Suite for
Permanent Visualization & Data Analysis Engine Repair.

Tests:
1. Smart tabular header detection (handling banner title rows like Bluestock Cashflow header=1).
2. Financial numeric type inference (Indian commas, currencies ₹/$/€/£/Rs., accounting negatives, percentages).
3. Identifier column protection (id, company_id, sku, account_no).
4. Separation of Contract A (100-row preview) from Contract B (1,187-row analytical calculation).
5. Chart Data API (/api/v1/datasets/{id}/chart-data) for Bar, Scatter, Histogram, Line, KPI.
6. Multi-tenant workspace authorization and security guardrails.
"""

import io
from pathlib import Path
from uuid import UUID, uuid4
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token
from backend.app.database.postgres import PostgresDatabase
from backend.app.main import create_app
from backend.app.models.tenant import Tenant
from backend.app.models.user import User
from backend.app.models.workspace import Workspace
from backend.app.models.dataset import Dataset
from backend.app.core.workspace_authorization import (
    tenant_memberships,
    workspace_memberships,
    dataset_workspace_bindings,
)
from backend.app.services.tabular_loader import (
    detect_header_row,
    parse_financial_value,
    is_identifier_column,
    load_tabular_dataframe,
)
from backend.app.services.data_retrieval_service import DataRetrievalService


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
        email=f"{email_prefix}_{user_id.hex[:6]}@viz-recovery.test",
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


# ==============================================================================
# MILESTONE 1 & 3: TABULAR LOADER & FINANCIAL NUMERIC INFERENCE TESTS
# ==============================================================================

def test_financial_numeric_parsing():
    """Verify robust parsing of Indian commas, currency symbols, accounting negatives, and percentages."""
    # Western and Indian commas
    assert parse_financial_value("12,500") == 12500.0
    assert parse_financial_value("1,25,000") == 125000.0
    assert parse_financial_value("10,00,000") == 1000000.0
    
    # Currency symbols
    assert parse_financial_value("₹12,500") == 12500.0
    assert parse_financial_value("₹ 1,25,000.50") == 125000.50
    assert parse_financial_value("$1,250.75") == 1250.75
    assert parse_financial_value("€999.00") == 999.0
    assert parse_financial_value("£450.25") == 450.25
    assert parse_financial_value("Rs. 50,000") == 50000.0

    # Accounting parentheses for negative numbers
    assert parse_financial_value("(12,500)") == -12500.0
    assert parse_financial_value("(₹5,000.50)") == -5000.50
    assert parse_financial_value("($100)") == -100.0

    # Standard positive/negative numbers
    assert parse_financial_value("12500") == 12500.0
    assert parse_financial_value("-12500") == -12500.0
    assert parse_financial_value("-1,250.25") == -1250.25
    assert parse_financial_value("0.25") == 0.25

    # Percentages
    assert parse_financial_value("25%") == 25.0
    assert parse_financial_value("12.5%") == 12.5

    # Non-numeric strings must return None without crashing
    assert parse_financial_value("Bluestock Fintech — Nifty 100") is None
    assert parse_financial_value("TCS") is None
    assert parse_financial_value("Mar-13") is None
    assert parse_financial_value(None) is None


def test_identifier_column_protection():
    """Ensure identifiers like ID, SKU, Account number are not selected as numeric metrics."""
    assert is_identifier_column("id") is True
    assert is_identifier_column("company_id") is True
    assert is_identifier_column("account_number") is True
    assert is_identifier_column("customer_uuid") is True
    assert is_identifier_column("zip_code") is True
    assert is_identifier_column("sku") is True
    assert is_identifier_column("phone_number") is True

    # Measures must NOT be marked as identifiers
    assert is_identifier_column("revenue") is False
    assert is_identifier_column("net_cash_flow") is False
    assert is_identifier_column("operating_activity") is False
    assert is_identifier_column("sales_amount") is False


def test_smart_header_detection_bluestock_cashflow():
    """Verify that Bluestock cashflow dataset correctly skips the banner title row."""
    file_path = Path("/app/storage/raw/excel/6ac6f755-9978-4ce0-b3dc-928b70c2eeff_cashflow.xlsx")
    if not file_path.exists():
        pytest.skip(f"Test file not found at {file_path}")

    # Load with smart tabular loader
    df = load_tabular_dataframe(file_path)

    # 1. Row 0 banner title must NOT be used as column headers
    assert "Bluestock Fintech — Nifty 100 | Cash Flow | 1,187 records" not in df.columns
    assert "Unnamed: 1" not in df.columns

    # 2. Columns must be the clean actual fields
    expected_cols = ["id", "company_id", "year", "operating_activity", "investing_activity", "financing_activity", "net_cash_flow"]
    assert list(df.columns) == expected_cols

    # 3. Total records must be exactly 1,187
    assert len(df) == 1187

    # 4. Numeric fields must be properly converted to float/int
    numeric_cols = ["operating_activity", "investing_activity", "financing_activity", "net_cash_flow"]
    for col in numeric_cols:
        assert pd.api.types.is_numeric_dtype(df[col]), f"Column {col} was not parsed as numeric"
        assert df[col].notna().sum() > 1000


# ==============================================================================
# MILESTONE 2: CONTRACT A (100-ROW PREVIEW) VS CONTRACT B (1,187-ROW ANALYTICS)
# ==============================================================================

def test_1187_row_aggregation_separate_from_preview(tmp_path):
    """
    CRITICAL ARCHITECTURAL TEST:
    A 100-row preview must never silently become the source of truth for 1,187-row calculations!
    We construct a deterministic 1,187-row fixture where rows 1..100 have amount=1.0 and
    rows 101..1187 have amount=10.0.
    Preview sum = 100 * 1.0 = 100.0.
    Full population sum = 100 * 1.0 + 1087 * 10.0 = 100.0 + 10870.0 = 10,970.0.
    """
    csv_file = tmp_path / "deterministic_1187_fixture.csv"
    
    rows = []
    # First 100 rows: amount = 1.0
    for i in range(1, 101):
        region = "North" if i % 2 == 0 else "South"
        rows.append({"order_id": i, "region": region, "amount": 1.0, "status": "completed"})
    # Remaining 1,087 rows: amount = 10.0
    for i in range(101, 1188):
        region = "North" if i % 2 == 0 else "South"
        rows.append({"order_id": i, "region": region, "amount": 10.0, "status": "completed"})
    
    df_fixture = pd.DataFrame(rows)
    assert len(df_fixture) == 1187
    df_fixture.to_csv(csv_file, index=False)

    # 1. Preview Contract (Contract A):
    preview_df = load_tabular_dataframe(csv_file, max_rows=100)
    assert len(preview_df) == 100
    preview_sum = float(preview_df["amount"].sum())
    assert preview_sum == 100.0, f"Preview sum expected 100.0, got {preview_sum}"

    # 2. Analytical Query Contract (Contract B):
    full_df = load_tabular_dataframe(csv_file, max_rows=None)
    assert len(full_df) == 1187
    full_sum = float(full_df["amount"].sum())
    expected_full_sum = 100.0 + (1087 * 10.0)  # 10,970.0
    assert full_sum == expected_full_sum, f"Full sum expected {expected_full_sum}, got {full_sum}"

    # 3. Prove that preview_sum != full_sum
    assert full_sum > preview_sum * 100


# ==============================================================================
# MILESTONES 4 & 5: CHART DATA ENDPOINT & MULTI-TENANT AUTHORIZATION
# ==============================================================================

def test_chart_data_endpoint_full_population_and_metrics(client, db_session):
    """Verify POST /api/v1/datasets/{id}/chart-data computes exact full calculations over Bluestock cashflow."""
    user, token = make_user_token(db_session, "chart_tester")
    ws = make_workspace(db_session, user)

    dataset_id = UUID("6ac6f755-9978-4ce0-b3dc-928b70c2eeff")
    # Bind dataset to workspace and assign owner_id to test user
    db_session.execute(
        text("UPDATE datasets SET owner_id = :uid WHERE dataset_id = :did"),
        {"uid": str(user.id), "did": str(dataset_id)},
    )
    db_session.execute(
        text("DELETE FROM dataset_workspace_bindings WHERE dataset_id = :did"),
        {"did": str(dataset_id)},
    )
    db_session.execute(
        dataset_workspace_bindings.insert().values(
            workspace_id=ws.id,
            dataset_id=str(dataset_id),
        )
    )
    db_session.commit()

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Workspace-Id": str(ws.id),
    }

    # 1. Query Bar chart aggregating net_cash_flow by year
    bar_payload = {
        "chart_type": "Bar",
        "x_axis": "year",
        "y_axis": "net_cash_flow",
        "aggregation": "sum",
        "limit_categories": 50,
    }
    resp = client.post(f"/api/v1/datasets/{dataset_id}/chart-data", json=bar_payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["dataset_id"] == str(dataset_id)
    assert data["total_records"] == 1187
    assert data["is_sampled"] is False
    assert len(data["points"]) > 0
    p0 = data["points"][0]
    assert "label" in p0 and "value" in p0

    # Verify KPI calculations
    metrics = data["summary_metrics"]
    assert metrics["count"] == 1185  # 1,185 non-null values out of 1,187 total records
    assert data["total_records"] == 1187
    assert "sum" in metrics
    assert "mean" in metrics
    assert "min" in metrics
    assert "max" in metrics
    assert metrics["sum"] is not None

    # 2. Query Scatter chart comparing operating_activity vs investing_activity
    scatter_payload = {
        "chart_type": "Scatter",
        "x_axis": "operating_activity",
        "y_axis": "investing_activity",
    }
    resp_scatter = client.post(f"/api/v1/datasets/{dataset_id}/chart-data", json=scatter_payload, headers=headers)
    assert resp_scatter.status_code == 200, resp_scatter.text
    scatter_data = resp_scatter.json()
    assert scatter_data["chart_type"] == "Scatter"
    assert len(scatter_data["scatter_points"]) > 500  # genuine paired points
    sp0 = scatter_data["scatter_points"][0]
    assert "x" in sp0 and "y" in sp0

    # 3. Query Histogram for financing_activity
    hist_payload = {
        "chart_type": "Histogram",
        "y_axis": "financing_activity",
    }
    resp_hist = client.post(f"/api/v1/datasets/{dataset_id}/chart-data", json=hist_payload, headers=headers)
    assert resp_hist.status_code == 200, resp_hist.text
    hist_data = resp_hist.json()
    assert hist_data["chart_type"] == "Histogram"
    assert len(hist_data["histogram_bins"]) > 0
    # Sum of histogram frequencies should equal valid observations (1,185)
    total_freq = sum(b["count"] for b in hist_data["histogram_bins"])
    assert total_freq == 1185


def test_chart_data_multi_tenant_isolation(client, db_session):
    """Verify that User B in another workspace CANNOT access User A's dataset chart data."""
    user_a, _ = make_user_token(db_session, "user_a")
    ws_a = make_workspace(db_session, user_a)

    user_b, token_b = make_user_token(db_session, "user_b")
    ws_b = make_workspace(db_session, user_b)

    dataset_id = UUID("6ac6f755-9978-4ce0-b3dc-928b70c2eeff")
    # Bind exclusively to Workspace A and assign owner_id to User A
    db_session.execute(
        text("UPDATE datasets SET owner_id = :uid WHERE dataset_id = :did"),
        {"uid": str(user_a.id), "did": str(dataset_id)},
    )
    db_session.execute(
        text("DELETE FROM dataset_workspace_bindings WHERE dataset_id = :did"),
        {"did": str(dataset_id)},
    )
    db_session.execute(
        dataset_workspace_bindings.insert().values(
            workspace_id=ws_a.id,
            dataset_id=str(dataset_id),
        )
    )
    db_session.commit()

    # User B attempts to query User A's dataset in Workspace B
    headers_b = {
        "Authorization": f"Bearer {token_b}",
        "X-Workspace-Id": str(ws_b.id),
    }
    payload = {
        "chart_type": "bar",
        "dimension": "year",
        "metric": "net_cash_flow",
        "aggregation": "sum",
    }
    resp = client.post(f"/api/v1/datasets/{dataset_id}/chart-data", json=payload, headers=headers_b)
    # Must be 403 Forbidden or 404 Not Found
    assert resp.status_code in [403, 404], f"Expected 403/404, got {resp.status_code}: {resp.text}"

    # Teardown: Restore owner_id to canonical development user
    db_session.execute(
        text("UPDATE datasets SET owner_id = :uid WHERE dataset_id = :did"),
        {"uid": "a9573a0b-8a48-4883-a54f-46650627ecdf", "did": str(dataset_id)},
    )
    db_session.commit()
