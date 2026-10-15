"""Best-effort audit middleware for externally visible platform actions."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from backend.app.services.audit_trail_service import audit_trail_service


class AuditTrailMiddleware(BaseHTTPMiddleware):
    """Record successful user actions without adding a second database setup."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if response.status_code < 400 and not request.url.path.startswith(("/metrics", "/api/v1/audit")):
            action, resource_type, resource_id = self._describe(request)
            postgres = getattr(request.app.state, "postgres", None)
            session_factory = getattr(postgres, "_session_factory", None)
            try:
                if session_factory is not None:
                    with session_factory() as session:
                        audit_trail_service.record(
                            actor=getattr(request.state, "actor_id", "anonymous"),
                            action=action,
                            resource_type=resource_type,
                            resource_id=resource_id,
                            request_id=request.headers.get("X-Request-ID"),
                            ip_address=request.client.host if request.client else None,
                            user_agent=request.headers.get("User-Agent"),
                            details={"method": request.method, "path": request.url.path, "status_code": response.status_code},
                            session=session,
                        )
                else:
                    audit_trail_service.record(
                        actor=getattr(request.state, "actor_id", "anonymous"),
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        details={"method": request.method, "path": request.url.path, "status_code": response.status_code},
                    )
            except Exception:
                # Audit failure must not turn a completed user operation into an API failure.
                pass
        return response

    @staticmethod
    def _describe(request: Request) -> tuple[str, str, str | None]:
        path = request.url.path
        parts = [part for part in path.split("/") if part]
        resource_id = parts[-1] if len(parts) > 3 and parts[-1] not in {"upload", "execute", "login", "logout"} else None
        if "/datasets" in path:
            return ("dataset.upload" if path.endswith("/upload") else "dataset.delete" if request.method == "DELETE" else "dataset.access", "dataset", resource_id)
        if "/forecasting" in path:
            return "forecast.request", "forecast", resource_id
        if "/orchestrator/execute" in path:
            return "agent.execute", "agent", "orchestrator"
        if "/auth/" in path:
            return f"authentication.{path.rsplit('/', 1)[-1]}", "authentication", None
        return f"api.{request.method.lower()}", "api", resource_id
