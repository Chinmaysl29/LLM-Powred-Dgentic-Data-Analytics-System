"""Offline, read-only regression evaluation. Never trains or promotes weights."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import tempfile

from backend.app.learning.golden_cases import SOURCES, question_contracts
from backend.app.learning.golden_reference import read_excel, expected_rows

MAX_SOURCE_BYTES = 50_000_000
ABS_TOLERANCE = Decimal("0.00000001")
REL_TOLERANCE = Decimal("0.00000000000001")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encode(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def source_bytes(root: Path, relative: str) -> bytes:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()) or path.suffix.lower() != ".xlsx":
        raise ValueError("Golden source must be an Excel file within the source root")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Golden source exceeds size bound")
    return path.read_bytes()


def freeze(root: Path, sources: dict[str, str], destination: Path) -> str:
    """Create once. Re-freezing requires a new destination, never overwrite gold."""
    if set(sources) != set(SOURCES):
        raise ValueError("All four approved source types are required")
    records, provenance = {}, {}
    for name, spec in SOURCES.items():
        raw = source_bytes(root, sources[name])
        rows = read_excel(raw, sheet_name=spec["sheet"], header_row=spec["header_row"], columns=spec["columns"])
        if not rows:
            raise ValueError("Empty golden source")
        records[name] = rows
        provenance[name] = {"path": sources[name], "sha256": digest(raw), "row_count": len(rows),
                            "sheet": spec["sheet"], "header_row": spec["header_row"], "columns": spec["columns"]}
    cases = question_contracts()
    for case in cases:
        if case["kind"] == "analytics":
            case["expected_rows"] = [] if case["expected_status"] == "clarification_required" else expected_rows(
                records[case["source"]], case["operation"], case["metric"], case["dimension"])
    manifest = {"format": 1, "purpose": "regression_only", "reference": "openpyxl + Decimal, 50-digit context",
                "absolute_tolerance": str(ABS_TOLERANCE), "relative_tolerance": str(REL_TOLERANCE),
                "sources": provenance, "cases": cases}
    raw_manifest = encode(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # x mode protects an existing approved manifest, even under concurrent runs.
    with destination.open("xb") as stream:
        stream.write(raw_manifest)
    return digest(raw_manifest)


def load_manifest(path: Path, expected_digest: str) -> dict:
    if path.stat().st_size > 2_000_000:
        raise ValueError("Golden manifest exceeds size bound")
    raw = path.read_bytes()
    if digest(raw) != expected_digest:
        raise ValueError("Golden manifest hash mismatch")
    manifest = json.loads(raw)
    if (manifest.get("format") != 1 or manifest.get("purpose") != "regression_only"
            or manifest.get("absolute_tolerance") != str(ABS_TOLERANCE)
            or manifest.get("relative_tolerance") != str(REL_TOLERANCE)
            or set(manifest.get("sources", {})) != set(SOURCES)):
        raise ValueError("Unsupported golden manifest contract")
    contracts = question_contracts()
    cases = manifest.get("cases", [])
    if len(cases) != len(contracts) or len(cases) < 30:
        raise ValueError("Incomplete golden coverage")
    for case, contract in zip(cases, contracts):
        if {key: value for key, value in case.items() if key != "expected_rows"} != contract:
            raise ValueError("Golden case contract changed or duplicated")
        if case["kind"] == "analytics" and not isinstance(case.get("expected_rows"), list):
            raise ValueError("Golden answer is missing")
    for name, source in manifest["sources"].items():
        spec = SOURCES[name]
        if any(source.get(key) != spec[key] for key in ("columns", "sheet", "header_row")):
            raise ValueError("Golden source contract changed")
        if type(source.get("row_count")) is not int or source["row_count"] <= 0:
            raise ValueError("Golden source row count is invalid")
    return manifest


def same_rows(actual: list[dict], expected: list[dict], numeric_column: str | None,
              dimension: str | None, *, ordered: bool = False) -> bool:
    if len(actual) != len(expected):
        return False
    if dimension and not ordered:
        actual = sorted(actual, key=lambda row: str(row.get(dimension)))
        expected = sorted(expected, key=lambda row: str(row.get(dimension)))
    for left, right in zip(actual, expected):
        if set(left) != set(right):
            return False
        for key, target in right.items():
            value = left[key]
            if key != numeric_column:
                if value != target:
                    return False
            elif target is None or value is None:
                if target is not None or value is not None:
                    return False
            else:
                try:
                    if isinstance(value, bool):
                        return False
                    a, b = Decimal(str(value)), Decimal(str(target))
                    if not a.is_finite() or not b.is_finite() or abs(a - b) > max(ABS_TOLERANCE, abs(b) * REL_TOLERANCE):
                        return False
                except (InvalidOperation, ValueError):
                    return False
    return True


async def evaluate(root: Path, manifest_path: Path, expected_digest: str, candidate_payload: dict | None = None,
                   *, allow_unknown: bool = False) -> dict:
    # Imports are intentionally absent from the independent freeze/reference path.
    from backend.app.learning.features import extract, bootstrap_prior, feature_version
    from backend.app.learning.perceptron import AveragedPerceptron
    from backend.app.services.intent_classification_service import IntentRegistry
    from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
    from backend.app.services.tabular_loader import load_tabular_dataframe

    manifest = load_manifest(manifest_path, expected_digest)
    model = bootstrap_prior() if candidate_payload is None else AveragedPerceptron.from_payload(candidate_payload, feature_version())
    candidate_hash = digest(encode(model.to_payload(feature_version())))
    frames, source_hashes = {}, {}
    # Read each original once and evaluate the exact bytes whose hash was checked.
    with tempfile.TemporaryDirectory(prefix="perceptron-golden-") as directory:
        for name, source in manifest["sources"].items():
            raw = source_bytes(root, source["path"])
            if digest(raw) != source["sha256"]:
                raise ValueError("Golden source hash mismatch")
            path = Path(directory) / f"{name}.xlsx"
            path.write_bytes(raw)
            frame = load_tabular_dataframe(path)
            if len(frame) != source["row_count"] or list(frame.columns) != source["columns"]:
                raise ValueError("Application loader disagrees with frozen source structure")
            frames[name] = frame
            source_hashes[name] = source["sha256"]

    registry, analytics = IntentRegistry(), NaturalLanguageAnalyticsService()
    results = []
    for case in manifest["cases"]:
        frame = frames[case["source"]]
        result = {"id": case["id"], "kind": case["kind"], "passed": False}
        if case["kind"] == "intent":
            matched, _, _ = registry.match_heuristic(case["question"])
            baseline = matched.name if matched else "unknown"
            schema = {"columns": list(frame.columns), "dtypes": {c: str(t) for c, t in frame.dtypes.items()}}
            prediction = model.predict(extract(case["question"], schema), allow_unknown=allow_unknown)
            result.update(expected_intent=case["expected_intent"], baseline_intent=baseline,
                shadow_intent=prediction.intent, abstained=prediction.abstained,
                baseline_passed=baseline == case["expected_intent"], passed=prediction.intent == case["expected_intent"])
        else:
            # This invokes the existing deterministic executor, not the learner.
            # Check the actual chat bypass predicate as well as its operation.
            try:
                if not analytics.is_analytics_query(case["question"]):
                    raise ValueError("Golden question did not select the analytics route")
                output = await analytics.analyze(case["question"], dataframe=frame.copy(deep=True))
                numeric = "records" if case["operation"] == "count" else case["metric"]
                result["passed"] = (output.get("status") == case["expected_status"]
                    and (output.get("plan") or {}).get("operation") == case["operation"]
                    and same_rows(output.get("data", []), case["expected_rows"], numeric, case["dimension"],
                                  ordered=case["operation"] == "top"))
                result["status"] = output.get("status")
            except Exception:
                result["error"] = "ANALYTICS_EXECUTION_FAILED"
        results.append(result)
    intents = [row for row in results if row["kind"] == "intent"]
    answers = [row for row in results if row["kind"] == "analytics"]
    baseline_correct = sum(row["baseline_passed"] for row in intents)
    candidate_correct = sum(row["passed"] for row in intents)
    regressions = [row["id"] for row in intents if row["baseline_passed"] and not row["passed"]]
    code_paths = [Path(__file__), Path(__file__).with_name("golden_cases.py"),
                  Path(__file__).with_name("golden_reference.py"), Path(__file__).with_name("features.py"),
                  Path(__file__).with_name("perceptron.py"),
                  Path(__file__).parents[1] / "services/natural_language_analytics.py",
                  Path(__file__).parents[1] / "services/tabular_loader.py",
                  Path(__file__).parents[1] / "services/intent_classification_service.py"]
    code_digest = digest(b"".join(path.read_bytes() for path in code_paths))
    return {"format": 1, "manifest_digest": expected_digest, "candidate_digest": candidate_hash,
        "unknown_policy": "explicit_if_confident" if allow_unknown else "abstain",
        "feature_version": feature_version(), "code_digest": code_digest, "source_hashes": source_hashes,
        "case_count": len(results), "intent_count": len(intents), "answer_count": len(answers),
        "baseline_correct": baseline_correct, "candidate_correct": candidate_correct,
        "baseline_accuracy": baseline_correct / len(intents), "candidate_accuracy": candidate_correct / len(intents),
        "answers_passed": sum(row["passed"] for row in answers), "abstentions": sum(row["abstained"] for row in intents),
        "regressions": regressions, "beats_baseline": candidate_correct > baseline_correct,
        "quality_gate_passed": all(row["passed"] for row in results) and not regressions and candidate_correct >= baseline_correct,
        "promotion_performed": False, "training_performed": False, "cases": results}
