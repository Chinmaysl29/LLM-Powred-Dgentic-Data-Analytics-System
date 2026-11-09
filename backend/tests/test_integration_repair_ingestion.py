"""Regressions for reproduced lossy ingestion; synthetic files only."""
import pytest
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
