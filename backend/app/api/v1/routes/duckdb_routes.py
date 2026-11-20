"""DuckDB analytical query endpoints."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/duckdb", tags=["duckdb"])


class QueryRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=10_000, description="SQL query to execute")
    parameters: list[Any] | None = Field(default=None, description="Bind parameters")


class CSVQueryRequest(BaseModel):
    file_path: str = Field(min_length=1, max_length=500, description="Path to the CSV file")
    sql: str | None = Field(default=None, max_length=10_000, description="SQL query (table alias is 'source')")


@router.get("/health")
async def duckdb_health(request: Request):
    """Check DuckDB engine status."""
    duck = getattr(request.app.state, "duckdb", None)
    if duck is None:
        raise HTTPException(503, "DuckDB not initialized")
    ok, message = await duck.health_check()
    if not ok:
        raise HTTPException(503, message)
    return {"status": "healthy", "message": message}


@router.get("/extensions")
async def duckdb_extensions(request: Request):
    """List all DuckDB extensions and their install/load status."""
    duck = getattr(request.app.state, "duckdb", None)
    if duck is None:
        raise HTTPException(503, "DuckDB not initialized")
    extensions = await asyncio.to_thread(duck.list_extensions)
    installed = [e for e in extensions if e["installed"]]
    return {
        "total": len(extensions),
        "installed": len(installed),
        "extensions": extensions,
    }


@router.post("/query")
async def duckdb_query(request: Request, body: QueryRequest):
    """Execute a SQL query against the DuckDB analytical engine."""
    duck = getattr(request.app.state, "duckdb", None)
    if duck is None:
        raise HTTPException(503, "DuckDB not initialized")
    try:
        rows = await asyncio.to_thread(duck.execute, body.sql, body.parameters)
        return {"rows": rows, "row_count": len(rows)}
    except Exception as exc:
        raise HTTPException(400, str(exc)[:500]) from exc


@router.post("/query/csv")
async def duckdb_query_csv(request: Request, body: CSVQueryRequest):
    """Read a CSV file and run an optional SQL query against it."""
    duck = getattr(request.app.state, "duckdb", None)
    if duck is None:
        raise HTTPException(503, "DuckDB not initialized")
    try:
        result = await asyncio.to_thread(duck.query_csv, body.file_path, body.sql)
        return {"rows": result, "row_count": len(result)}
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, str(exc)[:500]) from exc
