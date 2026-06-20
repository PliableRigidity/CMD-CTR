"""API key authentication middleware.

Disabled when API_KEY env var is not set (backwards compatible).
Localhost requests (127.0.0.1, ::1) always bypass authentication.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from backend.config import API_KEY

_EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")
_LOCAL_HOSTS = {"127.0.0.1", "::1"}


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Auth disabled when no key configured
        if not API_KEY:
            return await call_next(request)

        # Exempt documentation / health paths
        path = request.url.path
        if any(path.startswith(p) for p in _EXEMPT_PREFIXES):
            return await call_next(request)

        # Localhost always passes
        client_host = (request.client.host if request.client else "") or ""
        if client_host in _LOCAL_HOSTS:
            return await call_next(request)

        # WebSocket: check ?api_key= query param
        if request.scope.get("type") == "websocket":
            key = request.query_params.get("api_key", "")
            if key == API_KEY:
                return await call_next(request)
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        # HTTP: check X-API-Key or Authorization: Bearer
        key = (
            request.headers.get("X-API-Key")
            or _extract_bearer(request.headers.get("Authorization", ""))
        )
        if key == API_KEY:
            return await call_next(request)

        return JSONResponse({"detail": "Unauthorized"}, status_code=401)


def _extract_bearer(header: str) -> str:
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""
