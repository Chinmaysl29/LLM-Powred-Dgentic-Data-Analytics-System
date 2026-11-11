"""Small positive SQL grammar for aggregate-only plans, not a SQL sandbox."""
import sqlglot
from sqlglot import exp

AGGREGATES = (exp.Sum, exp.Avg, exp.Min, exp.Max, exp.Count)
ALLOWED = (
    exp.Select, exp.From, exp.Table, exp.Identifier, exp.Column, exp.Star, exp.Alias,
    exp.Group, exp.Order, exp.Ordered, exp.Limit, exp.Literal, exp.Placeholder,
    exp.Where, exp.And, exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.Is, exp.Not, exp.Null, exp.Boolean, *AGGREGATES,
)


def validate(sql: str, schema: dict[str, str], max_rows: int, *, table="source", dialect="duckdb"):
    if len(sql) > 16000:
        raise ValueError("SQL too large")
    trees = sqlglot.parse(sql, read=dialect)
    if len(trees) != 1 or not isinstance(trees[0], exp.Select):
        raise ValueError("Exactly one aggregate SELECT is required")
    tree = trees[0]
    if any(type(node) not in ALLOWED for node in tree.walk()):
        raise ValueError("Unsupported SQL expression")
    tables = list(tree.find_all(exp.Table))
    if len(tables) != 1 or tables[0].name != table or tables[0].db or tables[0].catalog or tables[0].alias:
        raise ValueError("Unknown data source")
    for column in tree.find_all(exp.Column):
        if column.name not in schema or column.table:
            raise ValueError("Unknown or qualified column")
    group = tree.args.get("group")
    dimensions = {c.name for c in group.expressions} if group else set()
    if group and any(type(c) is not exp.Column for c in group.expressions):
        raise ValueError("Only named dimensions may be grouped")
    found_aggregate = False
    for projection in tree.expressions:
        value = projection.this if isinstance(projection, exp.Alias) else projection
        if isinstance(value, AGGREGATES):
            found_aggregate = True
            if not isinstance(value.this, (exp.Column, exp.Star)):
                raise ValueError("Aggregate must reference one column")
            if isinstance(value.this, exp.Star) and not isinstance(value, exp.Count):
                raise ValueError("Only COUNT may use star")
        elif not isinstance(value, exp.Column) or value.name not in dimensions:
            raise ValueError("Raw rows cannot be returned")
    if not found_aggregate:
        raise ValueError("An aggregate is required")
    limit = tree.args.get("limit")
    if not limit or not isinstance(limit.expression, exp.Literal) or not limit.expression.is_int:
        raise ValueError("A fixed result limit is required")
    if not 1 <= int(limit.expression.this) <= max_rows + 1:
        raise ValueError("Result limit exceeded")
    return tree
