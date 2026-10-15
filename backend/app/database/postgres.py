"""SQLAlchemy PostgreSQL engine and request-scoped session dependency."""

import asyncio
import logging
from collections.abc import Generator

from fastapi import Request
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import Settings
from backend.app.core.exceptions import DatabaseConnectionError

logger = logging.getLogger(__name__)


class PostgresDatabase:
    """Own the SQLAlchemy engine lifecycle and session factory."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        """Return the initialized engine or raise a clear infrastructure error."""
        if self._engine is None:
            raise DatabaseConnectionError("PostgreSQL connection has not been initialized")
        return self._engine

    def connect(self) -> None:
        """Create a pooled engine and validate it with a lightweight query."""
        if self._engine is None:
            self._engine = create_engine(
                self._settings.postgres_dsn,
                pool_pre_ping=True,
                pool_size=self._settings.database_pool_size,
                max_overflow=self._settings.database_max_overflow,
                pool_recycle=1800,
            )
            self._session_factory = sessionmaker(bind=self._engine, autoflush=False, autocommit=False)
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("PostgreSQL connection established")
        except Exception as exc:
            self.close()
            raise DatabaseConnectionError("PostgreSQL connection validation failed") from exc

    async def health_check(self) -> tuple[bool, str]:
        """Check PostgreSQL without blocking the asynchronous request loop."""
        try:
            await asyncio.to_thread(self.connect)
            return True, "PostgreSQL is reachable"
        except DatabaseConnectionError:
            return False, "PostgreSQL is unavailable"

    async def schema_check(self) -> tuple[bool, str]:
        """Connectivity is insufficient when required application objects are absent."""
        from backend.app.database.schema_contract import inspect_schema
        def check():
            with self.engine.connect() as connection:
                result = inspect_schema(connection)
            return result['compatible']
        try:
            compatible = await asyncio.to_thread(check)
            return compatible, "Schema compatible" if compatible else "Schema incompatible; run migration preflight"
        except Exception:
            return False, "Schema compatibility could not be verified"

    def session(self) -> Generator[Session, None, None]:
        """Yield one transaction-safe SQLAlchemy session per request."""
        if self._session_factory is None:
            raise DatabaseConnectionError("PostgreSQL session factory is not initialized")
        database_session = self._session_factory()
        try:
            yield database_session
        finally:
            database_session.close()

    def close(self) -> None:
        """Dispose pooled database connections during shutdown."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("PostgreSQL connections closed")


def get_db_session(request: Request) -> Generator[Session | None, None, None]:
    """FastAPI dependency that reads the database adapter from application state."""
    postgres = getattr(request.app.state, "postgres", None)
    if getattr(request.app.state, "schema_compatible", None) is False:
        raise DatabaseConnectionError("Database schema is incompatible or unverified; run migration preflight")
    if postgres is not None and getattr(postgres, "_session_factory", None) is not None:
        yield from postgres.session()
    else:
        yield None
