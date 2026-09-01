"""SILVIA cognition layer (Phases 3–4).

Task-specific cognition that sits on top of the memory providers: it plans
targeted memory queries, reranks and expands results, composes bounded model
context, and extracts review-gated write proposals — emitting a typed stream of
**observable system-activity** events (never model chain-of-thought) that the
Cognitive Graph visualizes.

The event system is provider-agnostic: it describes SILVIA's own activity, not
KOSINE's internals.
"""
from __future__ import annotations

from backend.app.services.cognition.events import (
    CognitiveEvent,
    CognitiveEventType,
    get_cognitive_bus,
)

__all__ = ["CognitiveEvent", "CognitiveEventType", "get_cognitive_bus"]
