"""Excel (XLSX, XLS) Document Loader for RAG ingestion.

Parses multi-sheet workbooks using openpyxl and pandas, converting
each worksheet into structured sections and markdown tables.
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


class XlsxLoader(BaseDocumentLoader):
    """Loader extracting text across worksheets in Excel workbooks."""

    def supported_extensions(self) -> list[str]:
        return [".xlsx", ".xls"]

    def load(
        self,
        file_input: str | Path | bytes,
        filename: str | None = None,
        max_rows_per_sheet: int = 250,
        **kwargs: Any,
    ) -> LoadedDocument:
        raw_bytes, resolved_name = self._read_bytes_and_filename(file_input, filename)
        logger.info("Loading Excel workbook '%s' (%d bytes)", resolved_name, len(raw_bytes))

        stream = io.BytesIO(raw_bytes)
        excel_file = pd.ExcelFile(stream)
        sheet_names = excel_file.sheet_names

        sections: list[str] = [f"# Workbook: {resolved_name}", f"Worksheets ({len(sheet_names)}): {', '.join(sheet_names)}", ""]
        total_rows = 0

        for sheet in sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet)
            sheet_rows = len(df)
            total_rows += sheet_rows
            col_count = len(df.columns)

            sections.append(f"## Worksheet: {sheet} ({sheet_rows:,} rows, {col_count} columns)")
            if not df.empty:
                preview = df.head(max_rows_per_sheet)
                try:
                    sections.append(preview.to_markdown(index=False))
                except (ImportError, ModuleNotFoundError, Exception):
                    col_names = [str(c) for c in preview.columns]
                    headers = "| " + " | ".join(col_names) + " |"
                    sep_line = "| " + " | ".join(["---"] * len(col_names)) + "|"
                    rows = ["| " + " | ".join(str(val) for val in row) + " |" for row in preview.values]
                    sections.append("\n".join([headers, sep_line] + rows))
                if sheet_rows > max_rows_per_sheet:
                    sections.append(f"*(Truncated: showing first {max_rows_per_sheet} of {sheet_rows:,} rows)*")
            else:
                sections.append("*(Sheet is empty)*")
            sections.append("")

        full_text = "\n".join(sections)
        normalized_content = self.normalize_text(full_text)

        ext = Path(resolved_name).suffix.lstrip(".").lower() or "xlsx"
        metadata = self.build_metadata(
            filename=resolved_name,
            file_type=ext,
            size=len(raw_bytes),
            content=normalized_content,
            sheet_names=sheet_names,
            row_count=total_rows,
        )

        return LoadedDocument(
            document_id=str(uuid4()),
            content=normalized_content,
            metadata=metadata,
        )
