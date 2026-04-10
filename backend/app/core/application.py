from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.app.api import actions, assistant, decision, devices, events, maps, mode, system, voice, web, world
from backend.app.orchestration.assistant_router import AssistantPlatformRouter
from backend.utils import get_logger, setup_logging


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    router = AssistantPlatformRouter()
    app.state.router = router
    logger.info("Assistant platform initialized")
    yield
    logger.info("Assistant platform shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Personal AI Assistant Command Center",
        description="Local-first assistant platform with conversation and decision modes",
        version="3.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "assistant-command-center", "version": "3.0.0"}

    app.include_router(assistant.router, prefix="/api")
    app.include_router(decision.router, prefix="/api")
    app.include_router(mode.router, prefix="/api")
    app.include_router(actions.router, prefix="/api")
    app.include_router(devices.router, prefix="/api")
    app.include_router(world.router, prefix="/api")
    app.include_router(maps.router, prefix="/api")
    app.include_router(voice.router, prefix="/api")
    app.include_router(web.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    return app
