"""Best-effort audit middleware for externally visible platform actions."""

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.app.services.audit_trail_service import audit_trail_service


class AuditTrailMiddleware:
    """Await best-effort persistence after response and dependency cleanup.

    No detached queue or task is introduced. The ASGI invocation remains alive
    until the write finishes, while the response body can reach the client first.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or scope['path'].startswith(('/metrics', '/api/v1/audit')):
            await self.app(scope, receive, send)
            return
        status = None

        async def capture(message: Message) -> None:
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            # Waiting for the inner ASGI application also releases yield-based
            # request sessions. Opening the audit session earlier can exhaust
            # the very pool whose connections those requests are still holding.
            if status is not None and status < 400:
                request = Request(scope)
                action, resource_type, resource_id = self._describe(request)
                postgres = getattr(request.app.state, 'postgres', None)
                session_factory = getattr(postgres, '_session_factory', None)
                values = dict(actor=getattr(request.state, 'actor_id', 'anonymous'),
                    action=action, resource_type=resource_type, resource_id=resource_id,
                    details={'method': request.method, 'path': request.url.path, 'status_code': status})
                if session_factory is not None:
                    values.update(request_id=request.headers.get('X-Request-ID'),
                        ip_address=request.client.host if request.client else None,
                        user_agent=request.headers.get('User-Agent'))
                await run_in_threadpool(self._record, session_factory, values)

    @staticmethod
    def _record(session_factory, values) -> None:
        try:
            if session_factory is not None:
                # The session is created, used and closed on this one worker.
                with session_factory() as session:
                    audit_trail_service.record(**values, session=session)
            else:
                audit_trail_service.record(**values)
        except Exception:
            # Preserve the existing best-effort contract and original response.
            pass

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
