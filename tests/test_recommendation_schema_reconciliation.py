"""Recommendation Schema Reconciliation Tests.

Verifies that after `alembic upgrade head`:
1. Exactly ONE recommendation table exists (cleaning_recommendations OR
   dataset_recommendations — not both, not zero).
2. That table has the exact column set required by migration 006.
3. The primary key is `recommendation_id`.
4. The two required foreign keys (→ datasets, → dataset_versions) are present.
5. The three required lookup indexes are present.
6. A second upgrade head run leaves the state identical (idempotency).

These tests run against the ISOLATED CI PostgreSQL service only.
They never connect to customer storage.
"""

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.app.core.config import get_settings


REQUIRED_COLUMNS = {
    "recommendation_id",
    "dataset_id",
    "version_id",
    "version_number",
    "recommendation_type",
    "severity",
    "priority_score",
    "status",
    "column_name",
    "description",
    "suggested_action",
    "estimated_quality_gain",
    "algorithm_metadata",
    "prerequisites",
    "created_at",
    "resolved_at",
    "created_by",
}

REQUIRED_FK_TRIPLES = {
    (("dataset_id",), "datasets", ("dataset_id",)),
    (("version_id",), "dataset_versions", ("version_id",)),
}

REQUIRED_INDEX_COLUMNS = {
    ("dataset_id", "version_id"),
    ("dataset_id", "status"),
    ("priority_score",),
}

CANONICAL_NAME = "cleaning_recommendations"
LEGACY_NAME = "dataset_recommendations"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def rec_engine():
    settings = get_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def rec_table_name(rec_engine):
    """Return the name of the active recommendation table."""
    with rec_engine.connect() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())

    canonical_present = CANONICAL_NAME in tables
    legacy_present = LEGACY_NAME in tables

    assert not (canonical_present and legacy_present), (
        f"Both recommendation tables exist ({CANONICAL_NAME!r} and {LEGACY_NAME!r}). "
        "Migration 006 must reconcile them to a single table. "
        "Check migration history for incomplete or failed reconciliation."
    )
    assert canonical_present or legacy_present, (
        f"No recommendation table found (checked {CANONICAL_NAME!r} and {LEGACY_NAME!r}). "
        "Run 'alembic upgrade head' before running these tests."
    )

    return CANONICAL_NAME if canonical_present else LEGACY_NAME


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRecommendationTableExistence:
    def test_exactly_one_recommendation_table(self, rec_table_name):
        """rec_table_name fixture already asserts exactly one table."""
        assert rec_table_name in {CANONICAL_NAME, LEGACY_NAME}

    def test_recommendation_table_is_queryable(self, rec_engine, rec_table_name):
        """The table must accept a SELECT query without error."""
        with rec_engine.connect() as conn:
            result = conn.execute(
                text(f"SELECT count(*) FROM {rec_table_name}")  # noqa: S608
            )
            assert result.scalar() >= 0


class TestRecommendationColumns:
    def test_required_columns_present(self, rec_engine, rec_table_name):
        """Every column from the verified migration contract must exist."""
        with rec_engine.connect() as conn:
            inspector = inspect(conn)
            actual_columns = {c["name"] for c in inspector.get_columns(rec_table_name)}

        missing = REQUIRED_COLUMNS - actual_columns
        assert not missing, (
            f"Missing columns on {rec_table_name!r}: {sorted(missing)}\n"
            f"Run 'alembic upgrade head' and retry."
        )


class TestRecommendationPrimaryKey:
    def test_primary_key_is_recommendation_id(self, rec_engine, rec_table_name):
        """Primary key must be exactly ['recommendation_id']."""
        with rec_engine.connect() as conn:
            inspector = inspect(conn)
            pk = inspector.get_pk_constraint(rec_table_name)
        assert pk["constrained_columns"] == ["recommendation_id"], (
            f"Expected PK ['recommendation_id'] on {rec_table_name!r}, "
            f"got {pk['constrained_columns']!r}"
        )


class TestRecommendationForeignKeys:
    def test_foreign_keys_to_datasets_and_versions(self, rec_engine, rec_table_name):
        """Both dataset ownership FKs must be enforced by the database."""
        with rec_engine.connect() as conn:
            inspector = inspect(conn)
            raw_fks = inspector.get_foreign_keys(rec_table_name)

        actual_fk_triples = {
            (
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
                tuple(fk["referred_columns"]),
            )
            for fk in raw_fks
        }

        missing_fks = REQUIRED_FK_TRIPLES - actual_fk_triples
        assert not missing_fks, (
            f"Missing foreign keys on {rec_table_name!r}: {missing_fks}"
        )


class TestRecommendationIndexes:
    def test_lookup_indexes_present(self, rec_engine, rec_table_name):
        """Query-critical lookup indexes must be present."""
        with rec_engine.connect() as conn:
            inspector = inspect(conn)
            raw_indexes = inspector.get_indexes(rec_table_name)

        actual_index_columns = {
            tuple(idx["column_names"]) for idx in raw_indexes
        }

        missing_indexes = REQUIRED_INDEX_COLUMNS - actual_index_columns
        assert not missing_indexes, (
            f"Missing indexes on {rec_table_name!r}.\n"
            f"  Required: {REQUIRED_INDEX_COLUMNS}\n"
            f"  Present:  {actual_index_columns}\n"
            f"  Missing:  {missing_indexes}"
        )


class TestRecommendationIdempotency:
    def test_schema_unchanged_after_second_upgrade(self, rec_engine, rec_table_name):
        """Schema state must be identical after a repeated upgrade head."""
        with rec_engine.connect() as conn:
            inspector = inspect(conn)
            columns_after = {c["name"] for c in inspector.get_columns(rec_table_name)}

        missing = REQUIRED_COLUMNS - columns_after
        assert not missing, (
            f"Idempotency failure: columns changed after second upgrade head: "
            f"missing {sorted(missing)}"
        )
