"""Redis-backed, dependency-light job queue with explicit lifecycle tracking."""

from __future__ import annotations

import inspect
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict

from pydantic import BaseModel, Field

from backend.app.core.exceptions import RedisConnectionError
from backend.app.database.redis import RedisCache
from backend.monitoring.prometheus_metrics import platform_metrics

logger = logging.getLogger(__name__)


class JobType(str, Enum):
    EDA = "eda"
    PROFILING = "profiling"
    FORECAST = "forecast"
    RECOMMENDATION = "recommendation"
    REPORT = "report"
    RAG = "rag"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundJob(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_type: JobType
    tenant_id: str
    actor_id: str | None = None
    workspace_id: str | None = None
    retry_safe: bool = False
    payload: Dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = JobStatus.QUEUED
    attempts: int = 0
    max_attempts: int = 3
    priority: int = Field(default=5, ge=0, le=9)
    progress: int = Field(default=0, ge=0, le=100)
    result: Any | None = None
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    duration_seconds: float | None = None


JobHandler = Callable[[Dict[str, Any]], Any | Awaitable[Any]]


class BackgroundJobManager:
    """Tracks jobs in Redis when available, with an in-memory test fallback.

    The manager accepts the application's ``RedisCache`` adapter; it never
    opens another Redis connection. A worker process should repeatedly call
    ``run_next`` for the queue it owns.
    """

    QUEUE_PREFIX = "ai-analyst:jobs:queue"
    JOB_PREFIX = "ai-analyst:jobs:item"
    JOB_TTL_SECONDS = 7 * 24 * 60 * 60

    def __init__(self, redis_cache: RedisCache | None = None, authorizer=None, session_factory=None) -> None:
        self._redis = redis_cache
        self._authorizer = authorizer
        self._handlers: dict[JobType, JobHandler] = {}
        self._memory_jobs: dict[str, BackgroundJob] = {}
        self._memory_queue: list[str] = []
        from backend.jobs.persistence import PersistentJobStore
        self.durable = PersistentJobStore(session_factory) if session_factory else None
        self._durable_handlers = {}

    def register_durable(self, kind, handler):
        self._durable_handlers[kind] = handler

    async def run_next_durable(self, worker_id):
        """Execute one SQL-claimed job; stale workers cannot publish completion."""
        from backend.jobs.persistence import LostLeaseError
        if self.durable is None:
            raise RuntimeError('Persistent session factory required')
        job = self.durable.claim(worker_id, list(self._durable_handlers))
        if job is None:
            return None
        token = job['lease_token']
        def progress(status):
            self.durable.advance(job['id'], token, status)
        async def heartbeat():
            while True:
                await asyncio.sleep(self.durable.lease_seconds / 3)
                self.durable.heartbeat(job['id'], token)
        renewal = asyncio.create_task(heartbeat())
        try:
            handler = self._durable_handlers[job['kind']]
            if asyncio.iscoroutinefunction(handler):
                import inspect as py_inspect
                sig = py_inspect.signature(handler)
                if len(sig.parameters) >= 2 and list(sig.parameters.keys())[0] in ('store', 'job_store'):
                    result = await handler(self.durable, job)
                else:
                    result = await handler(job, progress)
            else:
                result = await asyncio.to_thread(handler, job, progress)
            self.durable.advance(job['id'], token, 'READY', result=result)
        except LostLeaseError:
            pass  # Cancellation or replacement worker owns the authoritative state.
        except Exception as exc:
            from backend.app.core.exceptions import ChromaConnectionError
            from backend.app.services.document_indexing_service import DocumentSourceError
            retryable = isinstance(exc, (ChromaConnectionError, ConnectionError, TimeoutError))
            code = 'INDEX_DEPENDENCY_UNAVAILABLE' if retryable else 'JOB_EXECUTION_FAILED'
            if isinstance(exc, DocumentSourceError):
                code = exc.error_code
            elif isinstance(exc, ChromaConnectionError) and getattr(exc, 'error_code', None) == 'CHROMA_VERSION_INCOMPATIBLE':
                code = 'CHROMA_VERSION_INCOMPATIBLE'
            self.durable.fail(job['id'], token, code, retryable)
            logger.warning('Durable job failed job_id=%s code=%s', job['id'], code)
        finally:
            renewal.cancel()
            try:
                await renewal
            except (asyncio.CancelledError, LostLeaseError):
                pass
        return self.durable.get(job['id'])

    def register(self, job_type: JobType, handler: JobHandler) -> None:
        if not callable(handler):
            raise TypeError("Job handler must be callable")
        self._handlers[job_type] = handler

    async def create_job(
        self,
        job_type: JobType,
        tenant_id: str,
        payload: Dict[str, Any] | None = None,
        max_attempts: int = 3,
        priority: int = 5,
        actor_id: str | None = None,
        workspace_id: str | None = None,
        retry_safe: bool = False,
    ) -> BackgroundJob:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if not tenant_id:
            raise ValueError("tenant_id is required")
        job = BackgroundJob(job_type=job_type, tenant_id=tenant_id, payload=payload or {}, max_attempts=max_attempts, priority=priority, actor_id=actor_id, workspace_id=workspace_id, retry_safe=retry_safe)
        await self._authorize(job)
        await self._save(job)
        await self._enqueue_id(job.job_id)
        platform_metrics.record_job_event(job.job_type.value, job.status.value)
        return job

    async def get_job(self, job_id: str) -> BackgroundJob | None:
        if self._redis is not None:
            try:
                raw = await self._redis.get(self._job_key(job_id))
                return BackgroundJob.model_validate_json(raw) if raw else None
            except (RedisConnectionError, ValueError):
                raise RedisConnectionError('Job storage is unavailable or invalid') from None
        return self._memory_jobs.get(job_id)

    async def list_jobs(
        self, tenant_id: str | None = None, status: JobStatus | None = None
    ) -> list[BackgroundJob]:
        """List locally known jobs, optionally scoped by tenant and lifecycle state.

        Job records are keyed by ID in Redis; production callers should use this
        method per process/tenant or add an indexed repository when persistent
        cross-worker reporting is required.
        """
        jobs = list(self._memory_jobs.values())
        if tenant_id is not None:
            jobs = [job for job in jobs if job.tenant_id == tenant_id]
        if status is not None:
            jobs = [job for job in jobs if job.status == status]
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    async def cancel_job(self, job_id: str) -> BackgroundJob:
        job = await self.get_job(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            raise ValueError(f"Cannot cancel a {job.status.value} job")
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc).isoformat()
        job.duration_seconds = self._duration(job)
        await self._save(job)
        platform_metrics.record_job_event(job.job_type.value, job.status.value)
        logger.info("Job cancelled job_id=%s", job.job_id)
        return job

    async def update_progress(self, job_id: str, progress: int) -> BackgroundJob:
        job = await self.get_job(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
            raise ValueError("Only queued or running jobs can report progress")
        job.progress = max(0, min(100, int(progress)))
        await self._save(job)
        return job

    async def run_next(self) -> BackgroundJob | None:
        # Cancellation leaves an already-enqueued ID behind; discard stale IDs
        # until a runnable job is found so a cancelled high-priority job cannot
        # prevent lower-priority work from progressing.
        while True:
            job_id = await self._dequeue_id()
            if not job_id:
                return None
            job = await self.get_job(job_id)
            if job is None or job.status != JobStatus.QUEUED:
                continue
            return await self.execute(job)

    async def execute(self, job: BackgroundJob) -> BackgroundJob:
        try:
            await self._authorize(job)
        except Exception:
            # Revoked/missing membership is terminal, never automatically retried.
            job.status = JobStatus.FAILED
            job.error = 'Job authorization denied or unavailable'
            job.completed_at = datetime.now(timezone.utc).isoformat()
            await self._save(job)
            return job
        handler = self._handlers.get(job.job_type)
        if handler is None:
            job.attempts = job.max_attempts
            return await self._fail(job, f"No handler registered for {job.job_type.value}")

        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = datetime.now(timezone.utc).isoformat()
        job.error = None
        await self._save(job)
        platform_metrics.record_job_event(job.job_type.value, job.status.value)
        try:
            result = handler(job.payload)
            if inspect.isawaitable(result):
                result = await result
            job.result = result
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.duration_seconds = self._duration(job)
            await self._save(job)
            platform_metrics.record_job_event(job.job_type.value, job.status.value)
            return job
        except Exception as exc:
            return await self._fail(job, str(exc))

    async def retry(self, job_id: str) -> BackgroundJob:
        job = await self.get_job(job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        await self._authorize(job)
        if not job.retry_safe:
            raise ValueError('Job replay requires an explicitly retry-safe handler')
        if job.status != JobStatus.FAILED:
            raise ValueError("Only failed jobs may be retried")
        if job.attempts >= job.max_attempts:
            raise ValueError("Job retry limit has been reached")
        job.status = JobStatus.QUEUED
        job.error = None
        await self._save(job)
        await self._enqueue_id(job.job_id)
        return job

    async def retry_job(self, job_id: str) -> BackgroundJob:
        """Explicit API name used by services; retained alongside ``retry``."""
        return await self.retry(job_id)

    async def _authorize(self, job: BackgroundJob) -> None:
        if self._authorizer is None:
            raise PermissionError('A persisted job authorization provider is required')
        result = self._authorizer(job)
        if inspect.isawaitable(result):
            await result

    async def _fail(self, job: BackgroundJob, error: str) -> BackgroundJob:
        job.error = error[:2000]
        job.completed_at = datetime.now(timezone.utc).isoformat()
        if job.retry_safe and job.attempts < job.max_attempts:
            job.status = JobStatus.QUEUED
            await self._save(job)
            await self._enqueue_id(job.job_id)
            platform_metrics.record_job_event(job.job_type.value, job.status.value)
        else:
            job.status = JobStatus.FAILED
            job.duration_seconds = self._duration(job)
            await self._save(job)
            platform_metrics.record_job_event(job.job_type.value, job.status.value)
        return job

    async def _save(self, job: BackgroundJob) -> None:
        if self._redis is not None:
            await self._redis.set(self._job_key(job.job_id), job.model_dump_json(), self.JOB_TTL_SECONDS)
        self._memory_jobs[job.job_id] = job

    async def _enqueue_id(self, job_id: str) -> None:
        if self._redis is not None:
            await self._redis.push(self._queue_key(self._memory_jobs[job_id].priority), job_id)
            return
        self._memory_queue.append(job_id)
        self._memory_queue.sort(key=lambda item: self._memory_jobs[item].priority, reverse=True)

    async def _dequeue_id(self) -> str | None:
        if self._redis is not None:
            for priority in range(9, -1, -1):
                job_id = await self._redis.pop(self._queue_key(priority))
                if job_id:
                    return job_id
            return None
        return self._memory_queue.pop(0) if self._memory_queue else None

    @classmethod
    def _job_key(cls, job_id: str) -> str:
        return f"{cls.JOB_PREFIX}:{job_id}"

    @classmethod
    def _queue_key(cls, priority: int) -> str:
        return f"{cls.QUEUE_PREFIX}:{priority}"

    @staticmethod
    def _duration(job: BackgroundJob) -> float | None:
        if not job.started_at or not job.completed_at:
            return None
        return max(0.0, (datetime.fromisoformat(job.completed_at) - datetime.fromisoformat(job.started_at)).total_seconds())
