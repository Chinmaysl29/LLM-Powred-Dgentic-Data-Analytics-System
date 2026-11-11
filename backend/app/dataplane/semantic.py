"""Compile an explicitly registered metric; never invent business definitions."""
from backend.app.dataplane.contracts import Metric, QueryPlan


def quote(name: str) -> str:
    if not name or len(name) > 128 or "\x00" in name:
        raise ValueError("Invalid identifier")
    return '"' + name.replace('"', '""') + '"'


def compile_plan(plan: QueryPlan, metric: Metric, schema: dict[str, str], *, table="source"):
    if plan.metric != metric.name:
        raise ValueError("Metric version does not match plan")
    if len(set(plan.dimensions)) != len(plan.dimensions):
        raise ValueError("Repeated dimension")
    if "value" in plan.dimensions:
        raise ValueError("Dimension name 'value' conflicts with the aggregate output name")
    used = [*plan.dimensions, *(f.column for f in plan.filters)]
    if metric.column:
        used.append(metric.column)
    if any(column not in schema for column in used):
        raise ValueError("Unknown column")
    if metric.aggregation != "count":
        if metric.column is None:
            raise ValueError("A numeric metric column is required")
        dtype = schema[metric.column].upper()
        if not any(t in dtype for t in ("INT", "DECIMAL", "NUMERIC", "DOUBLE", "FLOAT", "REAL")):
            raise ValueError("Metric requires an explicitly typed numeric column")
    aggregation = metric.aggregation.upper()
    argument = quote(metric.column) if metric.column else "*"
    dimensions = [quote(c) for c in plan.dimensions]
    projections = [*dimensions, f"{aggregation}({argument}) AS value"]
    sql = "SELECT " + ", ".join(projections) + " FROM " + quote(table)
    predicates, parameters = [], []
    operators = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    for item in plan.filters:
        column = quote(item.column)
        if item.operator in ("is_null", "not_null"):
            predicates.append(column + (" IS NULL" if item.operator == "is_null" else " IS NOT NULL"))
        else:
            if item.value is None:
                raise ValueError("Use an explicit null filter")
            predicates.append(f"{column} {operators[item.operator]} ?")
            parameters.append(item.value)
    if predicates:
        sql += " WHERE " + " AND ".join(predicates)
    if dimensions:
        sql += " GROUP BY " + ", ".join(dimensions)
        sql += " ORDER BY " + ", ".join(c + " ASC NULLS LAST" for c in dimensions)
    sql += f" LIMIT {plan.limit + 1}"
    return sql, parameters
