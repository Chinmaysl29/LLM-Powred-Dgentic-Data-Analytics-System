"""Resource, parity, immutable storage and SQL-denial regressions."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import pytest
import pandas as pd
from backend.app.dataplane.config import Limits
from backend.app.dataplane.contracts import Metric, QueryPlan, Filter, CleaningPlan, SparkEngine
from backend.app.dataplane.ingestion import materialize
from backend.app.dataplane.engine import DuckDBEngine
from backend.app.dataplane.semantic import compile_plan
from backend.app.dataplane.validator import validate
from backend.app.dataplane.storage import digest, confined
from backend.app.dataplane.quality import volume_baseline, profile
from backend.app.dataplane.cleaning import propose, apply_cleaning
from backend.app.dataplane.postgres import encrypt, decrypt, validate_destination
from backend.app.dataplane import supervisor


@pytest.fixture
def engine(tmp_path):
    source = tmp_path/"source.csv"
    source.write_text("region,amount,label\na,10, alpha \na,-2,alpha\nb,3,beta\nb,,beta\n,7,missing\n")
    limits = Limits(enabled=True, memory_mb=64, worker_memory_mb=256)
    manifest = materialize(source, tmp_path/"snapshot", tmp_path, limits, version_id="v1")
    result = DuckDBEngine(tmp_path, manifest, tmp_path/"spill", limits)
    yield result, tmp_path, source, limits
    result.close()


@pytest.mark.parametrize("aggregation", ["sum", "avg", "min", "max", "count"])
@pytest.mark.parametrize("dimensions", [[], ["region"]])
def test_aggregates_match_pandas(engine, aggregation, dimensions):
    e, _, source, _ = engine
    metric = Metric(name="amount_metric", aggregation=aggregation, column="amount", description="Source amount")
    sql, parameters = compile_plan(QueryPlan(metric=metric.name, dimensions=dimensions), metric, e.schema())
    actual = e.execute(sql, parameters)["rows"]
    df = pd.read_csv(source)
    grouped = df.groupby("region", dropna=False)["amount"] if dimensions else df["amount"]
    result = getattr(grouped, "mean" if aggregation == "avg" else aggregation)()
    if dimensions:
        expected = {None if pd.isna(k) else k: None if pd.isna(v) else v for k,v in result.items()}
        assert {r["region"]: r["value"] for r in actual} == expected
    else:
        assert actual[0]["value"] == result


@pytest.mark.parametrize("sql", [
    "SELECT * FROM source LIMIT 10",
    "SELECT SUM(amount) FROM source; SELECT 1",
    "DELETE FROM source",
    "SELECT SUM(amount) FROM other LIMIT 10",
    "SELECT SUM(amount) FROM main.source LIMIT 10",
    "SELECT SUM(amount) FROM read_csv('/etc/passwd') LIMIT 10",
    "SELECT SUM(amount), read_text('/etc/passwd') FROM source LIMIT 10",
    "SELECT STRING_AGG(label, ',') FROM source LIMIT 10",
    "SELECT SUM(amount) FROM source UNION SELECT 1",
    "WITH x AS (SELECT * FROM source) SELECT SUM(amount) FROM x LIMIT 10",
    "SELECT SUM(amount) OVER () FROM source LIMIT 10",
    "SELECT SUM(amount), label FROM source LIMIT 10",
    "SELECT COUNT(*) FROM source JOIN source x ON true LIMIT 10",
    "SELECT SUM(amount) FROM source LIMIT 99999",
    "SELECT SUM(amount) FROM source",
    "COPY source TO '/tmp/leak'",
    "PRAGMA version",
    "SELECT SUM(secret) FROM source LIMIT 1",
])
def test_ast_denials(engine, sql):
    with pytest.raises((ValueError, Exception)):
        validate(sql, engine[0].schema(), 100)


def test_bound_parameters_and_caps(engine):
    e, _, _, limits = engine
    metric = Metric(name="amount_metric", column="amount", description="Source amount")
    plan = QueryPlan(metric=metric.name, filters=[Filter(column="label", operator="eq", value="x' OR 1=1 --")])
    sql, params = compile_plan(plan, metric, e.schema())
    assert "OR 1=1" not in sql
    assert e.execute(sql, params)["rows"] == [{"value": None}]
    e.limits = limits.model_copy(update={"result_rows": 1})
    sql, args = compile_plan(QueryPlan(metric=metric.name, dimensions=["region"], limit=1), metric, e.schema())
    with pytest.raises(ValueError, match="row budget"):
        e.execute(sql, args)


def test_raw_checksums_tampering_and_paths(engine):
    e, root, source, limits = engine
    before = digest(source)
    assert e.manifest["original"]["sha256"] == before
    with pytest.raises(ValueError):
        confined(root, "../outside")
    link = root/"linked"
    link.symlink_to(source)
    with pytest.raises(ValueError):
        confined(root, "linked")
    path = root/e.manifest["files"][0]["path"]
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        DuckDBEngine(root, e.manifest, root/"other-spill", limits)
    assert digest(source) == before


def test_engine_disables_external_reads(engine):
    with pytest.raises(Exception):
        engine[0].connection.execute("SELECT * FROM read_csv('/etc/passwd')").fetchall()
    with pytest.raises(Exception):
        engine[0].connection.execute("SET enable_external_access=true")


@pytest.mark.parametrize("operation,column", [("drop_nulls","amount"), ("deduplicate","region"), ("trim","label")])
def test_cleaning_sample_reconciliation_preserves_raw(engine, operation, column):
    e, root, source, _ = engine
    before = digest(source)
    plan = CleaningPlan(operation=operation, columns=[column], reason="Synthetic correction")
    proposal = propose(e, plan)
    assert proposal["requires_approval"] and proposal["snapshot_hash"] == e.manifest["snapshot_hash"]
    result = apply_cleaning(e, plan, root/"cleaned", root)
    counts = result["reconciliation"]
    assert counts["before"] == counts["after"] + counts["quarantined"]
    assert result["parent_hash"] == e.manifest["snapshot_hash"]
    assert digest(source) == before


def test_quality_and_robust_baseline(engine):
    e = engine[0]
    now = datetime.now(timezone.utc)
    value = profile(e, [], now.isoformat())
    assert value["row_count"] == 5
    assert value["volume"]["status"] == "insufficient_history"
    history = [{"as_of": (now-timedelta(weeks=i)).isoformat(), "row_count": 100} for i in range(1,9)]
    assert volume_baseline(10, history, now)["status"] == "warn"
    assert volume_baseline(100, history, now)["zero_mad"]
    assert volume_baseline(100, history+history, now)["observations"] == 8


def test_credentials_and_destination_policy(tmp_path):
    limits = Limits(postgres_hosts="company.example", credential_key_file=tmp_path/"secret.key")
    config = dict(host="company.example", password="never-log-this", username="reader", database="company", sslmode="verify-full")
    encrypted = encrypt(config, limits)
    assert config["password"] not in encrypted
    assert decrypt(encrypted, limits) == config
    with pytest.raises(ValueError):
        encrypt({**config, "host": "localhost"}, limits)
    with pytest.raises(ValueError):
        encrypt({**config, "sslmode": "disable"}, limits)


def test_real_child_timeout_and_lost_lease(tmp_path, monkeypatch):
    original = subprocess.Popen
    children = []
    def sleeping(*args, **kwargs):
        child = original([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(supervisor.subprocess, "Popen", sleeping)
    request = {"limits": {"result_bytes": 1024}}
    with pytest.raises(TimeoutError):
        supervisor.execute(request, tmp_path/"one", lambda: None, timeout_s=1)
    assert children[-1].poll() is not None
    def lost():
        raise RuntimeError("Lease lost")
    with pytest.raises(RuntimeError):
        supervisor.execute(request, tmp_path/"two", lost, timeout_s=30)
    assert children[-1].poll() is not None
    assert not (tmp_path/"two/request.json").exists()


def test_disabled_default_memory_policy_and_spark_contract(monkeypatch):
    monkeypatch.delenv("DATAPLANE_ENABLED", raising=False)
    assert Limits().enabled is False
    with pytest.raises(ValueError):
        Limits(memory_mb=1024, worker_memory_mb=1024)
    with pytest.raises(NotImplementedError):
        SparkEngine().execute("SELECT 1", [])


def test_checkpoint_resume_reuses_verified_parts(tmp_path):
    import json
    source = tmp_path/"input.csv"
    source.write_text("id,amount\n1,10\n2,20\n")
    limits = Limits()
    first = materialize(source, tmp_path/"one", tmp_path, limits, version_id="v1")
    checkpoint = json.loads((tmp_path/"one/checkpoint-000000.json").read_text())
    resumed = materialize(source, tmp_path/"two", tmp_path, limits, version_id="v1", resume=checkpoint)
    assert resumed["files"] == first["files"]
    assert resumed["row_count"] == 2
    with pytest.raises(ValueError, match="Checkpoint source"):
        materialize(source, tmp_path/"bad", tmp_path, limits, version_id="v2", resume=checkpoint)


@pytest.mark.asyncio
async def test_upload_budget_before_multipart(monkeypatch):
    from backend.app.dataplane.middleware import UploadBudgetMiddleware
    monkeypatch.setenv("DATAPLANE_ENABLED", "true")
    monkeypatch.setenv("DATAPLANE_UPLOAD_MB", "1")
    called, sent = [], []
    async def app(scope, receive, send):
        called.append(True)
        while (await receive()).get("more_body"):
            pass
    async def receive():
        return {"type": "http.request", "body": b"x" * (3*1024**2), "more_body": False}
    async def send(message):
        sent.append(message)
    scope = {"type": "http", "path": "/api/v1/dataplane/upload", "headers": []}
    await UploadBudgetMiddleware(app)(scope, receive, send)
    assert sent[0]["status"] == 413
    called.clear(); sent.clear()
    scope["headers"] = [(b"content-length", b"99999999")]
    await UploadBudgetMiddleware(app)(scope, receive, send)
    assert sent[0]["status"] == 413 and not called


def test_identifier_and_numeric_validation(engine):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Filter(column="amount", operator="eq", value=float("nan"))
    with pytest.raises(ValidationError):
        Filter(column="amount", operator="eq", value="x"*1001)
    with pytest.raises(ValueError):
        compile_plan(QueryPlan(metric="m", dimensions=["value"]),
                     Metric(name="m", column="amount", description="Test"),
                     {"value": "VARCHAR", "amount": "INTEGER"})


def test_xlsx_native_numbers_and_text_identifiers(tmp_path):
    from openpyxl import Workbook
    import pyarrow.parquet as pq
    book = Workbook()
    book.active.append(["account", "amount"])
    book.active.append(["001", 10.25])
    book.active.append(["002", 2.75])
    source = tmp_path/"typed.xlsx"
    book.save(source)
    before = digest(source)
    result = materialize(source, tmp_path/"xlsx", tmp_path, Limits(), version_id="v")
    table = pq.read_table(tmp_path/result["files"][0]["path"])
    assert table.to_pydict() == {"account": ["001", "002"], "amount": [10.25, 2.75]}
    assert digest(source) == before


def test_csv_identifiers_and_empty_cleaned_snapshot(tmp_path):
    import pyarrow.parquet as pq
    source = tmp_path/"ids.csv"
    source.write_text("account_id,amount\n001,\n002,\n")
    limits = Limits()
    manifest = materialize(source, tmp_path/"csv", tmp_path, limits, version_id="v")
    assert pq.read_table(tmp_path/manifest["files"][0]["path"])["account_id"].to_pylist() == ["001", "002"]
    engine = DuckDBEngine(tmp_path, manifest, tmp_path/"spill", limits)
    try:
        result = apply_cleaning(engine, CleaningPlan(operation="drop_nulls", columns=["amount"], reason="Test empty version"), tmp_path/"clean", tmp_path)
        assert result["row_count"] == 0 and result["reconciliation"]["quarantined"] == 2
        assert pq.read_metadata(tmp_path/result["files"][0]["path"]).num_rows == 0
    finally:
        engine.close()


