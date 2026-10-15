"""Domain exceptions and standardized FastAPI exception handlers."""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from backend.app.schemas.errors import ErrorResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Infrastructure Exceptions
# ---------------------------------------------------------------------------
class InfrastructureError(Exception):
    """Base error for an unavailable infrastructure dependency."""

    error_code = "INFRASTRUCTURE_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DatabaseConnectionError(InfrastructureError):
    """Raised when PostgreSQL cannot serve a request."""

    error_code = "DATABASE_UNAVAILABLE"


class RedisConnectionError(InfrastructureError):
    """Raised when Redis cannot serve a request."""

    error_code = "REDIS_UNAVAILABLE"


class ChromaConnectionError(InfrastructureError):
    """Raised when ChromaDB cannot serve a request."""

    error_code = "CHROMA_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------
class DomainError(Exception):
    """Base domain error for business logic and validation failures."""

    error_code = "DOMAIN_ERROR"
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, details: Any = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)


class InvalidChunkingStrategyError(DomainError, ValueError):
    """Raised when an unknown or invalid chunking strategy is requested."""

    error_code = "INVALID_CHUNKING_STRATEGY"
    status_code = status.HTTP_400_BAD_REQUEST


class DatasetNotFoundError(DomainError, ValueError):
    """Raised when a dataset is not found in the database."""

    error_code = "DATASET_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class CorruptedFileError(DomainError, ValueError):
    """Raised when an uploaded file is corrupted or cannot be parsed."""

    error_code = "CORRUPTED_FILE"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT


class DataRetrievalError(DomainError, ValueError):
    """Raised when retrieving or filtering data fails."""

    error_code = "DATA_RETRIEVAL_ERROR"
    status_code = status.HTTP_400_BAD_REQUEST


class StorageError(DomainError):
    """Base error for storage service operations."""

    error_code = "STORAGE_ERROR"
    status_code = status.HTTP_400_BAD_REQUEST


class UnsupportedFileTypeError(StorageError, ValueError):
    """Raised when an uploaded file extension is not supported."""

    error_code = "UNSUPPORTED_FILE_TYPE"
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE


class FileSizeExceededError(StorageError, ValueError):
    """Raised when an uploaded file exceeds the maximum allowed size."""

    error_code = "FILE_SIZE_EXCEEDED"
    status_code = status.HTTP_400_BAD_REQUEST


class StorageFileNotFoundError(StorageError, FileNotFoundError):
    """Raised when a requested file does not exist in storage."""

    error_code = "STORAGE_FILE_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class MetadataExtractionError(DomainError, ValueError):
    """Raised when extracting metadata from a dataset fails."""

    error_code = "METADATA_EXTRACTION_ERROR"
    status_code = 422


class DataProfilingError(DomainError, ValueError):
    """Raised when statistical profiling of a dataset fails."""

    error_code = "DATA_PROFILING_ERROR"
    status_code = 422


class DataQualityError(DomainError, ValueError):
    """Raised when computing dataset quality assessment fails."""

    error_code = "DATA_QUALITY_ERROR"
    status_code = 422


class QualityAssessmentError(DataQualityError):
    """Alias for quality assessment failure."""

    pass


class VersioningError(DomainError):
    """Base exception for dataset versioning operations."""

    error_code = "VERSIONING_ERROR"
    status_code = status.HTTP_400_BAD_REQUEST


class DuplicateVersionError(VersioningError, ValueError):
    """Raised when a version number already exists for a dataset."""

    error_code = "DUPLICATE_VERSION"
    status_code = status.HTTP_409_CONFLICT


class VersionNotFoundError(VersioningError, ValueError):
    """Raised when a requested dataset version is not found."""

    error_code = "VERSION_NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class CleaningRecommendationError(DomainError, ValueError):
    """Raised when generating or resolving cleaning recommendations fails."""

    error_code = "CLEANING_RECOMMENDATION_ERROR"
    status_code = 422


class IntentClassificationError(DomainError, ValueError):
    """Raised when intent classification fails or query is invalid."""

    error_code = "INTENT_CLASSIFICATION_ERROR"
    status_code = status.HTTP_400_BAD_REQUEST


class ValidationException(DomainError, ValueError):
    """Raised when input parameter validation fails."""

    error_code = "VALIDATION_ERROR"
    status_code = 422


class ForecastingError(DomainError, ValueError):
    """Base error for forecasting and predictive intelligence operations."""

    error_code = "FORECASTING_ERROR"
    status_code = status.HTTP_400_BAD_REQUEST


class ForecastingDatasetValidationError(ForecastingError):
    """Raised when a dataset fails time-series forecasting validation."""

    error_code = "FORECASTING_VALIDATION_ERROR"
    status_code = 422


class RecommendationError(DomainError, ValueError):
    """Base error for recommendation and decision intelligence operations."""

    error_code = "RECOMMENDATION_ERROR"
    status_code = status.HTTP_400_BAD_REQUEST


class RecommendationValidationError(RecommendationError):
    """Raised when analytical or forecast data fails recommendation validation."""

    error_code = "RECOMMENDATION_VALIDATION_ERROR"
    status_code = 422


# ---------------------------------------------------------------------------
# Standardized Error Response Builder
# ---------------------------------------------------------------------------
def error_response(
    request: Request, status_code: int, message: str, error_code: str, details: Any = None
) -> JSONResponse:
    """Build the single public error response contract."""
    payload = ErrorResponse(
        message=message,
        error_code=error_code,
        request_id=getattr(request.state, "request_id", None),
        details=details,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(exclude_none=True))


def register_exception_handlers(app: FastAPI) -> None:
    """Register centralized handlers for framework, domain, and infrastructure errors."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            request,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Request validation failed",
            "VALIDATION_ERROR",
            exc.errors(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        message = detail if isinstance(detail, str) else detail.get("message", "Request failed") if isinstance(detail, dict) else "Request failed"
        code = detail.get("code", "HTTP_ERROR") if isinstance(detail, dict) else "HTTP_ERROR"
        return error_response(request, exc.status_code, message, code)

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        logger.warning("Domain error [%s]: %s", exc.error_code, exc.message)
        return error_response(
            request,
            exc.status_code,
            exc.message,
            exc.error_code,
            exc.details,
        )

    @app.exception_handler(InfrastructureError)
    async def infrastructure_error_handler(
        request: Request, exc: InfrastructureError
    ) -> JSONResponse:
        logger.warning("Infrastructure error: %s", exc.message)
        return error_response(request, status.HTTP_503_SERVICE_UNAVAILABLE, exc.message, exc.error_code)

    @app.exception_handler(SQLAlchemyError)
    async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database operation failed")
        return error_response(request, status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable", "DATABASE_ERROR")

    @app.exception_handler(RedisError)
    async def redis_error_handler(request: Request, exc: RedisError) -> JSONResponse:
        logger.exception("Redis operation failed")
        return error_response(request, status.HTTP_503_SERVICE_UNAVAILABLE, "Redis unavailable", "REDIS_ERROR")

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error")
        return error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "An unexpected error occurred",
            "INTERNAL_SERVER_ERROR",
        )
