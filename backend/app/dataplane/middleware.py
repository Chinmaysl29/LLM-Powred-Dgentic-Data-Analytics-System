"""Cap upload bytes before multipart parsing can spool an oversized request."""
from fastapi import HTTPException
from starlette.responses import JSONResponse
from backend.app.dataplane.config import Limits


class UploadBudgetMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/api/v1/dataplane/upload":
            return await self.app(scope, receive, send)
        limits = Limits()
        if not limits.enabled:
            return await JSONResponse({"detail": "Data processing is disabled"}, 503)(scope, receive, send)
        budget = (limits.upload_mb+1)*1024**2  # One MiB for multipart framing.
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid content length"}, 400)(scope, receive, send)
        if length > budget or length < 0:
            return await JSONResponse({"detail": "Upload exceeds configured limit"}, 413)(scope, receive, send)
        consumed, started = 0, False

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > budget:
                raise HTTPException(413, "Upload exceeds configured limit")
            return message

        async def observed_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, bounded_receive, observed_send)
        except HTTPException as error:
            if started:
                raise
            await JSONResponse({"detail": error.detail}, error.status_code)(scope, receive, send)

