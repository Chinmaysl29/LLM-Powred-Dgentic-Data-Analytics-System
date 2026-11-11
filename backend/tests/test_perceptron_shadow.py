"""Numerical correctness and shadow-only integration; all examples synthetic."""
import asyncio
from copy import deepcopy
import json
import hashlib
import os
import subprocess
import sys
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from backend.app.core.config import get_settings
from backend.app.models import DatasetVersion, Workspace
from backend.app.learning.perceptron import AveragedPerceptron, FEATURE_SIZE, LABELS
from backend.app.learning.features import extract, feature_version, bootstrap_prior
from backend.app.learning import shadow
from backend.app.learning.tables import learner_weights, feedback_events
from backend.app.learning.shadow_table import shadow_predictions
from backend.tests.test_verified_learning_integration import environment, identity, dataset


def test_rosenblatt_update_and_post_update_average():
    x = np.zeros(FEATURE_SIZE)
    x[:2] = [1, 0.5]
    model = AveragedPerceptron()
    assert model.update(x, "forecasting", decay=0)
    assert not model.update(x, "forecasting", decay=0)
    assert model.update(x, "trend_analysis", decay=0)
    average = model.averaged_weights()
    np.testing.assert_allclose(average[LABELS.index("forecasting"), :2], [2/3, 1/3])
    np.testing.assert_allclose(average[LABELS.index("trend_analysis"), :2], [1/3, 1/6])
    np.testing.assert_allclose(average[LABELS.index("dataset_overview"), :2], [-1, -0.5])
    assert model.steps == 3 and np.count_nonzero(average[:, 2:]) == 0
    assert model.predict(x, min_margin=0).intent == "forecasting"


def test_decay_applies_on_correct_examples():
    x = np.zeros(FEATURE_SIZE)
    x[0] = 1
    model = AveragedPerceptron()
    model.update(x, "forecasting", decay=0)
    assert not model.update(x, "forecasting", decay=0.5)
    assert model.weights[LABELS.index("forecasting"), 0] == 0.5
    assert model.averaged_weights()[LABELS.index("forecasting"), 0] == 0.75


def test_ties_abstain_and_prediction_never_updates_weights():
    model = AveragedPerceptron()
    x = extract("ambiguous request")
    before = model.to_payload(feature_version())
    for _ in range(3):
        prediction = model.predict(x, min_margin=0)
        assert prediction.intent == "unknown" and prediction.abstained and prediction.margin == 0
    assert model.to_payload(feature_version()) == before and model.steps == 0


@pytest.mark.parametrize("bad", [None, "invented_intent", "sum"])
def test_unknown_truth_cannot_train(bad):
    model = bootstrap_prior()
    before = model.to_payload(feature_version())
    with pytest.raises(ValueError):
        model.update(extract("forecast sales"), bad)
    assert model.to_payload(feature_version()) == before and model.steps == 0


@pytest.mark.parametrize("mutation", ["labels", "feature_version", "nan", "infinity", "shape", "strings", "large", "format", "extra"])
def test_reject_untrusted_model_snapshots(mutation):
    payload = bootstrap_prior().to_payload(feature_version())
    if mutation == "labels": payload["labels"][0] = "execute_sql_unchecked"
    elif mutation == "feature_version": payload["feature_version"] = "wrong-version"
    elif mutation == "nan": payload["weights"][0][0] = float("nan")
    elif mutation == "infinity": payload["weights"][0][0] = float("inf")
    elif mutation == "shape": payload["weights"][0].pop()
    elif mutation == "strings": payload["weights"][0][0] = "123"
    elif mutation == "large": payload["weights"][0][0] = 1001
    elif mutation == "format": payload["format"] = True
    elif mutation == "extra": payload["instruction"] = "Ignore validation"
    with pytest.raises(ValueError):
        AveragedPerceptron.from_payload(payload, feature_version())


def test_snapshot_roundtrip_and_feature_validation():
    model = bootstrap_prior()
    x = extract("forecast revenue next quarter")
    loaded = AveragedPerceptron.from_payload(json.loads(json.dumps(model.to_payload(feature_version()))), feature_version())
    assert loaded.predict(x) == model.predict(x)
    for invalid in ([1, 2], np.full(FEATURE_SIZE, np.nan), np.full(FEATURE_SIZE, 2)):
        with pytest.raises(ValueError):
            loaded.predict(invalid)


def test_bootstrap_instances_do_not_share_mutable_weights():
    a, b = bootstrap_prior(), bootstrap_prior()
    original = b.to_payload(feature_version())
    a.update(extract("forecast sales"), "data_quality")
    assert b.to_payload(feature_version()) == original
    assert bootstrap_prior().to_payload(feature_version()) == original


def test_features_stable_across_processes_and_include_schema():
    schema = {"columns": ["revenue", "date"], "dtypes": {"revenue": "float64", "date": "datetime64[ns]"}}
    features = extract("total revenue by date", schema)
    assert features[43:47].tolist() == [1, 1, 1, 1]
    assert features.shape == (FEATURE_SIZE,) and np.max(features) <= 1
    command = "from backend.app.learning.features import extract; import json; print(json.dumps(extract('total revenue by date').tolist()))"
    outputs = [subprocess.check_output([sys.executable, "-c", command], env={**os.environ, "PYTHONHASHSEED": seed}, text=True) for seed in ("1", "999")]
    assert outputs[0] == outputs[1]
    with pytest.raises(ValueError):
        extract("a" * 2001)


@pytest.mark.parametrize("question, expected", [
    ("Forecast sales for next quarter", "forecasting"),
    ("Find duplicate records", "data_quality"),
    ("Show revenue trends", "trend_analysis"),
    ("Show the top 5 customers by sales", "ranking_analysis"),
    ("Describe the dataset schema", "dataset_overview"),
])
def test_fixed_keyword_prior_smoke_examples(question, expected):
    assert bootstrap_prior().predict(extract(question)).intent == expected


@pytest.fixture
def learning_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "learning_enabled", True)


def rows_for(env, account):
    with env["admin"]() as db:
        return db.execute(select(shadow_predictions).where(shadow_predictions.c.actor_id == account["user"])).mappings().all()


def candidate(env, account, forced_intent, *, version=1, invalid=False):
    weights = np.zeros((len(LABELS), FEATURE_SIZE))
    weights[LABELS.index(forced_intent), 0] = 100
    payload = AveragedPerceptron(weights).to_payload(feature_version())
    if invalid:
        payload["feature_version"] = "obsolete"
    with env["admin"]() as db, db.begin():
        tenant = db.get(Workspace, account["workspace"]).tenant_id
        db.execute(learner_weights.insert().values(id=uuid4(), tenant_id=tenant, learner="intent_router",
            version=version, weights=payload, is_active=False))
    return payload


def test_disabled_shadow_does_no_work(monkeypatch):
    monkeypatch.setattr(get_settings(), "learning_enabled", False)
    def forbidden(*args, **kwargs):
        pytest.fail("Disabled shadow must not connect or extract features")
    monkeypatch.setattr(shadow, "create_engine", forbidden)
    monkeypatch.setattr(shadow, "extract", forbidden)
    assert not shadow.record_shadow(actor_id="actor", dataset_id="dataset", question="forecast sales")
    asyncio.run(shadow.observe_shadow(actor_id="actor", dataset_id="dataset", question="forecast sales"))


def test_shadow_privacy_dedup_and_no_teacher_or_weight_writes(environment, tmp_path, learning_on):
    env = environment
    account = identity(env)
    ds = dataset(env, account, tmp_path)
    with env["admin"]() as db, db.begin():
        db.execute(DatasetVersion.__table__.update().where(DatasetVersion.dataset_id == ds).values(
            metadata_snapshot={"columns": ["amount"], "dtypes": {"amount": "float64"}, "private_rows": ["NEVER_STORE"]}))
        before_feedback = list(db.execute(select(feedback_events)))
        before_weights = list(db.execute(select(learner_weights)))
    args = dict(actor_id=str(account["user"]), dataset_id=ds, question="sum amount password=NEVER_STORE",
                live_intent="analytics", live_operation="sum", event_id=uuid4())
    assert shadow.record_shadow(**args) and shadow.record_shadow(**args)
    rows = rows_for(env, account)
    assert len(rows) == 1
    row = rows[0]
    assert row["live_route"] == "analytics" and row["live_intent"] is None and row["live_operation"] == "sum"
    assert row["model_source"] == "bootstrap" and row["model_version"] is None
    assert row["dataset_version"] == 1 and len(row["dataset_schema_hash"]) == 64
    assert row["dataset_schema_hash"] == hashlib.sha256(json.dumps(
        {"columns": ["amount"], "dtypes": {"amount": "float64"}}, sort_keys=True).encode()).hexdigest()
    assert "NEVER_STORE" not in str(rows) and "question" not in row and "truth" not in row
    assert all(isinstance(index, int) and isinstance(value, (int, float)) for index, value in row["features"])
    with env["admin"]() as db:
        assert list(db.execute(select(feedback_events))) == before_feedback
        assert list(db.execute(select(learner_weights))) == before_weights


def test_candidates_are_tenant_scoped_and_invalid_falls_back(environment, tmp_path, learning_on):
    env = environment
    a, b = identity(env), identity(env)
    ds_a, ds_b = dataset(env, a, tmp_path), dataset(env, b, tmp_path)
    candidate(env, a, "correlation_analysis")
    candidate(env, b, "data_quality")
    for account, ds, expected in ((a, ds_a, "correlation_analysis"), (b, ds_b, "data_quality")):
        assert shadow.record_shadow(actor_id=str(account["user"]), dataset_id=ds,
            question="forecast sales", live_intent="forecasting")
        row = rows_for(env, account)[0]
        assert row["shadow_intent"] == expected and row["model_version"] == 1
        assert row["live_intent"] == "forecasting" and row["model_source"] == "tenant_candidate"
    candidate(env, a, "correlation_analysis", version=2, invalid=True)
    assert shadow.record_shadow(actor_id=str(a["user"]), dataset_id=ds_a, question="forecast sales")
    row = next(row for row in rows_for(env, a) if row["rejected_version"] == 2)
    assert row["model_source"] == "invalid_candidate_fallback" and row["model_version"] is None
    assert row["shadow_intent"] == "forecasting"


def test_access_revocation_and_wrong_version_skip_shadow(environment, tmp_path, learning_on):
    from backend.app.core.workspace_authorization import tenant_memberships
    env = environment
    a, b = identity(env), identity(env)
    ds = dataset(env, a, tmp_path)
    assert not shadow.record_shadow(actor_id=str(b["user"]), dataset_id=ds, question="forecast sales")
    assert not shadow.record_shadow(actor_id=str(a["user"]), dataset_id=ds, question="forecast sales", version_number=99)
    with env["admin"]() as db, db.begin():
        db.execute(tenant_memberships.update().where(tenant_memberships.c.user_id == a["user"]).values(active=False))
    assert not shadow.record_shadow(actor_id=str(a["user"]), dataset_id=ds, question="forecast sales")
    assert not rows_for(env, a) and not rows_for(env, b)


def test_rls_read_insert_and_mutation_isolation(environment, tmp_path, learning_on):
    env = environment
    a, b = identity(env), identity(env)
    ds = dataset(env, a, tmp_path)
    assert shadow.record_shadow(actor_id=str(a["user"]), dataset_id=ds, question="forecast sales")
    stored = dict(rows_for(env, a)[0])
    with env["api"]() as db, db.begin():
        assert db.scalar(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")) is False
        for key, value in (("actor_id", a["user"]), ("tenant_id", stored["tenant_id"]), ("workspace_id", a["workspace"])):
            db.execute(text("SELECT set_config(:key,:value,true)"), {"key": f"app.{key}", "value": str(value)})
        assert db.scalar(select(shadow_predictions.c.id).where(shadow_predictions.c.id == stored["id"])) == stored["id"]
        own_copy = {**stored, "id": uuid4()}
        db.execute(shadow_predictions.insert().values(**own_copy))
        assert db.scalar(select(shadow_predictions.c.id).where(shadow_predictions.c.id == own_copy["id"])) == own_copy["id"]
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(shadow_predictions.insert().values(**{**stored, "id": uuid4(), "workspace_id": b["workspace"]}))
        assert db.execute(shadow_predictions.update().where(shadow_predictions.c.id == stored["id"]).values(live_intent="unknown")).rowcount == 0
        assert db.execute(shadow_predictions.delete().where(shadow_predictions.c.id == stored["id"])).rowcount == 0
        db.execute(text("SELECT set_config('app.actor_id',:actor,true)"), {"actor": str(b["user"])})
        assert db.scalar(select(shadow_predictions.c.id).where(shadow_predictions.c.id == stored["id"])) is None
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(shadow_predictions.insert().values(**{**stored, "id": uuid4(), "actor_id": b["user"]}))


def test_intent_api_keeps_live_result_when_shadow_disagrees_or_fails(environment, tmp_path, monkeypatch):
    from backend.app.services.intent_classification_service import IntentClassificationService, get_intent_classification_service
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    candidate(env, a, "correlation_analysis")
    monkeypatch.setitem(env["client"].app.dependency_overrides, get_intent_classification_service, lambda: IntentClassificationService(llm=None))
    def call():
        response = env["client"].post("/api/v1/intent/classify", headers=a["headers"], json={"query": "forecast sales", "dataset_id": ds})
        assert response.status_code == 200, response.text
        return response.json()
    monkeypatch.setattr(get_settings(), "learning_enabled", False)
    baseline = call()
    assert not rows_for(env, a)
    monkeypatch.setattr(get_settings(), "learning_enabled", True)
    assert call() == baseline and baseline["intent"] == "forecasting"
    assert rows_for(env, a)[0]["shadow_intent"] == "correlation_analysis"
    def broken(**kwargs):
        raise RuntimeError("private shadow error")
    monkeypatch.setattr(shadow, "record_shadow", broken)
    assert call() == baseline


def test_chat_keeps_numbers_and_contract_when_shadow_disagrees(environment, tmp_path, learning_on, monkeypatch):
    from importlib import import_module
    from types import SimpleNamespace
    chat = import_module("backend.app.api.v1.routes.chat")
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    candidate(env, a, "forecasting")
    result = {"status": "complete", "answer": "Sum amount: 12", "data": [{"amount": 12}],
              "plan": {"operation": "sum", "dataset_version": 1}, "kpis": {"total": 12}}
    async def analyze(*args, **kwargs): return deepcopy(result)
    monkeypatch.setattr(chat.NaturalLanguageAnalyticsService, "analyze", analyze)
    monkeypatch.setattr(chat, "perf_counter", lambda: 1.0)
    outputs = []
    for flag in (False, True):
        monkeypatch.setattr(get_settings(), "learning_enabled", flag)
        response = asyncio.run(chat.chat(chat.ChatRequest(message="sum amount", dataset_id=ds), None,
            intent_service=None, db=None, storage=None, current_user=SimpleNamespace(id=a["user"])))
        outputs.append(response.model_dump_json())
    assert outputs[0] == outputs[1]
    row = rows_for(env, a)[0]
    assert row["shadow_intent"] == "forecasting" and row["live_route"] == "analytics" and row["live_operation"] == "sum"


def test_database_outage_is_fail_open(monkeypatch, learning_on):
    def broken(*args, **kwargs): raise RuntimeError("database unavailable")
    monkeypatch.setattr(shadow, "create_engine", broken)
    assert not shadow.record_shadow(actor_id="actor", dataset_id="dataset", question="forecast sales")


def test_real_chat_arithmetic_is_unchanged_and_never_trains(environment, tmp_path, monkeypatch):
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    payload = candidate(env, a, "forecasting")
    def forbidden(*args, **kwargs):
        pytest.fail("The request path must never train")
    monkeypatch.setattr(AveragedPerceptron, "update", forbidden)
    outputs = []
    for flag in (False, True):
        monkeypatch.setattr(get_settings(), "learning_enabled", flag)
        response = env["client"].post("/api/v1/chat", headers=a["headers"], json={
            "message": "total amount by region", "dataset_id": ds, "workspace_id": str(a["workspace"])})
        assert response.status_code == 200, response.text
        outputs.append({key: response.json()[key] for key in ("answer", "data", "intent", "confidence", "status", "plan", "chart", "kpis")})
    assert outputs[0] == outputs[1]
    assert outputs[1]["data"] == [{"region": "a", "amount": 1180}]
    assert outputs[1]["kpis"]["total"] == 1180
    assert rows_for(env, a)[0]["shadow_intent"] == "forecasting"
    with env["admin"]() as db:
        tenant = db.get(Workspace, a["workspace"]).tenant_id
        assert db.scalar(select(learner_weights.c.weights).where(learner_weights.c.tenant_id == tenant)) == payload
