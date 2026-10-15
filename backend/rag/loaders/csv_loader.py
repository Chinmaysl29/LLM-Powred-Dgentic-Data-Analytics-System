"""CSV Document Loader for RAG ingestion.

Parses comma-separated and tab-separated tabular data, converting
records into readable, semantically rich text representations for RAG.
"""

import io
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from backend.app.schemas.document_loader import LoadedDocument
from backend.rag.loaders.base_loader import BaseDocumentLoader

logger = logging.getLogger(__name__)


class CSVLoader(BaseDocumentLoader):
    """Loader parsing CSV and TSV files into semantically searchable text."""

    def supported_extensions(self) -> list[str]:
        return [".csv", ".tsv"]

    def load(
        self,
        file_input: str | Path | bytes,
        filename: str | None = None,
        max_rows_as_table: int = 500,
        **kwargs: Any,
    ) -> LoadedDocument:
        raw_bytes, resolved_name = self._read_bytes_and_filename(file_input, filename)
        logger.info("Loading CSV document '%s' (%d bytes)", resolved_name, len(raw_bytes))

        # Detect delimiter
        sep = "\t" if resolved_name.endswith(".tsv") else ","
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), sep=sep, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(raw_bytes), sep=sep, encoding="latin-1")

        row_count = len(df)
        col_count = len(df.columns)
        col_names = [str(c) for c in df.columns]

        sections = [
            f"# Tabular Dataset: {resolved_name}",
            f"Attributes: {', '.join(col_names)} ({row_count:,} rows, {col_count} columns)",
            "",
            "## Summary Preview:",
        ]

        # Markdown table representation for the first N rows
        preview_df = df.head(max_rows_as_table)
        try:
            sections.append(preview_df.to_markdown(index=False))
        except (ImportError, ModuleNotFoundError, Exception):
            headers = "| " + " | ".join(col_names) + " |"
            sep_line = "| " + " | ".join(["---"] * len(col_names)) + "|"
            rows = ["| " + " | ".join(str(val) for val in row) + " |" for row in preview_df.values]
            sections.append("\n".join([headers, sep_line] + rows))

        if row_count > max_rows_as_table:
            sections.append(f"\n*(Truncated: showing first {max_rows_as_table} of {row_count:,} total records)*")

        full_text = "\n".join(sections)
        normalized_content = self.normalize_text(full_text)

        metadata = self.build_metadata(
            filename=resolved_name,
            file_type="csv" if not resolved_name.endswith(".tsv") else "tsv",
            size=len(raw_bytes),
            content=normalized_content,
            row_count=row_count,
            column_count=col_count,
            extra={"column_names": col_names},
        )

        return LoadedDocument(
            document_id=str(uuid4()),
            content=normalized_content,
            metadata=metadata,
        )
