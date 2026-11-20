"""Reflection boundary and HTTP regressions. PostgreSQL DDL is test-database only."""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError, TimeoutError

from backend.app.api.v1.routes import schema_reader as routes
from backend.app.core.exceptions import DatabaseConnectionError
from backend.app.repositories.index_metadata import normalize_index
from backend.app.repositories.schema_repository import SchemaRepository
from backend.app.schemas.schema_reader import DatabaseMetadata, DatabaseSchema, IndexKey, IndexMetadata
from backend.app.services.schema_reader_service import SchemaReaderService, get_schema_reader_service


@pytest.mark.parametrize("names,expressions,kinds", [
    (["id"], None, ["column"]),
    (["tenant_id", "email"], None, ["column", "column"]),
    ([None], ["lower(email)"], ["expression"]),
    (["tenant_id", None], ["tenant_id", "lower(email)"], ["column", "expression"]),
    ([None], ["((payload ->> 'revision')::integer)"], ["expression"]),
    (["Mixed Case", None], ['"Mixed Case"', 'lower("Email")'], ["column", "expression"]),
    (["id", None], None, ["column", "unknown"]),
    (["id", 42], ["id", "lower(email)"], ["column", "unknown"]),
])
def test_ordered_index_keys(names, expressions, kinds):
    result = normalize_index({"name": "lookup", "column_names": names, "expressions": expressions, "unique": True})
    assert [key.kind for key in result.keys] == kinds
    assert [key.position for key in result.keys] == list(range(len(names)))
    assert result.columns == [name for name in names if isinstance(name, str)]
    for key in result.keys:
        if key.kind == "expression":
            assert key.expression == expressions[key.position]
    assert result.unique and result.name == "lookup"
    assert IndexMetadata.model_validate_json(result.model_dump_json()) == result
    assert bool(result.warnings) == ("unknown" in kinds)


def test_options_partial_include_sorting_and_legacy_contract():
    result = normalize_index({
        "name": "lookup", "column_names": ["tenant", None],
        "expressions": ["tenant", "lower(email)"], "unique": True,
        "column_sorting": {"lower(email)": ("desc", "nulls_last")},
        "dialect_options": {"postgresql_include": ["payload"], "postgresql_where": "active = true", "postgresql_using": "btree", "postgresql_ops": {"tenant": "int4_ops"}},
        "duplicates_constraint": "uq_tenant",
    })
    data = json.loads(result.model_dump_json())
    assert data["columns"] == ["tenant"]
    assert data["keys"][1]["expression"] == "lower(email)"
    assert data["keys"][1]["sorting"] == ["desc", "nulls_last"]
    assert data["predicate"] == "active = true"
    assert data["include_columns"] == ["payload"]
    assert data["dialect_options"]["postgresql_ops"] == {"tenant": "int4_ops"}
    assert data["duplicates_constraint"] == "uq_tenant"
    assert not data["warnings"]
    assert IndexMetadata(name="legacy", columns=["id"]).keys == []


@pytest.mark.parametrize("raw", [
    {}, {"name": None, "column_names": None, "expressions": None, "unique": None},
    {"column_names": "bad"}, {"column_names": [None], "expressions": []},
    {"column_names": ["id", None], "expressions": ["id"]},
    {"column_names": ["id"], "dialect_options": {"unserializable": object()}},
    {"column_names": ["id"], "include_columns": [None]},
    {"column_names": ["id"], "column_sorting": {"id": ["invented"]}},
])
def test_incomplete_optional_metadata_is_explicit(raw):
    result = normalize_index(raw)
    assert result.warnings
    result.model_dump_json()
    assert "None" not in result.columns


def test_validation_remains_strict():
    with pytest.raises(ValidationError):
        IndexMetadata(columns=["id", None])
    with pytest.raises(ValidationError):
        IndexKey(position=0, kind="expression", column_name="id")
    with pytest.raises(ValidationError):
        normalize_index({"name": 123, "column_names": ["id"]})


def test_sqlite_empty_indexes_and_optional_comments():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("create table example (id integer primary key, email text unique)"))
        schema = SchemaRepository(connection).inspect_schema()
        assert schema.tables[0].indexes == []
        assert schema.tables[0].unique_constraints[0].columns == ["email"]
        assert schema.tables[0].columns[1].default is None
        schema.model_dump_json()
    engine.dispose()


def empty_schema():
    return DatabaseSchema(metadata=DatabaseMetadata(dialect="postgresql"))


def test_cache_refresh_reconnect_and_failure_recovery():
    repo = Mock()
    repo.inspect_schema.side_effect = [empty_schema(), DatabaseConnectionError("offline"), empty_schema()]
    service = SchemaReaderService(repo)
    assert not service.get_schema().metadata.is_cached
    assert service.get_schema().metadata.is_cached
    with pytest.raises(DatabaseConnectionError):
        service.get_schema(force_refresh=True)
    assert not service.get_schema(force_refresh=True).metadata.is_cached
    assert repo.inspect_schema.call_count == 3
    service.set_repository(Mock(inspect_schema=Mock(return_value=empty_schema())))
    assert not service.get_schema().metadata.is_cached
    with pytest.raises(DatabaseConnectionError):
        SchemaReaderService().get_schema()


@pytest.fixture
def api():
    app = FastAPI()
    app.include_router(routes.router)
    service = Mock()
    app.dependency_overrides[get_schema_reader_service] = lambda: service
    with TestClient(app) as client:
        yield client, service


@pytest.mark.parametrize("failure,status", [
    (ValueError("secret Pydantic internals"), 500),
    (DatabaseConnectionError("secret connection URL"), 503),
    (TimeoutError("secret timeout SQL"), 504),
    (OperationalError("secret SQL", {}, Exception("secret credential")), 503),
    (ProgrammingError("secret SQL", {}, SimpleNamespace(sqlstate="42501")), 403),
    (ProgrammingError("secret SQL", {}, SimpleNamespace(sqlstate="42601")), 500),
])
def test_classified_errors_and_retry(api, failure, status):
    client, service = api
    service.get_schema.side_effect = [failure, empty_schema()]
    response = client.get("/schema")
    assert response.status_code == status
    assert "secret" not in response.text
    assert "pydantic" not in response.text.lower()
    response = client.get("/schema?refresh=true")
    assert response.status_code == 200
    assert service.get_schema.call_args.kwargs["force_refresh"] is True


def test_other_schemas_denied_before_inspection(api):
    client, service = api
    for endpoint in ("", "/compact", "/tables/users", "/prompt-context"):
        assert client.get(f"/schema{endpoint}?schema_name=other_tenant").status_code == 403
    assert not service.mock_calls


def test_postgres_real_reflection():
    url = os.environ.get("WAREHOUSE_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not url or make_url(url).database != "analyst_setup_test" or make_url(url).username != "setup":
        pytest.skip("Requires the dedicated analyst_setup_test database with setup role")
    engine = create_engine(url)
    namespace = "warehouse_test_" + uuid4().hex
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            # Transactional DDL: all test-owned resources disappear on rollback.
            connection.execute(text(f'CREATE SCHEMA "{namespace}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{namespace}"'))
            connection.execute(text('CREATE TABLE parent (id integer PRIMARY KEY)'))
            connection.execute(text('CREATE TABLE sample (id integer PRIMARY KEY, tenant_id integer REFERENCES parent(id), "Email" text UNIQUE, payload jsonb, active boolean)'))
            for ddl in [
                'CREATE INDEX simple ON sample (tenant_id)',
                'CREATE INDEX composite ON sample (tenant_id, "Email")',
                'CREATE INDEX functional ON sample (lower("Email"))',
                'CREATE UNIQUE INDEX mixed ON sample (tenant_id, lower("Email") DESC NULLS LAST) INCLUDE (payload) WHERE active',
                "CREATE INDEX json_expression ON sample (((payload ->> 'revision')::integer))",
            ]:
                connection.execute(text(ddl))
            reflected = inspect(connection).get_indexes("sample", schema=namespace)
            raw = next(index for index in reflected if index["name"] == "mixed")
            assert raw["column_names"] == ["tenant_id", None]
            schema = SchemaRepository(connection).inspect_schema(schema_name=namespace)
            table = schema.get_table("sample")
            assert table.primary_keys == ["id"]
            assert table.foreign_keys[0].target_table == "parent"
            assert table.unique_constraints[0].columns == ["Email"]
            mixed = next(index for index in table.indexes if index.name == "mixed")
            assert mixed.columns == ["tenant_id"]
            assert mixed.keys[1].expression == 'lower("Email")'
            assert mixed.keys[1].sorting == ["desc", "nulls_last"]
            assert mixed.include_columns == ["payload"] and mixed.predicate == "active"
            assert mixed.unique and not mixed.warnings
            assert DatabaseSchema.model_validate_json(schema.model_dump_json()) == schema
        finally:
            transaction.rollback()
    engine.dispose()
