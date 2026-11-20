"""Normalize SQLAlchemy reflection at the boundary of the public schema contract."""

from collections.abc import Mapping

from pydantic import JsonValue, TypeAdapter, ValidationError
from sqlalchemy.sql.elements import TextClause

from backend.app.schemas.schema_reader import IndexKey, IndexMetadata

_json_value = TypeAdapter(JsonValue)
_sorts = {"asc", "desc", "nulls_first", "nulls_last"}


def normalize_index(raw: Mapping[str, object]) -> IndexMetadata:
    """Preserve key positions without treating expression placeholders as columns.

    SQLAlchemy's expressions list, when supplied, is aligned with column_names
    and contains BOTH column names and SQL expressions. Never compact it before
    matching positions. Unknown optional metadata is reported explicitly.
    """
    warnings: list[str] = []

    def sequence(value: object, field: str) -> list:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return list(value)
        warnings.append(f"{field} was not a sequence.")
        return []

    names = sequence(raw.get("column_names"), "column_names")
    expressions = sequence(raw.get("expressions"), "expressions")
    if not names and not expressions:
        warnings.append("Index key metadata was not returned by the database driver.")
    if expressions and len(expressions) != len(names):
        warnings.append("Index column and expression counts differ; unavailable keys are unknown.")
    options: dict[str, JsonValue] = {}
    raw_options = raw.get("dialect_options")
    if raw_options is not None:
        if isinstance(raw_options, Mapping):
            for key, value in raw_options.items():
                try:
                    if not isinstance(key, str):
                        raise ValueError("Invalid option name")
                    if isinstance(value, TextClause):
                        value = str(value)
                    options[key] = _json_value.validate_python(value)
                except (ValidationError, ValueError):
                    warnings.append("An unsupported dialect option could not be represented.")
        else:
            warnings.append("dialect_options was not a mapping.")

    included = sequence(raw.get("include_columns") or options.get("postgresql_include"), "include_columns")
    include_columns = [name for name in included if isinstance(name, str) and name]
    if len(include_columns) != len(included):
        warnings.append("Some included column names were unavailable.")
    sorting = raw.get("column_sorting") or {}
    if not isinstance(sorting, Mapping):
        warnings.append("column_sorting was not a mapping.")
        sorting = {}

    keys: list[IndexKey] = []
    for position in range(max(len(names), len(expressions))):
        name = names[position] if position < len(names) else None
        expression = expressions[position] if position < len(expressions) else None
        if isinstance(name, str) and name:
            kind, column, sql = "column", name, None
        elif name is None and isinstance(expression, str) and expression:
            kind, column, sql = "expression", None, expression
        else:
            kind, column, sql = "unknown", None, None
            warnings.append(f"Index key {position + 1} has unavailable or invalid reflection metadata.")
        sort = sequence(sorting.get(column or sql), "key sorting")
        valid_sort = [value for value in sort if isinstance(value, str) and value in _sorts]
        if len(sort) != len(valid_sort):
            warnings.append(f"Index key {position + 1} has unsupported sorting metadata.")
        keys.append(IndexKey(position=position, kind=kind, column_name=column, expression=sql, sorting=valid_sort))

    predicate = options.get("postgresql_where", options.get("sqlite_where"))
    if predicate is not None and not isinstance(predicate, str):
        warnings.append("The partial-index predicate was unavailable.")
        predicate = None
    return IndexMetadata(
        name=raw.get("name"),
        columns=[key.column_name for key in keys if key.kind == "column"],
        unique=raw.get("unique") if raw.get("unique") is not None else False,
        keys=keys,
        include_columns=include_columns,
        predicate=predicate,
        dialect_options=options,
        duplicates_constraint=raw.get("duplicates_constraint"),
        warnings=warnings,
    )
