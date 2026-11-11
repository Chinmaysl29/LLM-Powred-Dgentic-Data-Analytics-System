"""Cleaning creates new versions and quarantines removals; never updates a source."""
from pathlib import Path
from backend.app.dataplane.contracts import CleaningPlan
from backend.app.dataplane.semantic import quote
from backend.app.dataplane.storage import digest, fingerprint, write_new_json


def transform(plan: CleaningPlan, schema: dict[str, str], source="source"):
    if any(c not in schema for c in plan.columns) or len(set(plan.columns)) != len(plan.columns):
        raise ValueError("Invalid cleaning columns")
    if plan.operation == "drop_nulls":
        return f"SELECT * FROM {source} WHERE " + " AND ".join(quote(c)+" IS NOT NULL" for c in plan.columns)
    if plan.operation == "deduplicate":
        # Explicit order defines the representative row for partial-key duplicates.
        keys = ", ".join(quote(c) for c in plan.columns)
        order = ", ".join(quote(c)+" ASC NULLS LAST" for c in schema)
        if "__dp_rank" in schema:
            raise ValueError("Reserved internal column")
        return f"SELECT * EXCLUDE (__dp_rank) FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY {keys} ORDER BY {order}) AS __dp_rank FROM {source}) WHERE __dp_rank=1"
    if any(schema[c] != "VARCHAR" for c in plan.columns):
        raise ValueError("Trim requires text columns")
    expressions = [f"TRIM({quote(c)}) AS {quote(c)}" if c in plan.columns else quote(c) for c in schema]
    return f"SELECT {', '.join(expressions)} FROM {source}"


def propose(engine, plan: CleaningPlan):
    conn = engine.connection
    conn.execute("CREATE TEMP VIEW sample AS SELECT * FROM source LIMIT 1000")
    sql = transform(plan, engine.schema(), "sample")
    before = conn.execute("SELECT COUNT(*) FROM sample").fetchall()[0][0]
    after = conn.execute("SELECT COUNT(*) FROM ("+sql+")").fetchall()[0][0]
    from backend.app.dataplane.engine import scalar
    def preview(query):
        cursor = conn.execute(query)
        names = [column[0] for column in cursor.description]
        return [{name: (str(value)[:200] if isinstance(value, str) else scalar(value))
                 for name, value in zip(names, row)} for row in cursor.fetchall()]
    return {"plan": plan.model_dump(), "plan_hash": fingerprint(plan.model_dump()),
            "snapshot_hash": engine.manifest["snapshot_hash"],
            "sample": {"before": before, "after": after, "removed": before-after,
                       "selection": "first 1000 rows; not a population estimate"},
            'preview_rows': {'before': preview('SELECT * FROM sample LIMIT 5'),
                             'after': preview('SELECT * FROM ('+sql+') LIMIT 5'),
                             'coverage': 'First five rows of the first 1000; text truncated to 200 characters'},
            "requires_approval": True}


def apply_cleaning(engine, plan: CleaningPlan, output: Path, root: Path, version_id=None):
    # Execution connection is locked against arbitrary file access. A trusted output
    # connection below consumes an Arrow batch stream, never a whole DataFrame.
    import pyarrow as pa
    import pyarrow.parquet as pq
    output.mkdir(parents=True, exist_ok=False)
    sql = transform(plan, engine.schema())
    files, rows = [], 0
    reader = engine.connection.sql(sql).to_arrow_reader(engine.limits.batch_rows)
    for index, batch in enumerate(reader):
        target = output / f"part-{index:06d}.parquet"
        pq.write_table(pa.Table.from_batches([batch]), target, compression="zstd")
        files.append({"path": str(target.relative_to(root)), "sha256": digest(target),
                      "rows": batch.num_rows, "bytes": target.stat().st_size})
        rows += batch.num_rows
    if not files:
        target = output / "part-000000.parquet"
        pq.write_table(reader.schema.empty_table(), target, compression="zstd")
        files.append({"path": str(target.relative_to(root)), "sha256": digest(target), "rows": 0,
                      "bytes": target.stat().st_size})
    before = engine.manifest["row_count"]
    quarantine, removed = [], 0
    if plan.operation != "trim":
        remainder = engine.connection.sql("SELECT * FROM source EXCEPT ALL ("+sql+")").to_arrow_reader(engine.limits.batch_rows)
        for index, batch in enumerate(remainder):
            target = output / f"quarantine-{index:06d}.parquet"
            pq.write_table(pa.Table.from_batches([batch]), target, compression="zstd")
            removed += batch.num_rows
            quarantine.append({"path": str(target.relative_to(root)), "sha256": digest(target),
                               "rows": batch.num_rows})
    if before != rows + removed:
        raise ValueError("Cleaning reconciliation failed")
    manifest = {"format_version": 1, "layer": "cleaned", "version_id": version_id or engine.manifest["version_id"],
                "parent_version_id": engine.manifest["version_id"],
                "original": engine.manifest["original"], "files": files, "row_count": rows,
                "schema": engine.schema(), "parent_hash": engine.manifest["snapshot_hash"],
                "transformation": plan.model_dump(), "quarantine": quarantine,
                "reconciliation": {"before": before, "after": rows, "quarantined": removed}}
    manifest["snapshot_hash"] = fingerprint(manifest)
    write_new_json(output/"manifest.json", manifest)
    return manifest
