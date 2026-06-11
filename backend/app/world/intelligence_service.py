"""SILVIA Intelligence Service — generates O/A/P/R assessments for world events via Ollama."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

import httpx

from backend.config import OLLAMA_CHAT_URL

logger = logging.getLogger(__name__)

_ASSESSMENT_MODEL = "qwen2.5:3b"
_CACHE_TTL = 1800  # 30 minutes

_PROMPT_TEMPLATE = """\
You are a strategic intelligence analyst. Analyze this news event in three concise sentences.

Title: {title}
Summary: {summary}
Category: {category}
Region: {country}

Respond in EXACTLY this format (no other text):
ASSESSMENT: <one sentence — what this event means strategically>
PREDICTION: <one sentence — most likely next development>
RECOMMENDATION: <one sentence — what to monitor or watch for next>"""

_ASSESS_RE  = re.compile(r"ASSESSMENT:\s*(.+?)(?:\n|$)", re.I)
_PREDICT_RE = re.compile(r"PREDICTION:\s*(.+?)(?:\n|$)", re.I)
_RECOM_RE   = re.compile(r"RECOMMENDATION:\s*(.+?)(?:\n|$)", re.I)


class IntelligenceService:
    def __init__(self):
        self._cache: dict[str, dict] = {}
        self._generating: set[str] = set()

    def get(self, event_id: str) -> Optional[dict]:
        entry = self._cache.get(event_id)
        if not entry:
            return None
        if time.time() - entry["ts"] > _CACHE_TTL:
            del self._cache[event_id]
            return None
        return entry

    def _set(self, event_id: str, assessment: str, prediction: str, recommendation: str = "") -> None:
        self._cache[event_id] = {
            "assessment": assessment,
            "prediction": prediction,
            "recommendation": recommendation,
            "ts": time.time(),
        }

    async def generate_one(self, event) -> bool:
        if event.id in self._generating:
            return False
        if self.get(event.id):
            return True

        self._generating.add(event.id)
        try:
            summary_short = (event.summary or "")[:300].strip()
            prompt = _PROMPT_TEMPLATE.format(
                title=event.title,
                summary=summary_short,
                category=event.category or "general",
                country=event.primary_country or event.country or "Global",
            )
            messages = [
                {"role": "system", "content": "You are a concise strategic intelligence analyst. Reply only in the requested format."},
                {"role": "user", "content": prompt},
            ]
            payload = {
                "model": _ASSESSMENT_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 180},
            }
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(OLLAMA_CHAT_URL, json=payload)
                resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "").strip()
            a_match = _ASSESS_RE.search(content)
            p_match = _PREDICT_RE.search(content)
            r_match = _RECOM_RE.search(content)
            if a_match or p_match:
                assessment     = a_match.group(1).strip() if a_match else ""
                prediction     = p_match.group(1).strip() if p_match else ""
                recommendation = r_match.group(1).strip() if r_match else ""
                self._set(event.id, assessment, prediction, recommendation)
                logger.debug("Intel generated for %s", event.id)
                return True
            else:
                logger.warning("Intel parse failed for %s: %r", event.id, content[:200])
                return False
        except Exception as exc:
            logger.warning("Intel generation failed for %s: %s", event.id, exc)
            return False
        finally:
            self._generating.discard(event.id)

    async def generate_batch(self, events: list, max_concurrent: int = 3) -> None:
        sem = asyncio.Semaphore(max_concurrent)
        async def _guarded(ev):
            async with sem:
                await self.generate_one(ev)
        tasks = [_guarded(ev) for ev in events if not self.get(ev.id)]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def attach(self, events: list) -> list:
        for ev in events:
            cached = self.get(ev.id)
            if cached:
                ev.assessment     = cached["assessment"]
                ev.prediction     = cached["prediction"]
                ev.recommendation = cached.get("recommendation", "")
        return events


intelligence_service = IntelligenceService()
