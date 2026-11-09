"""Bounded conversion, original-byte preservation and per-part checksums."""
import csv
import json
import re
from pathlib import Path
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from backend.app.dataplane.config import Limits
from backend.app.dataplane.storage import digest, fingerprint, write_new_json


def batches(source: Path, file_type: str, limits: Limits):
    if file_type in ("csv", "tsv"):
        # Arrow rejects late type drift. Never silently coerce bad values to null.
        reader = pacsv.open_csv(source, read_options=pacsv.ReadOptions(block_size=1024**2),
            parse_options=pacsv.ParseOptions(delimiter="\t" if file_type == "tsv" else ","),
            convert_options=pacsv.ConvertOptions(strings_can_be_null=True))
        identifiers = {name: pa.string() for name in reader.schema.names if re.search(
            r"(?i)(?:^|[_ -])(id|identifier|zip|zipcode|postal|phone|telephone|account|code|sku)(?:$|[_ -])|Id$|ID$", name)}
        if identifiers:
            reader.close()
            reader = pacsv.open_csv(source, read_options=pacsv.ReadOptions(block_size=1024**2),
                parse_options=pacsv.ParseOptions(delimiter="\t" if file_type == "tsv" else ","),
                convert_options=pacsv.ConvertOptions(strings_can_be_null=True, column_types=identifiers))
        for batch in reader:
            yield pa.Table.from_batches([batch])
    elif file_type == "parquet":
        parquet = pq.ParquetFile(source)
        if len(parquet.schema.names) > limits.max_columns:
            raise ValueError("Too many columns")
        for batch in parquet.iter_batches(batch_size=limits.batch_rows):
            yield pa.Table.from_batches([batch])
    elif file_type in ("jsonl", "ndjson"):
        rows = []
        with source.open(encoding="utf-8") as stream:
            while line := stream.readline(1024**2 + 1):
                if len(line) > 1024**2:
                    raise ValueError("JSON record exceeds one MiB")
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("JSONL requires objects")
                rows.append(item)
                if len(rows) == limits.batch_rows:
                    yield pa.Table.from_pylist(rows)
                    rows = []
        if rows:
            yield pa.Table.from_pylist(rows)
    elif file_type == "xlsx":
        from openpyxl import load_workbook
        book = load_workbook(source, read_only=True, data_only=True)
        try:
            sheet = book.worksheets[0]
            if sheet.max_column and sheet.max_column > limits.max_columns:
                raise ValueError("Too many columns")
            rows = sheet.iter_rows(values_only=True)
            header = [str(v) if v is not None else f"column_{i}" for i, v in enumerate(next(rows))]
            # Check before dict(zip(...)): duplicate keys would already lose values.
            if (len({name.casefold() for name in header}) != len(header)
                    or any(not name or len(name) > 128 or "\x00" in name for name in header)):
                raise ValueError("Duplicate or invalid XLSX columns")
            batch = []
            for row in rows:
                # Preserve native cell types, including text identifiers with leading zeros.
                # Incompatible late type changes fail instead of silently coercing values.
                batch.append(dict(zip(header, row)))
                if len(batch) == limits.batch_rows:
                    yield pa.Table.from_pylist(batch)
                    batch = []
            if batch:
                yield pa.Table.from_pylist(batch)
        finally:
            book.close()
    else:
        raise ValueError("Use CSV, TSV, Parquet, XLSX or newline-delimited JSON for bounded ingestion")


def materialize(source: Path, output: Path, root: Path, limits: Limits, *, version_id: str, resume=None):
    if source.stat().st_size > limits.upload_mb * 1024**2:
        raise ValueError("Upload budget exceeded")
    output.mkdir(parents=True, exist_ok=False)
    raw = output / ("original." + source.suffix.lstrip(".").lower())
    total = 0
    with source.open("rb") as incoming, raw.open("xb") as outgoing:
        for chunk in iter(lambda: incoming.read(1024**2), b""):
            total += len(chunk)
            if total > limits.upload_mb * 1024**2:
                raise ValueError("Upload budget exceeded")
            outgoing.write(chunk)
    original_hash = digest(raw)
    if resume and (resume.get("source_hash") != original_hash or resume.get("version_id") != version_id):
        raise ValueError("Checkpoint source mismatch")
    files, row_count, schema = [], 0, None
    for index, table in enumerate(batches(raw, source.suffix.lstrip(".").lower(), limits)):
        if (len(table.column_names) > limits.max_columns
                or len({c.casefold() for c in table.column_names}) != len(table.column_names)
                or any(not c or len(c)>128 or "\x00" in c for c in table.column_names)):
            raise ValueError("Duplicate or excessive columns")
        if schema is None:
            schema = table.schema
        elif table.schema != schema:
            # Safe casts reject overflows and incompatible batches.
            table = table.cast(schema, safe=True)
        if table.nbytes > 64 * 1024**2:
            raise ValueError("Batch memory budget exceeded")
        if resume and index < len(resume["files"]):
            from backend.app.dataplane.storage import confined
            part = resume["files"][index]
            if part["rows"] != table.num_rows or digest(confined(root, part["path"])) != part["sha256"]:
                raise ValueError("Checkpoint part mismatch")
            files.append(part)
            row_count += table.num_rows
            continue
        target = output / "normalized" / f"part-{index:06d}.parquet"
        target.parent.mkdir(exist_ok=True)
        pq.write_table(table, target, compression="zstd", row_group_size=limits.batch_rows)
        files.append({"path": str(target.relative_to(root)), "sha256": digest(target),
                      "rows": table.num_rows, "bytes": target.stat().st_size})
        row_count += table.num_rows
        write_new_json(output / f"checkpoint-{index:06d}.json", {
            "source_hash": original_hash, "version_id": version_id, "files": files})
    if schema is None:
        raise ValueError("Dataset has no rows")
    if digest(source) != original_hash:
        raise ValueError("Source changed during ingestion")
    manifest = {"format_version": 1, "layer": "raw", "version_id": version_id,
        "original": {"path": str(raw.relative_to(root)), "sha256": original_hash, "bytes": total},
        "files": files, "row_count": row_count,
        "schema": {field.name: str(field.type) for field in schema},
        "typing": "Arrow first-block inference; identifier columns as text; strict late-drift rejection; XLSX native cell types",
        "partitioning": "bounded row-group parts; no guessed business partition key"}
    manifest["snapshot_hash"] = fingerprint(manifest)
    write_new_json(output / "manifest.json", manifest)
    return manifest
