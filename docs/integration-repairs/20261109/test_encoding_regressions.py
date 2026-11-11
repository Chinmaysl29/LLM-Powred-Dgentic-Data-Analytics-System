"""Bounded ingestion must reject unsupported text encodings before publication."""
import pytest
import pyarrow.parquet as pq
from backend.app.dataplane.config import Limits
from backend.app.dataplane.ingestion import materialize
from backend.app.dataplane.storage import digest


@pytest.mark.parametrize('suffix,delimiter', [('csv', ','), ('tsv', '\t')])
def test_f006_latin1_input_rejected_before_publication(tmp_path, suffix, delimiter):
    source = tmp_path/('source.'+suffix)
    source.write_bytes(('region'+delimiter+'amount\ncaf\xe9'+delimiter+'35\n').encode('latin-1'))
    before = digest(source)
    with pytest.raises(ValueError, match='UTF-8'):
        materialize(source, tmp_path/'snapshot', tmp_path, Limits(), version_id='encoding')
    assert digest(source) == before
    assert not (tmp_path/'snapshot'/'manifest.json').exists()


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig'])
@pytest.mark.parametrize('suffix,delimiter', [('csv', ','), ('tsv', '\t')])
def test_f006_utf8_and_bom_preserve_values(tmp_path, encoding, suffix, delimiter):
    source = tmp_path/('source.'+suffix)
    source.write_bytes(('region'+delimiter+'amount\ncaf\xe9'+delimiter+'35\n').encode(encoding))
    manifest = materialize(source, tmp_path/'snapshot', tmp_path, Limits(), version_id='encoding')
    assert pq.read_table(tmp_path/manifest['files'][0]['path']).to_pylist() == [{'region': 'caf\xe9', 'amount': 35}]
    assert manifest['original']['sha256'] == digest(source)
