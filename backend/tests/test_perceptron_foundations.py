"""Phase 1 evidence, privacy, isolation and fail-open regression tests."""
import asyncio
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from backend.app.core.config import Settings, get_settings
from backend.app.models import DatasetVersion
from backend.app.learning import evidence
from backend.app.learning.tables import feedback_events, learner_weights, mistakes
from backend.tests.test_verified_learning_integration import environment, identity, dataset


@pytest.fixture
def learning_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "learning_enabled", True)


def test_flag_defaults_off_and_reads_environment(monkeypatch):
    monkeypatch.delenv("LEARNING_ENABLED", raising=False)
    assert Settings(_env_file=None).learning_enabled is False
    monkeypatch.setenv("LEARNING_ENABLED", "true")
    assert Settings(_env_file=None).learning_enabled is True


def test_disabled_capture_never_opens_database(monkeypatch):
    monkeypatch.setattr(get_settings(), "learning_enabled", False)
    def forbidden(*args, **kwargs):
        raise AssertionError("Disabled evidence must not connect")
    monkeypatch.setattr(evidence, "create_engine", forbidden)
    assert evidence.record_failure(actor_id=str(uuid4()), dataset_id=str(uuid4()),
        question="sum amount", error_type="execution_error") is False


@pytest.mark.parametrize("enabled", [False, True])
def test_observer_preserves_results_and_original_exception(monkeypatch, enabled):
    monkeypatch.setattr(get_settings(), "learning_enabled", enabled)
    def unavailable(**kwargs):
        raise RuntimeError("Evidence unavailable")
    monkeypatch.setattr(evidence, "record_failure", unavailable)
    expected = {"status": "complete", "answer": "Sum amount: 12", "data": [{"amount": 12}],
                "plan": {"operation": "sum"}, "kpis": {"total": 12}}
    async def successful():
        result = deepcopy(expected)
        async with evidence.observe_chat(actor_id="actor", dataset_id="dataset", question="sum amount", version_number=1) as observed:
            observed.result = result
        return result
    assert asyncio.run(successful()) == expected
    error = ValueError("Original execution error")
    async def failing():
        async with evidence.observe_chat(actor_id="actor", dataset_id="dataset", question="sum amount", version_number=1):
            raise error
    with pytest.raises(ValueError) as caught:
        asyncio.run(failing())
    assert caught.value is error


def test_hard_failures_do_not_turn_ambiguity_or_zero_into_labels():
    assert evidence.result_failure({"status": "complete", "plan": {"operation": "sum"}, "data": [{"amount": 0}]}) is None
    assert evidence.result_failure({"status": "clarification_required", "plan": {"validation_errors": ["Choose a metric"]}, "data": []}) is None
    assert evidence.result_failure({"status": "complete", "plan": {"operation": "sum"}, "data": []}) == "empty_result"
    assert evidence.result_failure({"status": "clarification_required", "plan": {"validation_errors": ["The metric contains non-finite values."]}}) == "validator_rejection"


def test_persistence_privacy_idempotency_and_no_training(environment, tmp_path, learning_on):
    env = environment
    account = identity(env)
    ds = dataset(env, account, tmp_path)
    with env["admin"]() as db, db.begin():
        db.execute(update(DatasetVersion).where(DatasetVersion.dataset_id == ds).values(
            metadata_snapshot={"columns": ["region", "amount"], "dtypes": {"region": "object", "amount": "int64"},
                               "private_rows": ["DO_NOT_STORE"]}))
        before_weights = list(db.execute(select(learner_weights)))
        before_mistakes = list(db.execute(select(mistakes)))
    event_id = uuid4()
    args = dict(actor_id=str(account["user"]), dataset_id=ds,
                question="password=DO_NOT_STORE; sum amount", predicted="sum", error_type="execution_error", event_id=event_id)
    assert evidence.record_failure(**args)
    assert evidence.record_failure(**args)
    with env["admin"]() as db:
        rows = db.execute(select(feedback_events).where(feedback_events.c.id == event_id)).mappings().all()
        assert len(rows) == 1
        row = rows[0]
        assert row["truth"] is None and row["question"] is None
        assert row["predicted"] == "sum" and row["signal_type"] == "hard_failure"
        assert len(row["dataset_schema_hash"]) == 64 and len(row["question_hash"]) == 64
        assert "DO_NOT_STORE" not in str(dict(row))
        assert list(db.execute(select(learner_weights))) == before_weights
        assert list(db.execute(select(mistakes))) == before_mistakes


def test_unauthorized_and_revoked_actor_cannot_record(environment, tmp_path, learning_on):
    env = environment
    account, outsider = identity(env), identity(env)
    ds = dataset(env, account, tmp_path)
    event_id = uuid4()
    args = dict(actor_id=str(outsider["user"]), dataset_id=ds, question="sum amount",
                error_type="execution_error", event_id=event_id)
    assert evidence.record_failure(**args) is False
    from backend.app.core.workspace_authorization import tenant_memberships
    with env["admin"]() as db, db.begin():
        db.execute(tenant_memberships.update().where(tenant_memberships.c.user_id == account["user"]).values(active=False))
    assert evidence.record_failure(**{**args, "actor_id": str(account["user"])}) is False
    with env["admin"]() as db:
        assert db.scalar(select(feedback_events.c.id).where(feedback_events.c.id == event_id)) is None


def test_database_failure_is_fail_open(monkeypatch, learning_on):
    def unavailable(*args, **kwargs):
        raise RuntimeError("Unavailable, with private driver details")
    monkeypatch.setattr(evidence, "create_engine", unavailable)
    assert evidence.record_failure(actor_id=str(uuid4()), dataset_id=str(uuid4()),
        question="sum amount", error_type="execution_error") is False


def test_rls_cross_tenant_and_forged_scope_denied(environment, tmp_path, learning_on):
    env = environment
    a, b = identity(env), identity(env)
    ds = dataset(env, a, tmp_path)
    event_id = uuid4()
    assert evidence.record_failure(actor_id=str(a["user"]), dataset_id=ds, question="sum amount",
        error_type="execution_error", event_id=event_id)
    with env["admin"]() as db:
        stored = dict(db.execute(select(feedback_events).where(feedback_events.c.id == event_id)).mappings().one())
    with env["api"]() as db, db.begin():
        assert db.scalar(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")) is False
        for key, value in (("actor_id", a["user"]), ("tenant_id", stored["tenant_id"]), ("workspace_id", a["workspace"])):
            db.execute(text("SELECT set_config(:key,:value,true)"), {"key": f"app.{key}", "value": str(value)})
        assert db.scalar(select(feedback_events.c.id).where(feedback_events.c.id == event_id)) == event_id
        db.execute(text("SELECT set_config('app.actor_id',:actor,true)"), {"actor": str(b["user"])})
        assert db.scalar(select(feedback_events.c.id).where(feedback_events.c.id == event_id)) is None
        forged = {**stored, "id": uuid4(), "actor_id": b["user"]}
        with pytest.raises(DBAPIError), db.begin_nested():
            db.execute(feedback_events.insert().values(**forged))


def test_chat_hook_captures_failure_without_changing_exception(environment, tmp_path, learning_on, monkeypatch):
    from backend.app.api.v1.routes.chat import chat, ChatRequest
    from backend.app.services.natural_language_analytics import NaturalLanguageAnalyticsService
    from types import SimpleNamespace
    env = environment
    account = identity(env)
    ds = dataset(env, account, tmp_path)
    error = ValueError("PRIVATE_DATASET_VALUE")
    async def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(NaturalLanguageAnalyticsService, "analyze", fail)
    with pytest.raises(ValueError) as caught:
        asyncio.run(chat(ChatRequest(message="sum amount", dataset_id=ds), None,
                         intent_service=None, db=None, storage=None, current_user=SimpleNamespace(id=account["user"])))
    assert caught.value is error
    with env["admin"]() as db:
        rows = db.execute(select(feedback_events).where(feedback_events.c.actor_id == account["user"])).mappings().all()
        assert len(rows) == 1 and rows[0]["truth"] is None
        assert "PRIVATE_DATASET_VALUE" not in str(rows)


def test_durable_failure_hook_and_delivery_dedup(environment, tmp_path, learning_on, monkeypatch):
    from backend.app.services import analysis_run_service
    from backend.tests.test_verified_learning_integration import run
    from backend.jobs.persistence import PersistentJobStore
    env = environment
    account = identity(env)
    ds = dataset(env, account, tmp_path)
    created = run(env, account, ds)
    store = PersistentJobStore(env["worker"])
    job = {"payload": {"run_id": created["id"]}, "owner_id": str(account["user"])}
    evidence.record_job_failure(store, job, 1, exception=True)
    evidence.record_job_failure(store, job, 1, exception=True)
    with env["admin"]() as db:
        rows = db.execute(select(feedback_events).where(feedback_events.c.actor_id == account["user"])).mappings().all()
        assert len(rows) == 1 and rows[0]["features"]["source"] == "analysis_job"
    # The actual worker exception path must invoke the hook and preserve the error.
    seen = []
    original = ValueError("worker failure")
    def failed_stage(*args):
        raise original
    def denied_fence(*args):
        from fastapi import HTTPException
        raise HTTPException(404)
    monkeypatch.setattr(analysis_run_service, "_execute_stage", failed_stage)
    monkeypatch.setattr(analysis_run_service, "fence", denied_fence)
    monkeypatch.setattr(analysis_run_service, "record_job_failure", lambda *args, **kwargs: seen.append(kwargs))
    with pytest.raises(ValueError) as caught:
        asyncio.run(analysis_run_service.execute_analysis_job(store, job))
    assert caught.value is original and seen == [{"exception": True}]


def test_chat_response_identical_with_flag_off_and_on(environment, tmp_path, monkeypatch):
    from importlib import import_module
    from types import SimpleNamespace
    chat_module = import_module("backend.app.api.v1.routes.chat")
    env = environment
    account = identity(env)
    ds = dataset(env, account, tmp_path)
    output = {"status": "complete", "answer": "Sum amount: 12", "data": [{"amount": 12}],
              "plan": {"operation": "sum"}, "kpis": {"total": 12}}
    async def analyze(*args, **kwargs):
        return deepcopy(output)
    monkeypatch.setattr(chat_module.NaturalLanguageAnalyticsService, "analyze", analyze)
    monkeypatch.setattr(chat_module, "perf_counter", lambda: 1.0)
    responses = []
    for flag in (False, True):
        monkeypatch.setattr(get_settings(), "learning_enabled", flag)
        response = asyncio.run(chat_module.chat(chat_module.ChatRequest(message="sum amount", dataset_id=ds),
            None, intent_service=None, db=None, storage=None, current_user=SimpleNamespace(id=account["user"])))
        responses.append(response.model_dump_json())
    assert responses[0] == responses[1]
    with env["admin"]() as db:
        assert db.scalar(select(feedback_events.c.id).where(feedback_events.c.actor_id == account["user"])) is None
