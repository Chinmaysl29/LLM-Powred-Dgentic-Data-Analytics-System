"""Root application entry point delegating to the production FastAPI app."""

from backend.app.main import app

__all__ = ["app"]
