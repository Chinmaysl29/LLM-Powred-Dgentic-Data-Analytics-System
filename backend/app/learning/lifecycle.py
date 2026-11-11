"""Privileged operator lifecycle. Golden reports are recomputed, never accepted as input."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from sqlalchemy import select, text, func
from sqlalchemy.orm import Session
from backend.app.core.workspace_authorization import authorize_tenant
from backend.app.learning.golden import evaluate, digest, encode
from backend.app.learning.golden_cases import question_contracts
from backend.app.learning.features import feature_version
from backend.app.learning.release import LEARNER, active_version, approved, read_version, runtime_digest, validated_payload
from backend.app.learning.release_table import router_releases
from backend.app.learning.shadow_table import shadow_predictions
from backend.app.learning.tables import learner_weights

SessionFactory = Callable[[], Session]


def operator(db: Session, actor_id: str | UUID, tenant_id: str | UUID) -> tuple[UUID, UUID]:
    # RLS-protected runtime accounts cannot use lifecycle functions even if the
    # supplied actor is an owner. DB operators must also name an authorized actor.
    if not db.scalar(text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user")):
        raise PermissionError("Router lifecycle requires an operator database role")
    tenant = authorize_tenant(db, actor_id, tenant_id, "manage")
    return UUID(str(actor_id)), tenant


def lock(db: Session, tenant: UUID) -> None:
    db.execute(text("SET LOCAL lock_timeout='2s'"))
    db.execute(text("SET LOCAL statement_timeout='5s'"))
    key = int.from_bytes(hashlib.sha256(f"{tenant}:{LEARNER}".encode()).digest()[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    # Also exclude direct concurrent updates of existing versions while switching.
    db.execute(select(learner_weights.c.id).where(learner_weights.c.tenant_id == tenant,
        learner_weights.c.learner == LEARNER).with_for_update()).all()


def state(db: Session, tenant: UUID) -> tuple[int, int]:
    return (active_version(db, tenant), db.scalar(select(func.max(router_releases.c.id)).where(
        router_releases.c.tenant_id == tenant)) or 0)


def event(db: Session, actor: UUID, tenant: UUID, action: str, version: int, previous: int,
          payload: dict | None = None, evidence: dict | None = None) -> None:
    db.execute(router_releases.insert().values(tenant_id=tenant, actor_id=actor, action=action,
        version=version, previous_version=previous, model_digest=digest(encode(payload)) if payload else None,
        runtime_digest=runtime_digest(), evidence=evidence or {}))


def stage(factory: SessionFactory, actor_id: str | UUID, tenant_id: str | UUID, payload: dict) -> dict[str, Any]:
    payload = validated_payload(payload)
    with factory() as db, db.begin():
        actor, tenant = operator(db, actor_id, tenant_id)
        lock(db, tenant)
        version = (db.scalar(select(func.max(learner_weights.c.version)).where(
            learner_weights.c.tenant_id == tenant, learner_weights.c.learner == LEARNER)) or 0) + 1
        db.execute(learner_weights.insert().values(id=uuid4(), tenant_id=tenant, learner=LEARNER,
            version=version, weights=payload, is_active=False))
        event(db, actor, tenant, "stage", version, active_version(db, tenant), payload)
    return {"version": version, "model_digest": digest(encode(payload)), "active": False}


def has_shadow(db: Session, tenant: UUID, version: int, payload: dict) -> bool:
    # Match the Phase 2 observation digest exactly; raw JSON formatting differs
    # from the offline report's canonical indented representation.
    shadow_digest = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return db.scalar(select(shadow_predictions.c.id).where(
        shadow_predictions.c.tenant_id == tenant, shadow_predictions.c.model_version == version,
        shadow_predictions.c.model_source == "tenant_candidate", shadow_predictions.c.model_digest == shadow_digest,
        shadow_predictions.c.feature_version == feature_version()).limit(1)) is not None


def effective(report: dict) -> tuple[dict[str, bool], dict[str, bool], bool]:
    contracts = question_contracts()
    cases = report["cases"]
    if [row["id"] for row in cases] != [row["id"] for row in contracts]:
        raise ValueError("Evaluation coverage mismatch")
    result, baseline = {}, {}
    answers_pass = True
    for row, contract in zip(cases, contracts):
        if contract["kind"] == "intent":
            if row["expected_intent"] != contract["expected_intent"]:
                raise ValueError("Evaluation label mismatch")
            routed = row["baseline_intent"] if row["abstained"] else row["shadow_intent"]
            result[row["id"]] = routed == contract["expected_intent"]
            baseline[row["id"]] = row["baseline_intent"] == contract["expected_intent"]
        else:
            answers_pass = answers_pass and row["passed"] is True
    return result, baseline, answers_pass


def promotion_gate(candidate_report: dict, live_report: dict | None = None) -> dict[str, Any]:
    if candidate_report.get("unknown_policy") != "explicit_if_confident" or (
            live_report is not None and live_report.get("unknown_policy") != "explicit_if_confident"):
        raise ValueError("Evaluation runtime policy mismatch")
    candidate, baseline, answers = effective(candidate_report)
    live = baseline if live_report is None else effective(live_report)[0]
    regressions = [key for key in candidate if live[key] and not candidate[key]]
    candidate_correct, live_correct = sum(candidate.values()), sum(live.values())
    passed = (candidate_report["quality_gate_passed"] is True and answers and all(candidate.values())
              and not regressions and candidate_correct > live_correct)
    return {"passed": passed, "candidate_correct": candidate_correct, "live_correct": live_correct,
            "intent_count": len(candidate), "answers_passed": answers, "regressions": regressions,
            "beats_live": candidate_correct > live_correct}


async def promote(factory: SessionFactory, actor_id: str | UUID, tenant_id: str | UUID,
                  version: int, expected_version: int, root: Path, manifest: Path,
                  manifest_digest: str) -> dict[str, Any]:
    if type(version) is not int or version <= 0:
        raise ValueError("Invalid version")
    fingerprint = runtime_digest()
    with factory() as db, db.begin():
        actor, tenant = operator(db, actor_id, tenant_id)
        before = state(db, tenant)
        if before[0] != expected_version or version == expected_version:
            raise ValueError("Active version changed or already active")
        payload = read_version(db, tenant, version)
        if not has_shadow(db, tenant, version, payload):
            raise ValueError("Candidate has no matching tenant shadow observation")
        current = read_version(db, tenant, before[0]) if before[0] else None
        if current is not None and not approved(db, tenant, before[0], current):
            raise ValueError("Current version has no compatible approval; disable it first")
    # File loading and evaluation occur outside any database lock/transaction.
    report = await evaluate(root, manifest, manifest_digest, payload, allow_unknown=True)
    live_report = await evaluate(root, manifest, manifest_digest, current, allow_unknown=True) if current else None
    gate = promotion_gate(report, live_report)
    if not gate["passed"]:
        return {"promoted": False, "version": version, "gate": gate}
    if report["candidate_digest"] != digest(encode(payload)) or runtime_digest() != fingerprint:
        raise ValueError("Evaluation provenance changed")
    with factory() as db, db.begin():
        actor, tenant = operator(db, actor_id, tenant_id)  # Catch revocation during evaluation.
        lock(db, tenant)
        if state(db, tenant) != before or read_version(db, tenant, version) != payload:
            raise ValueError("Router state changed during evaluation; retry")
        if current is not None and read_version(db, tenant, before[0]) != current:
            raise ValueError("Live weights changed during evaluation")
        if not has_shadow(db, tenant, version, payload) or runtime_digest() != fingerprint:
            raise ValueError("Shadow evidence or runtime changed")
        db.execute(learner_weights.update().where(learner_weights.c.tenant_id == tenant,
            learner_weights.c.learner == LEARNER).values(is_active=False))
        db.execute(learner_weights.update().where(learner_weights.c.tenant_id == tenant,
            learner_weights.c.learner == LEARNER, learner_weights.c.version == version).values(is_active=True))
        evidence = {key: report[key] for key in ("manifest_digest", "candidate_digest", "feature_version", "code_digest", "source_hashes", "case_count", "unknown_policy")}
        evidence.update(gate=gate, live_model_digest=digest(encode(current)) if current else None)
        event(db, actor, tenant, "promote", version, before[0], payload, evidence)
    return {"promoted": True, "version": version, "gate": gate}


def rollback(factory: SessionFactory, actor_id: str | UUID, tenant_id: str | UUID,
             version: int, expected_version: int) -> dict[str, Any]:
    if type(version) is not int or version < 0:
        raise ValueError("Invalid rollback version")
    with factory() as db, db.begin():
        actor, tenant = operator(db, actor_id, tenant_id)
        lock(db, tenant)
        previous = active_version(db, tenant)
        if previous != expected_version:
            raise ValueError("Active version changed")
        payload = read_version(db, tenant, version) if version else None
        if payload is not None and not approved(db, tenant, version, payload):
            raise ValueError("Rollback target was never compatibly promoted")
        db.execute(learner_weights.update().where(learner_weights.c.tenant_id == tenant,
            learner_weights.c.learner == LEARNER).values(is_active=False))
        if version:
            db.execute(learner_weights.update().where(learner_weights.c.tenant_id == tenant,
                learner_weights.c.learner == LEARNER, learner_weights.c.version == version).values(is_active=True))
        event(db, actor, tenant, "rollback" if version else "disable", version, previous, payload)
    return {"version": version, "previous_version": previous, "rolled_back": True}


def status(factory: SessionFactory, actor_id: str | UUID, tenant_id: str | UUID) -> dict[str, Any]:
    with factory() as db, db.begin():
        _, tenant = operator(db, actor_id, tenant_id)
        versions = db.execute(select(learner_weights.c.version, learner_weights.c.is_active).where(
            learner_weights.c.tenant_id == tenant, learner_weights.c.learner == LEARNER
        ).order_by(learner_weights.c.version)).mappings().all()
        return {"active_version": active_version(db, tenant), "versions": [dict(row) for row in versions]}
