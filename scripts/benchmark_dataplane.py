"""Synthetic engine benchmark; never loads user files or connects to a database."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def child(root, rows, mode):
    import duckdb
    from backend.app.dataplane.config import Limits
    from backend.app.dataplane.engine import DuckDBEngine
    from backend.app.dataplane.storage import digest, fingerprint
    from backend.app.dataplane.contracts import Metric, QueryPlan
    from backend.app.dataplane.semantic import compile_plan
    folder = root/str(rows)
    source = folder/"synthetic.parquet"
    started = time.perf_counter()
    limits = Limits(memory_mb=512, worker_memory_mb=1024, threads=2, scan_mb=4096)
    if mode == "generate":
        folder.mkdir()
        conn = duckdb.connect(config={"memory_limit": "512MB", "threads": 2,
            "temp_directory": str(folder/"generation-spill"), "max_temp_directory_size": "2GB",
            "preserve_insertion_order": False})
        target = str(source).replace("'", "''")
        conn.execute(f"COPY (SELECT i::BIGINT row_id, (i%4)::INTEGER region, (i%10000)::BIGINT amount FROM range({rows}) t(i)) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)")
        conn.close()
        result = {"mode": mode, "rows": rows, "seconds": time.perf_counter()-started, "bytes": source.stat().st_size}
    else:
        manifest = {"version_id": "synthetic", "row_count": rows, "files": [
            {"path": str(source.relative_to(root)), "sha256": digest(source)}]}
        manifest["snapshot_hash"] = fingerprint(manifest)
        engine = DuckDBEngine(root, manifest, folder/"query-spill", limits)
        metric = Metric(name="amount", column="amount", description="Synthetic amount")
        plan = QueryPlan(metric="amount", dimensions=["region"])
        sql, args = compile_plan(plan, metric, engine.schema())
        result = engine.execute(sql, args)
        expected = {i: (rows//10000)*sum(range(i, 10000, 4)) for i in range(4)}
        assert {r["region"]: r["value"] for r in result["rows"]} == expected
        engine.close()
        result.update(mode=mode, source_rows=rows, oracle_passed=True,
                      total_seconds=time.perf_counter()-started, source_bytes=source.stat().st_size)
    result["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    (folder/(mode+".json")).write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--rows", type=int, nargs="+", default=[1_000_000, 10_000_000, 100_000_000])
    parser.add_argument("--child", choices=["generate", "query"])
    args = parser.parse_args()
    if args.child:
        child(args.root, args.rows[0], args.child)
        return
    target = args.root/("run-"+uuid4().hex[:10])
    target.mkdir(parents=True, exist_ok=False)
    results = []
    for rows in args.rows:
        if rows <= 0 or rows % 10000:
            raise ValueError("Rows must be positive multiples of 10,000")
        for mode in ("generate", "query"):
            command = [sys.executable, str(Path(__file__).resolve()), "--root", str(target),
                       "--rows", str(rows), "--child", mode]
            try:
                completed = subprocess.run(command, timeout=300, check=False)
                file = target/str(rows)/(mode+".json")
                value = json.loads(file.read_text()) if completed.returncode == 0 else {
                    "mode": mode, "source_rows": rows, "exit_code": completed.returncode, "failed": True}
            except subprocess.TimeoutExpired:
                value = {"mode": mode, "source_rows": rows, "failed": True, "reason": "300-second wall limit"}
            results.append(value)
            (target/"summary.json").write_text(json.dumps(results, indent=2))
            if value.get("failed"):
                print(json.dumps({"evidence": str(target), "stopped_at": rows}), flush=True)
                return
    print(json.dumps({"evidence": str(target), "all_passed": True}), flush=True)


if __name__ == "__main__":
    main()

