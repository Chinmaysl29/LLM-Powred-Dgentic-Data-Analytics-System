"""Health endpoint response models."""

from typing import Literal

from pydantic import BaseModel


class DependencyHealth(BaseModel):
    """Health result for one application dependency."""

    status: Literal["healthy", "unhealthy"]
    message: str


class LivenessResponse(BaseModel):
    """Liveness probe response model."""

    status: Literal["alive"]
    message: str = "Process is responsive"


class ReadinessResponse(BaseModel):
    """Readiness probe response model."""

    success: bool
    status: Literal["ready", "unready"]
    critical_dependencies: dict[str, DependencyHealth]
    optional_dependencies: dict[str, DependencyHealth]


class HealthResponse(BaseModel):
    """Detailed service readiness response."""

    success: bool
    status: Literal["healthy", "degraded"]
    application: DependencyHealth
    postgresql: DependencyHealth
    redis: DependencyHealth
    chromadb: DependencyHealth
