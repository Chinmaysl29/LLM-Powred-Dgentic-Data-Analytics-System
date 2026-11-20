"""Schema Reader Service with thread-safe caching and prompt context generation.

Coordinates dynamic database schema extraction, TTL-based caching,
table lookups, and prompt context formatting for downstream SQL agents.
"""

from datetime import datetime, timezone
import logging
import threading
import time
from typing import Any

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from backend.app.database.postgres import get_db_session
from backend.app.core.exceptions import DatabaseConnectionError
from backend.app.repositories.schema_repository import SchemaRepository
from backend.app.schemas.schema_reader import (
    DatabaseMetadata,
    DatabaseSchema,
    TableMetadata,
)


logger = logging.getLogger(__name__)


class SchemaReaderService:
    """Service providing cached, thread-safe access to database schema metadata."""

    def __init__(
        self,
        schema_repository: SchemaRepository | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._repository = schema_repository
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, DatabaseSchema]] = {}
        self._lock = threading.Lock()

    @property
    def repository(self) -> SchemaRepository | None:
        """Access underlying repository."""
        return self._repository

    def set_repository(self, repository: SchemaRepository) -> None:
        """Configure or update schema repository."""
        with self._lock:
            self._repository = repository
            self._cache.clear()

    def get_schema(
        self,
        force_refresh: bool = False,
        schema_name: str | None = None,
        table_names: list[str] | None = None,
    ) -> DatabaseSchema:
        """Retrieve complete database schema with caching support."""
        cache_key = f"{schema_name or 'default'}:{','.join(sorted(table_names)) if table_names else 'all'}"
        now = time.time()

        if not force_refresh:
            with self._lock:
                cached_entry = self._cache.get(cache_key)
                if cached_entry:
                    cached_at, cached_schema = cached_entry
                    if now - cached_at < self._cache_ttl:
                        logger.debug("Returning cached schema for key=%s (age=%.1fs)", cache_key, now - cached_at)
                        # Return cached instance with metadata updated
                        data = cached_schema.model_copy(deep=True)
                        data.metadata.is_cached = True
                        data.metadata.ttl_seconds = self._cache_ttl
                        return data

        if self._repository is None:
            raise DatabaseConnectionError("Schema repository is unavailable")

        schema = self._repository.inspect_schema(
            schema_name=schema_name,
            table_names=table_names,
        )

        schema.metadata.cached_at = datetime.now(timezone.utc).isoformat()
        schema.metadata.is_cached = False
        schema.metadata.ttl_seconds = self._cache_ttl

        with self._lock:
            self._cache[cache_key] = (now, schema.model_copy(deep=True))

        return schema

    def invalidate_cache(self) -> None:
        """Explicitly invalidate all cached schema representations."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info("Invalidated %d cached schema entries", count)

    def get_table_schema(
        self,
        table_name: str,
        schema_name: str | None = None,
        force_refresh: bool = False,
    ) -> TableMetadata | None:
        """Retrieve schema metadata for a specific table."""
        schema = self.get_schema(
            force_refresh=force_refresh,
            schema_name=schema_name,
            table_names=[table_name],
        )
        return schema.get_table(table_name)


    def get_compact_tables(
        self,
        schema_name: str | None = None,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Retrieve prompt-friendly compact schema: [{'table': 'sales', 'columns': [...]}]"""
        schema = self.get_schema(force_refresh=force_refresh, schema_name=schema_name)
        return schema.to_compact_tables()

    def generate_prompt_context(
        self,
        table_names: list[str] | None = None,
        schema_name: str | None = None,
        force_refresh: bool = False,
    ) -> str:
        """Render a formatted markdown/DDL schema representation for downstream LLM prompts."""
        schema = self.get_schema(force_refresh=force_refresh, schema_name=schema_name, table_names=table_names)
        return schema.to_prompt_context(table_names=table_names)


def get_schema_reader_service(
    request: Request,
    db: Session | None = Depends(get_db_session),
) -> SchemaReaderService:
    """FastAPI dependency provider for SchemaReaderService."""
    if db is not None:
        repo = SchemaRepository(bind=db)
        return SchemaReaderService(schema_repository=repo)

    # Check postgres adapter from app state
    postgres = getattr(request.app.state, "postgres", None)
    if postgres is not None:
        try:
            repo = SchemaRepository(bind=postgres.engine)
            return SchemaReaderService(schema_repository=repo)
        except Exception as exc:
            logger.warning("Could not bind SchemaRepository to application postgres engine: %s", exc)

    return SchemaReaderService()
