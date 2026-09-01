"""Relationship Expansion (Phase 3).

After the central objects are retrieved, selectively pull in a FEW relevant
neighbours — never the whole graph. Strict bounds: max depth, max nodes,
per-node fan-out, allowed relation types, and cycle prevention.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("silvia.cognition.expansion")


class RelationshipExpander:
    def __init__(self, memory_manager, *, max_depth: int = 1, max_nodes: int = 20,
                 per_node: int = 5, allowed_relations: set[str] | None = None) -> None:
        self._mm = memory_manager
        self.max_depth = max(1, max_depth)
        self.max_nodes = max_nodes
        self.per_node = per_node
        self.allowed = allowed_relations  # None = all

    def expand(self, seed_entries: list) -> list[dict]:
        """Return a bounded list of neighbour edges discovered from the seeds.

        Each item: {source, target, relation, direction, target_label}. Cycle-
        and cap-safe. Uses the provider's ``relationships`` capability only.
        """
        seeds = [e for e in seed_entries if getattr(e, "title", "")]
        visited: set[str] = set(e.title for e in seeds)
        frontier = list(seeds)
        edges: list[dict] = []
        depth = 0
        while frontier and depth < self.max_depth and len(edges) < self.max_nodes:
            next_frontier = []
            for entry in frontier:
                entity = entry.title
                if not entity:
                    continue
                try:
                    rels = self._mm.relationships(entity=entity,
                                                  limit=self.per_node) or []
                except Exception as e:
                    logger.debug("expansion relationships(%s) failed: %s", entity, e)
                    continue
                for rel in rels:
                    relation = str(rel.get("relation") or rel.get("relation_type")
                                   or rel.get("type") or "related_to")
                    if self.allowed and relation not in self.allowed:
                        continue
                    target = str(rel.get("object_id") or rel.get("target")
                                 or rel.get("title") or "")
                    target_label = str(rel.get("title") or target)
                    if not target:
                        continue
                    edges.append({
                        "source": entity, "target": target,
                        "relation": relation,
                        "direction": rel.get("direction", "out"),
                        "target_label": target_label,
                    })
                    if target_label not in visited:
                        visited.add(target_label)
                    if len(edges) >= self.max_nodes:
                        break
                if len(edges) >= self.max_nodes:
                    break
            frontier = next_frontier  # depth-1 only unless max_depth>1 wired
            depth += 1
        return edges[: self.max_nodes]
