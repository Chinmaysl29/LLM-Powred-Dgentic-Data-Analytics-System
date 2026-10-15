"""ChromaDB Persistent Vector Store (Phase 5.4)."""

import uuid
from typing import Any, Dict, List, Optional

from backend.app.schemas.vector_store import IndexStats, VectorSearchResult
from backend.rag.vectorstores.base_store import BaseVectorStore
from backend.app.core.exceptions import ChromaConnectionError

try:
    import chromadb
    from chromadb.config import Settings
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False


class ChromaDBStore(BaseVectorStore):
    """ChromaDB persistent vector store with collection management."""

    def __init__(
        self,
        collection_name: str = "rag_chunks",
        persist_directory: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        client: Optional[Any] = None,
        embedding_model: Optional[str] = None,
        expected_dimension: Optional[int] = None,
    ) -> None:
        if not _CHROMA_AVAILABLE:
            raise RuntimeError("chromadb package is not installed.")

        self._collection_name = collection_name
        self._dimension: int = 0

        try:
            if client is not None:
                self._client = client
            elif host:
                self._client = chromadb.HttpClient(host=host, port=port or 8000)
            elif persist_directory:
                self._client = chromadb.PersistentClient(path=persist_directory)
            else:
                from backend.app.core.config import get_settings
                settings = get_settings()
                if settings.chroma_host:
                    self._client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
                else:
                    self._client = chromadb.PersistentClient(path=str(settings.upload_dir + "/embeddings/chroma"))

            if host or (client is None and not persist_directory):
                from backend.rag.vectorstores.compatibility import verify_chroma_compatibility
                verify_chroma_compatibility(self._client, chromadb.__version__)
            expected_metadata = {"hnsw:space": "cosine"}
            if embedding_model:
                expected_metadata['embedding_model'] = embedding_model
            if expected_dimension:
                expected_metadata['embedding_dimension'] = expected_dimension
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata=expected_metadata,
            )
            metadata = self._collection.metadata or {}
            if metadata.get('hnsw:space', 'cosine') != 'cosine':
                raise ChromaConnectionError('Collection distance metric is incompatible')
            if embedding_model and metadata.get('embedding_model') != embedding_model:
                raise ChromaConnectionError('Collection embedding model is incompatible')
            if expected_dimension:
                if metadata.get('embedding_dimension') != expected_dimension:
                    raise ChromaConnectionError('Collection embedding dimensions are incompatible')
                if self._collection.count():
                    sample = self._collection.get(limit=1, include=['embeddings'])['embeddings']
                    if sample is None or len(sample[0]) != expected_dimension:
                        raise ChromaConnectionError('Stored embedding dimensions are incompatible')
                self._dimension = expected_dimension
        except Exception as exc:
            if isinstance(exc, ChromaConnectionError):
                raise
            raise ChromaConnectionError(f"ChromaDB persistent store initialization failed for '{collection_name}': {exc}") from exc

    def add(
        self,
        chunk_ids: List[str],
        document_ids: List[str],
        texts: List[str],
        embeddings: List[List[float]],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        if not embeddings:
            return
        dim = len(embeddings[0])
        if self._dimension == 0:
            self._dimension = dim
        elif dim != self._dimension:
            raise ValueError(
                f"Embedding dimension mismatch: cannot add {dim}-dimensional vector to {self._dimension}-dimensional collection"
            )

        if metadatas is None:
            metadatas = [{} for _ in embeddings]

        # ChromaDB metadatas must be flat str/int/float/bool dicts
        safe_metas = []
        for m, doc_id in zip(metadatas, document_ids):
            flat = {"document_id": doc_id}
            for k, v in (m or {}).items():
                if k == "extra" and isinstance(v, dict):
                    for ek, ev in v.items():
                        if isinstance(ev, (str, int, float, bool)):
                            flat[ek] = ev
                        elif ev is not None:
                            flat[ek] = str(ev)
                elif isinstance(v, (str, int, float, bool)):
                    flat[k] = v
                elif v is not None:
                    flat[k] = str(v)
            safe_metas.append(flat)

        self._collection.upsert(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=safe_metas,
        )

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        min_score: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        if self._dimension > 0 and len(query_vector) != self._dimension:
            raise ValueError(
                f"Embedding dimension mismatch: query vector has dimension {len(query_vector)}, but collection requires {self._dimension}"
            )

        count = self._collection.count()
        if count == 0:
            return []

        where = None
        if filters:
            # Convert to ChromaDB where clause
            where = {"$and": [{k: {"$eq": v}} for k, v in filters.items()]} if len(filters) > 1 else filters

        n_results = min(top_k, count)
        try:
            result = self._collection.query(
                query_embeddings=[query_vector],
                n_results=n_results,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise ChromaConnectionError("Vector retrieval failed") from exc

        results: List[VectorSearchResult] = []
        for chunk_id, doc, meta, dist in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
        ):
            # ChromaDB cosine distance: score = 1 - distance
            score = max(0.0, min(1.0, 1.0 - float(dist)))
            if score < min_score:
                continue
            results.append(
                VectorSearchResult(
                    chunk_id=chunk_id,
                    document_id=meta.get("document_id", ""),
                    content=doc,
                    score=score,
                    metadata=meta,
                )
            )

        return results

    def delete(self, chunk_ids: Optional[List[str]] = None, document_id: Optional[str] = None) -> None:
        if chunk_ids:
            self._collection.delete(ids=chunk_ids)
        elif document_id:
            try:
                self._collection.delete(where={"document_id": document_id})
            except Exception:
                pass


    def clear(self) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._dimension = 0

    def stats(self) -> IndexStats:
        count = self._collection.count()
        collections = [col if isinstance(col, str) else getattr(col, "name", str(col)) for col in self._client.list_collections()]
        return IndexStats(
            total_vectors=count,
            dimension=self._dimension,
            index_type="chromadb_hnsw_cosine",
            collections=collections,
        )
