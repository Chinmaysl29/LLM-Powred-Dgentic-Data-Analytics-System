"""Independent Excel/Decimal oracle for golden fixtures; no app analytics imports."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from io import BytesIO
import re
from typing import Any

from openpyxl import load_workbook


def read_excel(raw: bytes, *, sheet_name: str, header_row: int, columns: list[str]) -> list[dict[str, Any]]:
    book = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    try:
        sheet = book[sheet_name]
        values = sheet.iter_rows(min_row=header_row + 1, values_only=True)
        if list(next(values)) != columns:
            raise ValueError("Golden source header changed")
        return [dict(zip(columns, row)) for row in values if any(value is not None for value in row)]
    finally:
        book.close()


def number(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not a financial measure")
    if isinstance(value, str):
        value = value.strip()
        if value.casefold() in {"", "na", "n/a", "null", "none", "-", "--"}:
            return None
        negative = value.startswith("(") and value.endswith(")")
        if negative:
            value = "-" + value[1:-1]
        value = re.sub(r"(?:Rs\.?|INR|USD|EUR|GBP|[₹$€£])\s*", "", value, flags=re.I)
        value = value.removesuffix("%").replace(",", "")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Unrecognized financial source value") from exc
    if not result.is_finite():
        raise ValueError("Non-finite source measure")
    return result


def expected_rows(rows: list[dict], operation: str, metric: str | None = None,
                  dimension: str | None = None, limit: int = 5) -> list[dict]:
    """Named operations only; never evaluate a formula supplied as text."""
    if operation == "count":
        return [{"records": str(len(rows))}]
    if operation not in {"sum", "average", "min", "max", "top"} or not metric:
        raise ValueError("Unsupported golden reference operation")
    groups: dict[Any, list[Decimal]] = defaultdict(list)
    if dimension is None:
        groups[None] = []
    for row in rows:
        key = row[dimension] if dimension else None
        groups[key]  # Retain groups whose measures are all missing.
        value = number(row[metric])
        if value is not None:
            groups[key].append(value)
    output = []
    with localcontext() as context:
        context.prec = 50
        for key, values in groups.items():
            if not values:
                result = None
            elif operation in {"sum", "top"}:
                result = sum(values, Decimal(0))
            elif operation == "average":
                result = sum(values, Decimal(0)) / len(values)
            elif operation == "min":
                result = min(values)
            else:
                result = max(values)
            item = {metric: None if result is None else str(result)}
            if dimension:
                item[dimension] = key
            output.append(item)
    if operation == "top":
        output.sort(key=lambda row: (row[metric] is None, -Decimal(row[metric]) if row[metric] is not None else Decimal(0), str(row[dimension])))
        output = output[:limit]
    return output
