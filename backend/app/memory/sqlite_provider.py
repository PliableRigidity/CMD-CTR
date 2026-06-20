"""SQLite Memory Provider — conversation history and user facts."""
from __future__ import annotations

import logging
import time
from typing import Optional

from backend.app.memory.provider import MemoryEntry, MemoryProvider, ProviderHealth

logger = logging.getLogger("silvia.memory.sqlite")


class SQLiteProvider(MemoryProvider):

    @property
    def name(self) -> str:
        return "SQLite"

    @property
    def provider_id(self) -> str:
        return "sqlite"

    def search(self, query: str, project: str = "", limit: int = 10) -> list[MemoryEntry]:
        try:
            from backend.memory.database import get_all_facts
            facts = get_all_facts()
            query_lower = query.lower()
            matches = []
            for key, value in facts.items():
                if query_lower in key.lower() or query_lower in value.lower():
                    matches.append(MemoryEntry(
                        id=f"fact_{key}",
                        provider=self.provider_id,
                        type="fact",
                        title=key,
                        content=value,
                        source="facts",
                        score=0.5,
                    ))
            return matches[:limit]
        except Exception as e:
            logger.debug("SQLite search error: %s", e)
            return []

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        return None

    def timeline(self, project: str = "", limit: int = 50) -> list[MemoryEntry]:
        try:
            from backend.memory.database import get_messages, list_sessions
            sessions = list_sessions()
            entries = []
            for sess in sessions[:5]:
                msgs = get_messages(sess["session_id"], limit=4)
                for msg in msgs:
                    if msg["role"] == "user":
                        entries.append(MemoryEntry(
                            id=f"conv_{len(entries)}",
                            provider=self.provider_id,
                            type="conversation",
                            title=msg["content"][:80],
                            content=msg["content"],
                            date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(msg.get("ts", 0))),
                            source="conversation_history",
                        ))
            return entries[:limit]
        except Exception:
            return []

    def health(self) -> ProviderHealth:
        try:
            from backend.memory.database import list_sessions, get_all_facts
            sessions = list_sessions()
            facts = get_all_facts()
            return ProviderHealth(
                name=self.name,
                available=True,
                entry_count=len(sessions),
                details=f"{len(sessions)} sessions, {len(facts)} facts",
            )
        except Exception as e:
            return ProviderHealth(name=self.name, available=False, details=str(e))

    def store(self, entry: dict) -> Optional[str]:
        try:
            from backend.memory.database import set_fact
            key = entry.get("key", "")
            value = entry.get("value", "")
            if key and value:
                set_fact(key, value)
                return key
        except Exception:
            pass
        return None
