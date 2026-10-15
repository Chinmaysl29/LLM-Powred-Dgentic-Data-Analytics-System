"""RAG Service Layer (Phase 5.8)."""

from typing import Any, Dict, Optional
from functools import lru_cache
from uuid import UUID
from fastapi import Depends, Request
from backend.app.core.security import get_current_user
from backend.app.core.exceptions import ChromaConnectionError

from backend.app.schemas.rag_pipeline import (
    RAGIngestRequest,
    RAGIngestResponse,
    RAGQueryRequest,
    RAGResponse,
)
from backend.rag.rag_pipeline import RAGPipeline


@lru_cache(maxsize=128)
def get_pipeline(owner_id: str) -> RAGPipeline:
    # Identity comes from verified authentication, never metadata or filters.
    # Existing global rag_chunks remain quarantined and are not migrated here.
    owner = UUID(str(owner_id))
    from backend.rag.vectorstores.chromadb_store import ChromaDBStore
    from backend.app.core.config import get_settings
    settings = get_settings()
    try:
        store = ChromaDBStore(
            collection_name=f"rag_owner_{owner.hex}",
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
    except Exception as exc:
        raise ChromaConnectionError("RAG storage is unavailable") from exc
    return RAGPipeline(vector_store=store)


class RAGService:
    """High-level service interface for document ingestion and RAG querying."""

    def __init__(self, pipeline: Optional[RAGPipeline] = None, *, owner_id: str | None = None) -> None:
        # Route modules construct this service during ASGI import. Loading an
        # embedding model or connecting to Chroma must wait for an actual RAG
        # operation so unrelated health/auth routes can start independently.
        self._pipeline = pipeline
        self.owner_id = str(UUID(owner_id)) if owner_id else None

    @property
    def pipeline(self) -> RAGPipeline:
        if self.owner_id is None:
            raise PermissionError("Verified RAG owner is required")
        if self._pipeline is None:
            self._pipeline = get_pipeline(self.owner_id)
        return self._pipeline

    def ingest_document(
        self,
        document_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunking_strategy: str = "recursive",
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        auto_chunk: bool = True,
    ) -> RAGIngestResponse:
        meta = metadata or {}
        if auto_chunk and chunking_strategy is None and (chunk_size is None or chunk_size == 1000):
            try:
                from backend.rag.dynamic_chunking import get_dynamic_chunking_service
                dyn_svc = get_dynamic_chunking_service()
                fname = str(meta.get("file_name", "") or meta.get("filename", ""))
                ftype = str(meta.get("file_type", "") or meta.get("filetype", ""))
                dyn_cfg = dyn_svc.get_config(content, filename=fname, file_type=ftype)
                chunk_size = dyn_cfg.chunk_size
                chunk_overlap = dyn_cfg.chunk_overlap
                chunking_strategy = dyn_cfg.strategy
                meta["detected_category"] = dyn_cfg.category
            except Exception:
                chunk_size = chunk_size or 500
                chunk_overlap = chunk_overlap or 100
                chunking_strategy = "recursive"
        else:
            chunk_size = chunk_size or 500
            chunk_overlap = chunk_overlap or 100
            if chunking_strategy is None:
                chunking_strategy = "recursive"

        request = RAGIngestRequest(
            document_id=document_id,
            content=content,
            metadata=meta,
            chunking_strategy=chunking_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        return self.pipeline.ingest(request)

    def query(
        self,
        query: str,
        session_id: Optional[str] = None,
        top_k: int = 5,
        min_score: float = 0.0,
        use_hybrid: bool = False,
        max_context_tokens: int = 3000,
        filters: Optional[Dict[str, Any]] = None,
    ) -> RAGResponse:
        request = RAGQueryRequest(
            query=query,
            session_id=session_id,
            top_k=top_k,
            min_score=min_score,
            use_hybrid=use_hybrid,
            max_context_tokens=max_context_tokens,
            filters=filters,
        )
        return self.pipeline.query(request)

    def delete_document(self, document_id: str) -> None:
        """Remove a document from the scoped vector store."""
        self.pipeline.delete_document(document_id)



def get_rag_service(request: Request, current_user: Any = Depends(get_current_user)) -> RAGService:
    from backend.security.rbac import enforce_permission
    permission = 'write_dataset' if request.url.path.endswith('/ingest') else 'use_chat'
    enforce_permission(current_user.role, permission)
    return RAGService(owner_id=str(current_user.id))
