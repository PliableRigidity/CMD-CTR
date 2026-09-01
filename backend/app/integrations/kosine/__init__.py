"""SILVIA-side KOSINE integration package (Phase 19 / boundary hardening).

This package is the ONLY place SILVIA talks to KOSINE, and it does so purely
over KOSINE's public REST contract (``POST /agent/tool/{name}`` + ``GET
/agent/tools`` + ``GET /health``). It contains **no** ``import kos`` — KOSINE
is treated as an independent external service reachable over HTTP, exactly as
another AI client would use it.

Public exports:
- ``KosineHTTPClient`` — the transport/translation client.
- error classes for provider-level handling.
"""
from __future__ import annotations

from backend.app.integrations.kosine.client import KosineHTTPClient
from backend.app.integrations.kosine.errors import (
    KosineError,
    KosineProtocolError,
    KosineToolError,
    KosineUnavailable,
    KosineWriteBlocked,
)

__all__ = [
    "KosineHTTPClient",
    "KosineError",
    "KosineUnavailable",
    "KosineToolError",
    "KosineWriteBlocked",
    "KosineProtocolError",
]
