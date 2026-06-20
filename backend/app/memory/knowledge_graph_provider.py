"""Knowledge Graph Memory Provider — entities and relationships."""
from __future__ import annotations

import json
import logging
from typing import Optional

from backend.app.memory.provider import MemoryEntry, MemoryProvider, ProviderHealth

logger = logging.getLogger("silvia.memory.kg")


class KnowledgeGraphProvider(MemoryProvider):

    @property
    def name(self) -> str:
        return "Knowledge Graph"

    @property
    def provider_id(self) -> str:
        return "knowledge_graph"

    def _service(self):
        from backend.app.services.knowledge_graph import get_graph
        return get_graph()

    def search(self, query: str, project: str = "", limit: int = 10) -> list[MemoryEntry]:
        try:
            kg = self._service()
            entity = kg.find_entity(project or query)
            if not entity:
                entities = kg.list_entities()
                query_lower = query.lower()
                matches = [e for e in entities if query_lower in e.get("name", "").lower()]
                return [
                    MemoryEntry(
                        id=e["id"],
                        provider=self.provider_id,
                        type=f"entity:{e.get('type', '')}",
                        title=e.get("name", ""),
                        content=json.dumps(json.loads(e.get("metadata", "{}")), indent=2) if e.get("metadata") else "",
                        project=e.get("name", "") if e.get("type") == "project" else "",
                        date=e.get("created_at", ""),
                        source="knowledge_graph",
                        score=0.8,
                    )
                    for e in matches[:limit]
                ]

            rels = kg.list_relationships(entity["id"])
            entries = [
                MemoryEntry(
                    id=entity["id"],
                    provider=self.provider_id,
                    type=f"entity:{entity.get('type', '')}",
                    title=entity.get("name", ""),
                    content=f"{len(rels)} relationships",
                    project=entity.get("name", "") if entity.get("type") == "project" else "",
                    date=entity.get("created_at", ""),
                    source="knowledge_graph",
                    score=1.0,
                )
            ]
            return entries[:limit]
        except Exception as e:
            logger.debug("KG search error: %s", e)
            return []

    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        try:
            kg = self._service()
            entity = kg.get_entity(entry_id)
            if not entity:
                return None
            return MemoryEntry(
                id=entity["id"],
                provider=self.provider_id,
                type=f"entity:{entity.get('type', '')}",
                title=entity.get("name", ""),
                content="",
                date=entity.get("created_at", ""),
                source="knowledge_graph",
            )
        except Exception:
            return None

    def timeline(self, project: str = "", limit: int = 50) -> list[MemoryEntry]:
        return self.search(project or "", limit=limit)

    def health(self) -> ProviderHealth:
        try:
            kg = self._service()
            entities = kg.list_entities()
            rels = kg.list_relationships()
            return ProviderHealth(
                name=self.name,
                available=True,
                entry_count=len(entities),
                details=f"{len(entities)} entities, {len(rels)} relationships",
            )
        except Exception as e:
            return ProviderHealth(name=self.name, available=False, details=str(e))

    def relationships(self, entity: str = "", limit: int = 20) -> list[dict]:
        try:
            kg = self._service()
            if entity:
                ent = kg.find_entity(entity)
                if ent:
                    return kg.list_relationships(ent["id"])[:limit]
            return kg.list_relationships()[:limit]
        except Exception:
            return []
