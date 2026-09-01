"""KOSINE Memory Provider — Phase 19.

Wraps the KOSINE structured-memory backend behind SILVIA's MemoryProvider
interface. Reads (search / get / timeline / relationships) are always safe.
Writes go through ``store``/``update`` but are gated by ``KOSINE_ALLOW_WRITES``
and audited (see kosine_audit.py); destructive KOSINE tools are disabled at the
transport layer (kosine_client creates the SDK with allow_destructive=False).

KOSINE object shape (from the SDK): {id, type, title, description, status, tags,
source, confidence, created_at, updated_at, source_path}.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from backend.app.memory.provider import MemoryEntry, MemoryProvider, ProviderHealth

logger = logging.getLogger("silvia.memory.kosine")


class KosineProvider(MemoryProvider):

    @property
    def name(self) -> str:
        return "KOSINE"

    @property
    def provider_id(self) -> str:
        return "kosine"

    # ── transport ────────────────────────────────────────────────────────────

    def _client(self):
        from backend.app.memory.kosine_client import get_client
        return get_client()

    # ── mapping ────────────────────────────────────────────────────────────────

    def _object_to_entry(self, obj: dict, score: float = 0.0) -> MemoryEntry:
        obj = obj or {}
        return MemoryEntry(
            id=str(obj.get("id", "")),
            provider=self.provider_id,
            type=str(obj.get("type", "") or "").lower(),
            title=str(obj.get("title", "") or ""),
            content=str(obj.get("description", "") or ""),
            project=str(obj.get("title", "")) if obj.get("type") == "Project" else "",
            date=str(obj.get("updated_at") or obj.get("created_at") or ""),
            source=obj.get("source_path") or "kosine",
            score=score,
            metadata={
                "status": obj.get("status", ""),
                "tags": obj.get("tags", []),
                "confidence": obj.get("confidence", 1.0),
                "kosine_type": obj.get("type", ""),
            },
        )

    # ── reads ──────────────────────────────────────────────────────────────────

    def search(self, query: str, project: str = "", limit: int = 10) -> list[MemoryEntry]:
        try:
            client = self._client()
            objs = client.search_memory(query=query, limit=limit) or []
            entries: list[MemoryEntry] = []
            for i, obj in enumerate(objs):
                # KOSINE returns results in relevance order but no numeric score;
                # synthesize a descending score so the MemoryManager keeps the order
                # and KOSINE (primary) ranks near the top of aggregated results.
                score = max(0.1, 1.0 - i * 0.03)
                entry = self._object_to_entry(obj, score=score)
                if project and project.lower() not in (
                    entry.project.lower(),
                    entry.title.lower(),
                    " ".join(str(t) for t in entry.metadata.get("tags", [])).lower(),
                ) and project.lower() not in entry.content.lower():
                    # Best-effort project narrowing — KOSINE search is global.
                    continue
                entries.append(entry)
            return entries[:limit]
        except Exception as e:
            logger.debug("KOSINE search error: %s", e)
            return []

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        try:
            client = self._client()
            data = client.show_object(entry_id) or {}
            obj = data.get("object") if isinstance(data, dict) else None
            if not obj:
                return None
            entry = self._object_to_entry(obj, score=1.0)
            entry.metadata["related"] = data.get("related", [])
            return entry
        except Exception as e:
            logger.debug("KOSINE get error: %s", e)
            return None

    def timeline(self, project: str = "", limit: int = 50) -> list[MemoryEntry]:
        try:
            client = self._client()
            target = project or None
            events = client.get_timeline(target=target, limit=limit) or []
            return [
                MemoryEntry(
                    id=str(ev.get("id", "")),
                    provider=self.provider_id,
                    type=str(ev.get("event_type", "event")),
                    title=str(ev.get("description", "") or ""),
                    content=str(ev.get("description", "") or ""),
                    project=project,
                    date=str(ev.get("created_at", "")),
                    source="kosine",
                    metadata={"object_id": ev.get("object_id", ""), **(ev.get("metadata") or {})},
                )
                for ev in events
            ]
        except Exception as e:
            logger.debug("KOSINE timeline error: %s", e)
            return []

    def relationships(self, entity: str = "", limit: int = 20) -> list[dict]:
        if not entity:
            return []
        try:
            client = self._client()
            rels = client.get_related(entity) or []
            return rels[:limit]
        except Exception as e:
            logger.debug("KOSINE relationships error: %s", e)
            return []

    def health(self) -> ProviderHealth:
        try:
            client = self._client()
            objs = client.list_objects(limit=100000) or []
            count = len(objs)
            return ProviderHealth(
                name=self.name,
                available=True,
                entry_count=count,
                details=f"{count} structured objects",
            )
        except Exception as e:
            return ProviderHealth(name=self.name, available=False, details=str(e))

    def capabilities(self) -> dict:
        from backend import config
        return {
            "provider_id": self.provider_id,
            "searchable": True,
            "timeline": True,
            "relationships": True,
            "provenance": True,   # source_path + append-only events
            "writable": bool(config.KOSINE_ALLOW_WRITES),  # gated + audited
            "remote": True,       # network boundary — can be degraded/unreachable
        }

    # ── writes (gated + audited) ────────────────────────────────────────────────

    def store(self, entry: dict) -> Optional[str]:
        """Create a KOSINE object. Returns the new object id, or None if writes
        are disabled. Requires ``type`` and ``title`` in ``entry``."""
        from backend import config
        if not config.KOSINE_ALLOW_WRITES:
            logger.info("KOSINE write blocked (KOSINE_ALLOW_WRITES is off): %s", entry.get("title"))
            return None
        obj_type = entry.get("type")
        title = entry.get("title")
        if not obj_type or not title:
            logger.warning("KOSINE store requires 'type' and 'title'")
            return None
        actor = entry.pop("_actor", "silvia")
        fields = {k: v for k, v in entry.items() if k not in ("type", "title")}
        try:
            from backend.app.memory.kosine_audit import audited_write
            data = audited_write(
                "create_memory",
                {"type": obj_type, "title": title, **fields},
                actor=actor,
            )
            return data.get("id") if isinstance(data, dict) else None
        except Exception as e:
            logger.warning("KOSINE store failed: %s", e)
            return None

    def update(self, entry_id: str, updates: dict) -> bool:
        from backend import config
        if not config.KOSINE_ALLOW_WRITES:
            logger.info("KOSINE update blocked (KOSINE_ALLOW_WRITES is off): %s", entry_id)
            return False
        actor = updates.pop("_actor", "silvia") if isinstance(updates, dict) else "silvia"
        try:
            from backend.app.memory.kosine_audit import audited_write
            audited_write(
                "update_memory",
                {"target": entry_id, **updates},
                actor=actor,
            )
            return True
        except Exception as e:
            logger.warning("KOSINE update failed: %s", e)
            return False

    # ── review-gated write proposal (folds into the approval/audit lifecycle) ──

    _OP_TOOL = {
        "create": "create_memory",
        "update": "update_memory",
        "relate": "create_relationship",
        "event": "add_event",
    }

    def propose_write(self, proposal) -> Optional[str]:
        """Register a proposed KOSINE write as a review-gated ``kosine_suggestion``
        workflow (draft). It writes NOTHING itself — the existing approval UI +
        ``kosine_apply`` execute it (audited) only after a human approves and
        ``KOSINE_ALLOW_WRITES`` is on. Returns the workflow code."""
        tool = self._OP_TOOL.get(getattr(proposal, "operation", ""))
        if not tool:
            logger.warning("KOSINE propose_write: unsupported operation %r",
                           getattr(proposal, "operation", None))
            return None
        args = dict(getattr(proposal, "content", {}) or {})
        label = (args.get("title") or args.get("target")
                 or getattr(proposal, "object_type", "") or proposal.operation)
        try:
            from backend.app.services.workflow_engine import get_workflow_engine
            wf = get_workflow_engine().create(
                category="kosine_suggestion",
                title=f"KOSINE {proposal.operation}: {label}"[:120],
                description=(getattr(proposal, "source_event", "")
                            or f"Proposed {proposal.operation} from SILVIA cognition"),
                risk_level="low",
                tool_name=tool,
                tool_args=args,
                project="KOSINE",
                template="kosine_suggestion",
                auto_submit=False,
            )
            return wf.get("code")
        except Exception as e:
            logger.warning("KOSINE propose_write failed: %s", e)
            return None
