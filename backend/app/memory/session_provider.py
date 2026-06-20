"""Session Memory Provider — workspace sessions and context history."""
from __future__ import annotations

import logging
from typing import Optional

from backend.app.memory.provider import MemoryEntry, MemoryProvider, ProviderHealth

logger = logging.getLogger("silvia.memory.session")


class SessionProvider(MemoryProvider):

    @property
    def name(self) -> str:
        return "Session Memory"

    @property
    def provider_id(self) -> str:
        return "session_memory"

    def _service(self):
        from backend.app.services.session_manager import get_session_manager
        return get_session_manager()

    def search(self, query: str, project: str = "", limit: int = 10) -> list[MemoryEntry]:
        try:
            sm = self._service()
            sessions = sm.get_recent_sessions(limit=50)
            query_lower = query.lower()
            matches = []
            for s in sessions:
                proj = s.get("project", "")
                stype = s.get("session_type", "")
                summary = s.get("summary", "")
                if (query_lower in proj.lower()
                    or query_lower in stype.lower()
                    or query_lower in summary.lower()
                    or (project and project.lower() in proj.lower())):
                    matches.append(MemoryEntry(
                        id=s.get("id", ""),
                        provider=self.provider_id,
                        type=f"session:{stype}",
                        title=f"{proj} — {stype}" if proj else stype or "Session",
                        content=summary or f"Duration: {s.get('duration_minutes', 0)} min",
                        project=proj,
                        date=s.get("started_at", ""),
                        source="session_manager",
                        score=0.7,
                        metadata={
                            "duration_minutes": s.get("duration_minutes", 0),
                            "apps": s.get("apps", []),
                        },
                    ))
            return matches[:limit]
        except Exception as e:
            logger.debug("Session search error: %s", e)
            return []

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        return None

    def timeline(self, project: str = "", limit: int = 50) -> list[MemoryEntry]:
        try:
            sm = self._service()
            sessions = sm.get_recent_sessions(limit=limit)
            if project:
                sessions = [s for s in sessions if project.lower() in s.get("project", "").lower()]
            entries = []
            for s in sessions:
                proj = s.get("project", "")
                stype = s.get("session_type", "")
                entries.append(MemoryEntry(
                    id=s.get("id", ""),
                    provider=self.provider_id,
                    type=f"session:{stype}",
                    title=f"{proj} — {stype}" if proj else stype or "Session",
                    content=s.get("summary", ""),
                    project=proj,
                    date=s.get("started_at", ""),
                    source="session_manager",
                ))
            return entries
        except Exception:
            return []

    def health(self) -> ProviderHealth:
        try:
            sm = self._service()
            sessions = sm.get_recent_sessions(limit=9999)
            return ProviderHealth(
                name=self.name,
                available=True,
                entry_count=len(sessions),
                details=f"{len(sessions)} sessions",
            )
        except Exception as e:
            return ProviderHealth(name=self.name, available=False, details=str(e))
