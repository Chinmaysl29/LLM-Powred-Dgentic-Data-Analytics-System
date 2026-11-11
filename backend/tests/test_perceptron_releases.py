"""Release isolation/atomicity using synthetic tenants, workbooks and gate reports."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from backend.app.core.config import get_settings
from backend.app.core.workspace_authorization import tenant_memberships
from backend.app.learning import lifecycle, release, routing, shadow
from backend.app.learning.features import bootstrap_prior, feature_version
from backend.app.learning.golden import digest, encode
from backend.app.learning.golden_cases import question_contracts
from backend.app.learning.perceptron import AveragedPerceptron, LABELS, FEATURE_SIZE
from backend.app.learning.release_table import router_releases
from backend.app.learning.tables import learner_weights
from backend.app.models import Workspace
from backend.app.services.intent_classification_service import IntentClassificationService, get_intent_classification_service
from backend.tests.test_verified_learning_integration import environment, identity, dataset
from backend.tests.test_perceptron_golden import frozen


@pytest.fixture
def learning_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "learning_enabled", True)


def tenant_of(env, account):
    with env["admin"]() as db:
        return db.get(Workspace, account["workspace"]).tenant_id


def forced(intent):
    weights = np.zeros((len(LABELS), FEATURE_SIZE))
    weights[LABELS.index(intent), 0] = 100
    return AveragedPerceptron(weights).to_payload(feature_version())


def staged(env, account, payload):
    tenant = tenant_of(env, account)
    version = lifecycle.stage(env["admin"], account["user"], tenant, payload)["version"]
    return tenant, version


def approved_fixture(env, account, payload):
    # Runtime tests install an operator-written synthetic approval. This is not
    # a claim that these deliberately forced weights pass the real golden set.
    tenant, version = staged(env, account, payload)
    with env["admin"]() as db, db.begin():
        db.execute(learner_weights.update().where(learner_weights.c.tenant_id == tenant).values(is_active=True))
        lifecycle.event(db, account["user"], tenant, "promote", version, 0, payload, {"synthetic_fixture": True})
    return tenant, version


def synthetic_report(payload, *, wrong=False):
    # A hypothetical perfect candidate over a baseline with one miss. Lifecycle
    # transaction tests stub the evaluator; actual evaluation is tested below.
    cases = []
    for contract in question_contracts():
        row = {"id": contract["id"], "kind": contract["kind"], "passed": True}
        if contract["kind"] == "intent":
            expected = contract["expected_intent"]
            baseline = "forecasting" if contract["id"] == "intent-dataset_overview-1" else expected
            row.update(expected_intent=expected, baseline_intent=baseline, baseline_passed=baseline == expected,
                       shadow_intent=expected, abstained=expected == "unknown")
        cases.append(row)
    if wrong:
        cases[0]["passed"] = False
    return {"cases": cases, "quality_gate_passed": not wrong, "candidate_digest": digest(encode(payload)),
            "unknown_policy": "explicit_if_confident",
            "manifest_digest": "m" * 64, "feature_version": feature_version(), "code_digest": "c" * 64,
            "source_hashes": {}, "case_count": len(cases)}


def install_evaluator(monkeypatch, hook=None, *, wrong=False):
    async def evaluate(root, manifest, fingerprint, payload, *, allow_unknown=False):
        assert allow_unknown
        if hook:
            hook()
        return synthetic_report(payload, wrong=wrong)
    monkeypatch.setattr(lifecycle, "evaluate", evaluate)


def promote(env, account, tenant, version, expected=0):
    return asyncio.run(lifecycle.promote(env["admin"], account["user"], tenant, version,
        expected, Path("."), Path("manifest.json"), "m" * 64))


def test_disabled_and_llm_paths_preserve_original_service(monkeypatch):
    original = IntentClassificationService(llm=None)
    monkeypatch.setattr(get_settings(), "learning_enabled", False)
    def forbidden(*args, **kwargs):
        pytest.fail("Disabled router must not open a connection")
    monkeypatch.setattr(routing, "create_engine", forbidden)
    assert routing.scoped_router(original, "actor") is original
    assert routing.read_prediction("actor", "dataset", "forecast") is None
    monkeypatch.setattr(get_settings(), "learning_enabled", True)
    with_llm = IntentClassificationService(llm=object())
    assert routing.scoped_router(with_llm, "actor") is with_llm
    assert routing.scoped_router(original, None) is original


def test_stage_versions_are_immutable_serialized_and_tenant_local(environment):
    env = environment
    a, b = identity(env), identity(env)
    tenant = tenant_of(env, a)
    payload = forced("forecasting")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(lifecycle.stage, env["admin"], a["user"], tenant, payload) for _ in range(2)]
        assert sorted(f.result()["version"] for f in futures) == [1, 2]
    assert staged(env, b, payload)[1] == 1
    assert lifecycle.status(env["admin"], a["user"], tenant) == {"active_version": 0,
        "versions": [{"version": 1, "is_active": False}, {"version": 2, "is_active": False}]}
    with env["admin"]() as db:
        assert release.read_version(db, tenant, 1) == release.read_version(db, tenant, 2) == payload


def test_stage_denies_wrong_tenant_viewer_and_runtime_database_role(environment):
    env = environment
    owner, other, viewer = identity(env), identity(env), identity(env, role="viewer")
    payload = forced("forecasting")
    for actor, tenant in ((other["user"], tenant_of(env, owner)), (viewer["user"], tenant_of(env, viewer))):
        with pytest.raises(HTTPException):
            lifecycle.stage(env["admin"], actor, tenant, payload)
    with pytest.raises(PermissionError):
        lifecycle.stage(env["api"], owner["user"], tenant_of(env, owner), payload)
    invalid = deepcopy(payload)
    invalid["feature_version"] = "stale"
    with pytest.raises(ValueError):
        staged(env, owner, invalid)


def test_runtime_requires_approval_and_ownership(environment, tmp_path, learning_on):
    env = environment
    a, b = identity(env), identity(env)
    ds_a, ds_b = dataset(env, a, tmp_path), dataset(env, b, tmp_path)
    tenant, version = staged(env, a, forced("correlation_analysis"))
    assert routing.read_prediction(a["user"], ds_a, "forecast sales") is None
    with env["admin"]() as db, db.begin():
        db.execute(learner_weights.update().where(learner_weights.c.tenant_id == tenant).values(is_active=True))
    assert routing.read_prediction(a["user"], ds_a, "forecast sales") is None
    with env["admin"]() as db, db.begin():
        lifecycle.event(db, a["user"], tenant, "promote", version, 0, forced("correlation_analysis"))
    approved_fixture(env, b, forced("data_quality"))
    assert routing.read_prediction(a["user"], ds_a, "forecast sales")[0].intent == "correlation_analysis"
    assert routing.read_prediction(b["user"], ds_b, "forecast sales")[0].intent == "data_quality"
    assert routing.read_prediction(b["user"], ds_a, "forecast sales") is None
    assert routing.read_prediction(a["user"], ds_a, "forecast sales", 99) is None
    with env["admin"]() as db, db.begin():
        db.execute(tenant_memberships.update().where(tenant_memberships.c.user_id == a["user"]).values(active=False))
    assert routing.read_prediction(a["user"], ds_a, "forecast sales") is None


@pytest.mark.parametrize("damage", ["digest", "incompatible", "low_margin", "code_changed", "database"])
def test_runtime_corruption_and_outage_fall_back(environment, tmp_path, learning_on, monkeypatch, damage):
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    payload = AveragedPerceptron().to_payload(feature_version()) if damage == "low_margin" else forced("data_quality")
    tenant, _ = approved_fixture(env, a, payload)
    if damage in {"digest", "incompatible"}:
        altered = forced("forecasting")
        if damage == "incompatible":
            altered["feature_version"] = "wrong"
        with env["admin"]() as db, db.begin():
            db.execute(learner_weights.update().where(learner_weights.c.tenant_id == tenant).values(weights=altered))
    elif damage == "code_changed":
        monkeypatch.setattr(release, "runtime_digest", lambda: "changed")
    elif damage == "database":
        def broken(*args, **kwargs):
            raise RuntimeError("private database error")
        monkeypatch.setattr(routing, "create_engine", broken)
    assert routing.read_prediction(a["user"], ds, "forecast sales") is None


def test_intent_api_flag_off_parity_active_route_and_exception_fallback(environment, tmp_path, monkeypatch):
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    approved_fixture(env, a, forced("correlation_analysis"))
    monkeypatch.setitem(env["client"].app.dependency_overrides, get_intent_classification_service,
                        lambda: IntentClassificationService(llm=None))
    def call():
        response = env["client"].post("/api/v1/intent/classify", headers=a["headers"],
            json={"query": "forecast sales", "dataset_id": ds})
        assert response.status_code == 200, response.text
        return response.json()
    monkeypatch.setattr(get_settings(), "learning_enabled", False)
    baseline = call()
    assert baseline["intent"] == "forecasting"
    monkeypatch.setattr(get_settings(), "learning_enabled", True)
    learned = call()
    assert learned["intent"] == "correlation_analysis" and set(learned) == set(baseline)
    assert learned["required_agents"] == IntentClassificationService().registry.get("correlation_analysis").required_agents
    def broken(*args, **kwargs):
        raise RuntimeError("private learner error")
    monkeypatch.setattr(routing, "read_prediction", broken)
    assert call() == baseline


def test_approved_router_never_changes_chat_arithmetic_or_trains(environment, tmp_path, monkeypatch):
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    tenant, version = approved_fixture(env, a, forced("forecasting"))
    def forbidden(*args, **kwargs):
        pytest.fail("Request must not train")
    monkeypatch.setattr(AveragedPerceptron, "update", forbidden)
    outputs = []
    for flag in (False, True):
        monkeypatch.setattr(get_settings(), "learning_enabled", flag)
        response = env["client"].post("/api/v1/chat", headers=a["headers"], json={
            "message": "total amount by region", "dataset_id": ds, "workspace_id": str(a["workspace"])})
        assert response.status_code == 200, response.text
        outputs.append({key: response.json()[key] for key in ("data", "plan", "kpis", "answer", "intent", "confidence")})
    assert outputs[0] == outputs[1]
    assert outputs[1]["data"] == [{"region": "a", "amount": 1180}]
    with env["admin"]() as db:
        assert release.read_version(db, tenant, version) == forced("forecasting")


def test_orchestrator_receives_scoped_router(environment, tmp_path, learning_on):
    from backend.app.services.orchestrator_service import OrchestratorService
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    approved_fixture(env, a, forced("data_quality"))
    service = OrchestratorService(intent_classifier=IntentClassificationService(), owner_id=str(a["user"]))
    assert asyncio.run(service._intent_classifier.classify("forecast sales", dataset_id=ds)).intent == "data_quality"


def test_promotion_gate_checks_effective_fallback_and_strict_improvement():
    report = synthetic_report(forced("data_quality"))
    assert lifecycle.promotion_gate(report)["passed"]
    assert not lifecycle.promotion_gate(report, report)["passed"]
    unknown = next(row for row in report["cases"] if row["id"] == "intent-unknown-2")
    unknown["baseline_intent"] = "rag_query"
    assert not lifecycle.promotion_gate(report)["passed"]  # Raw model unknown is an abstention.
    unknown["abstained"] = False  # Confident explicit unknown corrects the fallback miss.
    assert lifecycle.promotion_gate(report)["passed"]
    report = synthetic_report(forced("data_quality"), wrong=True)
    assert not lifecycle.promotion_gate(report)["passed"]
    report["cases"].pop()
    with pytest.raises(ValueError):
        lifecycle.promotion_gate(report)


def test_confident_unknown_is_a_live_decision_but_shadow_default_is_preserved(environment, tmp_path, learning_on):
    from backend.app.learning.features import extract
    model = AveragedPerceptron.from_payload(forced("unknown"), feature_version())
    vector = extract("an out of domain question")
    assert model.predict(vector).abstained
    assert not model.predict(vector, allow_unknown=True).abstained
    assert AveragedPerceptron().predict(vector, allow_unknown=True).abstained
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    approved_fixture(env, a, forced("unknown"))
    result = routing.read_prediction(a["user"], ds, "Tell me a bedtime story about a dragon")
    assert result[0].intent == "unknown" and not result[0].abstained


def test_promotion_requires_shadow_then_recomputes_real_golden(environment, tmp_path, frozen, learning_on):
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    tenant, version = staged(env, a, bootstrap_prior().to_payload(feature_version()))
    with pytest.raises(ValueError, match="shadow"):
        promote(env, a, tenant, version)
    assert shadow.record_shadow(actor_id=str(a["user"]), dataset_id=ds, question="forecast sales")
    root, _, manifest, fingerprint = frozen
    result = asyncio.run(lifecycle.promote(env["admin"], a["user"], tenant, version, 0, root, manifest, fingerprint))
    assert not result["promoted"] and result["gate"]["candidate_correct"] == 33
    assert lifecycle.status(env["admin"], a["user"], tenant)["active_version"] == 0
    with env["admin"]() as db:
        assert db.execute(select(router_releases.c.action).where(router_releases.c.tenant_id == tenant)).scalars().all() == ["stage"]


def test_atomic_promotion_and_one_command_rollback(environment, tmp_path, learning_on, monkeypatch):
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    tenant, version = staged(env, a, forced("data_quality"))
    assert shadow.record_shadow(actor_id=str(a["user"]), dataset_id=ds, question="forecast sales")
    install_evaluator(monkeypatch)
    assert promote(env, a, tenant, version)["promoted"]
    assert routing.read_prediction(a["user"], ds, "forecast sales")[0].intent == "data_quality"
    lifecycle.rollback(env["admin"], a["user"], tenant, 0, version)
    assert routing.read_prediction(a["user"], ds, "forecast sales") is None
    lifecycle.rollback(env["admin"], a["user"], tenant, version, 0)
    assert lifecycle.status(env["admin"], a["user"], tenant)["active_version"] == version
    _, unapproved = staged(env, a, forced("forecasting"))
    with pytest.raises(ValueError, match="never"):
        lifecycle.rollback(env["admin"], a["user"], tenant, unapproved, version)
    with pytest.raises(ValueError, match="changed"):
        lifecycle.rollback(env["admin"], a["user"], tenant, 0, 99)
    with env["admin"]() as db:
        actions = db.execute(select(router_releases.c.action).where(router_releases.c.tenant_id == tenant).order_by(router_releases.c.id)).scalars().all()
        assert actions == ["stage", "promote", "disable", "rollback", "stage"]


@pytest.mark.parametrize("interference", ["state", "revocation", "audit_failure", "bad_score"])
def test_failed_promotion_never_partially_activates(environment, tmp_path, learning_on, monkeypatch, interference):
    env = environment
    a = identity(env)
    ds = dataset(env, a, tmp_path)
    tenant, version = staged(env, a, forced("data_quality"))
    assert shadow.record_shadow(actor_id=str(a["user"]), dataset_id=ds, question="forecast sales")
    def hook():
        if interference == "state":
            staged(env, a, forced("forecasting"))
        elif interference == "revocation":
            with env["admin"]() as db, db.begin():
                db.execute(tenant_memberships.update().where(tenant_memberships.c.user_id == a["user"]).values(active=False))
    install_evaluator(monkeypatch, hook, wrong=interference == "bad_score")
    if interference == "audit_failure":
        def broken(*args, **kwargs):
            raise RuntimeError("Audit persistence failed")
        monkeypatch.setattr(lifecycle, "event", broken)
    if interference == "bad_score":
        assert not promote(env, a, tenant, version)["promoted"]
    else:
        with pytest.raises((ValueError, HTTPException, RuntimeError)):
            promote(env, a, tenant, version)
    with env["admin"]() as db:
        assert release.active_version(db, tenant) == 0
        assert not db.scalar(select(router_releases.c.id).where(router_releases.c.tenant_id == tenant, router_releases.c.action == "promote"))


def test_release_rls_disallows_forgery_mutation_and_other_tenants(environment):
    env = environment
    a, b = identity(env), identity(env)
    tenant, _ = staged(env, a, forced("data_quality"))
    with env["admin"]() as db:
        row = dict(db.execute(select(router_releases).where(router_releases.c.tenant_id == tenant)).mappings().one())
    with env["api"]() as db, db.begin():
        for key, value in (("tenant_id", tenant), ("actor_id", a["user"])):
            db.execute(text("SELECT set_config(:key,:value,true)"), {"key": f"app.{key}", "value": str(value)})
        assert db.scalar(select(router_releases.c.id).where(router_releases.c.id == row["id"])) == row["id"]
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(router_releases.insert().values(**{key: value for key, value in row.items() if key != "id"}))
        assert db.execute(router_releases.update().where(router_releases.c.id == row["id"]).values(action="promote")).rowcount == 0
        assert db.execute(router_releases.delete().where(router_releases.c.id == row["id"])).rowcount == 0
        assert db.execute(learner_weights.update().where(learner_weights.c.tenant_id == tenant).values(is_active=True)).rowcount == 0
        db.execute(text("SELECT set_config('app.actor_id',:actor,true)"), {"actor": str(b["user"])})
        assert db.scalar(select(router_releases.c.id).where(router_releases.c.id == row["id"])) is None


def test_operator_cli_status_and_disable(environment):
    env = environment
    a = identity(env)
    tenant, version = approved_fixture(env, a, forced("data_quality"))
    script = str(Path(__file__).resolve().parents[2] / "scripts/perceptron_router.py")
    common = ["--actor-id", str(a["user"]), "--tenant-id", str(tenant)]
    result = subprocess.run([sys.executable, script, "status", *common], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["active_version"] == version
    result = subprocess.run([sys.executable, script, "rollback", *common, "--version", "0", "--expected-version", str(version)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["version"] == 0
