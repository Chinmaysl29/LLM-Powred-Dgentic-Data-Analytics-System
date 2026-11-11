"""Maintainer utility: generate the initial migration SQL before publishing revision 011.

Do not regenerate an already deployed migration; create a new revision instead.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable
from backend.app.models.learning import TABLES

selected = {model.__table__.name for model in TABLES}
metadata = TABLES[0].metadata
statements = []
for table in metadata.sorted_tables:
    if table.name in selected:
        statements.append(str(CreateTable(table).compile(dialect=postgresql.dialect())) + ';')
        for index in sorted(table.indexes, key=lambda i: i.name):
            statements.append(str(CreateIndex(index).compile(dialect=postgresql.dialect())) + ';')
Path(sys.argv[1]).write_text('\n'.join(statements))
