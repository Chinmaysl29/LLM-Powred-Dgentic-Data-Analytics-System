"""Validated structured plans: SQL and paths are never accepted from clients."""
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Metric(StrictModel):
    name: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    column: str | None = Field(None, max_length=128)
    aggregation: Literal["sum", "avg", "min", "max", "count"] = "sum"
    description: str = Field(min_length=1, max_length=500)
    unit: str = Field("unspecified", max_length=40)
    grain: str = Field("source row", max_length=200)


class Filter(StrictModel):
    column: str = Field(min_length=1, max_length=128)
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte", "is_null", "not_null"]
    value: str | int | float | bool | None = None

    @field_validator("value")
    @classmethod
    def bounded_literal(cls, value):
        if isinstance(value, str) and len(value) > 1000:
            raise ValueError("Filter literal exceeds 1000 characters")
        return value


class QueryPlan(StrictModel):
    metric: str = Field(min_length=1, max_length=80)
    dimensions: list[str] = Field(default_factory=list, max_length=3)
    filters: list[Filter] = Field(default_factory=list, max_length=20)
    limit: int = Field(100, ge=1, le=5000)


class CleaningPlan(StrictModel):
    operation: Literal["drop_nulls", "deduplicate", "trim"]
    columns: list[str] = Field(min_length=1, max_length=20)
    reason: str = Field(min_length=1, max_length=500)


class ExecutionEngine(Protocol):
    name: str
    def schema(self) -> dict[str, str]: ...
    def explain(self, sql: str, parameters: list) -> dict: ...
    def execute(self, sql: str, parameters: list) -> dict: ...
    def health(self) -> dict: ...


class SparkEngine:
    name = "spark"
    def __getattr__(self, name):
        raise NotImplementedError("Spark runtime deferred pending measured workload need")


class StreamingSource(Protocol):
    """Reserved contract; no streaming service is started."""
    def checkpoint(self) -> str: ...
