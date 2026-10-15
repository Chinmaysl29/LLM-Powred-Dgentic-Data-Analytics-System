"""Pure NumPy In-Memory Vector Store (Phase 5.4).

Zero external dependencies — pure numpy cosine similarity index.
"""

from typing import Any, Dict, List, Optional
import numpy as np

from backend.app.schemas.vector_store import IndexStats, VectorSearchResult
from backend.rag.vectorstores.base_store import BaseVectorStore


class InMemoryVectorStore(BaseVectorStore):
    """Fast in-memory vector store using NumPy L2-normalised dot-product search."""

    def __init__(self) -> None:
        self._chunk_ids: List[str] = []
        self._document_ids: List[str] = []
        self._texts: List[str] = []
        self._metadatas: List[Dict[str, Any]] = []
        self._matrix: Optional[np.ndarray] = None  # (N, D) float32
        self._dimension: int = 0

    def _matches_filter(self, metadata: Dict[str, Any], filters: Optional[Dict[str, Any]]) -> bool:
        if not filters:
            return True
        return all(str(metadata.get(k)) == str(v) for k, v in filters.items())

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
        if metadatas is None:
            metadatas = [{} for _ in embeddings]

        if not (len(chunk_ids) == len(document_ids) == len(texts) == len(embeddings) == len(metadatas)):
            raise ValueError("Vector index batch lengths do not match")
        new_matrix = np.array(embeddings, dtype=np.float32)
        if new_matrix.ndim != 2 or not np.isfinite(new_matrix).all():
            raise ValueError("Embedding vectors must be a finite rectangular matrix")
        if self._dimension and new_matrix.shape[1] != self._dimension:
            raise ValueError("Embedding dimension mismatch")
        # Match persistent-store upsert behavior, including idempotent job retries.
        self.delete(chunk_ids=chunk_ids)
        # L2 normalize rows
        norms = np.linalg.norm(new_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        new_matrix = new_matrix / norms

        if self._matrix is None:
            self._matrix = new_matrix
            self._dimension = new_matrix.shape[1]
        else:
            self._matrix = np.vstack([self._matrix, new_matrix])

        self._chunk_ids.extend(chunk_ids)
        self._document_ids.extend(document_ids)
        self._texts.extend(texts)
        self._metadatas.extend(metadatas)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        min_score: float = 0.0,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        if self._matrix is None or len(self._chunk_ids) == 0:
            return []

        q = np.array(query_vector, dtype=np.float32)
        norm = np.linalg.norm(q)
        if norm > 0:
            q = q / norm

        scores = self._matrix @ q  # cosine similarities

        # Apply filters — mask out non-matching rows
        results: List[VectorSearchResult] = []
        for i, score in enumerate(scores.tolist()):
            if score < min_score:
                continue
            if not self._matches_filter(self._metadatas[i], filters):
                continue
            results.append(
                VectorSearchResult(
                    chunk_id=self._chunk_ids[i],
                    document_id=self._document_ids[i],
                    content=self._texts[i],
                    score=max(0.0, min(1.0, float(score))),
                    metadata=self._metadatas[i],
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def delete(self, chunk_ids: Optional[List[str]] = None, document_id: Optional[str] = None) -> None:
        if document_id:
            keep_indices = [i for i, did in enumerate(self._document_ids) if did != document_id]
        elif chunk_ids:
            ids_to_remove = set(chunk_ids)
            keep_indices = [i for i, cid in enumerate(self._chunk_ids) if cid not in ids_to_remove]
        else:
            return
        if not keep_indices:
            self.clear()
            return

        self._chunk_ids = [self._chunk_ids[i] for i in keep_indices]
        self._document_ids = [self._document_ids[i] for i in keep_indices]
        self._texts = [self._texts[i] for i in keep_indices]
        self._metadatas = [self._metadatas[i] for i in keep_indices]
        self._matrix = self._matrix[keep_indices] if self._matrix is not None else None

    def clear(self) -> None:
        self._chunk_ids = []
        self._document_ids = []
        self._texts = []
        self._metadatas = []
        self._matrix = None
        self._dimension = 0

    def stats(self) -> IndexStats:
        return IndexStats(
            total_vectors=len(self._chunk_ids),
            dimension=self._dimension,
            index_type="in_memory_numpy",
            collections=[],
        )
