"""Enterprise Data Lake Lifecycle Management & Cleanup Services (Phase 18.6.1).

Orchestrates automated domain provisioning, dataset lifecycle transitions,
archive management, disaster recovery restoration, and storage garbage collection.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.core.config import Settings, get_settings
from backend.app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


@dataclass
class LifecycleEvent:
    event_id: str
    dataset_id: str
    from_state: str
    to_state: str
    timestamp: str
    actor: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CleanupReport:
    timestamp: str
    files_removed: int
    bytes_freed: int
    domains_scanned: list[str]
    archives_purged: int
    orphans_removed: int
    temp_files_removed: int
    duration_ms: float
    status: str = "completed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DataLakeLifecycleService:
    """Manages dataset lifecycle states, retention enforcement, archiving, and restoration."""

    VALID_STATES = {
        "uploaded",
        "canonicalized",
        "profiled",
        "quality_assessed",
        "active",
        "archived",
        "purged",
    }

    def __init__(self, storage_service: StorageService | None = None) -> None:
        if storage_service is None:
            settings = get_settings()
            self.storage_service = StorageService(settings=settings)
        else:
            self.storage_service = storage_service

        self.storage_dir = self.storage_service.upload_dir
        self.lifecycle_log_dir = self.storage_service.lineage_dir
        self.lifecycle_log_path = self.lifecycle_log_dir / "lifecycle_events.json"

        # Ensure all data lake storage directories exist automatically
        self.storage_service.ensure_lake_directories()

    def transition_state(
        self,
        dataset_id: str,
        from_state: str,
        to_state: str,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> LifecycleEvent:
        """Record and validate a dataset lifecycle state transition."""
        if to_state not in self.VALID_STATES:
            raise ValueError(f"Invalid target lifecycle state '{to_state}'. Valid states: {self.VALID_STATES}")

        event = LifecycleEvent(
            event_id=f"evt_{int(time.time() * 1000)}",
            dataset_id=dataset_id,
            from_state=from_state,
            to_state=to_state,
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=actor,
            details=details or {},
        )

        self._record_event(event)
        logger.info(
            "Dataset lifecycle transition dataset_id=%s from=%s to=%s actor=%s",
            dataset_id,
            from_state,
            to_state,
            actor,
        )
        return event

    def archive_dataset(self, dataset_id: str, reason: str = "user_deletion", actor: str = "system") -> bool:
        """Soft-delete a dataset by archiving all domain artifacts into storage/archives/."""
        success = self.storage_service.archive_dataset(dataset_id, reason=reason)
        if success:
            self.transition_state(dataset_id, from_state="active", to_state="archived", actor=actor, details={"reason": reason})
        return success

    def restore_dataset(self, dataset_id: str, actor: str = "system") -> bool:
        """Restore an archived dataset back into active data lake domains."""
        success = self.storage_service.restore_from_archive(dataset_id)
        if success:
            self.transition_state(dataset_id, from_state="archived", to_state="active", actor=actor)
        return success

    def purge_dataset(self, dataset_id: str, actor: str = "system") -> bool:
        """Permanently purge a dataset and its archive from disk."""
        archive_dir = self.storage_service.archives_dir / dataset_id
        deleted = False
        if archive_dir.exists():
            shutil.rmtree(archive_dir)
            deleted = True

        self.storage_service.delete_dataset(dataset_id)
        self.transition_state(dataset_id, from_state="archived", to_state="purged", actor=actor)
        logger.info("Permanently purged dataset artifacts dataset_id=%s", dataset_id)
        return deleted

    def _record_event(self, event: LifecycleEvent) -> None:
        """Append lifecycle transition event to persistent audit trail."""
        events: list[dict[str, Any]] = []
        if self.lifecycle_log_path.exists():
            try:
                events = json.loads(self.lifecycle_log_path.read_text(encoding="utf-8"))
            except Exception:
                events = []
        events.append(asdict(event))
        # Keep latest 5000 lifecycle events
        events = events[-5000:]
        self.lifecycle_log_path.write_text(json.dumps(events, indent=2), encoding="utf-8")


class DataLakeCleanupService:
    """Enterprise storage garbage collector and housekeeping service."""

    def __init__(self, storage_service: StorageService | None = None) -> None:
        if storage_service is None:
            settings = get_settings()
            self.storage_service = StorageService(settings=settings)
        else:
            self.storage_service = storage_service

    def cleanup_temp_files(self, max_age_seconds: int = 86400) -> tuple[int, int]:
        """Remove leftover temporary or partial upload files older than threshold."""
        now = time.time()
        files_removed = 0
        bytes_freed = 0

        # Scan upload directory for temp patterns (*.tmp, *.part, scratch/)
        patterns = ["*.tmp", "*.part", "*.crdownload"]
        for pattern in patterns:
            for p in self.storage_service.upload_dir.rglob(pattern):
                if p.is_file():
                    try:
                        mtime = p.stat().st_mtime
                        if now - mtime > max_age_seconds:
                            size = p.stat().st_size
                            p.unlink(missing_ok=True)
                            files_removed += 1
                            bytes_freed += size
                    except Exception as e:
                        logger.warning("Failed to remove temp file %s: %s", p, e)

        return files_removed, bytes_freed

    def cleanup_expired_archives(self, retention_days: int = 90) -> tuple[int, int]:
        """Purge archives that exceed enterprise retention limits."""
        now = time.time()
        max_age_sec = retention_days * 86400
        archives_purged = 0
        bytes_freed = 0

        if not self.storage_service.archives_dir.exists():
            return 0, 0

        for archive_folder in self.storage_service.archives_dir.iterdir():
            if not archive_folder.is_dir():
                continue
            manifest_p = archive_folder / "manifest.json"
            purge_needed = False
            if manifest_p.exists():
                try:
                    data = json.loads(manifest_p.read_text(encoding="utf-8"))
                    archived_at_str = data.get("archived_at")
                    if archived_at_str:
                        archived_dt = pd.to_datetime(archived_at_str).timestamp()
                        if now - archived_dt > max_age_sec:
                            purge_needed = True
                except Exception:
                    pass
            else:
                # No manifest; check directory mtime
                if now - archive_folder.stat().st_mtime > max_age_sec:
                    purge_needed = True

            if purge_needed:
                folder_bytes = sum(f.stat().st_size for f in archive_folder.rglob("*") if f.is_file())
                shutil.rmtree(archive_folder)
                archives_purged += 1
                bytes_freed += folder_bytes
                logger.info("Purged expired archive %s (freed %d bytes)", archive_folder.name, folder_bytes)

        return archives_purged, bytes_freed

    def cleanup_empty_directories(self) -> int:
        """Remove empty subdirectories in archives or datasets (preserves core lake domains)."""
        removed = 0
        preserve = {
            self.storage_service.raw_dir,
            self.storage_service.raw_csv_dir,
            self.storage_service.raw_excel_dir,
            self.storage_service.raw_json_dir,
            self.storage_service.raw_pdf_dir,
            self.storage_service.raw_parquet_dir,
            self.storage_service.canonical_dir,
            self.storage_service.processed_dir,
            self.storage_service.profiles_dir,
            self.storage_service.quality_dir,
            self.storage_service.embeddings_dir,
            self.storage_service.reports_dir,
            self.storage_service.forecasts_dir,
            self.storage_service.lineage_dir,
            self.storage_service.archives_dir,
        }

        # Check datasets and archives subdirectories
        for root in [self.storage_service.archives_dir, self.storage_service.datasets_dir]:
            if not root.exists():
                continue
            for item in list(root.iterdir()):
                if item.is_dir() and item not in preserve:
                    try:
                        if not any(item.iterdir()):
                            item.rmdir()
                            removed += 1
                    except Exception:
                        pass
        return removed

    def run_comprehensive_cleanup(
        self,
        retention_days: int = 90,
        temp_max_age_seconds: int = 86400,
    ) -> CleanupReport:
        """Execute full housekeeping routine across all storage domains."""
        start = time.perf_counter()
        domains = [
            "raw", "canonical", "processed", "profiles",
            "quality", "embeddings", "reports", "forecasts", "lineage", "archives"
        ]

        temp_removed, temp_bytes = self.cleanup_temp_files(max_age_seconds=temp_max_age_seconds)
        arch_purged, arch_bytes = self.cleanup_expired_archives(retention_days=retention_days)
        empty_dirs_removed = self.cleanup_empty_directories()

        total_files = temp_removed + arch_purged
        total_bytes = temp_bytes + arch_bytes
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        report = CleanupReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            files_removed=total_files,
            bytes_freed=total_bytes,
            domains_scanned=domains,
            archives_purged=arch_purged,
            orphans_removed=0,
            temp_files_removed=temp_removed,
            duration_ms=duration_ms,
        )

        # Store cleanup report in reports domain
        report_path = self.storage_service.reports_dir / "latest_cleanup_report.json"
        report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")

        logger.info(
            "Completed comprehensive data lake cleanup in %.2fms. Freed %d bytes across %d files.",
            duration_ms, total_bytes, total_files,
        )
        return report


__all__ = [
    "DataLakeLifecycleService",
    "DataLakeCleanupService",
    "LifecycleEvent",
    "CleanupReport",
]
