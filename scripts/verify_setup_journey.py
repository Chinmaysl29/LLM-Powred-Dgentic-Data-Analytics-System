"""Synthetic local-auth API journey, plus a separate post-restart persistence check.

Does not exercise Supabase browser login or make an external provider request.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
import time
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from pypdf import PdfReader
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-persistence", action="store_true")
    args = parser.parse_args()
    if make_url(os.environ["DATABASE_URL"]).database != "analyst_setup_test":
        raise SystemExit("Refusing journey outside the setup test database")
    from backend.app.core.config import Settings, get_settings
    Settings.model_config = {**Settings.model_config, "env_file": None}
    get_settings.cache_clear()
    from backend.app.core.security import create_access_token
    from backend.app.models.tenant import Tenant
    from backend.app.models.workspace import Workspace
    from backend.app.core.workspace_authorization import tenant_memberships, workspace_memberships
    state_file = Path("/verification/journey.json")
    with httpx.Client(base_url="http://api:8000", timeout=60) as client:
        deadline = time.monotonic() + 180
        while True:
            try:
                if client.get("/health/ready").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline:
                raise SystemExit("Isolated API readiness timed out")
            time.sleep(2)
        if args.verify_persistence:
            state = json.loads(state_file.read_text())
            client.headers["Authorization"] = "Bearer " + create_access_token({"sub": state["user_id"]})
            assert client.get(f'/api/v1/datasets/{state["dataset_id"]}').status_code == 200
            response = client.get(f'/api/v1/reports/{state["report_id"]}/download')
            assert response.status_code == 200
            assert PdfReader(BytesIO(response.content)).pages
            assert response.content == Path("/verification/setup-report.pdf").read_bytes()
            print("PASS: dataset and exact PDF bytes survived PostgreSQL and API service restart")
            return
        assert client.get("/api/v1/datasets").status_code in (401, 403)
        email = f"setup-{uuid4().hex[:12]}@example.com"
        password = "Setup-" + uuid4().hex + "-9!"
        response = client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Synthetic Setup Analyst"})
        assert response.status_code == 201, f"Register returned {response.status_code}"
        user_id = UUID(response.json()["id"])
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, f"Login returned {login.status_code}"
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        assert client.get("/api/v1/auth/me").status_code == 200
        tenant_id, workspace_id = uuid4(), uuid4()
        engine = create_engine(get_settings().postgres_dsn)
        with Session(engine) as db, db.begin():
            db.add(Tenant(id=tenant_id, tenant_name="Synthetic setup", tenant_slug=f"setup-{tenant_id.hex}", tenant_status="active"))
            db.flush()
            db.add(Workspace(id=workspace_id, tenant_id=tenant_id, workspace_name="Setup fixtures", workspace_slug="setup-fixtures", status="active"))
            db.flush()
            db.execute(tenant_memberships.insert().values(tenant_id=tenant_id, user_id=user_id, role="owner", active=True))
            db.execute(workspace_memberships.insert().values(workspace_id=workspace_id, user_id=user_id, role="owner", active=True))
        engine.dispose()
        client.headers["X-Workspace-Id"] = str(workspace_id)
        upload = client.post(f"/api/v1/datasets/upload?workspace_id={workspace_id}",
                             files={"file": ("setup_revenue.csv", b"region,revenue\nNorth,100\nSouth,200\nWest,300\nNorth,400\nSouth,500\nWest,600\n", "text/csv")})
        assert upload.status_code == 201, f"Upload returned {upload.status_code}"
        dataset_id = upload.json()["dataset_id"]
        binding = client.post(f"/api/v1/datasets/{dataset_id}/workspace", json={"workspace_id": str(workspace_id)})
        assert binding.status_code == 200, f"Workspace binding returned {binding.status_code}"
        chart = client.post(f"/api/v1/datasets/{dataset_id}/chart-data", json={"chart_type": "Histogram", "y_axis": "revenue"})
        assert chart.status_code == 200 and chart.json()["summary_metrics"]["sum"] == 2100
        # Supervisor business semantics are explicit, even in a synthetic fixture.
        definition = client.post(f'/api/v1/learning/definitions?workspace_id={workspace_id}', json={
            'key':'setup_revenue','version':1,'source':'Synthetic setup fixture specification','owner':'Synthetic setup owner',
            'metric':{'column':'revenue','aggregation':'sum','missing':'reject','definition_ref':None},
            'filters':[],'units':'fixture units','currency':None,'examples':[{'expected_total':2100}]})
        assert definition.status_code == 201
        task_spec = {'workspace_id':str(workspace_id),'objective':'What is the total revenue?','task_type':'descriptive',
            'datasets':[{'dataset_id':dataset_id,'version':1}],
            'metrics':[{'column':'revenue','aggregation':'sum','missing':'reject','definition_ref':'setup_revenue@1'}],
            'dimensions':[],'grain':'one synthetic source record','filters':[],'date_range':None,'timezone':'UTC',
            'units':'fixture units','currency':None,'output':'table','definition_refs':['setup_revenue@1'],
            'assumptions':['Synthetic fixture only'],'ambiguity':[],'success_criteria':['Independent total 2100']}
        queued = client.post("/api/v1/orchestrator/runs", json={"query": "What is the total revenue?", "dataset_id": dataset_id,
                             "workspace_id": str(workspace_id), "task_spec":task_spec, "idempotency_key": f"setup-{uuid4().hex}"})
        assert queued.status_code == 201, f"Queue returned {queued.status_code}"
        worker_run = queued.json()["id"]
        deadline = time.monotonic() + 90
        while True:
            executed = client.get(f"/api/v1/orchestrator/runs/{worker_run}").json()
            if executed["status"] in ("COMPLETED", "FAILED", "BLOCKED", "CANCELLED"):
                break
            if time.monotonic() > deadline:
                raise SystemExit("Durable analysis worker did not complete within 90 seconds")
            time.sleep(1)
        assert executed["status"] == "COMPLETED", f'Durable worker ended in {executed["status"]}'
        assert all(stage["status"] == "COMPLETED" for stage in executed["stages"])
        chat = client.post("/api/v1/chat", json={"message": "What is the total revenue?", "dataset_id": dataset_id, "workspace_id": str(workspace_id)})
        assert chat.status_code == 200, f"Analysis returned {chat.status_code}"
        analysis = chat.json()
        report = client.post("/api/v1/reports/from-analysis", json={"run_id": analysis["run_id"], "session_id": analysis["session_id"], "title": "Synthetic setup revenue report", "format_type": "pdf", "report_type": "Executive Report"})
        assert report.status_code == 201, f"Report returned {report.status_code}"
        report_id = report.json()["id"]
        download = client.get(f"/api/v1/reports/{report_id}/download")
        assert download.status_code == 200 and len(download.content) > 1000
        pdf = PdfReader(BytesIO(download.content))
        assert pdf.pages and "2,100" in "".join(page.extract_text() or "" for page in pdf.pages).replace("2100", "2,100")
        Path("/verification/setup-report.pdf").write_bytes(download.content)
        state_file.write_text(json.dumps({"user_id": str(user_id), "workspace_id": str(workspace_id), "dataset_id": dataset_id, "report_id": report_id}))
        print(json.dumps({"local_login": "PASS", "unauthorized_access": "denied", "upload": "PASS", "chart_total": 2100,
                          "deterministic_analysis": "PASS", "durable_worker_seven_stages": "PASS", "pdf_bytes": len(download.content), "pdf_pages": len(pdf.pages),
                          "provider_call": "not attempted", "supabase_browser_login": "not tested"}, indent=2))


if __name__ == "__main__":
    main()
