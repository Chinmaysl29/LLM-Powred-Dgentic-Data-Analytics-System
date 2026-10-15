"""Read-only schema compatibility checks shared by readiness and preflight."""
from functools import lru_cache
from pathlib import Path
from sqlalchemy import inspect, text


@lru_cache(maxsize=1)
def required_revisions() -> tuple[str, ...]:
    from alembic.script import ScriptDirectory
    migrations = Path(__file__).resolve().parents[3] / 'migrations'
    return tuple(sorted(ScriptDirectory(str(migrations)).get_heads()))


def inspect_schema(connection, metadata=None, *, expected_revisions=None) -> dict:
    if metadata is None:
        from backend.app.models import Base
        metadata = Base.metadata
        if expected_revisions is None:
            expected_revisions = required_revisions()
    inspector = inspect(connection)
    present = set(inspector.get_table_names())
    missing_tables = sorted(set(metadata.tables) - present)
    missing_columns = {}
    invalid_primary_keys = []
    missing_foreign_keys = {}
    actual_revisions = []
    revision_matches = True
    if expected_revisions is not None:
        if 'alembic_version' in present:
            actual_revisions = sorted(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
        revision_matches = actual_revisions == sorted(expected_revisions)
    for name, table in metadata.tables.items():
        if name not in present:
            continue
        absent = sorted(set(table.columns.keys()) - {c['name'] for c in inspector.get_columns(name)})
        if absent:
            missing_columns[name] = absent
        expected_pk = [c.name for c in table.primary_key.columns]
        if expected_pk != inspector.get_pk_constraint(name)['constrained_columns']:
            invalid_primary_keys.append(name)
        actual_fk = {(tuple(f['constrained_columns']), f['referred_table'], tuple(f['referred_columns'])) for f in inspector.get_foreign_keys(name)}
        expected_fk = {(tuple(e.parent.name for e in f.elements), f.referred_table.name, tuple(e.column.name for e in f.elements)) for f in table.foreign_key_constraints}
        if expected_fk - actual_fk:
            missing_foreign_keys[name] = sorted(str(f) for f in expected_fk - actual_fk)
    return {
        'compatible': revision_matches and not (missing_tables or missing_columns or invalid_primary_keys or missing_foreign_keys),
        'missing_tables': missing_tables, 'missing_columns': missing_columns,
        'invalid_primary_keys': sorted(invalid_primary_keys), 'missing_foreign_keys': missing_foreign_keys,
        'revision_matches': revision_matches,
        'expected_revisions': list(expected_revisions) if expected_revisions is not None else None,
        'actual_revisions': actual_revisions,
    }
