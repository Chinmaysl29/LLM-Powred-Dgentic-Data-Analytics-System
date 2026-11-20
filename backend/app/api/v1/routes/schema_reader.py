"""API routes for SQL Schema Reader."""

import logging
import traceback
from contextlib import contextmanager
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import DBAPIError, TimeoutError as SQLTimeoutError
from backend.app.core.config import get_settings
from backend.app.core.exceptions import DatabaseConnectionError

from backend.app.schemas.schema_reader import (
    DatabaseSchema,
    SchemaReaderResponse,
    TableMetadata,
)
from backend.app.services.schema_reader_service import (
    SchemaReaderService,
    get_schema_reader_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schema", tags=["SQL Schema Reader"])


def authorized_schema(
    schema_name: str | None = Query(None, description="Configured application schema"),
) -> str:
    """This explorer serves the shared application catalog, never arbitrary tenants' schemas."""
    configured = get_settings().database_schema
    if schema_name is not None and schema_name != configured:
        raise HTTPException(403, "Access to this database schema is not permitted.")
    return configured


@contextmanager
def schema_errors():
    """Classify failures without disclosing SQL, credentials, or validator inputs."""
    try:
        yield
    except HTTPException:
        raise
    except Exception as exc:
        code = getattr(getattr(exc, "orig", None), "sqlstate", None)
        logger.error(
            "Schema inspection failed category=%s sqlstate=%s\n%s",
            type(exc).__name__, code, "".join(traceback.format_tb(exc.__traceback__)),
        )
        if code == "42501":
            raise HTTPException(403, "Permission to inspect database metadata was denied.") from exc
        if isinstance(exc, SQLTimeoutError) or code == "57014":
            raise HTTPException(504, "Database schema inspection timed out. Please retry.") from exc
        if isinstance(exc, DatabaseConnectionError) or (
            isinstance(exc, DBAPIError) and (
                exc.connection_invalidated or (code and code.startswith("08"))
                or code in {"57P01", "57P02", "57P03", "53300"}
                or (code is None and type(exc).__name__ == "OperationalError")
            )
        ):
            raise HTTPException(503, "The database is temporarily unavailable. Please retry.") from exc
        raise HTTPException(500, "Database schema could not be loaded. Please retry or contact support.") from exc


@router.get(
    "",
    response_model=SchemaReaderResponse,
    summary="Inspect and retrieve database schema",
)
def get_database_schema(
    refresh: bool = Query(False, description="Force refresh schema cache"),
    schema_name: str = Depends(authorized_schema),
    service: SchemaReaderService = Depends(get_schema_reader_service),
) -> SchemaReaderResponse:
    """Retrieve full database schema including tables, columns, foreign keys, and indexes."""
    with schema_errors():
        schema_data = service.get_schema(force_refresh=refresh, schema_name=schema_name)
        return SchemaReaderResponse(
            status="success",
            schema_data=schema_data,
        )


@router.get(
    "/compact",
    response_model=list[dict[str, Any]],
    summary="Get compact prompt-ready table/column representations",
)
def get_compact_schema(
    refresh: bool = Query(False, description="Force refresh schema cache"),
    schema_name: str = Depends(authorized_schema),
    service: SchemaReaderService = Depends(get_schema_reader_service),
) -> list[dict[str, Any]]:
    """Retrieve lightweight table-column mappings: [{'table': 'sales', 'columns': [...]}]"""
    with schema_errors():
        return service.get_compact_tables(schema_name=schema_name, force_refresh=refresh)


@router.get(
    "/tables/{table_name}",
    response_model=TableMetadata,
    summary="Get detailed schema metadata for a single table",
)
def get_table_schema(
    table_name: str,
    schema_name: str = Depends(authorized_schema),
    refresh: bool = Query(False, description="Force refresh cache"),
    service: SchemaReaderService = Depends(get_schema_reader_service),
) -> TableMetadata:
    """Retrieve detailed column, index, and constraint information for a specific table."""
    with schema_errors():
        table = service.get_table_schema(table_name=table_name, schema_name=schema_name, force_refresh=refresh)
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' was not found in schema",
        )
    return table


@router.get(
    "/prompt-context",
    response_model=dict[str, str],
    summary="Get formatted schema markdown for LLM SQL generation prompts",
)
def get_prompt_context(
    tables: list[str] | None = Query(None, description="Optional subset of table names to include"),
    schema_name: str = Depends(authorized_schema),
    service: SchemaReaderService = Depends(get_schema_reader_service),
) -> dict[str, str]:
    """Render formatted markdown DDL context for LLM prompt construction."""
    with schema_errors():
        context_text = service.generate_prompt_context(table_names=tables, schema_name=schema_name)
    return {"prompt_context": context_text}


@router.post(
    "/refresh",
    response_model=dict[str, str],
    summary="Invalidate and refresh database schema cache",
)
async def refresh_schema_cache(
    service: SchemaReaderService = Depends(get_schema_reader_service),
) -> dict[str, str]:
    """Clear all in-memory cached schemas to force immediate re-introspection."""
    service.invalidate_cache()
    return {"status": "cache_invalidated", "message": "Schema cache successfully cleared"}
