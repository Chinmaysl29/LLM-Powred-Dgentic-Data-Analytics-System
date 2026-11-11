"""Bounded conversion, original-byte preservation and interpretation provenance."""
from pathlib import Path
import time

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from backend.app.dataplane.config import Limits
from backend.app.dataplane.ingestion_policy import IngestionOptions, headers, read_batches
from backend.app.dataplane.storage import digest, fingerprint, write_new_json


def batches(source: Path, file_type: str, limits: Limits, options=None, metadata=None):
    yield from read_batches(source, file_type, limits, options, metadata if metadata is not None else {})


def materialize(source: Path, output: Path, root: Path, limits: Limits, *, version_id: str,
                resume=None, options=None):
    options = IngestionOptions.model_validate(options or {})
    options_hash = fingerprint(options.model_dump(mode='json'))
    if source.stat().st_size > limits.upload_mb * 1024**2:
        raise ValueError('Upload budget exceeded')
    output.mkdir(parents=True, exist_ok=False)
    raw = output / ('original.' + source.suffix.lstrip('.').lower())
    total = 0
    with source.open('rb') as incoming, raw.open('xb') as outgoing:
        for chunk in iter(lambda: incoming.read(1024**2), b''):
            total += len(chunk)
            if total > limits.upload_mb * 1024**2:
                raise ValueError('Upload budget exceeded')
            outgoing.write(chunk)
    original_hash = digest(raw)
    if resume and (resume.get('source_hash') != original_hash or resume.get('version_id') != version_id
                   or resume.get('options_hash') != options_hash):
        raise ValueError('Checkpoint source or interpretation policy mismatch')
    files, row_count, schema = [], 0, None
    metadata = {}
    expanded = 0
    started = time.monotonic()
    original_parquet = source.suffix.lower() == '.parquet' and not options.column_types
    for index, table in enumerate(batches(raw, source.suffix.lstrip('.').lower(), limits,
                                        options.model_dump(mode='json'), metadata)):
        if time.monotonic() - started > limits.timeout_s:
            raise TimeoutError('Ingestion parsing deadline exceeded')
        headers(table.column_names, limits)
        if schema is None:
            schema = table.schema
        elif table.schema != schema:
            table = table.cast(schema, safe=True)
        expanded += table.nbytes
        if table.nbytes > 64 * 1024**2 or expanded > limits.expanded_mb * 1024**2:
            raise ValueError('Expanded data or batch memory budget exceeded')
        widths = None
        for column in table.columns:
            if pa.types.is_string(column.type) or pa.types.is_large_string(column.type):
                lengths = pc.fill_null(pc.binary_length(pc.cast(column, pa.binary())), 0)
                if (pc.max(lengths).as_py() or 0) > limits.field_bytes:
                    raise ValueError('Field byte budget exceeded')
                widths = lengths if widths is None else pc.add(widths, lengths)
            elif pa.types.is_nested(column.type):
                raise ValueError('Nested columns require an explicit flatten/explode ingestion policy')
        if widths is not None and (pc.max(widths).as_py() or 0) > limits.row_bytes:
            raise ValueError('Row byte budget exceeded')
        if original_parquet:
            row_count += table.num_rows
            continue
        if index >= limits.max_files:
            raise ValueError('Normalized file-count budget exceeded')
        if resume and index < len(resume['files']):
            from backend.app.dataplane.storage import confined
            part = resume['files'][index]
            if part['rows'] != table.num_rows or digest(confined(root, part['path'])) != part['sha256']:
                raise ValueError('Checkpoint part mismatch')
            files.append(part)
            row_count += table.num_rows
            continue
        target = output / 'normalized' / f'part-{index:06d}.parquet'
        target.parent.mkdir(exist_ok=True)
        pq.write_table(table, target, compression='zstd', row_group_size=limits.batch_rows)
        files.append({'path': str(target.relative_to(root)), 'sha256': digest(target),
            'rows': table.num_rows, 'bytes': target.stat().st_size, 'source_row_start': row_count})
        row_count += table.num_rows
        write_new_json(output / f'checkpoint-{index:06d}.json', {
            'source_hash': original_hash, 'version_id': version_id, 'options_hash': options_hash, 'files': files})
    if schema is None or row_count == 0:
        raise ValueError('Dataset has no rows')
    if digest(source) != original_hash:
        raise ValueError('Source changed during ingestion')
    if original_parquet:
        files = [{'path': str(raw.relative_to(root)), 'sha256': original_hash,
            'rows': row_count, 'bytes': total, 'source_row_start': 0}]
    manifest = {'format_version': 2, 'layer': 'raw', 'version_id': version_id,
        'original': {'path': str(raw.relative_to(root)), 'sha256': original_hash, 'bytes': total},
        'files': files, 'row_count': row_count, 'schema': {field.name: str(field.type) for field in schema},
        'typing': 'Explicit overrides and recorded inference; identifiers preserve text; strict late-drift rejection',
        'ingestion': metadata, 'options_hash': options_hash, 'expanded_bytes': expanded,
        'partitioning': 'validated original Parquet' if original_parquet else 'bounded row-group parts; no guessed business partition key'}
    manifest['snapshot_hash'] = fingerprint(manifest)
    write_new_json(output / 'manifest.json', manifest)
    return manifest
