"""ChromaDB HTTP adapter and collection manager for future RAG services."""

import asyncio
import logging
from typing import Any

import chromadb

from backend.app.core.config import Settings
from backend.app.core.exceptions import ChromaConnectionError

logger = logging.getLogger(__name__)


class ChromaDatabase:
    """Manage one ChromaDB HTTP client for the application process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: chromadb.ClientAPI | None = None

    @property
    def client(self) -> chromadb.ClientAPI:
        """Return the initialized ChromaDB client."""
        if self._client is None:
            raise ChromaConnectionError("ChromaDB connection has not been initialized")
        return self._client

    def _connect_sync(self) -> None:
        if self._client is None:
            self._client = chromadb.HttpClient(
                host=self._settings.chroma_host,
                port=self._settings.chroma_port,
            )
        self._client.heartbeat()

    async def connect(self) -> None:
        """Create and validate the ChromaDB HTTP client."""
        try:
            await asyncio.to_thread(self._connect_sync)
            logger.info("ChromaDB connection established")
        except Exception as exc:
            self._client = None
            raise ChromaConnectionError("ChromaDB connection validation failed") from exc

    async def health_check(self) -> tuple[bool, str]:
        """Validate ChromaDB reachability."""
        try:
            await self.connect()
            return True, "ChromaDB is reachable"
        except ChromaConnectionError:
            return False, "ChromaDB is unavailable"

    async def indexing_health_check(self) -> tuple[bool, str]:
        """Reachability alone does not establish indexing protocol compatibility."""
        from backend.rag.vectorstores.compatibility import verify_chroma_compatibility
        try:
            await self.connect()
            versions = await asyncio.to_thread(verify_chroma_compatibility, self.client, chromadb.__version__)
            return True, f"Verified Chroma {versions['client_version']} pairing; collection checked on use"
        except ChromaConnectionError:
            return False, 'RAG indexing unavailable: dependency incompatible or unreachable'

    async def get_or_create_collection(self, name: str, metadata: dict[str, Any] | None = None) -> Any:
        """Create a named collection lazily for a future RAG feature."""
        try:
            return await asyncio.to_thread(self.client.get_or_create_collection, name, metadata)
        except Exception as exc:
            raise ChromaConnectionError("ChromaDB collection operation failed") from exc

    async def close(self) -> None:
        """Release the local ChromaDB client reference during shutdown."""
        self._client = None
        logger.info("ChromaDB client closed")
