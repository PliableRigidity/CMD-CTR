"""Typed errors for the KOSINE adapter.

The provider/router layers use these to distinguish "KOSINE is down" (degrade,
follow fallback policy) from "KOSINE refused this operation" (surface to the
cognition layer) — without leaking HTTP/urllib details upward.
"""
from __future__ import annotations

from typing import Optional


class KosineError(Exception):
    """Base class for all KOSINE adapter errors."""


class KosineUnavailable(KosineError):
    """Transport failure: KOSINE is unreachable, timed out, or returned 5xx.

    Callers should treat this as "provider degraded" and follow the configured
    fallback policy — NEVER fabricate KOSINE results.
    """


class KosineToolError(KosineError):
    """KOSINE reached, but a tool returned an error envelope (status='error')."""

    def __init__(self, tool: str, message: str, correlation_id: str = ""):
        self.tool = tool
        self.message = message
        self.correlation_id = correlation_id
        super().__init__(f"KOSINE tool '{tool}' error: {message}"
                         + (f" [cid={correlation_id}]" if correlation_id else ""))


class KosineWriteBlocked(KosineError):
    """A destructive/forbidden tool was requested but is not permitted."""


class KosineProtocolError(KosineError):
    """KOSINE returned a response that does not match the expected envelope."""

    def __init__(self, message: str, body: Optional[str] = None):
        self.body = body
        super().__init__(message)
