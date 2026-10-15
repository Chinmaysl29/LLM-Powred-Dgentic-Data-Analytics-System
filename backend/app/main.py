"""FastAPI application factory and infrastructure lifecycle management."""

import logging
from contextlib import asynccontextmanager
from inspect import isawaitable
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi import Response
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1.router import router as api_v1_router
from backend.app.api.v1.routes.health import router as health_router
from backend.app.core.config import get_settings
from backend.app.core.exceptions import register_exception_handlers
from backend.app.core.logging import configure_logging
from backend.app.database.chromadb import ChromaDatabase
from backend.app.database.postgres import PostgresDatabase
from backend.app.database.redis import RedisCache
from backend.app.middleware.request_id import RequestIDMiddleware
from backend.app.middleware.request_logging import RequestLoggingMiddleware
from backend.app.middleware.response_time import ResponseTimeMiddleware
from backend.app.middleware.metrics import PrometheusMetricsMiddleware
from backend.app.middleware.audit import AuditTrailMiddleware
from backend.app.middleware.tracing import TracingMiddleware
from backend.monitoring.prometheus_metrics import platform_metrics

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize and safely release infrastructure clients for one process."""
    settings = get_settings()
    configure_logging(settings)
    app.state.postgres = PostgresDatabase(settings)
    app.state.redis = RedisCache(settings)
    app.state.chroma = ChromaDatabase(settings)
    app.state.schema_compatible = False
    logger.info("Application startup initiated environment=%s", settings.environment)

    for dependency_name, connector in (
        ("PostgreSQL", app.state.postgres.connect),
        ("Redis", app.state.redis.connect),
        ("ChromaDB", app.state.chroma.connect),
    ):
        try:
            result = connector()
            if isawaitable(result):
                await result
        except Exception:
            logger.warning("%s is unavailable at startup; health checks will retry", dependency_name, exc_info=True)

    schema_ok, schema_message = await app.state.postgres.schema_check()
    app.state.schema_compatible = schema_ok
    if not schema_ok:
        logger.error("Database startup compatibility check failed: %s", schema_message)

    worker_task = None
    if app.state.schema_compatible and getattr(app.state.postgres, "_session_factory", None) is not None:
        import asyncio
        import socket
        import uuid
        from backend.jobs.manager import BackgroundJobManager
        from backend.jobs.job_worker import JobWorker
        from backend.app.services.document_indexing_service import DocumentIndexingService
        from backend.app.services.analysis_run_service import execute_analysis_job

        job_mgr = BackgroundJobManager(session_factory=app.state.postgres._session_factory)
        job_mgr.register_durable('rag', DocumentIndexingService(app.state.postgres._session_factory).execute)
        job_mgr.register_durable('analysis_pipeline', execute_analysis_job)
        job_worker = JobWorker(job_mgr, concurrency=2)
        app.state.job_worker = job_worker
        worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        worker_task = asyncio.create_task(job_worker.run_persistent(worker_id))
        logger.info("Durable background job worker launched worker_id=%s", worker_id)

    yield

    if worker_task:
        await app.state.job_worker.shutdown()
        worker_task.cancel()
        try:
            await worker_task
        except Exception:
            pass

    await app.state.redis.close()
    await app.state.chroma.close()
    app.state.postgres.close()
    logging.shutdown()


def create_app() -> FastAPI:
    """Construct the configured FastAPI application."""
    settings = get_settings()
    application = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(ResponseTimeMiddleware)
    application.add_middleware(PrometheusMetricsMiddleware)
    application.add_middleware(AuditTrailMiddleware)
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(TracingMiddleware)
    application.include_router(health_router)
    application.include_router(api_v1_router)

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=platform_metrics.render(), media_type="text/plain; version=0.0.4")

    register_exception_handlers(application)
    return application


app = create_app()
