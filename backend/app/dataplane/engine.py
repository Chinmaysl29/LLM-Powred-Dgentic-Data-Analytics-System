"""DuckDB execution over authorized immutable Parquet manifests."""
import json
import math
import time
from decimal import Decimal
from pathlib import Path

from backend.app.dataplane.config import Limits
from backend.app.dataplane.storage import confined, digest, fingerprint
from backend.app.dataplane.validator import validate


def scalar(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite aggregate")
    if isinstance(value, Decimal):
        # Preserve exact decimals in evidence instead of silently rounding money.
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


class DuckDBEngine:
    name = "duckdb"

    def __init__(self, root: Path, manifest: dict, temporary: Path, limits: Limits):
        import duckdb
        self.limits, self.manifest = limits, manifest
        files = [confined(root, entry["path"]) for entry in manifest["files"]]
        scanned = sum(p.stat().st_size for p in files)
        if scanned > limits.scan_mb * 1024**2:
            raise ValueError("Scan budget exceeded")
        for path, entry in zip(files, manifest["files"]):
            if digest(path) != entry["sha256"]:
                raise ValueError("Snapshot checksum mismatch")
        temporary.mkdir(parents=True, exist_ok=True)
        self.connection = duckdb.connect(config={
            "memory_limit": f"{limits.memory_mb}MB", "threads": limits.threads,
            "temp_directory": str(temporary), "max_temp_directory_size": f"{limits.spill_mb}MB",
            "preserve_insertion_order": False, "autoload_known_extensions": False,
            "autoinstall_known_extensions": False, "allow_community_extensions": False,
        })
        self.connection.read_parquet([str(p) for p in files]).create_view("source")
        self._schema = dict((r[0], r[1]) for r in self.connection.execute("DESCRIBE source").fetchall())
        escaped = ", ".join("'" + str(p).replace("'", "''") + "'" for p in files)
        self.connection.execute("SET allowed_paths = [" + escaped + "]")
        self.connection.execute("SET enable_external_access = false")
        self.connection.execute("SET lock_configuration = true")
        self.scanned_bytes = scanned

    def schema(self):
        return self._schema

    def health(self):
        return {"engine": self.name, "ready": self.connection.execute("SELECT 1").fetchall()[0][0] == 1}

    def explain(self, sql, parameters):
        validate(sql, self._schema, self.limits.result_rows)
        plan = self.connection.execute("EXPLAIN " + sql, parameters).fetchall()
        return {"estimated_plan": "\n".join(str(r[-1]) for r in plan),
                "input_bytes": self.scanned_bytes, "input_rows": self.manifest["row_count"]}

    def execute(self, sql, parameters):
        import duckdb
        validate(sql, self._schema, self.limits.result_rows)
        started = time.perf_counter()
        cursor = self.connection.execute(sql, parameters)
        columns = [c[0] for c in cursor.description]
        values, size = [], 0
        for row in iter(cursor.fetchone, None):
            if len(values) >= self.limits.result_rows:
                raise ValueError("Result row budget exceeded; narrow dimensions or filters")
            record = dict(zip(columns, (scalar(v) for v in row)))
            size += len(json.dumps(record, ensure_ascii=False, allow_nan=False).encode())
            if size > self.limits.result_bytes:
                raise ValueError("Result byte budget exceeded")
            values.append(record)
        return {"rows": values, "columns": columns, "result_rows": len(values),
                "result_bytes": size, "input_bytes": self.scanned_bytes,
                "input_rows": self.manifest["row_count"], "elapsed_ms": round((time.perf_counter()-started)*1000, 3),
                "engine": "duckdb", "engine_version": duckdb.__version__,
                "query_hash": fingerprint({"sql": sql, "parameters": parameters}),
                "result_hash": fingerprint(values), "sql": sql, "parameters": parameters,
                "snapshot_hash": self.manifest["snapshot_hash"]}

    def close(self):
        self.connection.close()
