"""Regressions for reproduced lossy ingestion; synthetic files only."""
import pytest
import json
import pyarrow.parquet as pq
from openpyxl import Workbook
from backend.app.dataplane.ingestion import materialize
from backend.app.dataplane.config import Limits
from backend.app.dataplane.storage import digest


@pytest.mark.parametrize('headers', [['amount', 'amount'], ['amount', 'AMOUNT']])
def test_f001_duplicate_excel_headers_rejected_before_values_are_lost(tmp_path, headers):
    source=tmp_path/'duplicate.xlsx'
    book=Workbook();sheet=book.active
    sheet.append(headers);sheet.append([10,99]);book.save(source);book.close()
    before=digest(source)
    with pytest.raises(ValueError, match='Duplicate'):
        materialize(source,tmp_path/'snapshot',tmp_path,Limits(),version_id='audit')
    assert digest(source)==before
    assert not (tmp_path/'snapshot'/'manifest.json').exists()


@pytest.mark.parametrize('offset', [1, 100, 101])
def test_f002_later_json_fields_rejected_without_loss(tmp_path, offset):
    source = tmp_path/'extra.jsonl'
    records = [{'amount': 10}] * offset + [{'amount': 25, 'extra': 99}]
    source.write_text(''.join(json.dumps(row)+'\n' for row in records), encoding='utf-8')
    before = digest(source)
    with pytest.raises(ValueError, match='JSONL schema'):
        materialize(source, tmp_path/'snapshot', tmp_path, Limits(batch_rows=100), version_id='audit')
    assert digest(source) == before
    assert not (tmp_path/'snapshot'/'manifest.json').exists()


def test_f002_missing_json_fields_are_explicit_nulls(tmp_path):
    source = tmp_path/'missing.jsonl'
    source.write_text('{"amount":10,"label":"first"}\n{"amount":25}\n', encoding='utf-8')
    manifest = materialize(source, tmp_path/'snapshot', tmp_path, Limits(), version_id='audit')
    rows = pq.read_table(tmp_path/manifest['files'][0]['path']).to_pylist()
    assert rows == [{'amount': 10, 'label': 'first'}, {'amount': 25, 'label': None}]
