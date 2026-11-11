"""Shared release validation. No training, activation, or business arithmetic."""
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, func, cast, Text
from sqlalchemy.orm import Session
from backend.app.learning.golden import digest, encode
from backend.app.learning.features import feature_version
from backend.app.learning.perceptron import AveragedPerceptron
from backend.app.learning.tables import learner_weights
from backend.app.learning.release_table import router_releases

LEARNER = "intent_router"


def runtime_digest() -> str:
    directory = Path(__file__).parent
    paths = [directory / name for name in (
        "release.py", "routing.py", "lifecycle.py", "features.py", "perceptron.py",
        "golden.py", "golden_cases.py", "golden_reference.py")]
    paths.append(directory.parent / "services/intent_classification_service.py")
    return digest(b"".join(path.read_bytes() for path in paths))


def validated_payload(payload: dict) -> dict:
    return AveragedPerceptron.from_payload(payload, feature_version()).to_payload(feature_version())


def read_version(db: Session, tenant: UUID, version: int) -> dict:
    query = (learner_weights.c.tenant_id == tenant) & (learner_weights.c.learner == LEARNER) & (learner_weights.c.version == version)
    size = db.scalar(select(func.octet_length(cast(learner_weights.c.weights, Text))).where(query))
    if size is None or size > 1_000_000:
        raise ValueError("Missing or oversized router version")
    return validated_payload(db.scalar(select(learner_weights.c.weights).where(query)))


def active_version(db: Session, tenant: UUID) -> int:
    return db.scalar(select(learner_weights.c.version).where(
        learner_weights.c.tenant_id == tenant, learner_weights.c.learner == LEARNER,
        learner_weights.c.is_active.is_(True))) or 0


def approved(db: Session, tenant: UUID, version: int, payload: dict) -> bool:
    return db.scalar(select(router_releases.c.id).where(
        router_releases.c.tenant_id == tenant, router_releases.c.version == version,
        router_releases.c.action == "promote", router_releases.c.model_digest == digest(encode(payload)),
        router_releases.c.runtime_digest == runtime_digest()).limit(1)) is not None
