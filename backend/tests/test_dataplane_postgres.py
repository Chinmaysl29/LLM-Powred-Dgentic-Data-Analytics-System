"""Actual TLS/read-only pushdown against an explicitly configured local test fixture."""
import os
from uuid import uuid4
import pytest
from sqlalchemy import text
from backend.tests.test_verified_learning_integration import environment
from backend.app.dataplane.config import Limits
from backend.app.dataplane.postgres import PostgresEngine
from backend.app.dataplane.contracts import Metric, QueryPlan, Filter
from backend.app.dataplane.semantic import compile_plan


def test_postgres_verified_tls_pushdown_and_privilege_denial(environment):
    certificate = os.environ.get("DATAPLANE_TEST_CA")
    if not certificate:
        pytest.skip("Set DATAPLANE_TEST_CA after starting the isolated TLS fixture")
    role, table = "dp_reader_"+uuid4().hex[:12], "dp_company_"+uuid4().hex[:12]
    with environment["admin"]() as db, db.begin():
        db.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD 'synthetic-fixture-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"))
        db.execute(text(f"CREATE TABLE public.{table} (region text, amount numeric(12,2))"))
        db.execute(text(f"INSERT INTO public.{table} VALUES ('east',10.25),('east',-2.00),('west',4.50)"))
        db.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        db.execute(text(f"GRANT SELECT ON public.{table} TO {role}"))
    limits = Limits(postgres_hosts="postgres", postgres_ca_file=certificate)
    config = dict(host="postgres", port=5432, database="analyst_setup_test", username=role,
                  password="synthetic-fixture-only", schema_name="public", table=table, sslmode="verify-full")
    engine = PostgresEngine(config, limits)
    try:
        assert engine.connection.execute("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()").fetchone()[0]
        assert engine.connection.execute("SHOW transaction_read_only").fetchone()[0] == "on"
        metric = Metric(name="amount", column="amount", description="Fixture amount")
        plan = QueryPlan(metric="amount", dimensions=["region"], filters=[Filter(column="region", operator="eq", value="east")])
        sql, parameters = compile_plan(plan, metric, engine.schema())
        result = engine.execute(sql, parameters)
        assert result["rows"] == [{"region": "east", "value": "8.25"}]
        assert result["transaction_snapshot"]
    finally:
        engine.close()
    with environment["admin"]() as db, db.begin():
        db.execute(text(f"GRANT INSERT ON public.{table} TO {role}"))
    with pytest.raises(ValueError, match="SELECT-only"):
        PostgresEngine(config, limits)

