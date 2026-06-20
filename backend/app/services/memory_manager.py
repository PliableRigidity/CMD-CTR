"""Memory Manager — Phase 18A.

Unified memory access layer that orchestrates all memory providers,
aggregates search results, and provides a single interface for
all memory operations in SILVIA.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from backend.app.memory.provider import MemoryEntry, MemoryProvider, ProviderHealth

logger = logging.getLogger("silvia.memory_manager")

DEFAULT_PRIORITY = [
    "brain63",
    "project_memory",
    "knowledge_graph",
    "workflow_history",
    "session_memory",
    "sqlite",
]


class MemoryManager:
    """Orchestrates memory providers for unified memory access."""

    def __init__(self) -> None:
        self._providers: dict[str, MemoryProvider] = {}
        self._priority: list[str] = list(DEFAULT_PRIORITY)
        self._init_providers()

    def _init_providers(self) -> None:
        try:
            from backend.app.memory.brain63_provider import Brain63Provider
            self._providers["brain63"] = Brain63Provider()
        except Exception as e:
            logger.warning("Brain63 provider init failed: %s", e)

        try:
            from backend.app.memory.project_memory_provider import ProjectMemoryProvider
            self._providers["project_memory"] = ProjectMemoryProvider()
        except Exception as e:
            logger.warning("Project memory provider init failed: %s", e)

        try:
            from backend.app.memory.knowledge_graph_provider import KnowledgeGraphProvider
            self._providers["knowledge_graph"] = KnowledgeGraphProvider()
        except Exception as e:
            logger.warning("Knowledge graph provider init failed: %s", e)

        try:
            from backend.app.memory.workflow_provider import WorkflowProvider
            self._providers["workflow_history"] = WorkflowProvider()
        except Exception as e:
            logger.warning("Workflow provider init failed: %s", e)

        try:
            from backend.app.memory.session_provider import SessionProvider
            self._providers["session_memory"] = SessionProvider()
        except Exception as e:
            logger.warning("Session provider init failed: %s", e)

        try:
            from backend.app.memory.sqlite_provider import SQLiteProvider
            self._providers["sqlite"] = SQLiteProvider()
        except Exception as e:
            logger.warning("SQLite provider init failed: %s", e)

        logger.info("Memory Manager: %d providers loaded", len(self._providers))

    # ── Unified Search ──────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        project: str = "",
        providers: list[str] | None = None,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        """Search across all (or specified) providers and aggregate results."""
        target_ids = providers or self._priority
        all_results: list[MemoryEntry] = []

        per_provider = max(limit // max(len(target_ids), 1), 3)

        for pid in target_ids:
            provider = self._providers.get(pid)
            if not provider:
                continue
            try:
                results = provider.search(query, project=project, limit=per_provider)
                all_results.extend(results)
            except Exception as e:
                logger.debug("Provider %s search failed: %s", pid, e)

        all_results.sort(key=lambda e: e.score, reverse=True)
        return all_results[:limit]

    # ── Unified Timeline ────────────────────────────────────────────────────

    def timeline(
        self,
        project: str = "",
        providers: list[str] | None = None,
        limit: int = 50,
    ) -> list[MemoryEntry]:
        """Build a unified timeline across providers."""
        target_ids = providers or self._priority
        all_entries: list[MemoryEntry] = []

        for pid in target_ids:
            provider = self._providers.get(pid)
            if not provider:
                continue
            try:
                entries = provider.timeline(project=project, limit=limit)
                all_entries.extend(entries)
            except Exception as e:
                logger.debug("Provider %s timeline failed: %s", pid, e)

        all_entries.sort(key=lambda e: e.date or "", reverse=True)
        return all_entries[:limit]

    # ── Unified Relationships ───────────────────────────────────────────────

    def relationships(self, entity: str = "", limit: int = 20) -> list[dict]:
        """Get relationships from graph-capable providers."""
        all_rels: list[dict] = []
        for pid in self._priority:
            provider = self._providers.get(pid)
            if not provider:
                continue
            try:
                rels = provider.relationships(entity=entity, limit=limit)
                all_rels.extend(rels)
            except Exception:
                pass
        return all_rels[:limit]

    # ── Provider Management ─────────────────────────────────────────────────

    def providers(self) -> list[dict[str, Any]]:
        """List all registered providers with status."""
        result = []
        for pid in self._priority:
            provider = self._providers.get(pid)
            if provider:
                h = provider.health()
                result.append({
                    "id": pid,
                    "name": h.name,
                    "available": h.available,
                    "entry_count": h.entry_count,
                    "details": h.details,
                    "priority": self._priority.index(pid) + 1,
                })
        for pid, provider in self._providers.items():
            if pid not in self._priority:
                h = provider.health()
                result.append({
                    "id": pid,
                    "name": h.name,
                    "available": h.available,
                    "entry_count": h.entry_count,
                    "details": h.details,
                    "priority": len(self._priority) + 1,
                })
        return result

    def health(self) -> dict[str, Any]:
        """Aggregate health across all providers."""
        provider_health = []
        total_entries = 0
        available_count = 0

        for pid in self._priority:
            provider = self._providers.get(pid)
            if not provider:
                continue
            h = provider.health()
            provider_health.append({
                "id": pid,
                "name": h.name,
                "available": h.available,
                "entry_count": h.entry_count,
                "details": h.details,
            })
            total_entries += h.entry_count
            if h.available:
                available_count += 1

        return {
            "providers": provider_health,
            "total_providers": len(provider_health),
            "available_providers": available_count,
            "total_entries": total_entries,
            "priority": self._priority,
        }

    # ── Single-entry access ─────────────────────────────────────────────────

    def get(self, entry_id: str, provider_id: str = "") -> Optional[MemoryEntry]:
        """Get a specific entry. Searches all providers if provider_id not given."""
        if provider_id:
            p = self._providers.get(provider_id)
            return p.get(entry_id) if p else None
        for pid in self._priority:
            p = self._providers.get(pid)
            if not p:
                continue
            result = p.get(entry_id)
            if result:
                return result
        return None

    # ── Store ───────────────────────────────────────────────────────────────

    def store(self, provider_id: str, entry: dict) -> Optional[str]:
        """Store a new entry in a specific provider."""
        p = self._providers.get(provider_id)
        if not p:
            return None
        return p.store(entry)

    # ── Context Assembly ────────────────────────────────────────────────────

    def build_context(self, project: str = "", query: str = "") -> str:
        """Build a unified context block for LLM enrichment."""
        lines = []

        if query:
            results = self.search(query, project=project, limit=8)
            if results:
                lines.append("Relevant memory:")
                for entry in results:
                    lines.append(f"  [{entry.provider}] {entry.title}: {entry.content[:150]}")

        if project:
            timeline = self.timeline(project=project, limit=5)
            if timeline:
                lines.append(f"\nRecent {project} history:")
                for entry in timeline:
                    date = entry.date[:10] if entry.date else ""
                    lines.append(f"  {date} [{entry.type}] {entry.title}")

        return "\n".join(lines) if lines else ""


# ── Singleton ───────────────────────────────────────────────────────────────

_instance: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    global _instance
    if _instance is None:
        _instance = MemoryManager()
    return _instance
