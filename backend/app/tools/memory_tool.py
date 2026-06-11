"""Semantic memory tool — search past conversation turns by meaning."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def _make_result(ok: bool, tool: str, summary: str, data: dict, error: str = "") -> dict:
    return {"ok": ok, "tool": tool, "summary": summary, "data": data, "error": error}


async def semantic_search(query: str, top_k: int = 5) -> dict:
    """Search conversation history semantically. Returns matching past turns."""
    from backend.app.services.semantic_memory_service import SemanticMemoryService
    svc = SemanticMemoryService()
    results = await svc.search(query, top_k=top_k)
    if not results:
        return _make_result(
            ok=True,
            tool="semantic_search",
            summary=f"No relevant memories found for: {query}",
            data={"query": query, "results": []},
        )
    return _make_result(
        ok=True,
        tool="semantic_search",
        summary=f"Found {len(results)} relevant memory snippet{'s' if len(results) != 1 else ''}",
        data={"query": query, "results": results},
    )
