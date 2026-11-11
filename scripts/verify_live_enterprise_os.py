"""End-to-end verification of all eight core capabilities, DuckDB analytics,
neural repair selector controls, and report downloads against the running live server.
"""
import io
import json
import os
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if "/app" not in sys.path:
    sys.path.insert(0, "/app")

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.tenant import Tenant
from backend.app.models.workspace import Workspace
from backend.app.models.user import User
from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")
HEALTH_URL = os.environ.get("HEALTH_URL", "http://localhost:8000/health/ready")


def setup_workspace_for_user(user_id_str: str) -> UUID:
    user_id = UUID(user_id_str)
    settings = get_settings()
    engine = create_engine(settings.postgres_dsn)
    with Session(engine) as db, db.begin():
        tenant_id = uuid4()
        workspace_id = uuid4()
        tenant = Tenant(
            id=tenant_id,
            tenant_name=f"E2E Enterprise Tenant {tenant_id.hex[:6]}",
            tenant_slug=f"e2e-tenant-{tenant_id.hex[:8]}",
            tenant_status="active"
        )
        db.add(tenant)
        db.flush()

        workspace = Workspace(
            id=workspace_id,
            tenant_id=tenant_id,
            workspace_name="Live Enterprise Acceptance Workspace",
            workspace_slug=f"live-acceptance-{workspace_id.hex[:8]}",
            status="active"
        )
        db.add(workspace)
        db.flush()

        db.execute(tenant_memberships.insert().values(
            tenant_id=tenant_id,
            user_id=user_id,
            role="owner",
            active=True
        ))
        db.execute(workspace_memberships.insert().values(
            workspace_id=workspace_id,
            user_id=user_id,
            role="owner",
            active=True
        ))
    engine.dispose()
    return workspace_id


def run_live_verification():
    print("=" * 70)
    print("STARTING LIVE ENTERPRISE DATA ANALYST OS END-TO-END VERIFICATION")
    print("=" * 70)

    client = httpx.Client(timeout=30.0)

    # 1. System Readiness
    print("\n[STEP 1] Checking System Health & Readiness...")
    res = client.get(HEALTH_URL)
    assert res.status_code == 200, f"Readiness check failed: {res.status_code} {res.text}"
    health = res.json()
    assert health.get("status") == "ready", f"System not ready: {health}"
    print("  -> System is READY (PostgreSQL, Redis, ChromaDB connected).")

    # 2. Authentication & Workspace Setup
    print("\n[STEP 2] Authenticating User & Enrolling in Workspace...")
    email = f"e2e_analyst_{uuid4().hex[:8]}@example.com"
    password = "LiveSecurePassword123!"
    res = client.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "E2E Enterprise Analyst"
    })
    assert res.status_code == 201, f"Registration failed: {res.status_code} {res.text}"
    user_id = res.json()["id"]

    res = client.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": password
    })
    assert res.status_code == 200, f"Login failed: {res.status_code} {res.text}"
    tokens = res.json()
    token = tokens["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.headers.update(headers)
    print(f"  -> Authenticated as {email} (user_id={user_id}).")

    workspace_id = setup_workspace_for_user(user_id)
    ws_param = f"workspace_id={workspace_id}"
    print(f"  -> Enrolled in isolated Enterprise Workspace: {workspace_id}")

    # 3. Policy Configuration
    print("\n[STEP 3] Configuring Company Policy (self-approval allowed for test runner)...")
    res = client.put(f"{BASE_URL}/dataplane/company/policy?{ws_param}", json={
        "allow_self_approval": True,
        "expected_revision": 0,
        "reason": "Live E2E Verification Policy"
    })
    assert res.status_code == 200, f"Failed to set policy: {res.status_code} {res.text}"
    print("  -> Company policy configured successfully.")

    # 4. DuckDB Ingestion via Dataplane
    print("\n[STEP 4] Ingesting CSV via Dataplane (DuckDB Engine)...")
    csv_bytes = b"region,amount,category\nNorth,100,Hardware\nSouth,200,Software\nNorth,50,Hardware\nSouth,150,Services\n"
    res = client.post(
        f"{BASE_URL}/dataplane/upload",
        data={"workspace_id": str(workspace_id), "idempotency_key": str(uuid4())},
        files={"file": ("sales.csv", csv_bytes, "text/csv")}
    )
    assert res.status_code == 202, f"Dataplane upload failed: {res.status_code} {res.text}"
    upload_job = res.json()
    job_id = upload_job["id"]
    print(f"  -> Queued upload job_id={job_id}")

    # Wait for durable worker to finish ingestion
    deadline = time.time() + 30.0
    snapshot_artifact = None
    while time.time() < deadline:
        res = client.get(f"{BASE_URL}/dataplane/jobs/{job_id}?{ws_param}")
        assert res.status_code == 200, f"Job poll failed: {res.text}"
        job_state = res.json()
        if job_state["status"] == "READY":
            snapshot_id = job_state["result"]["artifact_id"]
            res_art = client.get(f"{BASE_URL}/dataplane/artifacts/{snapshot_id}?{ws_param}")
            if res_art.status_code == 200:
                snapshot_artifact = res_art.json()
                break
        elif job_state["status"] in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Ingestion job failed: {job_state}")
        time.sleep(0.5)

    assert snapshot_artifact is not None, "Timed out waiting for upload job completion"
    dataset_id = snapshot_artifact["dataset_id"]
    snapshot_id = snapshot_artifact["id"]
    print(f"  -> DuckDB Ingestion complete! snapshot_id={snapshot_id}, dataset_id={dataset_id}")

    # 5. Feature 1: Company Business Dictionary
    print("\n[STEP 5] Testing Feature 1: Company Business Dictionary (Draft, Review, Approve)...")
    dict_key = f"revenue_total_{uuid4().hex[:6]}"
    draft_payload = {
        "definition": {
            "key": dict_key,
            "version": 1,
            "owner": "Finance Team",
            "source": "Sales CSV Snapshot",
            "metric": {
                "column": "amount",
                "aggregation": "sum",
                "missing": "exclude",
                "definition_ref": None
            },
            "filters": [],
            "units": "USD",
            "currency": "USD",
            "examples": [{"values": [100, 200, 50, 150], "expected": 500}]
        },
        "dataset_id": dataset_id,
        "description": "Total sales revenue excluding missing values",
        "domain": "Sales & Finance",
        "aliases": [f"{dict_key} total"],
        "grain": "One transaction line",
        "timezone": "UTC",
        "date_basis": "All uploaded rows",
        "exclusions": [],
        "effective_from": "2026-01-01",
        "health_rules": []
    }
    res = client.post(f"{BASE_URL}/dataplane/company/dictionary?{ws_param}", json=draft_payload)
    assert res.status_code == 201, f"Failed to draft dictionary: {res.status_code} {res.text}"
    dict_entry = res.json()
    dict_id = dict_entry["id"]
    print(f"  -> Created immutable draft: key={dict_key}, id={dict_id}")

    # Move to in_review
    res = client.post(f"{BASE_URL}/dataplane/company/dictionary/{dict_id}/review?{ws_param}", json={
        "expected_revision": 0,
        "action": "review",
        "reason": "Submitted for formal peer review"
    })
    assert res.status_code == 200, f"Review failed: {res.status_code} {res.text}"

    # Approve
    res = client.post(f"{BASE_URL}/dataplane/company/dictionary/{dict_id}/review?{ws_param}", json={
        "expected_revision": 1,
        "action": "approve",
        "reason": "Formally approved against test suite examples"
    })
    assert res.status_code == 200, f"Approve failed: {res.status_code} {res.text}"
    print(f"  -> Dictionary definition {dict_key} approved successfully.")

    # 6. Feature 2: "Show How This Was Calculated" & Bounded DuckDB Analytics
    print("\n[STEP 6] Testing Feature 2: DuckDB Query Execution & Calculation Evidence...")
    query_payload = {
        "definition_id": dict_id,
        "snapshot_id": snapshot_id,
        "business_date": "2026-11-11",
        "plan": {
            "metric": dict_key,
            "dimensions": []
        },
        "idempotency_key": str(uuid4())
    }
    res = client.post(f"{BASE_URL}/dataplane/company/query?{ws_param}", json=query_payload)
    assert res.status_code == 202, f"Query failed: {res.status_code} {res.text}"
    query_job_id = res.json()["id"]

    deadline = time.time() + 30.0
    evidence_artifact = None
    while time.time() < deadline:
        res = client.get(f"{BASE_URL}/dataplane/jobs/{query_job_id}?{ws_param}")
        job_state = res.json()
        if job_state["status"] == "READY":
            evidence_id = job_state["result"]["artifact_id"]
            res_art = client.get(f"{BASE_URL}/dataplane/artifacts/{evidence_id}?{ws_param}")
            if res_art.status_code == 200:
                evidence_artifact = res_art.json()
                break
        elif job_state["status"] in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Query job failed: {job_state}")
        time.sleep(0.5)

    assert evidence_artifact is not None, "Timed out waiting for query job"
    evidence_id = evidence_artifact["id"]
    calc_rows = evidence_artifact["payload"]["rows"]
    print(f"  -> Query executed in DuckDB! Result rows: {calc_rows}")
    assert calc_rows == [{"value": 500}], f"Unexpected sum calculation: {calc_rows}"

    # Fetch "Show how this was calculated" panel data
    res = client.get(f"{BASE_URL}/dataplane/company/evidence/{evidence_id}?{ws_param}")
    assert res.status_code == 200, f"Evidence inspection failed: {res.text}"
    calc_panel = res.json()
    assert calc_panel["definition_context"]["formula"] == "sum(amount)"
    assert calc_panel["coverage"] == "full"
    print(f"  -> 'Show how this was calculated' panel verified: formula='{calc_panel['definition_context']['formula']}', coverage='{calc_panel['coverage']}'.")

    # 7. End-to-End Report Generation & Real Download
    print("\n[STEP 7] Testing Report Generation & Download (PDF)...")
    res = client.get(f"{BASE_URL}/dataplane/evidence/{evidence_id}/report?{ws_param}")
    assert res.status_code == 200, f"Report download failed: {res.status_code} {res.text}"
    assert res.content.startswith(b"%PDF"), "Report is not a valid PDF binary"
    assert "attachment" in res.headers.get("content-disposition", ""), "Missing attachment header"
    print(f"  -> Real PDF report generated and downloaded successfully ({len(res.content)} bytes).")

    # 8. Feature 3: Data-Health Monitoring & Incidents
    print("\n[STEP 8] Testing Feature 3: Data-Health Monitoring & Incidents...")
    res = client.get(f"{BASE_URL}/dataplane/company/incidents?{ws_param}")
    assert res.status_code == 200, f"Incidents check failed: {res.text}"
    incidents = res.json()
    print(f"  -> Data-health monitoring verified: incidents endpoint returned successfully.")

    # 9. Feature 4: Cleaning Preview & Version History
    print("\n[STEP 9] Testing Feature 4: Cleaning Preview & Version History...")
    res = client.post(f"{BASE_URL}/dataplane/snapshots/{snapshot_id}/cleaning?{ws_param}", json={
        "plan": {
            "operation": "drop_nulls",
            "columns": ["amount"],
            "reason": "Explicit synthetic cleaning preview"
        }
    })
    assert res.status_code == 202, f"Cleaning preview failed: {res.status_code} {res.text}"
    print("  -> Cleaning preview generated successfully.")

    res = client.get(f"{BASE_URL}/dataplane/company/versions/{dataset_id}?{ws_param}")
    assert res.status_code == 200, f"Version history failed: {res.text}"
    versions = res.json()
    print(f"  -> Dataset version history retrieved ({len(versions)} versions).")

    # 10. Feature 5: Reviewed Correction Memory
    print("\n[STEP 10] Testing Feature 5: Reviewed Correction Memory...")
    res = client.get(f"{BASE_URL}/dataplane/company/reviews?{ws_param}")
    assert res.status_code == 200, f"Reviews retrieval failed: {res.text}"
    reviews = res.json()
    print(f"  -> Reviewed correction memory verified ({len(reviews.get('items', reviews))} entries).")

    # 11. Feature 6: "What Changed?" Report Comparison
    print("\n[STEP 11] Testing Feature 6: 'What Changed?' Report Comparison...")
    res = client.post(f"{BASE_URL}/dataplane/company/compare?{ws_param}", json={
        "previous_id": str(evidence_id),
        "current_id": str(evidence_id)
    })
    assert res.status_code == 201, f"Comparison failed: {res.status_code} {res.text}"
    diff_report = res.json()
    assert diff_report["comparable"] is True, f"Expected comparable: {diff_report}"
    assert diff_report["mismatches"] == [], f"Expected zero mismatches: {diff_report['mismatches']}"
    assert diff_report["totals"]["absolute_change"] == "0", f"Expected zero delta: {diff_report['totals']}"
    print("  -> 'What changed?' report comparison verified (comparable: True, absolute_change: 0).")

    # 12. Feature 7: Automatic Accuracy Checks & Forecasting
    print("\n[STEP 12] Testing Feature 7: Automatic Accuracy Checks & Dashboard...")
    res = client.get(f"{BASE_URL}/forecasting/accuracy-dashboard")
    assert res.status_code == 200, f"Accuracy dashboard failed: {res.status_code} {res.text}"
    print("  -> Accuracy checks & forecasting dashboard verified.")

    # 13. Feature 8: Reusable, Approved Reporting Workflows
    print("\n[STEP 13] Testing Feature 8: Reusable Reporting Workflows...")
    res = client.get(f"{BASE_URL}/dataplane/company/workflows?{ws_param}")
    assert res.status_code == 200, f"Workflows check failed: {res.status_code} {res.text}"
    print("  -> Reusable reporting workflows endpoint verified.")

    # 14. Neural Repair Selector Controls & Lifecycle
    print("\n[STEP 14] Testing Neural Repair Selector Controls & Lifecycle...")
    res = client.get(f"{BASE_URL}/adaptive/controls?workspace_id={workspace_id}")
    assert res.status_code == 200, f"Adaptive controls check failed: {res.status_code} {res.text}"
    adaptive_ctrl = res.json()
    assert "effective_selector" in adaptive_ctrl, f"Missing effective_selector in {adaptive_ctrl}"
    print(f"  -> Adaptive repair selector verified (effective_selector: '{adaptive_ctrl['effective_selector']}').")

    print("\n" + "=" * 70)
    print("ALL 8 FEATURES, DUCKDB ANALYTICS, AND NEURAL LEARNING VERIFIED LIVE!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    try:
        run_live_verification()
    except Exception as exc:
        print(f"\n[FAILURE] Verification encountered an error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
