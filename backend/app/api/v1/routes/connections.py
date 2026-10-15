"""External Database Connections API (PostgreSQL & MySQL source connectors)."""

from datetime import datetime, timezone
import ipaddress
import logging
import socket
import time
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from backend.app.core.security import get_current_user
from backend.app.core.workspace_authorization import authorize_workspace
from backend.app.database.postgres import get_db_session
from backend.app.models.connector import ConnectorRecord, ConnectorStatus, ConnectorType
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
    workspace_id: uuid.UUID
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "status": "FAILED",
                "connector_type": ctype,
                "latency_ms": latency_ms,
                "message": f"Connection test failed: {error_msg}",
            },
        )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Save external database connection")
def save_database_connection(
    payload: SaveConnectionRequest,
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Save an authorized external database connection for a workspace."""
    access = authorize_workspace(db, user.id, payload.workspace_id, "write")
    workspace = db.get(Workspace, payload.workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")

    ctype = payload.connector_type.lower()
    if ctype not in {"postgresql", "mysql"}:
        raise HTTPException(400, "Supported connector types are 'postgresql' and 'mysql'")

    # Mask password for stored and returned config
    masked_config = {
        "host": payload.host,
        "port": payload.port,
        "database": payload.database,
        "username": payload.username,
        "password": "••••••••" if payload.password else "",
        "schema_name": payload.schema_name or "public",
        "workspace_id": str(payload.workspace_id),
    }

    record = ConnectorRecord(
        tenant_id=workspace.tenant_id,
        connector_name=payload.connector_name,
        connector_type=ConnectorType.DATABASE,
        connector_subtype=ctype,
        status=ConnectorStatus.ACTIVE,
        config=masked_config,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": str(record.id),
        "connector_name": record.connector_name,
        "connector_type": record.connector_type.value,
        "connector_subtype": record.connector_subtype,
        "status": record.status.value,
        "config": record.config,
        "created_at": record.created_at.isoformat(),
    }


@router.get("", summary="List external database connections")
def list_database_connections(
    workspace_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List configured external database connections for a workspace."""
    authorize_workspace(db, user.id, workspace_id, "read")
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")

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
            "config": r.config,
            "created_at": r.created_at.isoformat(),
        }
        for r in records
    ]


@router.delete("/{connection_id}", summary="Delete external database connection")
def delete_database_connection(
    connection_id: uuid.UUID,
    workspace_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db_session),
    user: Any = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete an external database connection."""
    authorize_workspace(db, user.id, workspace_id, "write")
    record = db.get(ConnectorRecord, connection_id)
    if not record:
        raise HTTPException(404, "Connection not found")

    db.delete(record)
    db.commit()
    return {"success": True, "message": f"Connection '{connection_id}' deleted successfully"}
