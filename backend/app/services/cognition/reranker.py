"""Memory Reranker (Phase 3).

Deterministic, inspectable reranking of normalised MemoryEntry results. Every
component of the score is exposed in ``entry.metadata['rerank']`` so it can be
audited and tested — no opaque model. Signals (weighted):

  provider relevance · project match · recency · confirmed status ·
  source reliability · confidence · stale penalty · contradiction penalty
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

# Per-provider trust prior (0..1). KOSINE = curated structured store; Brain63 =
# human vault; others lower. Tunable, transparent.
_SOURCE_RELIABILITY = {
    "kosine": 1.0, "brain63": 0.9, "project_memory": 0.8,
    "knowledge_graph": 0.7, "workflow_history": 0.6, "session_memory": 0.5,
    "sqlite": 0.5,
}

_WEIGHTS = {
    "relevance": 0.35,
    "project": 0.15,
    "recency": 0.15,
    "confirmed": 0.10,
    "reliability": 0.10,
    "confidence": 0.15,
}
_STALE_PENALTY = 0.15
_CONTRADICTION_PENALTY = 0.20
_STALE_DAYS = 180


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
    return None


class MemoryReranker:
    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime.now(timezone.utc)

    def _recency(self, date_str: str) -> tuple[float, float]:
        dt = _parse_date(date_str)
        if not dt:
            return 0.4, 0.0  # unknown date → neutral, no stale penalty
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = max(0.0, (self._now - dt).total_seconds() / 86400.0)
        recency = 0.5 ** (days / 90.0)              # halves every 90 days
        stale = _STALE_PENALTY if days > _STALE_DAYS else 0.0
        return round(recency, 4), stale

    def score_one(self, entry, project: str = "") -> dict:
        meta = entry.metadata or {}
        relevance = max(0.0, min(1.0, entry.score))
        proj = 1.0 if project and project.lower() in (
            (entry.project or "").lower(), (entry.title or "").lower()) else 0.0
        recency, stale = self._recency(entry.date)
        status = str(meta.get("status", "")).lower()
        confirmed = 1.0 if status in ("active", "completed", "confirmed") else 0.0
        reliability = _SOURCE_RELIABILITY.get(entry.provider, 0.5)
        confidence = float(meta.get("confidence", 0.7) or 0.7)
        contradiction = _CONTRADICTION_PENALTY if meta.get("conflict") else 0.0

        base = (
            _WEIGHTS["relevance"] * relevance
            + _WEIGHTS["project"] * proj
            + _WEIGHTS["recency"] * recency
            + _WEIGHTS["confirmed"] * confirmed
            + _WEIGHTS["reliability"] * reliability
            + _WEIGHTS["confidence"] * min(1.0, confidence)
        )
        final = round(max(0.0, base - stale - contradiction), 4)
        return {
            "final": final,
            "relevance": relevance, "project": proj, "recency": recency,
            "confirmed": confirmed, "reliability": reliability,
            "confidence": round(min(1.0, confidence), 4),
            "stale_penalty": stale, "contradiction_penalty": contradiction,
        }

    def rerank(self, entries: list, project: str = "") -> list:
        for e in entries:
            breakdown = self.score_one(e, project=project)
            e.metadata = {**(e.metadata or {}), "rerank": breakdown}
            e.score = breakdown["final"]
        return sorted(entries, key=lambda e: e.score, reverse=True)
