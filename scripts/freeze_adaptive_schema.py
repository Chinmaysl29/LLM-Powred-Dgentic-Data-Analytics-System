"""Maintainer utility for the new, not-yet-published revision 012 only."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex,CreateTable
from backend.app.models.adaptive import TABLES

names={model.__table__.name for model in TABLES}
statements=[]
for table in TABLES[0].metadata.sorted_tables:
    if table.name in names:
        statements.append(str(CreateTable(table).compile(dialect=postgresql.dialect()))+';')
        statements.extend(str(CreateIndex(index).compile(dialect=postgresql.dialect()))+';' for index in sorted(table.indexes,key=lambda item:item.name))
Path(sys.argv[1]).write_text('\n'.join(statements))
