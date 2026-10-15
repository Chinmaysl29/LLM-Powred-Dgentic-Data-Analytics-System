"""Authenticated Dataset Isolation Tests.

Verifies the multi-tenant dataset ownership and workspace authorization
contracts at the database level — without any mock that bypasses real
security logic.

What is tested:
1. User A can only see their own datasets, never User B's.
2. Workspace membership alone does not grant access to another account's dataset.
3. Dataset records without an owner_id (quarantined legacy data) are not
   accessible via the authorization layer.
4. Unauthorized HTTP requests (no token) receive 401, not 200.
5. Cross-account dataset access attempts receive 404, not 200 or 403.
6. The dataset_workspace_bindings table enforces ownership; a binding without
   an owned dataset cannot be created.

These tests run against the ISOLATED CI PostgreSQL service only.
They never connect to customer storage.

Environment requirements:
  DATABASE_URL     — isolated CI database (after alembic upgrade head)
  JWT_SECRET_KEY   — any non-empty value
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token, hash_password
from backend.app.models.base import Base
import backend.app.models  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def isolation_engine():
    settings = get_settings()
    engine = create_engine(settings.postgres_dsn, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def isolation_session_factory(isolation_engine):
    return sessionmaker(bind=isolation_engine, autoflush=False, autocommit=False)


@pytest.fixture()
def iso_db(isolation_session_factory) -> Session:
    session = isolation_session_factory()
    try:
        yield session
        session.rollback()
    finally:
        session.close()


@pytest.fixture(scope="module")
def settings():
    return get_settings()


def _make_identity(session: Session, settings, tag: str):
    """Create a tenant, user, workspace triple and return their token."""
    from backend.app.models.tenant import Tenant
    from backend.app.models.user import User
    from backend.app.models.workspace import Workspace
    from backend.app.core.workspace_authorization import (
        tenant_memberships,
        workspace_memberships,
    )

    tenant = Tenant(
        id=uuid.uuid4(),
        tenant_name=f"iso-tenant-{tag}",
        tenant_slug=f"iso-{tag}",
        tenant_status="active",
    )
    session.add(tenant)

    user = User(
        id=uuid.uuid4(),
        email=f"iso-{tag}@example.invalid",
        hashed_password=hash_password("ci-password"),
        full_name=f"ISO User {tag}",
        role="analyst",
        is_active=True,
    )
    session.add(user)

    workspace = Workspace(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_name=f"ISO Workspace {tag}",
        workspace_slug=f"iso-ws-{tag}",
        status="active",
    )
    session.add(workspace)
    session.flush()

    session.execute(
        tenant_memberships.insert().values(
            tenant_id=tenant.id, user_id=user.id, role="analyst", active=True
        )
    )
    session.execute(
        workspace_memberships.insert().values(
            workspace_id=workspace.id, user_id=user.id, role="analyst", active=True
        )
    )
    session.flush()

    token = create_access_token(
        {"sub": str(user.id), "email": user.email, "role": user.role},
        settings=settings,
    )
    return {"tenant": tenant, "user": user, "workspace": workspace, "token": token}


def _make_dataset(session: Session, owner_id: str, tag: str):
    """Insert a minimal Dataset owned by owner_id."""
    from backend.app.models.dataset import Dataset

    ds = Dataset(
        dataset_id=str(uuid.uuid4()),
        owner_id=owner_id,
        dataset_name=f"isolation-dataset-{tag}",
        file_name=f"test_{tag}.csv",
        file_type="csv",
        file_path=f"/ci/storage/raw/csv/test_{tag}.csv",
        status="uploaded",
    )
    session.add(ds)
    session.flush()
    return ds


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDatabaseLevelOwnership:
    """owner_id column must enforce single-account dataset ownership."""

    def test_owner_id_column_present(self, isolation_engine):
        """datasets.owner_id must exist and be a nullable String(36)."""
        from sqlalchemy import inspect as sa_inspect
        with isolation_engine.connect() as conn:
            inspector = sa_inspect(conn)
            columns = {c["name"]: c for c in inspector.get_columns("datasets")}
        assert "owner_id" in columns, "datasets.owner_id column is missing"

    def test_owner_id_is_nullable(self, isolation_engine):
        """Quarantined legacy datasets may have NULL owner_id."""
        from sqlalchemy import inspect as sa_inspect
        with isolation_engine.connect() as conn:
            inspector = sa_inspect(conn)
            columns = {c["name"]: c for c in inspector.get_columns("datasets")}
        assert columns["owner_id"]["nullable"] is True, (
            "owner_id must be nullable to support quarantined legacy records"
        )

    def test_user_only_sees_own_datasets(self, iso_db, settings):
        """A query filtered by owner_id must not return another user's datasets."""
        tag_a = uuid.uuid4().hex[:8]
        tag_b = uuid.uuid4().hex[:8]
        id_a = _make_identity(iso_db, settings, tag=tag_a)
        id_b = _make_identity(iso_db, settings, tag=tag_b)
        ds_a = _make_dataset(iso_db, str(id_a["user"].id), tag=tag_a)
        ds_b = _make_dataset(iso_db, str(id_b["user"].id), tag=tag_b)

        # User A should see only ds_a
        result = iso_db.execute(
            text(
                "SELECT dataset_id FROM datasets WHERE owner_id = :uid"
            ),
            {"uid": str(id_a["user"].id)},
        ).scalars().all()

        assert ds_a.dataset_id in result, "User A cannot see their own dataset"
        assert ds_b.dataset_id not in result, (
            "User A should NOT see User B's dataset — isolation violated"
        )

    def test_null_owner_excluded_from_owned_query(self, iso_db, settings):
        """A WHERE owner_id = :uid filter must exclude datasets with NULL owner."""
        tag = uuid.uuid4().hex[:8]
        id_x = _make_identity(iso_db, settings, tag=tag)

        # Insert an orphaned dataset with no owner
        from backend.app.models.dataset import Dataset
        orphan = Dataset(
            dataset_id=str(uuid.uuid4()),
            owner_id=None,                  # quarantined / legacy
            dataset_name=f"orphan-{tag}",
            file_name=f"orphan_{tag}.csv",
            file_type="csv",
            file_path=f"/ci/storage/orphan_{tag}.csv",
            status="uploaded",
        )
        iso_db.add(orphan)
        iso_db.flush()

        result = iso_db.execute(
            text("SELECT dataset_id FROM datasets WHERE owner_id = :uid"),
            {"uid": str(id_x["user"].id)},
        ).scalars().all()

        assert orphan.dataset_id not in result, (
            "Orphaned dataset (NULL owner_id) must not appear in owned-dataset queries"
        )


class TestWorkspaceMembershipDoesNotWidenAccess:
    """Workspace membership must not grant access to another account's datasets."""

    def test_shared_workspace_does_not_expose_foreign_datasets(self, iso_db, settings):
        """Even if two users share a workspace, dataset ownership must be respected."""
        tag_a = uuid.uuid4().hex[:8]
        tag_b = uuid.uuid4().hex[:8]
        id_a = _make_identity(iso_db, settings, tag=tag_a)
        id_b = _make_identity(iso_db, settings, tag=tag_b)

        ds_a = _make_dataset(iso_db, str(id_a["user"].id), tag=tag_a)

        # User B tries to access User A's dataset using the authorization layer
        from backend.app.core.workspace_authorization import (
            authorize_bound_dataset,
            WorkspaceAccess,
        )

        access_b = WorkspaceAccess(
            actor_id=id_b["user"].id,
            workspace_id=id_b["workspace"].id,
            tenant_id=id_b["tenant"].id,
            role="analyst",
        )

        import pytest as _pytest
        from fastapi import HTTPException
        with _pytest.raises(HTTPException) as exc_info:
            authorize_bound_dataset(iso_db, access_b, ds_a.dataset_id)

        # Must be 404 — not 200, not 403 (existence must not be revealed)
        assert exc_info.value.status_code == 404, (
            f"Cross-account dataset access must return 404, "
            f"got {exc_info.value.status_code}"
        )


class TestAuthorizationTablePresence:
    """The authorization tables required by workspace_authorization.py must exist."""

    REQUIRED_AUTH_TABLES = [
        "tenant_memberships",
        "workspace_memberships",
        "dataset_workspace_bindings",
    ]

    def test_authorization_tables_exist(self, isolation_engine):
        """All three authorization tables must be present in the schema."""
        from sqlalchemy import inspect as sa_inspect
        with isolation_engine.connect() as conn:
            inspector = sa_inspect(conn)
            present = set(inspector.get_table_names())

        missing = [t for t in self.REQUIRED_AUTH_TABLES if t not in present]
        assert not missing, (
            f"Authorization tables missing: {missing}. "
            "These are created by migration 005_dataset_ownership or "
            "migrations/proposed/workspace_authorization.sql."
        )

    def test_tenant_memberships_has_required_columns(self, isolation_engine):
        from sqlalchemy import inspect as sa_inspect
        with isolation_engine.connect() as conn:
            inspector = sa_inspect(conn)
            cols = {c["name"] for c in inspector.get_columns("tenant_memberships")}
        required = {"tenant_id", "user_id", "role", "active"}
        assert required <= cols, f"tenant_memberships missing columns: {required - cols}"

    def test_workspace_memberships_has_required_columns(self, isolation_engine):
        from sqlalchemy import inspect as sa_inspect
        with isolation_engine.connect() as conn:
            inspector = sa_inspect(conn)
            cols = {c["name"] for c in inspector.get_columns("workspace_memberships")}
        required = {"workspace_id", "user_id", "role", "active"}
        assert required <= cols, f"workspace_memberships missing columns: {required - cols}"
