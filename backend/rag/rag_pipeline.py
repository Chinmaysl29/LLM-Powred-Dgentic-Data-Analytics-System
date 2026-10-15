"""End-to-End RAG Pipeline Orchestrator (Phase 5.8)."""

from hashlib import sha256
import json
from pathlib import Path

from typing import Any, Callable, Dict, List, Optional

from backend.app.schemas.context_builder import BuiltContext
from backend.app.schemas.rag_pipeline import (
    RAGIngestRequest,
    RAGIngestResponse,
    RAGQueryRequest,
    RAGResponse,
)
from backend.rag.chunking.chunker_factory import ChunkerFactory
from backend.rag.context_builder import ContextBuilder
from backend.rag.embeddings.base_embedding import BaseEmbedding
from backend.rag.embeddings.miniLM_embedding import MiniLMEmbedding
from backend.rag.knowledge_validation import KnowledgeValidator
from backend.rag.memory.conversation_memory import ConversationMemory
from backend.rag.memory.query_rewriter import QueryRewriter
from backend.rag.retrievers.bm25_retriever import BM25Retriever
from backend.rag.retrievers.hybrid_retriever import HybridRetriever
from backend.rag.retrievers.vector_retriever import VectorRetriever
from backend.rag.vectorstores.base_store import BaseVectorStore
from backend.rag.vectorstores.in_memory_store import InMemoryVectorStore


class RAGPipeline:
    """Orchestrates the full RAG lifecycle: Ingest → Retrieve → Context Build → Answer."""

    def __init__(
        self,
        embedding_model: Optional[BaseEmbedding] = None,
        vector_store: Optional[BaseVectorStore] = None,
        max_context_tokens: int = 3000,
        sparse_index_path: str | Path | None = None,
    ) -> None:
        self._embedder = embedding_model or MiniLMEmbedding()
        self._store = vector_store if vector_store is not None else InMemoryVectorStore()
        self._bm25 = BM25Retriever(storage_path=sparse_index_path)
        self._dense_retriever = VectorRetriever(self._embedder, self._store)
        self._hybrid_retriever = HybridRetriever(self._dense_retriever, self._bm25, alpha=0.7)
        self._context_builder = ContextBuilder(max_tokens=max_context_tokens)
        self._memory = ConversationMemory()
        self._rewriter = QueryRewriter()
        self._validator = KnowledgeValidator()

    def ingest(self, request: RAGIngestRequest, progress: Callable[[str], None] | None = None) -> RAGIngestResponse:
        """Chunk, embed, and index a document into the pipeline."""
        if progress:
            progress("CHUNKING")
        chunker = ChunkerFactory.get_chunker(
            strategy=request.chunking_strategy,
            chunk_size=request.chunk_size,
            chunk_overlap=min(request.chunk_overlap, request.chunk_size - 1),
        )
        chunks = chunker.split_text(
            request.content,
            document_id=request.document_id,
            metadata=request.metadata or {},
        )

        if not chunks:
            return RAGIngestResponse(
                document_id=request.document_id,
                chunks_created=0,
                chunks_indexed=0,
                status="empty",
            )

        texts = [c.content for c in chunks]
        version = (request.metadata or {}).get("document_version") or sha256(request.content.encode("utf-8")).hexdigest()
        fingerprint = json.dumps([request.document_id, str(version), request.chunking_strategy,
                                  request.chunk_size, request.chunk_overlap], separators=(",", ":"))
        chunk_ids = [sha256(f"{fingerprint}:{i}:{c.content}".encode("utf-8")).hexdigest()
                     for i, c in enumerate(chunks)]
        doc_ids = [c.document_id for c in chunks]
        metadatas = []
        for c in chunks:
            meta = c.metadata.model_dump()
            meta.update(meta.pop("extra", {}))
            meta.update(document_id=request.document_id, document_version=version)
            metadatas.append(meta)

        # Embed and index in vector store
        if progress:
            progress("EMBEDDING")
        embeddings = self._embedder.embed_documents(texts)
        if progress:
            progress("INDEXING")
        # Upsert deterministic IDs; never remove the last valid document version.
        # A durable job may retry after either index fails. Sparse publication is
        # atomic and happens only after the dense batch has completed.
        self._store.add(
            chunk_ids=chunk_ids,
            document_ids=doc_ids,
            texts=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # Index in BM25
        self._bm25.index(
            chunk_ids=chunk_ids,
            document_ids=doc_ids,
            texts=texts,
            metadatas=metadatas,
        )

        return RAGIngestResponse(
            document_id=request.document_id,
            chunks_created=len(chunks),
            chunks_indexed=len(chunks),
            status="success",
        )

    def query(self, request: RAGQueryRequest) -> RAGResponse:
        """Execute a full RAG query cycle and return an answer with citations."""
        query_text = request.query

        # Query rewriting with conversation memory
        if request.session_id:
            history = self._memory.get_history(request.session_id)
            if history:
                query_text = self._rewriter.rewrite(query_text, history)

        # Retrieval
        if request.use_hybrid:
            retriever = self._hybrid_retriever
            strategy = "hybrid"
        else:
            retriever = self._dense_retriever
            strategy = "dense"

        raw_chunks = retriever.retrieve(
            query=query_text,
            top_k=request.top_k,
            min_score=request.min_score,
            filters=request.filters,
        )

        # Build context
        context: BuiltContext = self._context_builder.build(
            results=raw_chunks,
            max_tokens=request.max_context_tokens,
        )

        # Generate answer (context assembly mode — LLM integration point)
        if context.formatted_text:
            answer = self._assemble_answer(request.query, context.formatted_text, context.sources)
            confidence = sum(s.score for s in context.sources) / max(1, len(context.sources))
        else:
            answer = "No relevant documents found for your query."
            confidence = 0.0

        # Store in conversation memory
        if request.session_id:
            from backend.app.schemas.memory import MessageRole
            self._memory.add_message(request.session_id, MessageRole.USER, request.query)
            self._memory.add_message(request.session_id, MessageRole.ASSISTANT, answer)

        return RAGResponse(
            query=request.query,
            answer=answer,
            sources=context.sources,
            confidence_score=round(min(1.0, confidence), 3),
            context_tokens=context.token_count,
            truncated=context.truncated,
            retrieval_strategy=strategy,
        )

    def _assemble_answer(self, query: str, context_text: str, sources: list) -> str:
        """Context-assembly answer (LLM synthesis integration point)."""
        citation_block = self._context_builder.format_citations(sources) if sources else ""
        answer = (
            f"Based on the retrieved documents:\n\n"
            f"{context_text[:2000]}"
        )
        if citation_block:
            answer += f"\n\n{citation_block}"
        return answer

    def validate_answer(self, answer: str, context_text: str, sources: Optional[list] = None):
        """Run knowledge validation on a generated answer."""
        return self._validator.validate(answer, context_text, sources)

    def delete_document(self, document_id: str) -> None:
        """Remove all chunks and indices for a specific document."""
        self._store.delete(document_id=document_id)
        if hasattr(self._bm25, "delete"):
            self._bm25.delete(document_id=document_id)

