"""Workflow History Memory Provider — workflow state and audit trail."""
from __future__ import annotations

import logging
from typing import Optional

from backend.app.memory.provider import MemoryEntry, MemoryProvider, ProviderHealth

logger = logging.getLogger("silvia.memory.workflow")


def _to_entry(wf: dict, provider_id: str) -> MemoryEntry:
    return MemoryEntry(
        id=wf.get("id", ""),
        provider=provider_id,
        type=f"workflow:{wf.get('category', '')}",
        title=f"{wf.get('code', '')} — {wf.get('title', '')}",
        content=wf.get("description", ""),
        project=wf.get("project", ""),
        date=wf.get("created_at", ""),
        source="workflow_engine",
        score=1.0,
        metadata={
            "code": wf.get("code", ""),
            "status": wf.get("status", ""),
            "risk_level": wf.get("risk_level", ""),
            "tool_name": wf.get("tool_name", ""),
            "execution_result": wf.get("execution_result", ""),
        },
    )


class WorkflowProvider(MemoryProvider):

    @property
    def name(self) -> str:
        return "Workflow History"

    @property
    def provider_id(self) -> str:
        return "workflow_history"

    def _service(self):
        from backend.app.services.workflow_engine import get_workflow_engine
        return get_workflow_engine()

    def search(self, query: str, project: str = "", limit: int = 10) -> list[MemoryEntry]:
        try:
            we = self._service()
            all_wfs = we.get_all(limit=100)
            query_lower = query.lower()
            matches = [
                wf for wf in all_wfs
                if query_lower in wf.get("title", "").lower()
                or query_lower in wf.get("description", "").lower()
                or query_lower in wf.get("category", "").lower()
                or (project and project.lower() in wf.get("project", "").lower())
            ]
            return [_to_entry(wf, self.provider_id) for wf in matches[:limit]]
        except Exception as e:
            logger.debug("Workflow search error: %s", e)
            return []

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        try:
            we = self._service()
            wf = we.get(entry_id)
            return _to_entry(wf, self.provider_id) if wf else None
        except Exception:
            return None

    def timeline(self, project: str = "", limit: int = 50) -> list[MemoryEntry]:
        try:
            we = self._service()
            wfs = we.get_all(limit=limit)
            if project:
                wfs = [w for w in wfs if project.lower() in w.get("project", "").lower()]
            return [_to_entry(wf, self.provider_id) for wf in wfs]
        except Exception:
            return []

    def health(self) -> ProviderHealth:
        try:
            we = self._service()
            all_wfs = we.get_all(limit=9999)
            pending = sum(1 for w in all_wfs if w.get("status") == "pending_review")
            return ProviderHealth(
                name=self.name,
                available=True,
                entry_count=len(all_wfs),
                details=f"{len(all_wfs)} workflows, {pending} pending",
            )
        except Exception as e:
            return ProviderHealth(name=self.name, available=False, details=str(e))
