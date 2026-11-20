"""DuckDB analytical engine adapter and application lifecycle management."""

import asyncio
import logging
from pathlib import Path
from typing import Any

import duckdb

from backend.app.core.config import Settings

logger = logging.getLogger(__name__)

# Official extensions to install and load for full analytical capability.
DUCKDB_EXTENSIONS: tuple[str, ...] = (
    # --- Bundled (always available, just need LOAD) ---
    "parquet",
    "json",
    "icu",
    # --- Installable core extensions ---
    "httpfs",
    "fts",           # Full-text search
    "excel",         # Read/write Excel files natively
    "spatial",       # Geospatial: ST_ functions, shapefiles, GeoJSON
    "inet",          # Network address types (IP, CIDR, MAC)
    "sqlite_scanner",  # Attach and query SQLite databases
    "postgres_scanner",  # Attach and query PostgreSQL databases
    "mysql_scanner",  # Attach and query MySQL databases
    "tpch",          # TPC-H benchmark data generator
    "tpcds",         # TPC-DS benchmark data generator
    "autocomplete",  # SQL autocomplete
    "aws",           # AWS credential chain (S3 access via httpfs)
    "azure",         # Azure credential chain (Blob/ADLS via httpfs)
    "delta",         # Delta Lake table support
    "iceberg",       # Apache Iceberg table support
    "vss",           # Vector similarity search
)


class DuckDBDatabase:
    """Manage one DuckDB connection per application process for analytical queries."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._extensions_loaded: list[str] = []

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        """Return the initialized DuckDB connection or raise."""
        if self._connection is None:
            raise RuntimeError("DuckDB connection has not been initialized")
        return self._connection

    def _connect_sync(self) -> None:
        """Create an in-memory DuckDB connection with extensions installed."""
        if self._connection is not None:
            return

        storage_root = Path(self._settings.upload_dir)
        duckdb_dir = storage_root / "duckdb"
        duckdb_dir.mkdir(parents=True, exist_ok=True)

        self._connection = duckdb.connect(
            database=str(duckdb_dir / "analytics.duckdb"),
            config={
                "threads": 4,
                "memory_limit": "512MB",
                "temp_directory": str(duckdb_dir / "tmp"),
                "extension_directory": str(duckdb_dir / "extensions"),
                "autoinstall_known_extensions": True,
                "autoload_known_extensions": True,
            },
        )

        # Install and load all extensions
        self._extensions_loaded = []
        for ext in DUCKDB_EXTENSIONS:
            try:
                self._connection.install_extension(ext)
                self._connection.load_extension(ext)
                self._extensions_loaded.append(ext)
            except Exception as exc:
                logger.debug("DuckDB extension %s unavailable: %s", ext, exc)

        logger.info(
            "DuckDB connection established version=%s extensions=%s",
            duckdb.__version__,
            ",".join(self._extensions_loaded),
        )

    async def connect(self) -> None:
        """Create and validate the DuckDB connection asynchronously."""
        try:
            await asyncio.to_thread(self._connect_sync)
        except Exception as exc:
            self._connection = None
            raise RuntimeError("DuckDB connection failed") from exc

    async def health_check(self) -> tuple[bool, str]:
        """Validate DuckDB is responsive."""
        try:
            if self._connection is None:
                await self.connect()
            result = await asyncio.to_thread(
                lambda: self._connection.execute("SELECT 1").fetchone()[0]
            )
            if result == 1:
                return True, f"DuckDB {duckdb.__version__} is ready"
            return False, "DuckDB returned unexpected result"
        except Exception as exc:
            return False, f"DuckDB is unavailable: {exc}"

    def execute(self, sql: str, parameters: list | None = None) -> list[tuple]:
        """Execute a SQL query and return all rows."""
        if parameters:
            return self.connection.execute(sql, parameters).fetchall()
        return self.connection.execute(sql).fetchall()

    def execute_df(self, sql: str, parameters: list | None = None) -> Any:
        """Execute a SQL query and return a pandas DataFrame."""
        if parameters:
            return self.connection.execute(sql, parameters).fetchdf()
        return self.connection.execute(sql).fetchdf()

    def query_csv(self, csv_path: str, sql: str | None = None) -> list[dict]:
        """Read a CSV file and optionally run SQL against it.

        When *sql* is None a default ``SELECT *`` with LIMIT 1000 is used.
        The table alias inside *sql* must be ``source``.
        """
        path = Path(csv_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        self.connection.execute(
            f"CREATE OR REPLACE TEMP VIEW source AS SELECT * FROM read_csv_auto('{path}')"
        )
        query = sql or "SELECT * FROM source LIMIT 1000"
        result = self.connection.execute(query)
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def list_extensions(self) -> list[dict]:
        """Return the status of every known extension."""
        rows = self.connection.execute(
            "SELECT extension_name, installed, loaded FROM duckdb_extensions()"
        ).fetchall()
        return [
            {"name": r[0], "installed": r[1], "loaded": r[2]} for r in rows
        ]

    async def close(self) -> None:
        """Release the DuckDB connection during shutdown."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("DuckDB connection closed")
