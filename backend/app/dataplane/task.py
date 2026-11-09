"""One execution per killable child; receives no application database credentials."""
import json
import sys
from pathlib import Path
from backend.app.dataplane.config import Limits
from backend.app.dataplane.contracts import Metric, QueryPlan, CleaningPlan
from backend.app.dataplane.storage import write_new_json


def run(request):
    limits = Limits(**request["limits"])
    root, output = Path(request["root"]), Path(request["output"])
    kind = request["kind"]
    if kind == "ingest":
        from backend.app.dataplane.ingestion import materialize
        return materialize(Path(request["source"]), output, root, limits,
                           version_id=request["version_id"], resume=request.get("checkpoint"))
    if kind == "postgres":
        from backend.app.dataplane.postgres import PostgresEngine
        engine = PostgresEngine(request["connection"], limits)
    else:
        from backend.app.dataplane.engine import DuckDBEngine
        engine = DuckDBEngine(root, request["manifest"], output/"spill", limits)
    try:
        if kind in ("query", "postgres"):
            from backend.app.dataplane.semantic import compile_plan
            plan, metric = QueryPlan(**request["plan"]), Metric(**request["metric"])
            if plan.limit > limits.result_rows:
                raise ValueError("Result limit exceeds policy")
            engine.limits = limits.model_copy(update={"result_rows": plan.limit})
            sql, args = compile_plan(plan, metric, engine.schema())
            estimate = engine.explain(sql, args)
            result = {**engine.execute(sql, args), "plan": plan.model_dump(), "metric": metric.model_dump(),
                    "estimate": estimate, "semantic_id": request["semantic_id"],
                    "snapshot_id": request.get("snapshot_id"), "source_id": request.get("source_id")}
            # Materialize the bounded aggregate as the curated layer, with the same
            # values and digest used by the dashboard and report.
            import pyarrow as pa
            import pyarrow.parquet as pq
            import resource
            from backend.app.dataplane.storage import digest
            output.mkdir(parents=True, exist_ok=True)
            if result["rows"]:
                curated = output/"aggregate.parquet"
                pq.write_table(pa.Table.from_pylist(result["rows"]), curated, compression="zstd")
                result["curated"] = {"path": str(curated.relative_to(root)), "sha256": digest(curated)}
            result["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
            write_new_json(output/"evidence.json", result)
            return result
        if kind == "quality":
            from backend.app.dataplane.quality import profile
            return profile(engine, request.get("history", []), request["source_created"], request.get("previous_schema"))
        if kind == "proposal":
            from backend.app.dataplane.cleaning import propose
            return propose(engine, CleaningPlan(**request["plan"]))
        if kind == "clean":
            from backend.app.dataplane.cleaning import apply_cleaning
            return apply_cleaning(engine, CleaningPlan(**request["plan"]), output/"cleaned", root, request["version_id"])
        raise ValueError("Unknown dataplane operation")
    finally:
        engine.close()


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    try:
        result = run(request)
        write_new_json(Path(sys.argv[2]), {"ok": True, "result": result})
    except Exception as error:
        # Do not expose file paths, rows, queries or credentials in errors/logs.
        safe = str(error) if isinstance(error, ValueError) else type(error).__name__
        write_new_json(Path(sys.argv[2]), {"ok": False, "error": safe[:240]})
        sys.exit(2)


if __name__ == "__main__":
    main()
