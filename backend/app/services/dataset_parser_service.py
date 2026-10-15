"""Parse supported source files into safe tabular or document representations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class ParsedDataset:
    dataframe: pd.DataFrame | None
    document: dict[str, Any] | None = None


class DatasetParserService:
    """Single parser boundary for CSV, Excel, JSON, and PDF uploads."""

    def parse(self, path: str | Path, file_type: str) -> ParsedDataset:
        source = Path(path)
        normalized_type = file_type.lower().lstrip(".")
        if normalized_type in {"csv", "tsv", "xlsx", "xls", "json", "jsonl", "ndjson", "parquet"}:
            from backend.app.services.tabular_loader import load_tabular_dataframe
            return ParsedDataset(load_tabular_dataframe(source, normalized_type))
        if normalized_type == "pdf":
            return ParsedDataset(None, self._parse_pdf(source))
        if normalized_type in {"txt", "text", "md", "markdown"}:
            return ParsedDataset(None, self._parse_text(source))
        raise ValueError(f"Unsupported dataset file type: {file_type}")

    @staticmethod
    def _parse_text(source: Path) -> dict[str, Any]:
        text_content = source.read_text(encoding="utf-8", errors="replace")
        lines = text_content.splitlines()
        return {
            "pages": [{"page": 1, "text": text_content}],
            "text": text_content,
            "line_count": len(lines),
            "tables": [],
        }

    @staticmethod
    def _parse_pdf(source: Path) -> dict[str, Any]:
        try:
            import fitz
        except ImportError as exc:  # pragma: no cover - production dependency
            raise RuntimeError("PDF parsing requires PyMuPDF") from exc
        document = fitz.open(source)
        pages: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        full_text_list: list[str] = []
        for number, page in enumerate(document, start=1):
            page_text = page.get_text("text") or ""
            pages.append({"page": number, "text": page_text})
            if page_text.strip():
                full_text_list.append(page_text.strip())
            try:
                for table in page.find_tables().tables:
                    tables.append({"page": number, "records": table.extract()})
            except (AttributeError, RuntimeError):
                pass
        return {"pages": pages, "text": "\n\n".join(full_text_list), "tables": tables}
