"""Cooperative worker engine for processing the shared job manager queue."""

from __future__ import annotations

import asyncio
import logging

from backend.jobs.manager import BackgroundJob, BackgroundJobManager, JobStatus

logger = logging.getLogger(__name__)


class JobWorker:
    def __init__(self, manager: BackgroundJobManager, concurrency: int = 1) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be at least 1")
        self.manager = manager
        self.concurrency = concurrency
        self._stopping = asyncio.Event()
        self.dead_letter: list[str] = []

    async def process_one(self) -> BackgroundJob | None:
        job = await self.manager.run_next()
        if job is not None and job.status == JobStatus.FAILED:
            self.dead_letter.append(job.job_id)
            logger.error("Job moved to dead letter queue job_id=%s", job.job_id)
        return job

    async def run_until_idle(self) -> int:
        processed = 0
        while not self._stopping.is_set():
            jobs = await asyncio.gather(*(self.process_one() for _ in range(self.concurrency)))
            count = sum(job is not None for job in jobs)
            processed += count
            if not count:
                break
        return processed

    async def shutdown(self) -> None:
        self._stopping.set()

    async def run_persistent(self, worker_id):
        """Polling SQL claims also recovers jobs when Redis is restarted."""
        from sqlalchemy.exc import SQLAlchemyError
        failures = 0
        while not self._stopping.is_set():
            # Await every slot before retrying: an early gather exception must
            # not leave another slot running while a duplicate batch starts.
            jobs = await asyncio.gather(*(self.manager.run_next_durable(worker_id) for _ in range(self.concurrency)), return_exceptions=True)
            errors = [job for job in jobs if isinstance(job, BaseException)]
            for error in errors:
                if not isinstance(error, SQLAlchemyError):
                    raise error
            failures = failures + 1 if errors else 0
            if errors:
                logger.warning('Persistent job database unavailable; retrying claims')
            delay = min(30, 2 ** min(failures, 5)) if errors else (1 if not any(jobs) else 0)
            if delay:
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass


def main():
    import socket
    import uuid
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.app.core.config import get_settings
    from backend.app.services.document_indexing_service import DocumentIndexingService
    from backend.app.services.analysis_run_service import execute_analysis_job
    engine = create_engine(get_settings().postgres_dsn, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    manager = BackgroundJobManager(session_factory=sessions)
    manager.register_durable('rag', DocumentIndexingService(sessions).execute)
    manager.register_durable('analysis_pipeline', execute_analysis_job)
    try:
        asyncio.run(JobWorker(manager).run_persistent(f'{socket.gethostname()}-{uuid.uuid4()}'))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
