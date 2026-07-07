"""Embedding service — wraps Ollama nomic-embed-text for 768-dim vectors."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_EMBED_URL   = "http://localhost:11434/api/embeddings"
_EMBED_MODEL = "nomic-embed-text"
_EMBED_DIM   = 768
# Keep the embedding model resident so memory search before each reply doesn't
# pay a reload — and, on VRAM-limited GPUs, doesn't thrash against the chat model.
_EMBED_KEEP_ALIVE = "30m"


async def get_embedding(text: str) -> list[float]:
    """Return a 768-dim embedding for text. Returns [] on failure."""
    if not text or not text.strip():
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _EMBED_URL,
                json={"model": _EMBED_MODEL, "prompt": text[:4096], "keep_alive": _EMBED_KEEP_ALIVE},
            )
            resp.raise_for_status()
        vec = resp.json().get("embedding", [])
        if len(vec) != _EMBED_DIM:
            logger.warning("Unexpected embedding dim %d (expected %d)", len(vec), _EMBED_DIM)
            return []
        return vec
    except Exception as exc:
        logger.debug("Embedding failed: %s", exc)
        return []
