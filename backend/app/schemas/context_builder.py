"""Schemas for Context Builder (Phase 18.6.2 — RAG Grounding 2.0)."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ContextSource(BaseModel):
    """Attributed source citation for a retrieved context passage.

    Phase 18.6.2 upgrade: full_content added for grounding validation.
    preview retained for UI display. Lineage fields added for citation tracking.
    """
    source_id: str = Field(..., description="Citation label e.g. '[Source 1]'")
    chunk_id: str = Field(..., description="UUID of the originating chunk")
    document_id: str = Field(..., description="UUID of the parent document")
    citation_url: Optional[str] = Field(default=None, description='Authenticated immutable source endpoint')
    filename: Optional[str] = Field(default=None, description="Original filename")
    file_type: Optional[str] = Field(default=None, description="File type")
    score: float = Field(..., description="Relevance score of the source [0.0, 1.0]")

    # UI display
    preview: str = Field(..., description="Short content preview (first 120 chars) for UI")

    # Grounding validation (Phase 18.6.2)
    full_content: str = Field(default="", description="Complete chunk text for grounding validation and fact-checking")

    # Document lineage
    page_number: Optional[int] = Field(default=None, description="Page number within source document (PDF etc.)")
    char_offset: Optional[int] = Field(default=None, description="Character offset of chunk within full document")

    # Citation tracking
    citation_ref: str = Field(default="", description="Structured citation reference string for report generation")

    # Source metadata passthrough
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw chunk metadata from vector store")

    @property
    def content(self) -> str:
        """Convenience property for accessing chunk text."""
        return self.full_content if self.full_content else self.preview


class BuiltContext(BaseModel):
    """Assembled, token-budgeted, citation-attributed context ready for LLM."""
    formatted_text: str = Field(..., description="Full concatenated context text with citations")
    sources: List[ContextSource] = Field(default_factory=list, description="Source citations")
    token_count: int = Field(..., description="Estimated total tokens in formatted_text")
    truncated: bool = Field(default=False, description="True if context was truncated due to token limit")
    chunk_count: int = Field(..., description="Number of chunks included")
