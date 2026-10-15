"""Schemas for RAG Pipeline (Phase 5.8)."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from backend.app.schemas.context_builder import ContextSource


class RetrievedChunk(BaseModel):
    """Normalized chunk representation used during retrieval and indexing."""
    chunk_id: str
    document_id: str = ""
    content: str
    score: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)



class RAGQueryRequest(BaseModel):
    """Incoming RAG query from a user or downstream agent."""
    query: str = Field(..., description="Natural language question")
    session_id: Optional[str] = Field(default=None, description="Conversation session identifier")
    top_k: int = Field(default=5, ge=1, description="Number of chunks to retrieve")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum retrieval score")
    use_hybrid: bool = Field(default=False, description="Use hybrid dense+BM25 retrieval")
    max_context_tokens: int = Field(default=3000, description="Maximum token budget for context")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Metadata retrieval filters")


class RAGResponse(BaseModel):
    """End-to-end RAG answer with citations and metrics."""
    query: str = Field(..., description="Original user query")
    answer: str = Field(..., description="Generated / assembled answer")
    sources: List[ContextSource] = Field(default_factory=list, description="Cited source chunks")
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Answer confidence estimate")
    context_tokens: int = Field(default=0, description="Token count of retrieved context")
    truncated: bool = Field(default=False, description="True if context was truncated")
    retrieval_strategy: str = Field(default="dense", description="Retrieval strategy used")


class RAGIngestRequest(BaseModel):
    """Request to ingest a pre-loaded document into the RAG pipeline."""
    document_id: str = Field(..., description="Source document UUID")
    content: str = Field(..., description="Normalized document text to ingest")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Document metadata")
    chunking_strategy: Optional[str] = Field(default="recursive", description="Chunking strategy to apply")
    chunk_size: int = Field(default=1000, description="Target chunk size")
    chunk_overlap: int = Field(default=200, description="Chunk overlap")


class RAGIngestResponse(BaseModel):
    """Response after ingesting a document into the RAG pipeline."""
    document_id: str
    chunks_created: int
    chunks_indexed: int
    status: str = "success"
