"""Pydantic schemas for Phase 4.1 Schema Reader.

Defines models for database schema representation including tables, columns,
datatypes, primary keys, foreign keys, indexes, and prompt-ready context.
"""

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class ColumnMetadata(BaseModel):
    """Metadata for an individual column."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., description="Column name")
    data_type: str = Field(..., description="Database data type (e.g. VARCHAR, INTEGER, NUMERIC)")
    nullable: bool = Field(default=True, description="Whether column permits NULL values")
    default: str | None = Field(default=None, description="Default value expression if defined")
    primary_key: bool = Field(default=False, description="Whether column is part of the primary key")
    autoincrement: bool = Field(default=False, description="Whether column autoincrements")
    comment: str | None = Field(default=None, description="Optional column description or comment")


class IndexKey(BaseModel):
    """One ordered index key; SQL text is metadata and is never executed."""

    position: int = Field(ge=0, description="Zero-based position among index keys")
    kind: Literal["column", "expression", "unknown"]
    column_name: str | None = None
    expression: str | None = None
    sorting: list[Literal["asc", "desc", "nulls_first", "nulls_last"]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_kind(self) -> "IndexKey":
        if self.kind == "column" and (not self.column_name or self.expression is not None):
            raise ValueError("Column keys require only a column name")
        if self.kind == "expression" and (not self.expression or self.column_name is not None):
            raise ValueError("Expression keys require only an expression")
        if self.kind == "unknown" and (self.column_name is not None or self.expression is not None):
            raise ValueError("Unknown keys cannot claim a column or expression")
        return self


class IndexMetadata(BaseModel):
    """Metadata for an index on a table."""

    model_config = ConfigDict(from_attributes=True)

    name: str | None = Field(default=None, description="Index name")
    columns: list[str] = Field(default_factory=list, description="Physical indexed column names in relative order; see keys for all key positions")
    unique: bool = Field(default=False, description="Whether the index enforces uniqueness")
    keys: list[IndexKey] = Field(default_factory=list)
    include_columns: list[str] = Field(default_factory=list)
    predicate: str | None = None
    dialect_options: dict[str, JsonValue] = Field(default_factory=dict)
    duplicates_constraint: str | None = None
    warnings: list[str] = Field(default_factory=list)


class UniqueConstraintMetadata(BaseModel):
    name: str | None = None
    columns: list[str] = Field(default_factory=list)


class ForeignKeyMetadata(BaseModel):
    """Foreign key relationship constraint definition."""

    model_config = ConfigDict(from_attributes=True)

    source_table: str = Field(..., description="Table defining the foreign key")
    source_columns: list[str] = Field(..., description="Columns in the source table")
    target_table: str = Field(..., description="Referenced parent table")
    target_columns: list[str] = Field(..., description="Referenced columns in the parent table")
    constraint_name: str | None = Field(default=None, description="Name of the foreign key constraint")


class RelationshipMetadata(BaseModel):
    """Normalized relationship between two tables."""

    model_config = ConfigDict(from_attributes=True)

    source_table: str = Field(..., description="Origin table with foreign key")
    source_columns: list[str] = Field(..., description="Columns referencing target")
    target_table: str = Field(..., description="Referenced target table")
    target_columns: list[str] = Field(..., description="Referenced target columns")
    constraint_name: str | None = Field(default=None, description="Constraint identifier")


class TableMetadata(BaseModel):
    """Comprehensive schema metadata for a single database table."""

    model_config = ConfigDict(from_attributes=True)

    table_name: str = Field(..., description="Name of the table")
    schema_name: str | None = Field(default=None, description="Database schema name (e.g. public)")
    columns: list[ColumnMetadata] = Field(default_factory=list, description="List of column specifications")
    column_names: list[str] = Field(default_factory=list, description="Quick-lookup list of column names")
    primary_keys: list[str] = Field(default_factory=list, description="List of primary key column names")
    foreign_keys: list[ForeignKeyMetadata] = Field(default_factory=list, description="Outbound foreign keys")
    indexes: list[IndexMetadata] = Field(default_factory=list, description="Indexes defined on this table")
    unique_constraints: list[UniqueConstraintMetadata] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    row_count_estimate: int | None = Field(default=None, description="Estimated row count if available")
    comment: str | None = Field(default=None, description="Table comment or documentation")


class DatabaseMetadata(BaseModel):
    """System metadata regarding the database connection and schema cache."""

    model_config = ConfigDict(from_attributes=True)

    dialect: str = Field(..., description="Database engine dialect (e.g. postgresql, sqlite)")
    database_name: str | None = Field(default=None, description="Name of the database")
    schema_name: str | None = Field(default=None, description="Inspected schema namespace")
    table_count: int = Field(default=0, description="Total number of tables discovered")
    relationship_count: int = Field(default=0, description="Total foreign key relationships detected")
    cached_at: str | None = Field(default=None, description="ISO timestamp when schema was cached")
    is_cached: bool = Field(default=False, description="Whether this schema was served from cache")
    ttl_seconds: int | None = Field(default=None, description="Cache TTL in seconds")


class DatabaseSchema(BaseModel):
    """Standardized root schema model providing full database structure and prompt context."""

    model_config = ConfigDict(from_attributes=True)

    tables: list[TableMetadata] = Field(default_factory=list, description="List of discovered tables")
    relationships: list[RelationshipMetadata] = Field(
        default_factory=list, description="Discovered cross-table relationships"
    )
    metadata: DatabaseMetadata = Field(..., description="Database and cache metadata")

    def get_table(self, table_name: str) -> TableMetadata | None:
        """Find a table by name (case-insensitive)."""
        target = table_name.strip().lower()
        for t in self.tables:
            if t.table_name.lower() == target:
                return t
        return None

    def get_column_names(self, table_name: str) -> list[str]:
        """Return list of column names for a given table."""
        t = self.get_table(table_name)
        return t.column_names if t else []

    def to_compact_tables(self) -> list[dict[str, Any]]:
        """Generate simplified compact table list: [{'table': 'sales', 'columns': ['order_id', ...]}]"""
        return [{"table": t.table_name, "columns": t.column_names} for t in self.tables]

    def to_prompt_context(self, table_names: list[str] | None = None) -> str:
        """Render a clean, markdown/DDL schema representation for LLM prompts."""
        selected_tables = self.tables
        if table_names:
            allowed = {name.lower().strip() for name in table_names}
            selected_tables = [t for t in self.tables if t.table_name.lower() in allowed]

        lines = [f"### Database Schema ({self.metadata.dialect.upper()})", ""]
        for t in selected_tables:
            pk_str = f" [PK: {', '.join(t.primary_keys)}]" if t.primary_keys else ""
            lines.append(f"Table `{t.table_name}`{pk_str}:")
            for c in t.columns:
                pk_marker = " (PRIMARY KEY)" if c.primary_key else ""
                nullable_marker = "" if c.nullable else " NOT NULL"
                lines.append(f"  - `{c.name}`: {c.data_type}{nullable_marker}{pk_marker}")
            if t.foreign_keys:
                lines.append("  Foreign Keys:")
                for fk in t.foreign_keys:
                    lines.append(
                        f"    - `{', '.join(fk.source_columns)}` -> `{fk.target_table}({', '.join(fk.target_columns)})`"
                    )
            lines.append("")

        if self.relationships:
            lines.append("### Relationships:")
            for rel in self.relationships:
                lines.append(
                    f"- `{rel.source_table}.{', '.join(rel.source_columns)}` -> `{rel.target_table}.{', '.join(rel.target_columns)}`"
                )
            lines.append("")

        return "\n".join(lines)


class SchemaReaderResponse(BaseModel):
    """API response envelope for schema reader endpoints."""

    model_config = ConfigDict(from_attributes=True)

    status: str = Field(default="success", description="Request status")
    schema_data: DatabaseSchema = Field(..., description="Extracted schema data")
    retrieved_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC timestamp of schema query",
    )
