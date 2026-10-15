"""Shared pytest fixtures for all backend integration tests.

All fixtures in this file target the ISOLATED CI PostgreSQL service
(DATABASE_URL env var), never customer storage.

Fixture hierarchy:
  db_engine (session scope)    — one engine per test run
    db_session (function scope) — one rolled-back transaction per test
      app_client (function scope) — FastAPI TestClient wired to the session
      token_user_a / token_user_b — pre-created tenant+workspace accounts

Environment variables required:
  DATABASE_URL  — postgresql+psycopg://... pointing at the isolated test DB
  JWT_SECRET_KEY — any non-empty string (safe placeholder value is fine in CI)
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

# ─── Make embedding-dependent imports conditional ─────────────────────────────
SKIP_EMBEDDING = os.getenv("SKIP_EMBEDDING_TESTS", "false").lower() == "true"

# ─── Application imports ──────────────────────────────────────────────────────
from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token, hash_password
from backend.app.database.schema_contract import inspect_schema
from backend.app.models.base import Base
import backend.app.models  # noqa: F401 — registers all ORM models with Base


# ─────────────────────────────────────────────────────────────────────────────
# Engine / session fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def settings():
    """Return application settings loaded from the CI environment."""
    return get_settings()


@pytest.fixture(scope="session")
def db_engine(settings):
    """Create one SQLAlchemy engine for the whole test session.

    The engine is created against the DATABASE_URL environment variable which
    must point at the ISOLATED CI database, not the customer instance.
    """
    engine = create_engine(
        settings.postgres_dsn,
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=4,
    )
    # Ensure all tables exist (migrations are run separately by the CI step).
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def tables_created(db_engine):
    """Verify the schema is migration-ready (migrations ran before this step)."""
    with db_engine.connect() as conn:
        result = inspect_schema(conn)
    if result["missing_tables"]:
        pytest.skip(
            f"Schema missing tables {result['missing_tables']} — run 'alembic upgrade head' first"
        )
    return result


@pytest.fixture()
def db_session(db_engine, tables_created) -> Generator[Session, None, None]:
    """Yield a database session that is rolled back after each test.

    This keeps tests isolated from each other without requiring a fresh
    database per test.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = session_factory()

    # Ensure nested transactions work across SQLAlchemy's session boundary.
    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(session, transaction_obj):
        if transaction_obj.nested and not transaction_obj._parent.nested:
            session.begin_nested()

    session.begin_nested()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


# ─────────────────────────────────────────────────────────────────────────────
# Application / HTTP client fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def app_client(db_session: Session) -> Generator[TestClient, None, None]:
    """Return a FastAPI TestClient backed by the isolated test session.

    The application's get_db_session dependency is overridden to return the
    rolled-back test session, so HTTP endpoints write to the same in-memory
    transaction that is torn down after the test.
    """
    from backend.app.main import create_app
    from backend.app.database.postgres import get_db_session

    application = create_app()
    application.state.schema_compatible = True  # Preflight already passed

    def override_db():
        yield db_session

    application.dependency_overrides[get_db_session] = override_db

    with TestClient(application, raise_server_exceptions=True) as client:
        yield client

    application.dependency_overrides.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Identity / authorization fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _create_tenant_user_workspace(
    session: Session, settings, *, suffix: str = ""
) -> dict[str, Any]:
    """Create a minimal Tenant → User → Workspace row set for test isolation."""
    from backend.app.models.tenant import Tenant
    from backend.app.models.user import User
    from backend.app.models.workspace import Workspace
    from backend.app.core.workspace_authorization import (
        authorization_metadata,
        tenant_memberships,
        workspace_memberships,
    )

    tag = suffix or uuid.uuid4().hex[:8]

    tenant = Tenant(
        id=uuid.uuid4(),
        tenant_name=f"ci-tenant-{tag}",
        tenant_slug=f"ci-{tag}",
        tenant_status="active",
    )
    session.add(tenant)

    user = User(
        id=uuid.uuid4(),
        email=f"ci-user-{tag}@example.invalid",
        hashed_password=hash_password("ci-password"),
        full_name=f"CI User {tag}",
        role="analyst",
        is_active=True,
    )
    session.add(user)

    workspace = Workspace(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        workspace_name=f"CI Workspace {tag}",
        workspace_slug=f"ws-{tag}",
        status="active",
    )
    session.add(workspace)
    session.flush()

    # Authorization tables live on a separate MetaData; insert directly.
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
    return {
        "tenant": tenant,
        "user": user,
        "workspace": workspace,
        "token": token,
        "auth_header": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture()
def identity_a(db_session: Session, settings):
    """First isolated tenant / user / workspace for multi-tenant tests."""
    return _create_tenant_user_workspace(db_session, settings, suffix="acct-a")


@pytest.fixture()
def identity_b(db_session: Session, settings):
    """Second isolated tenant / user / workspace for cross-tenant isolation tests."""
    return _create_tenant_user_workspace(db_session, settings, suffix="acct-b")
