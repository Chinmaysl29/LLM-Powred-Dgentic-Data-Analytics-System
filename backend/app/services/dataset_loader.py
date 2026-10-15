"""Canonical dataset loader used by agents and analytics services."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.models.dataset import Dataset


class DatasetLoader:
    def load_dataframe(self, dataset: Dataset) -> pd.DataFrame:
        from backend.app.services.tabular_loader import load_tabular_dataframe

        # 1. Parquet canonical or source format
        if dataset.canonical_format == "parquet" and dataset.canonical_path and Path(dataset.canonical_path).exists():
            return pd.read_parquet(dataset.canonical_path)

        # 2. Check JSON canonical or processed artifacts
        for p in (dataset.json_path, dataset.canonical_path):
            if p and Path(p).exists() and str(p).endswith(".json"):
                try:
                    payload = json.loads(Path(p).read_text(encoding="utf-8"))
                    if isinstance(payload, list):
                        return pd.DataFrame(payload)
                    if isinstance(payload, dict):
                        if "records" in payload and isinstance(payload["records"], list):
                            return pd.DataFrame(payload["records"])
                        elif "data" in payload and isinstance(payload["data"], list):
                            return pd.DataFrame(payload["data"])
                except Exception:
                    pass

        # 3. Tabular loader from canonical, original, or raw file path
        for p in (dataset.canonical_path, dataset.original_path, dataset.file_path):
            if p and Path(p).exists():
                try:
                    return load_tabular_dataframe(p, file_type=dataset.file_type)
                except Exception as exc:
                    logger = logging.getLogger(__name__)
                    logger.warning("Failed to load tabular data from %s: %s", p, exc)

        raise ValueError(f"Dataset '{dataset.dataset_name}' has no accessible tabular artifact or source file")

    def load_document(self, dataset: Dataset) -> dict[str, Any]:
        for p in (dataset.json_path, dataset.canonical_path, dataset.original_path, dataset.file_path):
            if p and Path(p).exists():
                if str(p).endswith(".json"):
                    return json.loads(Path(p).read_text(encoding="utf-8"))
                elif str(p).endswith((".txt", ".md", ".markdown")):
                    content = Path(p).read_text(encoding="utf-8", errors="replace")
                    return {"text": content, "source": str(p)}
        raise ValueError(f"Document dataset '{dataset.dataset_name}' has no accessible document artifact")
