"""Real database/API/child-process journeys with two isolated tenants."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from backend.tests.test_verified_learning_integration import environment, identity
from backend.app.dataplane.config import Limits
from backend.app.dataplane.worker import process_one
from backend.app.dataplane.records import artifacts, scoped, get_record
from backend.app.dataplane.service import publish
from backend.app.models.background_job import DurableJob
from backend.jobs.persistence import PersistentJobStore, LostLeaseError


@pytest.fixture
def case(environment, tmp_path, monkeypatch):
    monkeypatch.setenv("DATAPLANE_ENABLED", "true")
    monkeypatch.setenv("DATAPLANE_ROOT", str(tmp_path))
    monkeypatch.setenv("DATAPLANE_CREDENTIAL_KEY_FILE", str(tmp_path/"credential.key"))
    # Test-process RSS already includes all backend/library overhead; allow
    # the supervisor to observe a larger working set so synthetic child jobs
    # are not rejected purely because the shared parent baseline is counted.
    monkeypatch.setenv("DATAPLANE_WORKER_MEMORY_MB", "4096")
    account, outsider = identity(environment), identity(environment)
    return environment, account, outsider, tmp_path


def call(case, method, path, body=None, expected=200, actor=None):
    env, owner, *_ = case
    account = actor or owner
    response = env["client"].request(method, "/api/v1/dataplane/"+path,
        params={"workspace_id": str(account["workspace"])}, json=body, headers=account["headers"])
    assert response.status_code == expected, response.text
    return response


def uploaded(case):
    env, owner, *_ = case
    response = env["client"].post("/api/v1/dataplane/upload",
        data={"workspace_id": str(owner["workspace"]), "idempotency_key": str(uuid4())},
        files={"file": ("synthetic.csv", b"region,amount,label\na,10, first \na,10,duplicate\nb,, third \nb,4,fourth\n", "text/csv")},
        headers=owner["headers"])
    assert response.status_code == 202, response.text
    return response.json()


def finish(case, job):
    env = case[0]
    for _ in range(20):
        process_one(env["worker"], Limits(), "dataplane-test-worker")
        status = call(case, "GET", "jobs/"+job["id"]).json()
        if status["status"] in ("READY", "FAILED", "CANCELLED"):
            assert status["status"] == "READY", status
            return call(case, "GET", "artifacts/"+status["result"]["artifact_id"]).json()
    raise AssertionError("Job did not complete")


def test_full_upload_query_quality_approval_and_export(case):
    snapshot = finish(case, uploaded(case))
    assert snapshot["payload"]["row_count"] == 4
    metric = call(case, "POST", "metrics", {"dataset_id": snapshot["dataset_id"], "snapshot_id": snapshot["id"],
        "definition": {"name": "source_amount", "column": "amount", "aggregation": "sum",
                       "description": "Sum of the numeric source amount, excluding nulls"}}, 201).json()
    request = {"snapshot_id": snapshot["id"], "metric_id": metric["id"],
               "plan": {"metric": "source_amount", "dimensions": ["region"]}, "idempotency_key": str(uuid4())}
    job = call(case, "POST", "query", request, 202).json()
    assert call(case, "POST", "query", request, 202).json()["id"] == job["id"]
    evidence = finish(case, job)
    assert evidence["payload"]["rows"] == [{"region": "a", "value": 20}, {"region": "b", "value": 4}]
    report = call(case, "GET", "evidence/"+evidence["id"]+"/report")
    assert report.content.startswith(b"%PDF") and report.headers["cache-control"] == "private, no-store"
    quality = finish(case, call(case, "POST", "snapshots/"+snapshot["id"]+"/quality", {}, 202).json())
    assert quality["payload"]["volume"]["status"] == "insufficient_history"
    proposal = finish(case, call(case, "POST", "snapshots/"+snapshot["id"]+"/cleaning",
        {"plan": {"operation": "drop_nulls", "columns": ["amount"], "reason": "Remove missing amount in a new snapshot"}}, 202).json())
    assert proposal["payload"]["sample"] == {"before": 4, "after": 3, "removed": 1,
                                             "selection": "first 1000 rows; not a population estimate"}
    cleaned = finish(case, call(case, "POST", "proposals/"+proposal["id"]+"/approve", {}, 202).json())
    assert cleaned["payload"]["reconciliation"] == {"before": 4, "after": 3, "quarantined": 1}
    assert call(case, "GET", "artifacts/"+snapshot["id"]).json()["payload"]["row_count"] == 4
    outsider = case[2]
    for path in ("artifacts/"+snapshot["id"], "jobs/"+job["id"], "evidence/"+evidence["id"]+"/report"):
        call(case, "GET", path, expected=404, actor=outsider)
    assert call(case, "GET", "dashboard", actor=outsider).json()["records"] == []


def test_cancelled_job_never_executes_and_flag_off(case, monkeypatch):
    job = uploaded(case)
    call(case, "POST", "jobs/"+job["id"]+"/cancel", {})
    process_one(case[0]["worker"], Limits(), "cancel-check")
    assert call(case, "GET", "jobs/"+job["id"]).json()["status"] == "CANCELLED"
    monkeypatch.setenv("DATAPLANE_ENABLED", "false")
    call(case, "GET", "dashboard", expected=503)


def test_database_rls_and_lost_publication_lease(case):
    snapshot = finish(case, uploaded(case))
    env, owner, outsider, _ = case
    with env["api"]() as db:
        scoped(db, outsider["user"], outsider["workspace"])
        assert db.execute(select(artifacts).where(artifacts.c.id == UUID(snapshot["id"]))).first() is None
    job = call(case, "POST", "snapshots/"+snapshot["id"]+"/quality", {}, 202).json()
    store = PersistentJobStore(env["worker"])
    claim = store.claim("stale-worker", ("dp_quality",))
    assert claim is not None
    store.cancel(claim["id"])
    with env["worker"]() as db, db.begin(), pytest.raises(LostLeaseError):
        publish(db, claim, {"not": "published"}, UUID(snapshot["id"]))
    assert call(case, "GET", "jobs/"+job["id"]).json()["status"] == "CANCELLED"


def test_cross_snapshot_metric_and_approval_denied(case):
    first = finish(case, uploaded(case))
    second = finish(case, uploaded(case))
    metric = call(case, "POST", "metrics", {"dataset_id": first["dataset_id"], "snapshot_id": first["id"],
        "definition": {"name": "n", "aggregation": "count", "description": "Source rows"}}, 201).json()
    call(case, "POST", "query", {"snapshot_id": second["id"], "metric_id": metric["id"],
        "plan": {"metric": "n"}, "idempotency_key": "mismatch"}, 422)
    call(case, "POST", "proposals/"+first["id"]+"/approve", {}, 404)


def test_connector_secret_redaction_and_viewer_denial(case, monkeypatch):
    monkeypatch.setenv("DATAPLANE_POSTGRES_HOSTS", "company.example")
    response = call(case, "POST", "connectors", {
        "name": "Company", "host": "company.example", "database": "sales", "username": "reader",
        "password": "never-return-this-secret", "table": "orders"}, 201).json()
    value = call(case, "GET", "artifacts/"+response["id"]).text
    assert "encrypted" not in value and "never-return-this-secret" not in value
    assert response["dataset_id"]
    viewer = identity(case[0], role="viewer")
    call(case, "POST", "connectors", {"name": "Company", "host": "company.example",
        "database": "sales", "username": "reader", "password": "test", "table": "orders"},
         403, actor=viewer)


def test_chat_routes_registered_sum_and_returns_evidence(case):
    snapshot = finish(case, uploaded(case))
    call(case, "POST", "metrics", {"dataset_id": snapshot["dataset_id"], "snapshot_id": snapshot["id"],
        "definition": {"name": "amount_total", "column": "amount", "aggregation": "sum",
                       "description": "Sum of source amount"}}, 201)
    from backend.app.dataplane.chat import route
    from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
    env, account, *_ = case
    with env["api"]() as db:
        result = route(db, account["user"], account["workspace"], snapshot["dataset_id"], 1,
                       "sum amount by region", NaturalLanguageAnalyticsService())
    assert result["status"] == "queued"
    finish(case, {"id": result["plan"]["job_id"]})
    with env["api"]() as db:
        result = route(db, account["user"], account["workspace"], snapshot["dataset_id"], 1,
                       "sum amount by region", NaturalLanguageAnalyticsService())
    assert result["status"] == "complete"
    assert result["data"] == [{"region": "a", "value": 20}, {"region": "b", "value": 4}]
    assert result["citations"][0]["evidence_id"]

