"""
FastAPI application factory.

Creates and configures the main FastAPI app with all middleware,
dependency injection, exception handlers, and route registration.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from backend.utils.logger import setup_logging, get_logger
from backend.utils.errors import AppException


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup/shutdown.
    
    Startup:
    - Initialize logging
    - Initialize local services (voice, actions, devices)
    - Connect to Ollama
    
    Shutdown:
    - Clean up resources
    - Close connections
    """
    # Startup
    logger.info("Starting Personal AI Assistant")
    setup_logging()
    
    # TODO: Initialize subsystems
    # - Voice pipeline
    # - World event aggregator
    # - Device manager
    # - Memory store
    # - Action registry
    
    yield
    
    # Shutdown
    logger.info("Shutting down Personal AI Assistant")
    # TODO: Cleanup
    # - Close voice contexts
    # - Persist state
    # - Disconnect devices


def create_app(config: Optional[dict] = None) -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Args:
        config: Optional configuration overrides
        
    Returns:
        Configured FastAPI app instance
    """
    
    # Create app with lifespan
    app = FastAPI(
        title="Personal AI Assistant",
        description="Local-first AI command center with MAGI decision engine",
        version="2.0.0-beta",
        lifespan=lifespan,
    )
    
    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # GZIP Compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Exception handlers
    @app.exception_handler(AppException)
    async def app_exception_handler(request, exc: AppException):
        """Handle application exceptions gracefully."""
        logger.error(f"AppException: {exc.message}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.message, "code": exc.error_code},
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc: Exception):
        """Handle unexpected exceptions."""
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "code": "INTERNAL_ERROR"},
        )
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        """Simple health check endpoint."""
        return {
            "status": "ok",
            "version": "2.0.0-beta",
            "service": "Personal AI Assistant"
        }
    
    # Register routes
    # These will be imported and added here
    # app.include_router(conversation_router)
    # app.include_router(decision_router)
    # app.include_router(voice_router)
    # app.include_router(world_router)
    # app.include_router(actions_router)
    # app.include_router(devices_router)
    # app.include_router(memory_router)
    
    logger.debug("FastAPI app created and configured")
    return app
