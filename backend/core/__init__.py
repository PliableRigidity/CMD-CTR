"""
Core orchestration and application factory.

This module contains:
- FastAPI app creation (app.py)
- Assistant router/dispatcher (router.py)
- Mode base classes (modes.py)
- Request context management (context.py)
"""

from backend.core.app import create_app
from backend.core.router import AssistantRouter

__all__ = ["create_app", "AssistantRouter"]
