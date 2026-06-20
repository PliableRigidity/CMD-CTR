"""Knowledge Graph — entity relationship store for SILVIA Phase 14A."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

ENTITY_TYPES = frozenset({
    "project", "component", "node", "service", "task",
    "document", "order", "capability", "roadmap",
})

RELATIONSHIP_TYPES = frozenset({
    "uses", "depends_on", "hosted_on", "blocked_by", "related_to",
    "requires", "contains", "implements", "ordered_by", "assigned_to",
    "tracks", "supports",
})


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class KnowledgeGraph:
    def __init__(self) -> None:
        self._init_tables()

    def _init_tables(self) -> None:
        with _conn() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS kg_entities (
                    id          TEXT PRIMARY KEY,
                    type        TEXT NOT NULL,
                    name        TEXT NOT NULL,
                    external_id TEXT,
                    metadata    TEXT NOT NULL DEFAULT '{}',
                    created_at  TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_kg_ent_type ON kg_entities (type);
                CREATE INDEX IF NOT EXISTS idx_kg_ent_name ON kg_entities (name COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS idx_kg_ent_ext  ON kg_entities (external_id);

                CREATE TABLE IF NOT EXISTS kg_relationships (
                    id          TEXT PRIMARY KEY,
                    from_id     TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
                    to_id       TEXT NOT NULL REFERENCES kg_entities(id) ON DELETE CASCADE,
                    rel_type    TEXT NOT NULL,
                    weight      REAL NOT NULL DEFAULT 1.0,
                    metadata    TEXT NOT NULL DEFAULT '{}',
                    created_at  TEXT NOT NULL,
                    UNIQUE(from_id, to_id, rel_type)
                );
                CREATE INDEX IF NOT EXISTS idx_kg_rel_from ON kg_relationships (from_id);
                CREATE INDEX IF NOT EXISTS idx_kg_rel_to   ON kg_relationships (to_id);
                CREATE INDEX IF NOT EXISTS idx_kg_rel_type ON kg_relationships (rel_type);
            """)

    # ── Entity CRUD ──────────────────────────────────────────────────────────

    def upsert_entity(
        self,
        type: str,
        name: str,
        external_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Return id of existing entity matching (name, type) or insert new."""
        with _conn() as db:
            row = db.execute(
                "SELECT id FROM kg_entities WHERE lower(name) = lower(?) AND type = ? LIMIT 1",
                (name, type),
            ).fetchone()
            if row:
                return row["id"]
            eid = str(uuid.uuid4())[:12]
            db.execute(
                "INSERT INTO kg_entities (id, type, name, external_id, metadata, created_at) VALUES (?,?,?,?,?,?)",
                (eid, type, name, external_id, json.dumps(metadata or {}), _now()),
            )
            return eid

    def find_entity(self, name: str, type: Optional[str] = None) -> Optional[dict]:
        """LIKE search — returns first match."""
        with _conn() as db:
            if type:
                row = db.execute(
                    "SELECT * FROM kg_entities WHERE lower(name) LIKE lower(?) AND type = ? LIMIT 1",
                    (f"%{name}%", type),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM kg_entities WHERE lower(name) LIKE lower(?) LIMIT 1",
                    (f"%{name}%",),
                ).fetchone()
            return dict(row) if row else None

    def find_entity_exact(self, name: str, type: Optional[str] = None) -> Optional[dict]:
        """Exact case-insensitive match."""
        with _conn() as db:
            if type:
                row = db.execute(
                    "SELECT * FROM kg_entities WHERE lower(name) = lower(?) AND type = ? LIMIT 1",
                    (name, type),
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM kg_entities WHERE lower(name) = lower(?) LIMIT 1",
                    (name,),
                ).fetchone()
            return dict(row) if row else None

    def get_entity(self, entity_id: str) -> Optional[dict]:
        with _conn() as db:
            row = db.execute("SELECT * FROM kg_entities WHERE id = ?", (entity_id,)).fetchone()
            return dict(row) if row else None

    def list_entities(self, type: Optional[str] = None) -> list[dict]:
        with _conn() as db:
            if type:
                rows = db.execute(
                    "SELECT * FROM kg_entities WHERE type = ? ORDER BY name COLLATE NOCASE",
                    (type,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM kg_entities ORDER BY type, name COLLATE NOCASE"
                ).fetchall()
            return [dict(r) for r in rows]

    def delete_entity(self, entity_id: str) -> bool:
        with _conn() as db:
            cur = db.execute("DELETE FROM kg_entities WHERE id = ?", (entity_id,))
            return cur.rowcount > 0

    # ── Relationship CRUD ─────────────────────────────────────────────────────

    def add_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        metadata: Optional[dict] = None,
    ) -> None:
        rid = str(uuid.uuid4())[:12]
        with _conn() as db:
            db.execute(
                """INSERT INTO kg_relationships (id, from_id, to_id, rel_type, weight, metadata, created_at)
                   VALUES (?,?,?,?,1.0,?,?)
                   ON CONFLICT(from_id, to_id, rel_type) DO NOTHING""",
                (rid, from_id, to_id, rel_type, json.dumps(metadata or {}), _now()),
            )

    def remove_relationship(self, from_id: str, to_id: str, rel_type: str) -> None:
        with _conn() as db:
            db.execute(
                "DELETE FROM kg_relationships WHERE from_id=? AND to_id=? AND rel_type=?",
                (from_id, to_id, rel_type),
            )

    def list_relationships(self, entity_id: Optional[str] = None) -> list[dict]:
        with _conn() as db:
            if entity_id:
                rows = db.execute(
                    "SELECT * FROM kg_relationships WHERE from_id=? OR to_id=? ORDER BY created_at DESC",
                    (entity_id, entity_id),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM kg_relationships ORDER BY created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    def get_outgoing(self, entity_id: str) -> list[dict]:
        """All edges leaving entity_id, enriched with target name+type."""
        with _conn() as db:
            rows = db.execute("""
                SELECT r.rel_type, r.weight, r.metadata,
                       e.id AS target_id, e.name AS target_name, e.type AS target_type
                FROM kg_relationships r
                JOIN kg_entities e ON e.id = r.to_id
                WHERE r.from_id = ?
                ORDER BY r.rel_type, e.name COLLATE NOCASE
            """, (entity_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_incoming(self, entity_id: str) -> list[dict]:
        """All edges arriving at entity_id, enriched with source name+type."""
        with _conn() as db:
            rows = db.execute("""
                SELECT r.rel_type, r.weight, r.metadata,
                       e.id AS source_id, e.name AS source_name, e.type AS source_type
                FROM kg_relationships r
                JOIN kg_entities e ON e.id = r.from_id
                WHERE r.to_id = ?
                ORDER BY r.rel_type, e.name COLLATE NOCASE
            """, (entity_id,)).fetchall()
            return [dict(r) for r in rows]

    def get_subgraph(self, entity_id: str, depth: int = 2) -> dict:
        """BFS expansion up to `depth` hops. Returns {entities, relationships}."""
        visited_entities: set[str] = set()
        visited_rels: list[dict] = []
        frontier = {entity_id}

        for _ in range(depth):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for eid in frontier:
                if eid in visited_entities:
                    continue
                visited_entities.add(eid)
                out = self.get_outgoing(eid)
                inc = self.get_incoming(eid)
                for edge in out:
                    visited_rels.append({
                        "from_id": eid, "to_id": edge["target_id"],
                        "rel_type": edge["rel_type"],
                    })
                    next_frontier.add(edge["target_id"])
                for edge in inc:
                    visited_rels.append({
                        "from_id": edge["source_id"], "to_id": eid,
                        "rel_type": edge["rel_type"],
                    })
                    next_frontier.add(edge["source_id"])
            frontier = next_frontier - visited_entities

        entities = []
        for eid in visited_entities:
            e = self.get_entity(eid)
            if e:
                entities.append(e)

        # Deduplicate relationships
        seen_rels: set[tuple] = set()
        unique_rels = []
        for r in visited_rels:
            key = (r["from_id"], r["to_id"], r["rel_type"])
            if key not in seen_rels:
                seen_rels.add(key)
                unique_rels.append(r)

        return {"entities": entities, "relationships": unique_rels}

    # ── Higher-level queries ──────────────────────────────────────────────────

    def find_projects_using_component(self, component_name: str) -> list[dict]:
        """Project entities with uses/requires edge to a component matching name."""
        with _conn() as db:
            rows = db.execute("""
                SELECT DISTINCT ep.id, ep.name, ep.type, ep.external_id
                FROM kg_entities ep
                JOIN kg_relationships r ON r.from_id = ep.id
                JOIN kg_entities ec ON ec.id = r.to_id
                WHERE ep.type = 'project'
                  AND r.rel_type IN ('uses', 'requires', 'depends_on')
                  AND lower(ec.name) LIKE lower(?)
            """, (f"%{component_name}%",)).fetchall()
            return [dict(r) for r in rows]

    def get_entity_graph_for_api(self) -> dict:
        """All entities and relationships — for the graph visualization API."""
        entities = self.list_entities()
        rels = self.list_relationships()
        return {"entities": entities, "relationships": rels}

    def get_nodes_edges(self) -> dict:
        """Return graph in {nodes, edges} format for canvas visualization."""
        entities = self.list_entities()
        rels = self.list_relationships()
        nodes = [{"id": e["id"], "label": e["name"], "type": e["type"]} for e in entities]
        edges = [{"source": r["from_id"], "target": r["to_id"], "type": r["rel_type"]} for r in rels]
        return {"nodes": nodes, "edges": edges}

    def get_project_subgraph_nodes_edges(self, project_name: str, depth: int = 2) -> dict:
        """Return project-focused subgraph in {nodes, edges} format."""
        entity = self.find_entity(project_name, "project") or self.find_entity(project_name)
        if not entity:
            return {"nodes": [], "edges": []}
        raw = self.get_subgraph(entity["id"], depth=depth)
        nodes = [{"id": e["id"], "label": e["name"], "type": e["type"]} for e in raw["entities"]]
        edges = [{"source": r["from_id"], "target": r["to_id"], "type": r["rel_type"]} for r in raw["relationships"]]
        return {"nodes": nodes, "edges": edges}

    def get_summary(self) -> dict:
        """Return entity/relationship counts for chat summary."""
        with _conn() as db:
            entity_count = db.execute("SELECT COUNT(*) FROM kg_entities").fetchone()[0]
            rel_count = db.execute("SELECT COUNT(*) FROM kg_relationships").fetchone()[0]
            type_counts = {}
            for row in db.execute("SELECT type, COUNT(*) as c FROM kg_entities GROUP BY type").fetchall():
                type_counts[row["type"]] = row["c"]
            top_connected = db.execute("""
                SELECT e.name, e.type, COUNT(*) as degree
                FROM kg_relationships r
                JOIN kg_entities e ON e.id = r.from_id OR e.id = r.to_id
                GROUP BY e.id
                ORDER BY degree DESC
                LIMIT 5
            """).fetchall()
        return {
            "entity_count": entity_count,
            "relationship_count": rel_count,
            "type_counts": type_counts,
            "top_connected": [dict(r) for r in top_connected],
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_instance: Optional[KnowledgeGraph] = None


def get_graph() -> KnowledgeGraph:
    global _instance
    if _instance is None:
        _instance = KnowledgeGraph()
    return _instance


def rebuild_from_data_sources() -> dict:
    """Populate/refresh the knowledge graph from all SILVIA data sources.

    Idempotent — safe to call multiple times. Uses upsert_entity so existing
    nodes are not duplicated; add_relationship uses ON CONFLICT DO NOTHING.
    """
    kg = get_graph()
    counts: dict = {
        "projects": 0, "components": 0, "nodes": 0,
        "services": 0, "tasks": 0, "orders": 0, "edges": 0,
    }

    try:
        with _conn() as db:
            # hw_projects → project entities
            for row in db.execute("SELECT id, name FROM hw_projects").fetchall():
                kg.upsert_entity("project", row["name"], external_id=row["id"])
                counts["projects"] += 1

            # hw_inventory → component entities
            for row in db.execute("SELECT id, name, category FROM hw_inventory").fetchall():
                kg.upsert_entity(
                    "component", row["name"], external_id=row["id"],
                    metadata={"category": row["category"] or ""},
                )
                counts["components"] += 1

            # hw_project_parts → uses edges (project → component)
            for row in db.execute("""
                SELECT hp.name AS proj_name, hi.name AS comp_name
                FROM hw_project_parts hpp
                JOIN hw_projects hp ON hp.id = hpp.project_id
                JOIN hw_inventory hi ON hi.id = hpp.part_id
            """).fetchall():
                proj_id = kg.upsert_entity("project", row["proj_name"])
                comp_id = kg.upsert_entity("component", row["comp_name"])
                kg.add_relationship(proj_id, comp_id, "uses")
                counts["edges"] += 1

            # hw_orders → order entities + ordered_by edges (order → component)
            for row in db.execute("SELECT id, part_name FROM hw_orders").fetchall():
                order_id = kg.upsert_entity(
                    "order", f"Order:{row['part_name']}", external_id=row["id"],
                )
                comp_id = kg.upsert_entity("component", row["part_name"])
                kg.add_relationship(order_id, comp_id, "ordered_by")
                counts["orders"] += 1
                counts["edges"] += 1

            # nodes → node entities
            for row in db.execute("SELECT id, name, type FROM nodes").fetchall():
                kg.upsert_entity(
                    "node", row["name"], external_id=row["id"],
                    metadata={"node_type": row["type"] or ""},
                )
                counts["nodes"] += 1

            # node_services → service entities + hosted_on edges (service → node)
            for row in db.execute("""
                SELECT ns.id, ns.name AS svc_name, n.name AS node_name
                FROM node_services ns
                JOIN nodes n ON n.id = ns.node_id
            """).fetchall():
                svc_label = f"{row['svc_name']}@{row['node_name']}"
                svc_id = kg.upsert_entity("service", svc_label, external_id=row["id"])
                node_id = kg.upsert_entity("node", row["node_name"])
                kg.add_relationship(svc_id, node_id, "hosted_on")
                counts["services"] += 1
                counts["edges"] += 1

            # tasks → task entities + tracks edges (task → project)
            for row in db.execute(
                "SELECT id, title, project FROM tasks WHERE project IS NOT NULL AND project != ''"
            ).fetchall():
                task_id = kg.upsert_entity("task", row["title"], external_id=row["id"])
                proj_id = kg.upsert_entity("project", row["project"])
                kg.add_relationship(task_id, proj_id, "tracks")
                counts["tasks"] += 1
                counts["edges"] += 1

            # projects table → project entities + related_to edges (project → Brain63 doc)
            try:
                for row in db.execute(
                    "SELECT id, name, brain63_key FROM projects "
                    "WHERE brain63_key IS NOT NULL AND brain63_key != ''"
                ).fetchall():
                    proj_id = kg.upsert_entity("project", row["name"], external_id=row["id"])
                    doc_id = kg.upsert_entity(
                        "document", row["brain63_key"], metadata={"type": "brain63"},
                    )
                    kg.add_relationship(proj_id, doc_id, "related_to")
                    counts["edges"] += 1
            except Exception:
                pass  # projects table may not exist in all deployments

    except Exception as e:
        return {"ok": False, "error": str(e), "counts": counts}

    return {"ok": True, "counts": counts}
