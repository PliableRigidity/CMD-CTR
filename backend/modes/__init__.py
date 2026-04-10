"""
Operating modes for the personal AI assistant.

Modes define different operating paradigms:
- conversation: Fast, direct LLM responses
- decision: Slow, deep multi-agent reasoning (MAGI)
"""

from backend.modes.base import Mode, ModeType, ModeRequest, ModeResponse

__all__ = [
    "Mode",
    "ModeType",
    "ModeRequest",
    "ModeResponse",
]
