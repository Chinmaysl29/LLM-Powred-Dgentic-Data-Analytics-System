"""Exercise the previously unresolved runtime names using synthetic data only."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from typing import get_type_hints

from backend.app.repositories.audit_repository import AuditRepository
from backend.app.services.data_lake_lifecycle import DataLakeCleanupService
from backend.connectors.scheduler import ConnectorScheduler
from backend.operations.continuous_improvement_orchestrator import ContinuousImprovementOrchestrator
from backend.operations.cost_optimizer import cost_optimization_engine


def test_repository_and_scheduler_annotations_resolve():
    assert "audit_id" in get_type_hints(AuditRepository.get)
    assert "sync_kwargs" in get_type_hints(ConnectorScheduler.execute_job)


def test_orchestrator_uses_existing_cost_engine():
    orchestrator = ContinuousImprovementOrchestrator()
    assert orchestrator.cost_optimizer is cost_optimization_engine
    assert 0 <= orchestrator.calculate_platform_health() <= 100


def test_archive_retention_removes_only_expired_synthetic_archives(tmp_path):
    now = datetime.now(timezone.utc)
    manifests = {
        "expired": (now - timedelta(days=100)).isoformat(),
        "recent": (now - timedelta(days=1)).isoformat(),
        "future": (now + timedelta(days=1)).isoformat(),
        "invalid": "not-a-date",
    }
    for name, archived_at in manifests.items():
        folder = tmp_path / name
        folder.mkdir()
        (folder / "manifest.json").write_text(json.dumps({"archived_at": archived_at}))
        (folder / "synthetic.txt").write_text("synthetic fixture")
    expired_size = sum(p.stat().st_size for p in (tmp_path / "expired").iterdir())
    service = DataLakeCleanupService(SimpleNamespace(archives_dir=tmp_path))
    assert service.cleanup_expired_archives(retention_days=90) == (1, expired_size)
    assert not (tmp_path / "expired").exists()
    for name in ("recent", "future", "invalid"):
        assert (tmp_path / name / "synthetic.txt").read_text() == "synthetic fixture"
