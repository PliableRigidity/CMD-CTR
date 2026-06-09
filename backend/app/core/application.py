import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.app.api import actions, assistant, decision, devices, events, maps, memory, missions, mode, nodes, system, voice, watch, web, world
from backend.app.orchestration.assistant_router import AssistantPlatformRouter
from backend.config import CORS_ALLOW_ORIGINS
from backend.utils import get_logger, setup_logging


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    router = AssistantPlatformRouter()
    app.state.router = router
    logger.info("Assistant platform initialized")

    # Pre-warm wake word detector in a thread so model downloads and ONNX
    # session creation happen at startup, not on the first WS connection.
    loop = asyncio.get_event_loop()
    try:
        from backend.voice.wakeword.detector import get_detector
        await loop.run_in_executor(None, get_detector)
        logger.info("Wake word detector pre-warmed")
    except Exception as exc:
        logger.warning("Wake word detector pre-warm failed (non-fatal): %s", exc)

    yield
    logger.info("Assistant platform shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SILVIA — AI Operating System",
        description="Strategic Intelligence, Logistics, Voice & Integrated Assistant. Local-first. Ollama-powered. Multi-agent.",
        version="4.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "silvia", "version": "4.0.0"}

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
    app.include_router(memory.router, prefix="/api")
    app.include_router(missions.router, prefix="/api")
    app.include_router(nodes.router, prefix="/api")
    app.include_router(watch.router, prefix="/api")
    return app
