"""Compatibility entrypoint that now forwards to the modular backend app."""

from backend.app.main import app
from backend.config import APP_HOST, APP_PORT


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host=APP_HOST, port=APP_PORT, reload=True)
