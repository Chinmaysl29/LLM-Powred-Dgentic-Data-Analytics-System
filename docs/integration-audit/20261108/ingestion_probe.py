"""Synthetic reproductions; temporary files only, no application configuration changes."""
import json
import tempfile
from pathlib import Path
from openpyxl import Workbook
import pyarrow.parquet as pq
from backend.app.dataplane.config import Limits
from backend.app.dataplane.contracts import Metric, QueryPlan
from backend.app.dataplane.engine import DuckDBEngine
from backend.app.dataplane.ingestion import materialize
from backend.app.dataplane.semantic import compile_plan

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)
    book=Workbook(); sheet=book.active
    sheet.append(['amount','amount']);sheet.append([10,99])
    book.save(root/'duplicate.xlsx')
    (root/'extra.jsonl').write_text('{"a":1}\n{"a":2,"b":99}\n')
    for name in ('duplicate.xlsx','extra.jsonl'):
        result=materialize(root/name,root/(name+'-out'),root,Limits(),version_id='audit')
        print(json.dumps({'source':name,'schema':result['schema'],'rows':pq.read_table(root/result['files'][0]['path']).to_pylist()}))
    (root/'latin.csv').write_bytes(b'city,amount\ncaf\xe9,10\n')
    manifest=materialize(root/'latin.csv',root/'latin-out',root,Limits(),version_id='audit')
    engine=DuckDBEngine(root,manifest,root/'spill',Limits())
    try:
        sql,params=compile_plan(QueryPlan(metric='amount',dimensions=['city']),Metric(name='amount',column='amount',description='Synthetic amount'),engine.schema())
        engine.execute(sql,params)
    except Exception as error:
        print(json.dumps({'source':'latin.csv','schema':manifest['schema'],'query_error':type(error).__name__,'message':str(error)}))
    finally:
        engine.close()
