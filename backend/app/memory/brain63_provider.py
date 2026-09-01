"""Brain63 Memory Provider — READ-ONLY vault access."""
from __future__ import annotations

import logging
from typing import Optional

from backend.app.memory.provider import MemoryEntry, MemoryProvider, ProviderHealth

logger = logging.getLogger("silvia.memory.brain63")


class Brain63Provider(MemoryProvider):

    @property
    def name(self) -> str:
        return "Brain63"

    @property
    def provider_id(self) -> str:
        return "brain63"

    def _service(self):
        from backend.app.services.brain63_service import Brain63Service
        from backend.config import BRAIN63_VAULT_PATH
        return Brain63Service(BRAIN63_VAULT_PATH)

    def search(self, query: str, project: str = "", limit: int = 10) -> list[MemoryEntry]:
        try:
            svc = self._service()
            chunks = svc.search(query, entity_hint=project, top_k=limit)
            return [
                MemoryEntry(
                    id=f"b63_{i}",
                    provider=self.provider_id,
                    type=chunk.note_type,
                    title=chunk.section or chunk.file_path.split("/")[-1].replace(".md", ""),
                    content=chunk.content[:500],
                    project=chunk.project,
                    date="",
                    source=chunk.file_path,
                    score=chunk.score,
                    metadata={"file_path": chunk.file_path},
                )
                for i, chunk in enumerate(chunks)
            ]
        except Exception as e:
            logger.debug("Brain63 search error: %s", e)
            return []

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        return None

    def timeline(self, project: str = "", limit: int = 50) -> list[MemoryEntry]:
        return self.search(project or "overview", project=project, limit=limit)

    def health(self) -> ProviderHealth:
        try:
            svc = self._service()
            svc._ensure_index()
            count = len(svc._index) if svc._index else 0
            return ProviderHealth(
                name=self.name,
                available=count > 0,
                entry_count=count,
                details=f"{count} indexed chunks",
            )
        except Exception as e:
            return ProviderHealth(name=self.name, available=False, details=str(e))

    def capabilities(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "searchable": True,
            "timeline": True,
            "relationships": False,
            "provenance": True,    # vault file_path is the source
            "writable": False,     # strictly read-only vault archive
            "remote": False,       # local filesystem, always available
        }
