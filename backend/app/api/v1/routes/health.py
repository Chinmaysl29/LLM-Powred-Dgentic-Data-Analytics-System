"""Application dependency health, liveness, and readiness endpoints."""

import asyncio
from fastapi import APIRouter, Request, Response, status

from backend.app.schemas.health import (
    DependencyHealth,
    HealthResponse,
    LivenessResponse,
    ReadinessResponse,
)
from backend.monitoring.prometheus_metrics import platform_metrics

router = APIRouter(tags=["health"])

PROBE_TIMEOUT_SECONDS = 3.0


@router.get('/health/rag')
async def rag_readiness(request: Request, response: Response):
    healthy, message = await _check_component(request.app.state.chroma.indexing_health_check)
    if not healthy:
        response.status_code = 503
    return {'ready': healthy, 'message': message}


async def _check_component(coro_or_func) -> tuple[bool, str]:
    """Execute a component health probe with a strict timeout and sanitized output."""
    try:
        coro = coro_or_func()
        if asyncio.iscoroutine(coro):
            return await asyncio.wait_for(coro, timeout=PROBE_TIMEOUT_SECONDS)
        return coro
    except asyncio.TimeoutError:
        return False, f"Probe timed out after {PROBE_TIMEOUT_SECONDS}s"
    except Exception as exc:
        return False, f"Probe failed: {exc.__class__.__name__}"


@router.get("/health/live", response_model=LivenessResponse)
@router.get("/live", response_model=LivenessResponse, include_in_schema=False)
async def liveness_check() -> LivenessResponse:
    """Liveness probe indicating the ASGI process is running and responding."""
    return LivenessResponse(status="alive", message="Process is responsive")


@router.get("/health/ready", response_model=ReadinessResponse)
@router.get("/ready", response_model=ReadinessResponse, include_in_schema=False)
async def readiness_check(request: Request, response: Response) -> ReadinessResponse:
    """Readiness probe validating operational availability of mandatory infrastructure."""
    postgres_ok, postgres_message = await _check_component(request.app.state.postgres.health_check)
    redis_ok, redis_message = await _check_component(request.app.state.redis.health_check)
    chroma_ok, chroma_message = await _check_component(request.app.state.chroma.health_check)
    schema_ok, schema_message = await _check_component(request.app.state.postgres.schema_check)
    request.app.state.schema_compatible = schema_ok

    critical_healthy = postgres_ok and redis_ok and chroma_ok and schema_ok

    platform_metrics.set_dependency_health("postgres", postgres_ok)
    platform_metrics.set_dependency_health("redis", redis_ok)
    platform_metrics.set_dependency_health("chromadb", chroma_ok)

    # Optional integrations: External LLM providers
    settings = getattr(getattr(request.app.state, "postgres", None), "_settings", None)
    groq_configured = bool(getattr(settings, "groq_api_key", None))
    gemini_configured = bool(getattr(settings, "gemini_api_key", None))
    openai_configured = bool(getattr(settings, "openai_api_key", None))

    optional_dependencies = {
        "groq_api": DependencyHealth(
            status="healthy" if groq_configured else "unhealthy",
            message="API key configured" if groq_configured else "Optional provider not configured",
        ),
        "gemini_api": DependencyHealth(
            status="healthy" if gemini_configured else "unhealthy",
            message="API key configured" if gemini_configured else "Optional provider not configured",
        ),
        "openai_api": DependencyHealth(
            status="healthy" if openai_configured else "unhealthy",
            message="API key configured" if openai_configured else "Optional provider not configured",
        ),
    }

    if not critical_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        success=critical_healthy,
        status="ready" if critical_healthy else "unready",
        critical_dependencies={
            "schema": DependencyHealth(status="healthy" if schema_ok else "unhealthy", message=schema_message),
            "postgresql": DependencyHealth(
                status="healthy" if postgres_ok else "unhealthy", message=postgres_message
            ),
            "redis": DependencyHealth(
                status="healthy" if redis_ok else "unhealthy", message=redis_message
            ),
            "chromadb": DependencyHealth(
                status="healthy" if chroma_ok else "unhealthy", message=chroma_message
            ),
        },
        optional_dependencies=optional_dependencies,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request, response: Response) -> HealthResponse:
    """Return backward-compatible application dependency status with truthful HTTP status."""
    postgres_ok, postgres_message = await _check_component(request.app.state.postgres.health_check)
    redis_ok, redis_message = await _check_component(request.app.state.redis.health_check)
    chroma_ok, chroma_message = await _check_component(request.app.state.chroma.health_check)

    dependencies_healthy = postgres_ok and redis_ok and chroma_ok
    platform_metrics.set_dependency_health("postgres", postgres_ok)
    platform_metrics.set_dependency_health("redis", redis_ok)
    platform_metrics.set_dependency_health("chromadb", chroma_ok)

    if not dependencies_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        success=dependencies_healthy,
        status="healthy" if dependencies_healthy else "degraded",
        application=DependencyHealth(status="healthy", message="Application is running"),
        postgresql=DependencyHealth(
            status="healthy" if postgres_ok else "unhealthy", message=postgres_message
        ),
        redis=DependencyHealth(status="healthy" if redis_ok else "unhealthy", message=redis_message),
        chromadb=DependencyHealth(status="healthy" if chroma_ok else "unhealthy", message=chroma_message),
    )
