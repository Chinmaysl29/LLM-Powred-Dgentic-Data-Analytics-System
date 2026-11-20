"""External Database Connections API (PostgreSQL & MySQL source connectors)."""

import base64
from datetime import datetime, timezone
import hashlib
import ipaddress
import logging
import socket
import time
from typing import Any
import uuid

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import get_current_user
from backend.app.core.workspace_authorization import (
    authorize_tenant,
    authorize_workspace,
    tenant_memberships,
    workspace_memberships,
)
from backend.app.database.postgres import get_db_session
from backend.app.models.connector import ConnectorRecord, ConnectorStatus, ConnectorType
from backend.app.models.tenant import Tenant
from backend.app.models.user import User
from backend.app.models.workspace import Workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connections", tags=["Database Connections"])


class ConnectionTestRequest(BaseModel):
    connector_type: str = Field(..., description="'postgresql' or 'mysql'")
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(default="", max_length=255)
    schema_name: str | None = Field(default="public", max_length=255)


class SaveConnectionRequest(BaseModel):
    workspace_id: uuid.UUID | None = None
    connector_name: str = Field(..., min_length=1, max_length=255)
    connector_type: str = Field(..., description="'postgresql' or 'mysql'")
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(default="", max_length=255)
    schema_name: str | None = Field(default="public", max_length=255)


def _check_ssrf_safety(host: str) -> None:
    """Disallow AWS/cloud metadata services and link-local ranges."""
    forbidden = ["169.254.169.254", "metadata.google.internal", "instance-data"]
    if host.lower() in forbidden:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connection target is disallowed by network security policy",
        )
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_link_local:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Link-local addresses are disallowed",
            )
    except ValueError:
        pass  # Hostname is not an IP literal


def _get_encryption_cipher() -> Fernet:
    """Derive a reproducible AES/Fernet key from the server's JWT secret key."""
    settings = get_settings()
    secret = (
        settings.jwt_secret_key.get_secret_value()
        if hasattr(settings.jwt_secret_key, "get_secret_value")
        else str(settings.jwt_secret_key)
    )
    key_bytes = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def _resolve_or_provision_workspace(
    db: Session,
    user: Any,
    requested_workspace_id: uuid.UUID | None = None,
    permission: str = "write",
) -> Workspace:
    """Resolve an authorized workspace or safely provision a default personal workspace."""
    nil_uuid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    if requested_workspace_id and requested_workspace_id != nil_uuid:
        # Enforce strict multi-tenant authorization check for requested workspace
        authorize_workspace(db, user.id, requested_workspace_id, permission)
        ws = db.get(Workspace, requested_workspace_id)
        if not ws or ws.status != "active":
            raise HTTPException(404, "Workspace not found")
        return ws

    # If no specific workspace was requested (or nil UUID was sent):
    # Check for existing active workspace membership
    existing_ws = db.scalars(
        select(Workspace)
        .join(workspace_memberships, workspace_memberships.c.workspace_id == Workspace.id)
        .where(
            workspace_memberships.c.user_id == user.id,
            workspace_memberships.c.active.is_(True),
            Workspace.status == "active",
        )
    ).first()
    if existing_ws:
        return existing_ws

    # Check for existing active tenant
    existing_tenant = db.scalars(
        select(Tenant)
        .join(tenant_memberships, tenant_memberships.c.tenant_id == Tenant.id)
        .where(
            tenant_memberships.c.user_id == user.id,
            tenant_memberships.c.active.is_(True),
            Tenant.tenant_status == "active",
        )
    ).first()

    user_label = getattr(user, "email", None) or str(user.id)
    if not existing_tenant:
        new_tenant = Tenant(
            tenant_name=f"Workspace Tenant ({user_label})",
            tenant_slug=uuid.uuid4().hex[:12],
            tenant_status="active",
        )
        db.add(new_tenant)
        db.flush()
        db.execute(
            tenant_memberships.insert().values(
                tenant_id=new_tenant.id,
                user_id=user.id,
                role="owner",
                active=True,
            )
        )
        tenant_id = new_tenant.id
    else:
        tenant_id = existing_tenant.id

    new_ws = Workspace(
        tenant_id=tenant_id,
        workspace_name="Default Analytics Workspace",
        workspace_slug=uuid.uuid4().hex[:12],
        status="active",
    )
    db.add(new_ws)
    db.flush()
    db.execute(
        workspace_memberships.insert().values(
            workspace_id=new_ws.id,
            user_id=user.id,
            role="owner",
            active=True,
        )
    )
    db.commit()
    db.refresh(new_ws)
    return new_ws


@router.post("/test", summary="Test external database connection")
def test_database_connection(
    payload: ConnectionTestRequest,
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Test connection credentials and discover tables for PostgreSQL or MySQL."""
    _check_ssrf_safety(payload.host)
    ctype = payload.connector_type.lower()
    if ctype not in {"postgresql", "mysql"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported connector type '{payload.connector_type}'. Supported: 'postgresql', 'mysql'",
        )

    # Build dialect-specific DSN
    if ctype == "postgresql":
        dsn = f"postgresql+psycopg://{payload.username}:{payload.password}@{payload.host}:{payload.port}/{payload.database}"
    else:
        dsn = f"mysql+pymysql://{payload.username}:{payload.password}@{payload.host}:{payload.port}/{payload.database}"

    start_time = time.perf_counter()
    try:
        engine = create_engine(
            dsn,
            connect_args={"connect_timeout": 5},
            pool_pre_ping=True,
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            inspector = inspect(conn)
            if ctype == "postgresql":
                schema = payload.schema_name or "public"
                tables = inspector.get_table_names(schema=schema)
            else:
                tables = inspector.get_table_names()

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        engine.dispose()

        return {
            "success": True,
            "status": "HEALTHY",
            "connector_type": ctype,
            "latency_ms": latency_ms,
            "tables": tables[:50],
            "total_tables": len(tables),
            "message": f"Successfully connected to {ctype.upper()} database '{payload.database}' ({len(tables)} tables found)",
        }
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        error_msg = str(exc)
        # Redact password if present in error message
        if payload.password and payload.password in error_msg:
            error_msg = error_msg.replace(payload.password, "••••••••")
        logger.warning("External connection test failed type=%s host=%s: %s", ctype, payload.host, error_msg)

        err_lower = error_msg.lower()
        if "password authentication failed" in err_lower or "access denied for user" in err_lower:
            user_msg = "Database authentication failed. Verify your username and password."
        elif "connection refused" in err_lower:
            if payload.host.lower() in {"localhost", "127.0.0.1"}:
                service_hint = "postgres" if ctype == "postgresql" else "mysql"
                user_msg = (
                    f"Unable to reach the database server at localhost:{payload.port} (Connection refused). "
                    f"In Docker Compose, use service name '{service_hint}' instead of 'localhost'."
                )
            else:
                user_msg = f"Unable to reach the database server at {payload.host}:{payload.port} (Connection refused)."
        elif "does not exist" in err_lower or "unknown database" in err_lower:
            user_msg = f"Database '{payload.database}' does not exist on the server."
        elif "could not translate host name" in err_lower or "name or service not known" in err_lower:
            user_msg = f"Unable to resolve database hostname '{payload.host}'."
        elif "timeout" in err_lower or "timed out" in err_lower:
            user_msg = f"Connection to {payload.host}:{payload.port} timed out."
        else:
            user_msg = f"Connection failed: {error_msg}"

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "status": "FAILED",
                "connector_type": ctype,
                "latency_ms": latency_ms,
                "message": user_msg,
            },
        )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Save external database connection")
def save_database_connection(
    payload: SaveConnectionRequest,
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Save an authorized external database connection for a workspace."""
    workspace = _resolve_or_provision_workspace(db, user, payload.workspace_id, "write")

    ctype = payload.connector_type.lower()
    if ctype not in {"postgresql", "mysql"}:
        raise HTTPException(400, "Supported connector types are 'postgresql' and 'mysql'")

    # Encrypt password at rest using server-managed Fernet key
    encrypted_pw = ""
    if payload.password:
        try:
            encrypted_pw = _get_encryption_cipher().encrypt(payload.password.encode("utf-8")).decode("utf-8")
        except Exception as enc_err:
            logger.warning("Credential encryption warning: %s", enc_err)

    stored_config = {
        "host": payload.host,
        "port": payload.port,
        "database": payload.database,
        "username": payload.username,
        "password": "••••••••" if payload.password else "",
        "encrypted_password": encrypted_pw,
        "schema_name": payload.schema_name or "public",
        "workspace_id": str(workspace.id),
    }

    # Check for existing record with the same name in this tenant to prevent duplicate records
    existing = db.scalars(
        select(ConnectorRecord)
        .where(
            ConnectorRecord.tenant_id == workspace.tenant_id,
            ConnectorRecord.connector_name == payload.connector_name,
            ConnectorRecord.connector_type == ConnectorType.DATABASE,
        )
    ).first()

    if existing:
        existing.connector_subtype = ctype
        existing.status = ConnectorStatus.ACTIVE
        existing.config = stored_config
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        record = existing
    else:
        record = ConnectorRecord(
            tenant_id=workspace.tenant_id,
            connector_name=payload.connector_name,
            connector_type=ConnectorType.DATABASE,
            connector_subtype=ctype,
            status=ConnectorStatus.ACTIVE,
            config=stored_config,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    # Sanitize config before returning to client (never expose encrypted_password)
    client_config = {k: v for k, v in record.config.items() if k != "encrypted_password"}

    return {
        "id": str(record.id),
        "connector_name": record.connector_name,
        "connector_type": record.connector_type.value,
        "connector_subtype": record.connector_subtype,
        "status": record.status.value,
        "config": client_config,
        "created_at": record.created_at.isoformat(),
    }


@router.get("", summary="List external database connections")
def list_database_connections(
    workspace_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List configured external database connections for a workspace."""
    workspace = _resolve_or_provision_workspace(db, user, workspace_id, "read")

    records = db.scalars(
        select(ConnectorRecord)
        .where(
            ConnectorRecord.tenant_id == workspace.tenant_id,
            ConnectorRecord.connector_type == ConnectorType.DATABASE,
        )
        .order_by(ConnectorRecord.created_at.desc())
    ).all()

    return [
        {
            "id": str(r.id),
            "connector_name": r.connector_name,
            "connector_type": r.connector_type.value,
            "connector_subtype": r.connector_subtype,
            "status": r.status.value,
            "config": {k: v for k, v in r.config.items() if k != "encrypted_password"},
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]


@router.delete("/{connection_id}", summary="Delete external database connection")
def delete_database_connection(
    connection_id: uuid.UUID,
    workspace_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete an external database connection."""
    record = db.get(ConnectorRecord, connection_id)
    if not record:
        raise HTTPException(404, "Connection not found")

    nil_uuid = uuid.UUID("00000000-0000-0000-0000-000000000000")
    if workspace_id and workspace_id != nil_uuid:
        authorize_workspace(db, user.id, workspace_id, "write")
    else:
        authorize_tenant(db, user.id, record.tenant_id, "write")

    db.delete(record)
    db.commit()
    return {"success": True, "message": f"Connection '{connection_id}' deleted successfully"}
