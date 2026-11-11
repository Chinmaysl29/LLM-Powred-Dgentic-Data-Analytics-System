"""Deterministic health measurements; alerts never infer business causes."""
from datetime import datetime, timezone
from statistics import median
from backend.app.dataplane.semantic import quote


def volume_baseline(current: int, history: list[dict], now: datetime, minimum=8):
    # One latest observation per UTC date; compare the same weekday.
    dates = {}
    for item in history:
        day = datetime.fromisoformat(item["as_of"]).date()
        if day < now.date() and day.weekday() == now.weekday():
            dates[day] = item["row_count"]
    values = [dates[d] for d in sorted(dates)[-12:]]
    if len(values) < minimum:
        return {"status": "insufficient_history", "observations": len(values), "minimum": minimum}
    center = median(values)
    mad = median(abs(v-center) for v in values)
    changed = current != center if mad == 0 else abs(current-center) > 6*mad
    return {"status": "warn" if changed else "ok", "observations": len(values),
            "median": center, "mad": mad, "deviation_mads": None if mad == 0 else abs(current-center)/mad,
            "zero_mad": mad == 0, "message": "Possible data delay or business change; investigate." if changed else "Within baseline"}


def profile(engine, history: list[dict], source_created: str, previous_schema=None):
    connection, schema = engine.connection, engine.schema()
    now = datetime.now(timezone.utc)
    count = connection.execute("SELECT COUNT(*) FROM source").fetchone()[0]
    columns = []
    for name, dtype in schema.items():
        col = quote(name)
        nulls = connection.execute(f"SELECT COUNT(*)-COUNT({col}) FROM source").fetchone()[0]
        item = {"column": name, "type": dtype, "nulls": nulls, "missing_fraction": nulls/count if count else 0}
        if any(t in dtype for t in ("INT", "DOUBLE", "FLOAT", "DECIMAL")):
            avg, std, low, high = connection.execute(
                f"SELECT AVG({col}), STDDEV_POP({col}), MIN({col}), MAX({col}) FROM source").fetchone()
            from backend.app.dataplane.engine import scalar
            item.update(dict(zip(("mean", "stddev", "min", "max"), (scalar(v) for v in (avg, std, low, high)))))
        columns.append(item)
    names = ", ".join(quote(c) for c in schema)
    distinct = connection.execute(f"SELECT COUNT(*) FROM (SELECT DISTINCT {names} FROM source)").fetchone()[0]
    previous = history[-1] if history else None
    distribution = []
    if previous:
        old = {c["column"]: c for c in previous.get("columns", [])}
        for col in columns:
            before = old.get(col["column"], {})
            if col.get("mean") is not None and before.get("mean") is not None and before.get("stddev"):
                shift = abs(float(col["mean"])-float(before["mean"]))/float(before["stddev"])
                if shift > 3:
                    distribution.append({"column": col["column"], "mean_shift_stddevs": shift})
    created = datetime.fromisoformat(source_created)
    return {"as_of": now.isoformat(), "timezone": "UTC", "row_count": count, "columns": columns,
            "duplicate_rows": count-distinct, "schema": schema,
            "schema_drift": previous_schema is not None and previous_schema != schema,
            "snapshot_age_seconds": max(0, (now-created).total_seconds()),
            "freshness_note": "Snapshot age; source business freshness requires a configured event-time definition.",
            "volume": volume_baseline(count, history, now), "distribution_warnings": distribution,
            "distribution_method": "Mean shift relative to previous population standard deviation; descriptive only."}
