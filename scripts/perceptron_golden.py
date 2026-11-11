"""Freeze/evaluate approved local golden sources without DB access or training."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "evaluate"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source", action="append", default=[], help="name=relative/path.xlsx; repeat for each of four sources")
    parser.add_argument("--manifest-sha256", help="Reviewed digest emitted by freeze")
    parser.add_argument("--candidate", type=Path, help="Validated JSON inference snapshot; default is the fixed seed")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    from backend.app.learning.golden import freeze, evaluate, encode
    try:
        if args.command == "freeze":
            sources = dict(item.split("=", 1) for item in args.source)
            if len(sources) != len(args.source):
                raise ValueError("Duplicate source key")
            value = freeze(args.root, sources, args.manifest)
            print(json.dumps({"manifest_sha256": value, "status": "frozen"}))
            return 0
        if not args.manifest_sha256 or not args.report:
            parser.error("evaluate requires --manifest-sha256 and --report")
        payload = None
        if args.candidate:
            if args.candidate.stat().st_size > 1_000_000:
                raise ValueError("Candidate exceeds size bound")
            payload = json.loads(args.candidate.read_bytes())
        result = asyncio.run(evaluate(args.root, args.manifest, args.manifest_sha256, payload))
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("xb") as stream:
            stream.write(encode(result))
        print(json.dumps({key: result[key] for key in ("case_count", "intent_count", "answer_count", "baseline_correct",
            "candidate_correct", "answers_passed", "quality_gate_passed", "promotion_performed")}))
        return 0 if result["quality_gate_passed"] else 1
    except (ValueError, OSError, KeyError, TypeError):
        # Do not expose raw data, workbook contents, or credentials in exceptions.
        print("Golden evaluation refused: check input integrity, source contract and output paths.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
