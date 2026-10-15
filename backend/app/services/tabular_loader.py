"""Robust tabular data loader with smart header detection and financial numeric parsing.

Provides consistent, schema-aware DataFrame loading across CSV, TSV, Excel, Parquet,
and JSON files. Handles multi-row titles/banners, Indian comma formatting,
currency symbols, accounting negatives, and preserves identifier columns.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Regular expression to protect identifiers from aggressive numeric conversion
IDENTIFIER_PATTERN = re.compile(
    r"(?i)(?:^|[_ -])(id|identifier|zip|zipcode|postal|phone|telephone|account|code|sku)(?:$|[_ -])|Id$|ID$"
)


def is_identifier_column(name: str) -> bool:
    """Check whether a column name represents an identifier rather than a continuous measure."""
    return bool(IDENTIFIER_PATTERN.search(name.strip()))

# Currency and accounting prefixes/suffixes
CURRENCY_PREFIX_REGEX = re.compile(
    r"^[₹$€£]\s*|^(?:Rs\.?|INR|USD|EUR|GBP)\s*",
    flags=re.IGNORECASE
)


def parse_financial_value(val: Any) -> float | None:
    """Parse a single value into float, supporting financial conventions.
    
    Supports:
    - 12500, 12,500, 1,25,000 (Indian comma formatting)
    - ₹12,500, $12,500, Rs. 12,500, €12,500
    - -12500, (12,500) (accounting parentheses)
    - 0.25, 25% (percentages returned as numeric values)
    """
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if not np.isnan(val) else None
    if not isinstance(val, str):
        return None

    s = val.strip()
    if not s or s.lower() in {"n/a", "na", "null", "none", "-", "--"}:
        return None

    is_negative = False
    # Handle accounting parentheses: (12,500) -> -12500
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        is_negative = True
        s = s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()

    # Strip currency symbol or prefix
    s = CURRENCY_PREFIX_REGEX.sub("", s).strip()

    # Strip percent suffix
    if s.endswith("%"):
        s = s[:-1].strip()

    # Remove commas (Western 1,000,000 and Indian 1,00,000)
    s = s.replace(",", "")

    # Must match valid numeric string (integer or decimal)
    if not re.match(r"^\d+(\.\d+)?$", s):
        return None

    try:
        num = float(s)
        return -num if is_negative else num
    except (ValueError, OverflowError):
        return None


def detect_header_row(sample_df: pd.DataFrame) -> int:
    """Detect the true column header row index (0-based) from an untyped sample DataFrame.
    
    Handles files where row 0 is a title banner (e.g. 'Bluestock Fintech — Nifty 100 | Cash Flow')
    with mostly NaNs across other columns, while row 1 contains the actual column names.
    """
    if sample_df.empty or len(sample_df) < 2:
        return 0

    total_cols = sample_df.shape[1]
    best_row = 0
    max_score = -1.0

    # Inspect up to first 5 rows
    scan_limit = min(5, len(sample_df) - 1)
    for r_idx in range(scan_limit):
        row = sample_df.iloc[r_idx]
        non_null = row.dropna()
        non_null_count = len(non_null)

        # If row has only 1 non-null while file has > 2 columns, it is almost certainly a banner/title
        if non_null_count <= 1 and total_cols > 2:
            continue

        str_count = sum(1 for val in non_null if isinstance(val, str) and val.strip() != "")
        unique_count = len(set(str(v).strip().lower() for v in non_null))

        next_row = sample_df.iloc[r_idx + 1].dropna()
        has_numeric_data_after = any(
            isinstance(v, (int, float)) or (isinstance(v, str) and parse_financial_value(v) is not None)
            for v in next_row
        )

        score = (str_count / total_cols) * 2.0 + (unique_count / max(1, non_null_count)) + (1.0 if has_numeric_data_after else 0.0)

        # Heavily penalize if current row has significantly fewer non-nulls than the next row
        if len(next_row) > non_null_count * 1.5:
            score -= 2.0

        if score > max_score:
            max_score = score
            best_row = r_idx

    return best_row


def clean_and_infer_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean column names and infer financial numerics without mutating identifiers."""
    if df.empty:
        return df

    # 1. Clean column headers
    clean_columns = []
    seen = {}
    for col in df.columns:
        c_str = str(col).strip()
        if not c_str or c_str.lower().startswith("unnamed:"):
            c_str = f"column_{len(clean_columns) + 1}"
        # Ensure uniqueness
        if c_str in seen:
            seen[c_str] += 1
            clean_columns.append(f"{c_str}_{seen[c_str]}")
        else:
            seen[c_str] = 0
            clean_columns.append(c_str)
    df.columns = clean_columns

    # 2. Financial numeric inference on object columns
    for col in df.columns:
        # Do not convert protected identifiers
        if IDENTIFIER_PATTERN.search(col):
            continue

        if df[col].dtype == object:
            non_null_series = df[col].dropna()
            if len(non_null_series) == 0:
                continue

            # Sample up to 200 rows for type checking
            sample = non_null_series.iloc[:200]
            parsed_sample = [parse_financial_value(v) for v in sample]
            valid_count = sum(1 for p in parsed_sample if p is not None)

            # If >= 80% of sampled non-null values are financial numbers, parse the column
            if (valid_count / len(sample)) >= 0.8:
                converted = df[col].apply(parse_financial_value)
                df[col] = converted

    return df


def load_tabular_dataframe(
    path: str | Path,
    file_type: str | None = None,
    nrows: int | None = None,
    max_rows: int | None = None,
) -> pd.DataFrame:
    """Load a tabular file using smart header detection and financial numeric cleaning."""
    source_path = Path(path)
    limit = nrows if nrows is not None else max_rows

    if file_type:
        kind = file_type.lower().lstrip(".")
    else:
        ext = source_path.suffix.lower().lstrip(".")
        if ext in {"xlsx", "xls", "xlsm"}:
            kind = "excel"
        elif ext in {"tsv", "tab"}:
            kind = "tsv"
        elif ext == "parquet":
            kind = "parquet"
        elif ext in {"jsonl", "ndjson"}:
            kind = "jsonl"
        elif ext == "json":
            kind = "json"
        else:
            kind = "csv"

    if kind in {"xlsx", "xls", "excel"}:
        sample = pd.read_excel(source_path, header=None, nrows=10)
        h = detect_header_row(sample)
        df = pd.read_excel(source_path, header=h, nrows=limit)
    elif kind in {"csv", "tsv"}:
        sep = "\t" if kind == "tsv" else ","
        sample = pd.read_csv(source_path, sep=sep, header=None, nrows=10)
        h = detect_header_row(sample)
        df = pd.read_csv(source_path, sep=sep, header=h, nrows=limit)
    elif kind == "parquet":
        df = pd.read_parquet(source_path)
        if limit:
            df = df.head(limit)
    elif kind in {"jsonl", "ndjson"}:
        df = pd.read_json(source_path, lines=True, nrows=limit)
    elif kind == "json":
        df = pd.read_json(source_path)
        if limit:
            df = df.head(limit)
    else:
        raise ValueError(f"Unsupported tabular file type: {file_type or source_path.suffix}")

    return clean_and_infer_dataframe(df)
