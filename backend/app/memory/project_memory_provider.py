"""Project Memory Provider — engineering decisions, lessons, milestones."""
from __future__ import annotations

import logging
from typing import Optional

from backend.app.memory.provider import MemoryEntry, MemoryProvider, ProviderHealth

logger = logging.getLogger("silvia.memory.project")


def _to_entry(row: dict, provider_id: str) -> MemoryEntry:
    return MemoryEntry(
        id=row.get("id", ""),
        provider=provider_id,
        type=row.get("type", ""),
        title=row.get("title", ""),
        content=row.get("summary", "") or row.get("title", ""),
        project=row.get("project", ""),
        date=row.get("date", ""),
        source="project_memory",
        score=1.0,
        metadata={
            "reasoning": row.get("reasoning", ""),
            "tags": row.get("tags", []),
            "source": row.get("source", "manual"),
        },
    )


class ProjectMemoryProvider(MemoryProvider):

    @property
    def name(self) -> str:
        return "Project Memory"

    @property
    def provider_id(self) -> str:
        return "project_memory"

    def _service(self):
        from backend.app.services.project_memory import get_memory as get_project_memory
        return get_project_memory()

    def search(self, query: str, project: str = "", limit: int = 10) -> list[MemoryEntry]:
        try:
            svc = self._service()
            rows = svc.search(query, project=project or None, limit=limit)
            return [_to_entry(r, self.provider_id) for r in rows]
        except Exception as e:
            logger.debug("Project memory search error: %s", e)
            return []

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        try:
            svc = self._service()
            row = svc.get(entry_id)
            return _to_entry(row, self.provider_id) if row else None
        except Exception:
            return None

    def timeline(self, project: str = "", limit: int = 50) -> list[MemoryEntry]:
        try:
            svc = self._service()
            if project:
                rows = svc.get_timeline(project, limit=limit)
            else:
                rows = svc.get_project_memories(None, limit=limit)
            return [_to_entry(r, self.provider_id) for r in rows]
        except Exception:
            return []

    def health(self) -> ProviderHealth:
        try:
            svc = self._service()
            rows = svc.get_project_memories(None, limit=9999)
            return ProviderHealth(
                name=self.name,
                available=True,
                entry_count=len(rows),
                details=f"{len(rows)} memory entries",
            )
        except Exception as e:
            return ProviderHealth(name=self.name, available=False, details=str(e))

    def store(self, entry: dict) -> Optional[str]:
        try:
            svc = self._service()
            return svc.record(
                project=entry.get("project", ""),
                type=entry.get("type", "decision"),
                title=entry.get("title", ""),
                summary=entry.get("summary", ""),
                reasoning=entry.get("reasoning", ""),
            )
        except Exception:
            return None

    def delete(self, entry_id: str) -> bool:
        try:
            return self._service().delete(entry_id)
        except Exception:
            return False
