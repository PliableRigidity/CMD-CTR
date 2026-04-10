"""Primary FastAPI entrypoint for the command-center assistant platform."""

from backend.app.core.application import create_app

app = create_app()
