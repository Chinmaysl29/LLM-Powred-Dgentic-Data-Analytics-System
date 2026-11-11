"""Offline regression integrity tests. All workbooks here contain synthetic data."""
import asyncio
from decimal import Decimal
import json

import pytest
from openpyxl import Workbook

from backend.app.learning.golden import freeze, evaluate, load_manifest, encode, digest, same_rows, source_bytes
from backend.app.learning.golden_cases import SOURCES, question_contracts
from backend.app.learning.golden_reference import expected_rows, number
from backend.app.learning.features import bootstrap_prior, feature_version
from backend.app.learning.perceptron import AveragedPerceptron, LABELS


@pytest.fixture
def frozen(tmp_path):
    sources = {}
    for name, spec in SOURCES.items():
        book = Workbook()
        sheet = book.active
        sheet.title = spec["sheet"]
        sheet.append(["Synthetic financial example"])
        sheet.append(spec["columns"])
        for index in range(1, 13):
            values = {column: index * (position + 1) + 0.25 for position, column in enumerate(spec["columns"])}
            values.update(id=index, company_id=f"company-{index % 6}", year=f"Mar {2020 + index}",
                          pros="Synthetic positive", cons="Synthetic negative")
            if index == 3:
                for metric in spec["metrics"]:
                    values[metric] = None
            sheet.append([values[column] for column in spec["columns"]])
        path = tmp_path / f"{name}.xlsx"
        book.save(path)
        book.close()
        sources[name] = path.name
    path = tmp_path / "manifest.json"
    fingerprint = freeze(tmp_path, sources, path)
    return tmp_path, sources, path, fingerprint


def test_independent_decimal_reference():
    rows = [{"company": "a", "amount": "$1,000.10"}, {"company": "a", "amount": "(20.05)"},
            {"company": "b", "amount": None}, {"company": None, "amount": "2.45"}]
    assert expected_rows(rows, "sum", "amount") == [{"amount": "982.50"}]
    assert expected_rows(rows, "average", "amount") == [{"amount": "327.50"}]
    assert expected_rows(rows, "min", "amount") == [{"amount": "-20.05"}]
    assert expected_rows(rows, "max", "amount") == [{"amount": "1000.10"}]
    assert expected_rows(rows, "count") == [{"records": "4"}]
    assert expected_rows(rows, "top", "amount", "company", limit=2) == [
        {"company": "a", "amount": "980.05"}, {"company": None, "amount": "2.45"}]
    assert expected_rows(rows[2:3], "sum", "amount") == [{"amount": None}]
    assert number("12.5%") == Decimal("12.5")
    assert number("\u20b91,200.50") == Decimal("1200.50")


@pytest.mark.parametrize("value", [True, "NaN", "Infinity", "not a number", "__import__('os').system('echo bad')"])
def test_reference_rejects_invalid_measures(value):
    with pytest.raises(ValueError):
        number(value)


def test_reference_freeze_has_no_classifier_or_executor_dependency(frozen, monkeypatch):
    from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
    from backend.app.services.intent_classification_service import IntentRegistry

    def forbidden(*args, **kwargs):
        raise AssertionError("Reference must not ask implementation for expected answers")

    monkeypatch.setattr(NaturalLanguageAnalyticsService, "analyze", forbidden)
    monkeypatch.setattr(IntentRegistry, "match_heuristic", forbidden)
    root, sources, path, fingerprint = frozen
    second = root / "second.json"
    assert freeze(root, sources, second) == fingerprint
    assert path.read_bytes() == second.read_bytes()
    manifest = load_manifest(path, fingerprint)
    assert len(manifest["cases"]) == 84
    assert {c["expected_intent"] for c in manifest["cases"] if c["kind"] == "intent"} == set(LABELS)
    with pytest.raises(FileExistsError):
        freeze(root, sources, path)


def test_evaluation_is_deterministic_read_only_and_never_trains(frozen, monkeypatch):
    root, sources, path, fingerprint = frozen
    before = {name: (root / name).read_bytes() for name in sources.values()}
    payload = bootstrap_prior().to_payload(feature_version())
    serialized = encode(payload)

    def forbidden(*args, **kwargs):
        raise AssertionError("Golden examples must never train weights")

    monkeypatch.setattr(AveragedPerceptron, "update", forbidden)
    first = asyncio.run(evaluate(root, path, fingerprint, payload))
    assert first == asyncio.run(evaluate(root, path, fingerprint, payload))
    assert first["case_count"] == 84 and first["answer_count"] == first["answers_passed"] == 50
    assert first["intent_count"] == 34
    assert not first["training_performed"] and not first["promotion_performed"]
    assert encode(payload) == serialized
    assert before == {name: (root / name).read_bytes() for name in sources.values()}
    assert all("question" not in item and "expected_rows" not in item for item in first["cases"])


def test_weak_candidate_fails_gate(frozen):
    root, _, path, fingerprint = frozen
    payload = AveragedPerceptron().to_payload(feature_version())
    report = asyncio.run(evaluate(root, path, fingerprint, payload))
    assert not report["quality_gate_passed"] and not report["beats_baseline"]
    assert report["regressions"] and report["candidate_correct"] == 2
    assert report["answers_passed"] == 50


def test_wrong_answer_and_executor_error_fail_gate(frozen, monkeypatch):
    from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
    original = NaturalLanguageAnalyticsService.analyze

    async def broken(self, question, **kwargs):
        if question == "count records":
            raise RuntimeError("private source data must not appear in report")
        result = await original(self, question, **kwargs)
        if question == "show total net_cash_flow":
            result["data"][0]["net_cash_flow"] += 100
        return result

    monkeypatch.setattr(NaturalLanguageAnalyticsService, "analyze", broken)
    root, _, path, fingerprint = frozen
    report = asyncio.run(evaluate(root, path, fingerprint))
    assert not report["quality_gate_passed"] and report["answers_passed"] == 45
    assert "private source" not in json.dumps(report)


@pytest.mark.parametrize("change", ["digest", "coverage", "duplicate", "label", "tolerance", "source"])
def test_rejects_tampered_contract(frozen, change):
    root, _, path, fingerprint = frozen
    manifest = json.loads(path.read_bytes())
    if change == "coverage":
        manifest["cases"].pop()
    elif change == "duplicate":
        manifest["cases"][1] = manifest["cases"][0]
    elif change == "label":
        manifest["cases"][-1]["expected_intent"] = "sql_query"
    elif change == "tolerance":
        manifest["absolute_tolerance"] = "1000000"
    elif change == "source":
        manifest["sources"]["cashflow"]["columns"] = ["wrong"]
    else:
        fingerprint = "0" * 64
    if change != "digest":
        path.write_bytes(encode(manifest))
        fingerprint = digest(path.read_bytes())
    with pytest.raises(ValueError):
        load_manifest(path, fingerprint)


def test_source_bytes_are_hash_pinned(frozen):
    root, sources, path, fingerprint = frozen
    with (root / sources["cashflow"]).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="source hash"):
        asyncio.run(evaluate(root, path, fingerprint))


def test_outside_root_and_symlink_refused(tmp_path):
    outside = tmp_path / "outside.xlsx"
    outside.write_bytes(b"not opened")
    inside = tmp_path / "inside"
    inside.mkdir()
    for relative in ("../outside.xlsx", str(outside)):
        with pytest.raises(ValueError):
            source_bytes(inside, relative)
    (inside / "link.xlsx").symlink_to(outside)
    with pytest.raises(ValueError):
        source_bytes(inside, "link.xlsx")


def test_invalid_candidate_refused(frozen):
    root, _, path, fingerprint = frozen
    payload = bootstrap_prior().to_payload(feature_version())
    payload["feature_version"] = "incompatible"
    with pytest.raises(ValueError):
        asyncio.run(evaluate(root, path, fingerprint, payload))


@pytest.mark.parametrize("actual,expected,passed", [
    (0, "0", True), (None, None, True), (None, "0", False),
    (True, "1", False), (float("nan"), "0", False),
    (1.000000001, "1", True), (1.01, "1", False),
    (1000000000000.005, "1000000000000", True),
])
def test_numeric_tolerance(actual, expected, passed):
    assert same_rows([{"v": actual}], [{"v": expected}], "v", None) is passed


def test_group_membership_cardinality_and_ranking_order():
    rows = [{"group": "a", "v": 20}, {"group": "b", "v": 10}]
    assert same_rows(rows[::-1], rows, "v", "group")
    assert not same_rows(rows[::-1], rows, "v", "group", ordered=True)
    assert not same_rows(rows[:1], rows, "v", "group")
    assert not same_rows([{"group": "c", "v": 20}, rows[1]], rows, "v", "group")
    assert not same_rows([{"v": 20}, rows[1]], rows, "v", "group")
