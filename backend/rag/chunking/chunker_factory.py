"""Chunker Factory and Registry (Phase 5.2)."""

from typing import Dict, List, Optional, Type
from backend.app.core.exceptions import InvalidChunkingStrategyError
from backend.app.schemas.chunking import ChunkingStrategy
from backend.rag.chunking.base_chunker import BaseChunker
from backend.rag.chunking.fixed_chunker import FixedSizeChunker
from backend.rag.chunking.recursive_chunker import RecursiveCharacterChunker
from backend.rag.chunking.semantic_chunker import SemanticChunker
from backend.rag.chunking.table_aware_chunker import TableAwareChunker


class ChunkerFactory:
    """Factory to create and resolve text chunker strategies."""

    _REGISTRY: Dict[str, Type[BaseChunker]] = {
        ChunkingStrategy.RECURSIVE.value: RecursiveCharacterChunker,
        ChunkingStrategy.SEMANTIC.value: SemanticChunker,
        ChunkingStrategy.TABLE_AWARE.value: TableAwareChunker,
        ChunkingStrategy.FIXED.value: FixedSizeChunker,
    }

    @classmethod
    def supported_strategies(cls) -> List[str]:
        """Return list of registered chunking strategy identifiers."""
        return list(cls._REGISTRY.keys())

    @classmethod
    def get_chunker(
        cls,
        strategy: Optional[str | ChunkingStrategy] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> BaseChunker:
        # Strategy omitted -> use explicit documented default (RECURSIVE)
        if strategy is None:
            strat_key = ChunkingStrategy.RECURSIVE.value
        elif isinstance(strategy, ChunkingStrategy):
            strat_key = strategy.value
        elif isinstance(strategy, str):
            strat_key = strategy.strip().lower()
            if not strat_key:
                raise InvalidChunkingStrategyError(
                    f"Unknown chunking strategy: '{strategy}'. Supported: {cls.supported_strategies()}"
                )
        else:
            raise InvalidChunkingStrategyError(
                f"Unknown chunking strategy: '{strategy}'. Supported: {cls.supported_strategies()}"
            )

        chunker_cls = cls._REGISTRY.get(strat_key)
        if not chunker_cls:
            raise InvalidChunkingStrategyError(
                f"Unknown chunking strategy: '{strategy}'. Supported: {cls.supported_strategies()}"
            )
        return chunker_cls(chunk_size=chunk_size, chunk_overlap=chunk_overlap)


