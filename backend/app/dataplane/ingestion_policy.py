"""Explicit, bounded interpretation of uploaded files; never execute cell content."""
import csv
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path
import re
from typing import Literal
import zipfile

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from pydantic import Field, field_validator, model_validator

from backend.app.dataplane.contracts import StrictModel


class ColumnType(StrictModel):
    kind: Literal['string', 'int64', 'decimal', 'float64', 'boolean']
    precision: int = Field(38, ge=1, le=38)
    scale: int = Field(6, ge=0, le=18)

    @model_validator(mode='after')
    def decimal_bounds(self):
        if self.scale > self.precision:
            raise ValueError('Decimal scale cannot exceed precision')
        return self

    def arrow(self):
        return pa.decimal128(self.precision, self.scale) if self.kind == 'decimal' else {
            'string': pa.string, 'int64': pa.int64, 'float64': pa.float64,
            'boolean': pa.bool_}[self.kind]()


class IngestionOptions(StrictModel):
    encoding: Literal['utf-8', 'utf-8-sig', 'windows-1252', 'latin-1'] = 'utf-8'
    delimiter: str | None = Field(None, min_length=1, max_length=1)
    null_tokens: list[str] = Field(default_factory=lambda: ['', 'NULL', 'null', 'NA', 'N/A'], max_length=30)
    column_types: dict[str, ColumnType] = Field(default_factory=dict, max_length=200)
    sheet: str | None = Field(None, min_length=1, max_length=128)
    header_row: int = Field(1, ge=1, le=100)
    formula_policy: Literal['reject', 'cached_values'] = 'reject'
    json_missing: Literal['nulls', 'preserve', 'reject'] = 'nulls'
    json_nesting: Literal['reject', 'flatten_objects'] = 'reject'
    explode_array: str | None = Field(None, min_length=1, max_length=128)

    @field_validator('delimiter')
    @classmethod
    def delimiter_character(cls, value):
        if value in {'\r', '\n', '\x00', '"'}:
            raise ValueError('Select a single non-quote delimiter')
        return value

    @field_validator('column_types')
    @classmethod
    def valid_names(cls, value):
        if any(not name or len(name) > 128 or '\x00' in name for name in value):
            raise ValueError('Invalid column override name')
        return value

    @field_validator('null_tokens')
    @classmethod
    def bounded_tokens(cls, values):
        if any(len(token) > 100 for token in values):
            raise ValueError('Null token exceeds 100 characters')
        return values


def headers(names, limits):
    if (not names or len(names) > limits.max_columns or len({name.casefold() for name in names}) != len(names)
            or any(not name or len(name) > 128 or '\x00' in name for name in names)):
        raise ValueError('Duplicate, invalid or excessive columns')


def flatten(item, policy, prefix='', depth=0):
    if depth > 5:
        raise ValueError('JSON nesting exceeds five levels')
    result = {}
    for name, value in item.items():
        key = prefix + str(name)
        if isinstance(value, list):
            raise ValueError('JSON arrays require an explicit top-level explode_array policy')
        if isinstance(value, dict):
            if policy != 'flatten_objects':
                raise ValueError('Nested JSON requires an explicit flatten_objects policy')
            children = flatten(value, policy, key+'.', depth+1)
        else:
            children = {key: value}
        if result.keys() & children.keys():
            raise ValueError('Flattened JSON field names conflict')
        result.update(children)
    return result


def arrow_rows(rows, options):
    # Explicit decimal conversion occurs before Arrow float inference.
    for row in rows:
        for name, dtype in options.column_types.items():
            if name in row and row[name] is not None and dtype.kind == 'decimal':
                row[name] = Decimal(str(row[name]))
    table = pa.Table.from_pylist(rows)
    if options.column_types:
        schema = pa.schema([pa.field(f.name, options.column_types[f.name].arrow()
            if f.name in options.column_types else f.type) for f in table.schema])
        table = table.cast(schema, safe=True)
    return table


def read_batches(source: Path, file_type, limits, options, metadata):
    options = IngestionOptions.model_validate(options or {})
    metadata['options'] = options.model_dump(mode='json')
    if file_type in ('csv', 'tsv'):
        delimiter = options.delimiter or ('\t' if file_type == 'tsv' else ',')
        csv.field_size_limit(limits.field_bytes)
        with source.open(encoding=options.encoding, newline='') as stream:
            names = next(csv.reader(stream, delimiter=delimiter, strict=True), [])
        names = [name.removeprefix('\ufeff') if index == 0 else name for index, name in enumerate(names)]
        headers(names, limits)
        if options.column_types.keys() - set(names):
            raise ValueError('Schema override names do not exist in the CSV header')
        identifiers = {name: pa.string() for name in names if re.search(
            r'(?i)(?:^|[_ -])(id|identifier|zip|zipcode|postal|phone|telephone|account|code|sku)(?:$|[_ -])|Id$|ID$', name)}
        identifiers.update({name: spec.arrow() for name, spec in options.column_types.items()})
        reader = pacsv.open_csv(source,
            read_options=pacsv.ReadOptions(block_size=1024**2, encoding=options.encoding),
            parse_options=pacsv.ParseOptions(delimiter=delimiter, newlines_in_values=True),
            convert_options=pacsv.ConvertOptions(strings_can_be_null=True,
                null_values=options.null_tokens, column_types=identifiers))
        metadata.update(delimiter=delimiter, identifier_columns=sorted(name for name, kind in identifiers.items() if pa.types.is_string(kind)))
        try:
            for batch in reader:
                yield pa.Table.from_batches([batch])
        finally:
            reader.close()
    elif file_type == 'parquet':
        with source.open('rb') as stream:
            if stream.read(4) != b'PAR1':
                raise ValueError('File content is not supported Parquet')
        parquet = pq.ParquetFile(source)
        headers(parquet.schema_arrow.names, limits)
        metadata['schema_union'] = 'not performed; one validated schema'
        for batch in parquet.iter_batches(batch_size=limits.batch_rows):
            table = pa.Table.from_batches([batch])
            if options.column_types:
                if options.column_types.keys() - set(table.column_names):
                    raise ValueError('Unknown Parquet schema override column')
                table = table.cast(pa.schema([pa.field(f.name, options.column_types[f.name].arrow()
                    if f.name in options.column_types else f.type) for f in table.schema]), safe=True)
            yield table
    elif file_type in ('jsonl', 'ndjson'):
        rows, fields = [], None
        metadata.update(absent_field_counts={}, source_lines=0, exploded=bool(options.explode_array))
        with source.open(encoding=options.encoding) as stream:
            while line := stream.readline(limits.row_bytes + 1):
                if len(line.encode(options.encoding)) > limits.row_bytes:
                    raise ValueError('JSON record exceeds the configured row-width budget')
                item = json.loads(line, parse_float=Decimal,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Non-finite JSON number')))
                if not isinstance(item, dict):
                    raise ValueError('JSONL requires one object per line')
                metadata['source_lines'] += 1
                if options.explode_array:
                    array = item.get(options.explode_array)
                    if not isinstance(array, list) or not 1 <= len(array) <= 1000:
                        raise ValueError('Explode requires a nonempty array of at most 1000 elements per source line')
                    expanded = [{**item, options.explode_array: value} for value in array]
                else:
                    expanded = [item]
                for element, record in enumerate(expanded):
                    record = flatten(record, options.json_nesting)
                    if any(name.startswith('__source_') or name.startswith('__present_') for name in record):
                        raise ValueError('JSON field conflicts with reserved provenance columns')
                    if fields is None:
                        fields = list(dict.fromkeys([*record, *options.column_types]))
                        headers(fields, limits)
                    if record.keys() - set(fields):
                        raise ValueError('JSONL schema changed: declare all fields through explicit schema overrides')
                    missing = set(fields) - record.keys()
                    if missing and options.json_missing == 'reject':
                        raise ValueError('Absent JSON fields rejected by the selected policy')
                    row = {name: record.get(name) for name in fields}
                    for name in fields:
                        if name in missing:
                            metadata['absent_field_counts'][name] = metadata['absent_field_counts'].get(name, 0) + 1
                        if options.json_missing == 'preserve':
                            row['__present_'+name] = name in record
                    if options.explode_array:
                        row.update(__source_line=metadata['source_lines'], __source_element=element)
                    rows.append(row)
                    if len(rows) == limits.batch_rows:
                        yield arrow_rows(rows, options)
                        rows = []
        if rows:
            yield arrow_rows(rows, options)
    elif file_type == 'xlsx':
        from openpyxl import load_workbook
        with zipfile.ZipFile(source) as archive:
            members = archive.infolist()
            if len(members) > limits.max_files or sum(item.file_size for item in members) > limits.expanded_mb * 1024**2:
                raise ValueError('XLSX expanded-size or archive-file budget exceeded')
            if 'xl/workbook.xml' not in archive.namelist():
                raise ValueError('File content is not an XLSX workbook')
            if any('vbaproject' in item.filename.lower() or '/externallinks/' in item.filename.lower() for item in members):
                raise ValueError('Macros and external workbook links are not accepted')
        values = load_workbook(source, read_only=True, data_only=True, keep_links=False)
        formulas = load_workbook(source, read_only=True, data_only=False, keep_links=False)
        try:
            if options.sheet is None and len(values.worksheets) != 1:
                raise ValueError('Select the XLSX sheet explicitly when a workbook has multiple sheets')
            name = options.sheet or values.worksheets[0].title
            if name not in values.sheetnames:
                raise ValueError('Selected XLSX sheet does not exist')
            sheet, formula_sheet = values[name], formulas[name]
            if sheet.max_column and sheet.max_column > limits.max_columns:
                raise ValueError('Too many XLSX columns')
            value_rows = sheet.iter_rows(min_row=options.header_row)
            formula_rows = formula_sheet.iter_rows(min_row=options.header_row)
            header = next(value_rows, ())
            formula_header = next(formula_rows, ())
            if any(cell.data_type == 'f' for cell in formula_header):
                raise ValueError('Formula headers are not supported')
            names = [str(cell.value) if cell.value is not None else f'column_{i}' for i, cell in enumerate(header)]
            headers(names, limits)
            if options.column_types.keys() - set(names):
                raise ValueError('Unknown XLSX schema override column')
            metadata.update(sheet=name, header_row=options.header_row, date_system=values.epoch.isoformat(),
                formula_cells=0, formula_cache='not recalculated; cached values accepted only by explicit policy')
            rows = []
            for cells, expressions in zip(value_rows, formula_rows, strict=True):
                for cell, expression in zip(cells, expressions, strict=True):
                    if expression.data_type == 'f':
                        metadata['formula_cells'] += 1
                        if options.formula_policy != 'cached_values':
                            raise ValueError('Formula cells require explicit cached_values policy; no recalculation is performed')
                        if cell.value is None:
                            raise ValueError('XLSX formula cached value is missing; recalculate in a trusted spreadsheet tool before upload')
                rows.append(dict(zip(names, (cell.value for cell in cells))))
                if len(rows) == limits.batch_rows:
                    yield arrow_rows(rows, options)
                    rows = []
            if rows:
                yield arrow_rows(rows, options)
        finally:
            values.close()
            formulas.close()
    else:
        raise ValueError('Use CSV, TSV, Parquet, XLSX or newline-delimited JSON')
