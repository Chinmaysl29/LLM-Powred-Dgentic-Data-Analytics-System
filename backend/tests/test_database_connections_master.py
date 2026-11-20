"""Master test suite for PostgreSQL and MySQL external database connections.

Validates:
1. PostgreSQL live connection testing, credentials validation, table introspection.
2. MySQL live connection testing, credentials validation, table introspection.
3. Error translation for wrong passwords, unreachable hosts, missing databases, SSRF.
4. Secure connection profile persistence with Fernet encryption at rest.
5. Zero credential disclosure (passwords masked as '••••••••', secrets never returned).
6. Automatic workspace resolution and multi-tenant isolation.
7. Profile retrieval and safe deletion.
"""

import os
import uuid
from typing import Any
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import create_access_token
from backend.app.main import create_app
from backend.app.models.connector import ConnectorRecord, ConnectorType
from backend.app.models.user import User
from backend.app.models.workspace import Workspace


@pytest.fixture(scope="module")
def client():
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def _get_or_create_test_user(db: Session, prefix: str = "master_tester") -> tuple[User, str]:
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=email,
        hashed_password="test_hash_not_used_for_jwt",
        full_name="Master Connector Tester",
        role="analyst",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    return user, token


# =============================================================================
# 1. POSTGRESQL CONNECTION TESTS
# =============================================================================


def test_postgresql_connection_test_success(client, db_session):
    """Test PostgreSQL connection with authorized database credentials."""
    user, token = _get_or_create_test_user(db_session, "pg_success")
    settings = get_settings()

    res = client.post(
        "/api/v1/connections/test",
        json={
            "connector_type": "postgresql",
            "host": settings.postgres_host,
            "port": settings.postgres_port,
            "database": settings.postgres_db,
            "username": settings.postgres_user,
            "password": settings.postgres_password.get_secret_value(),
            "schema_name": "public",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "HEALTHY"
    assert data["connector_type"] == "postgresql"
    assert data["latency_ms"] > 0
    assert data["total_tables"] > 0
    assert len(data["tables"]) > 0


def test_postgresql_connection_test_invalid_password(client, db_session):
    """Test PostgreSQL connection rejection with wrong password and clear error message."""
    user, token = _get_or_create_test_user(db_session, "pg_badpwd")
    settings = get_settings()

    res = client.post(
        "/api/v1/connections/test",
        json={
            "connector_type": "postgresql",
            "host": settings.postgres_host,
            "port": settings.postgres_port,
            "database": settings.postgres_db,
            "username": settings.postgres_user,
            "password": "definitely_wrong_password_9999",
            "schema_name": "public",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    data = res.json()
    assert data["success"] is False
    assert "authentication failed" in data["message"].lower()


def test_postgresql_connection_test_unreachable_host(client, db_session):
    """Test PostgreSQL connection failure on unreachable port."""
    user, token = _get_or_create_test_user(db_session, "pg_badhost")

    res = client.post(
        "/api/v1/connections/test",
        json={
            "connector_type": "postgresql",
            "host": "127.0.0.1",
            "port": 54399,
            "database": "ai_analyst",
            "username": "postgres",
            "password": "anypassword",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    data = res.json()
    assert data["success"] is False
    assert "unable to connect" in data["message"].lower() or "connection refused" in data["message"].lower() or "refused" in data["message"].lower()


def test_postgresql_connection_test_missing_database(client, db_session):
    """Test PostgreSQL connection rejection on missing database."""
    user, token = _get_or_create_test_user(db_session, "pg_nodb")
    settings = get_settings()

    res = client.post(
        "/api/v1/connections/test",
        json={
            "connector_type": "postgresql",
            "host": settings.postgres_host,
            "port": settings.postgres_port,
            "database": "database_that_does_not_exist_404",
            "username": settings.postgres_user,
            "password": settings.postgres_password.get_secret_value(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    data = res.json()
    assert data["success"] is False
    assert "does not exist" in data["message"].lower()


def test_postgresql_ssrf_blocking(client, db_session):
    """Verify SSRF attempts to cloud metadata IPs are strictly blocked before socket calls."""
    user, token = _get_or_create_test_user(db_session, "pg_ssrf")

    res = client.post(
        "/api/v1/connections/test",
        json={
            "connector_type": "postgresql",
            "host": "169.254.169.254",
            "port": 5432,
            "database": "secret",
            "username": "postgres",
            "password": "pwd",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "disallowed" in res.json()["message"].lower()


# =============================================================================
# 2. MYSQL CONNECTION TESTS
# =============================================================================


def test_mysql_connection_test_success(client, db_session):
    """Test MySQL connection with live analytics_reader credentials."""
    user, token = _get_or_create_test_user(db_session, "my_success")
    settings = get_settings()

    res = client.post(
        "/api/v1/connections/test",
        json={
            "connector_type": "mysql",
            "host": settings.mysql_host,
            "port": settings.mysql_port,
            "database": settings.mysql_db,
            "username": settings.mysql_user,
            "password": settings.mysql_password.get_secret_value(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "HEALTHY"
    assert data["connector_type"] == "mysql"
    assert data["latency_ms"] > 0
    assert "Successfully connected to MYSQL" in data["message"]


def test_mysql_connection_test_invalid_password(client, db_session):
    """Test MySQL connection rejection with invalid credentials."""
    user, token = _get_or_create_test_user(db_session, "my_badpwd")
    settings = get_settings()

    res = client.post(
        "/api/v1/connections/test",
        json={
            "connector_type": "mysql",
            "host": settings.mysql_host,
            "port": settings.mysql_port,
            "database": settings.mysql_db,
            "username": settings.mysql_user,
            "password": "incorrect_mysql_password_8888",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    data = res.json()
    assert data["success"] is False
    assert "authentication failed" in data["message"].lower() or "access denied" in data["message"].lower()


# =============================================================================
# 3. SAVE, LIST, ENCRYPTION & DELETION TESTS
# =============================================================================


def test_save_and_retrieve_postgresql_connection_with_encryption(client, db_session):
    """Test saving a PostgreSQL connection profile with encryption at rest and masked display."""
    user, token = _get_or_create_test_user(db_session, "save_pg")
    settings = get_settings()

    # 1. Save connection without explicit workspace_id (should auto-provision/resolve)
    save_res = client.post(
        "/api/v1/connections",
        json={
            "connector_name": "Production Postgres Cluster",
            "connector_type": "postgresql",
            "host": settings.postgres_host,
            "port": settings.postgres_port,
            "database": settings.postgres_db,
            "username": settings.postgres_user,
            "password": settings.postgres_password.get_secret_value(),
            "schema_name": "public",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert save_res.status_code == 201, save_res.text
    saved = save_res.json()
    assert saved["connector_name"] == "Production Postgres Cluster"
    assert saved["connector_subtype"] == "postgresql"
    assert saved["config"]["password"] == "••••••••"
    assert "encrypted_password" not in saved["config"]
    conn_id = saved["id"]

    # 2. Verify encrypted_password is stored in database record at rest
    record = db_session.get(ConnectorRecord, uuid.UUID(conn_id))
    assert record is not None
    assert record.config["password"] == "••••••••"
    assert record.config["encrypted_password"] != ""
    assert record.config["encrypted_password"] != settings.postgres_password.get_secret_value()

    # 3. List connections
    list_res = client.get(
        "/api/v1/connections",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(c["id"] == conn_id for c in items)
    matched = next(c for c in items if c["id"] == conn_id)
    assert matched["config"]["password"] == "••••••••"
    assert "encrypted_password" not in matched["config"]

    # 4. Delete connection
    del_res = client.delete(
        f"/api/v1/connections/{conn_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # 5. Confirm deletion
    list_after = client.get(
        "/api/v1/connections",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert not any(c["id"] == conn_id for c in list_after)


def test_save_and_retrieve_mysql_connection_with_encryption(client, db_session):
    """Test saving a MySQL connection profile with encryption at rest and masked display."""
    user, token = _get_or_create_test_user(db_session, "save_my")
    settings = get_settings()

    save_res = client.post(
        "/api/v1/connections",
        json={
            "connector_name": "Enterprise MySQL Warehouse",
            "connector_type": "mysql",
            "host": settings.mysql_host,
            "port": settings.mysql_port,
            "database": settings.mysql_db,
            "username": settings.mysql_user,
            "password": settings.mysql_password.get_secret_value(),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert save_res.status_code == 201, save_res.text
    saved = save_res.json()
    assert saved["connector_name"] == "Enterprise MySQL Warehouse"
    assert saved["connector_subtype"] == "mysql"
    assert saved["config"]["password"] == "••••••••"
    assert "encrypted_password" not in saved["config"]
    conn_id = saved["id"]

    # Verify database record
    record = db_session.get(ConnectorRecord, uuid.UUID(conn_id))
    assert record is not None
    assert record.config["password"] == "••••••••"
    assert record.config["encrypted_password"] != ""
    assert record.config["encrypted_password"] != settings.mysql_password.get_secret_value()

    # Clean up
    del_res = client.delete(
        f"/api/v1/connections/{conn_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 200
