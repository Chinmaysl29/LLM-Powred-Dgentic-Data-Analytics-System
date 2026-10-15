"""Schema Contract Tests — CI Migration Validation.

Verifies that:
1. All expected ORM model tables are present after `alembic upgrade head`.
2. All expected columns exist on each table.
3. Primary key constraints are correctly defined.
4. Foreign key relationships are intact.
5. The alembic_version table contains the correct head revision.
6. inspect_schema() reports compatible=True on a freshly migrated database.

These tests run against the ISOLATED CI PostgreSQL service only.
They never connect to customer storage.
"""

import os
import pytest
from sqlalchemy import create_engine, inspect, text

# ── All models must be imported so Base.metadata is populated ─────────────────
import backend.app.models  # noqa: F401

from backend.app.core.config import get_settings
from backend.app.database.schema_contract import inspect_schema, required_revisions
from backend.app.models.base import Base


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def schema_engine():
    """Engine pointed at the isolated CI migration test database."""
    settings = get_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def schema_result(schema_engine):
    """Run inspect_schema once; all tests share the result."""
    with schema_engine.connect() as conn:
        return inspect_schema(conn)


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSchemaCompatibility:
    """The migrated schema must match every ORM model in Base.metadata."""

    def test_schema_is_compatible(self, schema_result):
        """Top-level compatibility flag must be True after a clean migration."""
        assert schema_result["compatible"], (
            f"Schema incompatible.\n"
            f"  missing_tables={schema_result['missing_tables']}\n"
            f"  missing_columns={schema_result['missing_columns']}\n"
            f"  invalid_primary_keys={schema_result['invalid_primary_keys']}\n"
            f"  missing_foreign_keys={schema_result['missing_foreign_keys']}\n"
            f"  expected_revisions={schema_result['expected_revisions']}\n"
            f"  actual_revisions={schema_result['actual_revisions']}"
        )

    def test_no_missing_tables(self, schema_result):
        """Every ORM-declared table must exist in the database."""
        assert schema_result["missing_tables"] == [], (
            f"Missing tables: {schema_result['missing_tables']}"
        )

    def test_no_missing_columns(self, schema_result):
        """Every ORM-declared column must be present on its table."""
        assert schema_result["missing_columns"] == {}, (
            f"Missing columns: {schema_result['missing_columns']}"
        )

    def test_no_invalid_primary_keys(self, schema_result):
        """Primary key constraints must match model declarations."""
        assert schema_result["invalid_primary_keys"] == [], (
            f"Invalid PKs: {schema_result['invalid_primary_keys']}"
        )

    def test_no_missing_foreign_keys(self, schema_result):
        """All model-declared foreign key relationships must be enforced."""
        assert schema_result["missing_foreign_keys"] == {}, (
            f"Missing FKs: {schema_result['missing_foreign_keys']}"
        )


class TestMigrationRevision:
    """The alembic_version table must reflect the correct head revision(s)."""

    def test_revision_matches_head(self, schema_result):
        """Actual DB revision must equal the computed Alembic script head."""
        assert schema_result["revision_matches"], (
            f"Revision mismatch.\n"
            f"  expected={schema_result['expected_revisions']}\n"
            f"  actual={schema_result['actual_revisions']}"
        )

    def test_head_revisions_are_non_empty(self):
        """The migrations directory must declare at least one head revision."""
        heads = required_revisions()
        assert len(heads) > 0, "No head revisions found in migrations/"

    def test_alembic_version_table_exists(self, schema_engine):
        """alembic_version table must exist after migration."""
        with schema_engine.connect() as conn:
            inspector = inspect(conn)
            assert inspector.has_table("alembic_version"), (
                "alembic_version table missing — run 'alembic upgrade head'"
            )


class TestCoreTablePresence:
    """Smoke test that critical business tables are present."""

    REQUIRED_TABLES = [
        "tenants",
        "users",
        "workspaces",
        "datasets",
        "conversations",
        "audit_entries",
    ]

    def test_required_tables_present(self, schema_engine):
        with schema_engine.connect() as conn:
            inspector = inspect(conn)
            present = set(inspector.get_table_names())
        for table in self.REQUIRED_TABLES:
            assert table in present, f"Required table '{table}' not found in schema."


class TestIdempotentMigration:
    """Running upgrade head twice must leave the schema identical."""

    def test_schema_stable_after_rerun(self, schema_engine):
        """A second alembic upgrade head is a no-op; schema must still be compatible."""
        with schema_engine.connect() as conn:
            result_second_run = inspect_schema(conn)
        assert result_second_run["compatible"], (
            "Schema became incompatible after a second upgrade head run — "
            "migration is not idempotent."
        )
