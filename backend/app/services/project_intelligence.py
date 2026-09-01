"""Project Intelligence — aggregates data from all sources to generate project briefings.

Phase 14A: Knowledge Graph + cross-domain reasoning.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

_DONE_STATUSES = frozenset({"completed", "archived", "complete", "abandoned"})


def _hw_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


class ProjectIntelligence:
    """Aggregates cross-domain project data into structured intelligence reports."""

    # ── Project lookup ────────────────────────────────────────────────────────

    def find_project_meta(self, name: str) -> Optional[dict]:
        """Look up project across both project_service (projects) and hardware_service (hw_projects).

        Returns merged meta dict or None.
        """
        from backend.app.services.project_service import ProjectService
        from backend.app.services.hardware_service import HardwareService

        ps = ProjectService()
        hs = HardwareService()

        # Search project_service (tags, brain63_key)
        proj = ps.find_by_name(name)
        hw_proj = hs.find_project(name)

        if not proj and not hw_proj:
            return None

        base_name = (proj.name if proj else None) or (hw_proj["name"] if hw_proj else name)
        base_status = (proj.status if proj else None) or (hw_proj.get("status") if hw_proj else "unknown")
        base_priority = (proj.priority if proj else None) or (hw_proj.get("priority") if hw_proj else "normal")
        brain63_key = (proj.brain63_key if proj else None)
        notes = (proj.notes if proj else None) or (hw_proj.get("notes") if hw_proj else "")
        tags = list(proj.tags) if proj and proj.tags else []

        return {
            "name": base_name,
            "status": base_status,
            "priority": base_priority,
            "brain63_key": brain63_key,
            "notes": notes,
            "tags": tags,
            "hw_project": hw_proj,
        }

    # ── Briefing ──────────────────────────────────────────────────────────────

    def get_briefing(self, project_name: str) -> dict:
        """Full project intelligence report aggregating all sources."""
        meta = self.find_project_meta(project_name)
        if not meta:
            return {
                "found": False,
                "project": project_name,
                "error": f"No project found matching '{project_name}'.",
            }

        name = meta["name"]
        hw_proj = meta.get("hw_project")

        # 1. Build readiness from hardware
        readiness_pct = 0
        build_status = "no_data"
        parts_total = 0
        parts_available = 0
        missing_parts: list[dict] = []
        all_parts: list[dict] = []

        if hw_proj:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()
            readiness = hs.get_build_readiness(hw_proj["id"])
            if readiness:
                readiness_pct = readiness.get("readiness_pct", 0)
                build_status = readiness.get("status", "no_data")
                all_parts = readiness.get("required_parts", [])
                missing_parts = readiness.get("missing", [])
                parts_total = readiness.get("total_required", 0)
                parts_available = readiness.get("fulfilled_required", 0)

        # 2. Pending orders relevant to missing parts
        pending_orders: list[dict] = []
        if missing_parts:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()
            all_orders = hs.list_orders()
            active_orders = [o for o in all_orders if o.get("status") not in ("delivered", "cancelled")]
            missing_names_lower = {p["name"].lower() for p in missing_parts}
            for order in active_orders:
                order_name_lower = order.get("part_name", "").lower()
                if any(mn in order_name_lower or order_name_lower in mn for mn in missing_names_lower):
                    pending_orders.append(order)

        # 3. Tasks from task_service
        open_tasks: list[dict] = []
        try:
            with _hw_conn() as db:
                rows = db.execute(
                    "SELECT id, title, status, priority FROM tasks WHERE lower(project) LIKE lower(?) AND status NOT IN ('done','completed','cancelled') LIMIT 10",
                    (f"%{name.lower()}%",),
                ).fetchall()
                open_tasks = [dict(r) for r in rows]
        except Exception:
            open_tasks = []

        # 4. Brain63 context
        brain63_context: Optional[str] = None
        brain63_sources: list[str] = []
        try:
            from backend.app.services.brain63_service import Brain63Service
            b63 = Brain63Service()
            b63_key = meta.get("brain63_key") or name
            chunks = b63.search(name, entity_hint=b63_key, query_type="status", top_k=4)
            if chunks:
                answer = b63.answer_status(b63_key, chunks)
                if answer:
                    brain63_context = answer.text[:400]
                    brain63_sources = answer.sources[:3]
                elif chunks[0].content:
                    brain63_context = chunks[0].content[:300]
                    brain63_sources = [chunks[0].file_path]
        except Exception:
            brain63_context = None

        # 5. Knowledge graph — related nodes and dependencies
        related_nodes: list[dict] = []
        dependencies: list[dict] = []
        try:
            from backend.app.services.knowledge_graph import get_graph
            kg = get_graph()
            ent = kg.find_entity_exact(name, type="project")
            if ent:
                outgoing = kg.get_outgoing(ent["id"])
                for edge in outgoing:
                    if edge["target_type"] == "node" or edge["rel_type"] == "hosted_on":
                        related_nodes.append({"name": edge["target_name"], "rel": edge["rel_type"]})
                    elif edge["rel_type"] in ("depends_on", "requires", "blocked_by"):
                        dependencies.append({
                            "name": edge["target_name"],
                            "type": edge["target_type"],
                            "rel": edge["rel_type"],
                        })
        except Exception:
            pass

        # 6. Build blockers list
        blockers = self._build_blockers(meta, missing_parts, dependencies)

        # 7. Recommended action
        recommended_action = self._generate_recommended_action(
            build_status=build_status,
            missing_parts=missing_parts,
            pending_orders=pending_orders,
            status=meta["status"],
        )

        # Register project in knowledge graph (auto-populate)
        try:
            from backend.app.services.knowledge_graph import get_graph
            kg = get_graph()
            kg.upsert_entity("project", name, external_id=hw_proj["id"] if hw_proj else None)
        except Exception:
            pass

        # 7. Engineering Memory — recent decisions, lessons, milestones, risks
        recent_decisions: list[dict] = []
        recent_lessons: list[dict] = []
        recent_milestones: list[dict] = []
        known_risks: list[dict] = []
        recent_failures: list[dict] = []
        try:
            from backend.app.services.project_memory import get_memory
            pm = get_memory()
            recent_decisions  = pm.get_project_memories(name, type="decision",   limit=3)
            recent_lessons    = pm.get_project_memories(name, type="lesson",     limit=3)
            recent_milestones = pm.get_project_memories(name, type="milestone",  limit=3)
            known_risks       = pm.get_project_memories(name, type="risk",       limit=3)
            recent_failures   = pm.get_project_memories(name, type="failure",    limit=3)
        except Exception:
            pass

        return {
            "found": True,
            "project": name,
            "status": meta["status"],
            "priority": meta["priority"],
            "notes": meta.get("notes") or "",
            "brain63_key": meta.get("brain63_key"),
            "readiness_pct": readiness_pct,
            "build_status": build_status,
            "parts": {
                "total": parts_total,
                "available": parts_available,
                "missing": missing_parts,
                "all": all_parts,
            },
            "orders": pending_orders,
            "tasks": {"open": len(open_tasks), "items": open_tasks},
            "brain63_context": brain63_context,
            "brain63_sources": brain63_sources,
            "related_nodes": related_nodes,
            "dependencies": dependencies,
            "blockers": blockers,
            "recommended_action": recommended_action,
            "memory": {
                "decisions":  recent_decisions,
                "lessons":    recent_lessons,
                "milestones": recent_milestones,
                "risks":      known_risks,
                "failures":   recent_failures,
            },
        }

    # ── Blockers ──────────────────────────────────────────────────────────────

    def get_blockers(self, project_name: str) -> list[dict]:
        meta = self.find_project_meta(project_name)
        if not meta:
            return []

        blockers = []
        hw_proj = meta.get("hw_project")

        if hw_proj:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()
            readiness = hs.get_build_readiness(hw_proj["id"])
            if readiness:
                for p in readiness.get("missing", []):
                    blockers.append({
                        "type": "missing_part",
                        "description": f"Missing part: {p['name']} (need {p['quantity_required']}, have {p.get('available_qty', 0)})",
                        "severity": "high",
                    })

        if meta["status"] == "blocked":
            blockers.append({
                "type": "status",
                "description": f"Project status is 'blocked'",
                "severity": "high",
            })

        try:
            from backend.app.services.knowledge_graph import get_graph
            kg = get_graph()
            ent = kg.find_entity_exact(meta["name"], type="project")
            if ent:
                for edge in kg.get_outgoing(ent["id"]):
                    if edge["rel_type"] == "blocked_by":
                        blockers.append({
                            "type": "kg_edge",
                            "description": f"Blocked by: {edge['target_name']}",
                            "severity": "high",
                        })
        except Exception:
            pass

        return blockers

    def _build_blockers(self, meta: dict, missing_parts: list, dependencies: list) -> list[dict]:
        blockers = []
        for p in missing_parts:
            blockers.append({
                "type": "missing_part",
                "description": f"{p['name']} — need {p['quantity_required']}, have {p.get('available_qty', 0)}",
                "severity": "high",
            })
        if meta["status"] == "blocked":
            blockers.append({"type": "status", "description": "Project marked as blocked", "severity": "high"})
        for dep in dependencies:
            if dep["rel"] == "blocked_by":
                blockers.append({"type": "kg_edge", "description": f"Blocked by: {dep['name']}", "severity": "high"})
        return blockers

    # ── Readiness ─────────────────────────────────────────────────────────────

    def get_readiness(self, project_name: str) -> dict:
        meta = self.find_project_meta(project_name)
        if not meta:
            return {"found": False, "project": project_name}
        hw_proj = meta.get("hw_project")
        if not hw_proj:
            return {
                "found": True, "project": meta["name"],
                "readiness_pct": 0, "build_status": "no_hw_data",
                "message": "No hardware project linked. Add parts to the Hardware Board.",
            }
        from backend.app.services.hardware_service import HardwareService
        hs = HardwareService()
        readiness = hs.get_build_readiness(hw_proj["id"])
        if not readiness:
            return {"found": True, "project": meta["name"], "readiness_pct": 0, "build_status": "unknown"}
        return {
            "found": True,
            "project": meta["name"],
            "readiness_pct": readiness["readiness_pct"],
            "build_status": readiness["status"],
            "total_required": readiness["total_required"],
            "fulfilled_required": readiness["fulfilled_required"],
            "missing": readiness["missing"],
            "available": readiness["available"],
        }

    # ── Dependencies ──────────────────────────────────────────────────────────

    def get_dependencies(self, project_name: str) -> dict:
        meta = self.find_project_meta(project_name)
        if not meta:
            return {"found": False, "project": project_name}

        name = meta["name"]
        hw_deps: list[dict] = []
        kg_deps: list[dict] = []

        # From hw_project_parts (hardware dependencies)
        hw_proj = meta.get("hw_project")
        if hw_proj:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()
            parts = hs.get_project_parts(hw_proj["id"])
            for p in parts:
                hw_deps.append({
                    "name": p.get("name", ""),
                    "type": "component",
                    "rel": "requires" if p.get("is_required", 1) else "uses",
                    "status": "available" if (p.get("stock_qty", 0) or 0) >= (p.get("quantity_required", 1) or 1) else "missing",
                })

        # From knowledge graph
        try:
            from backend.app.services.knowledge_graph import get_graph
            kg = get_graph()
            ent = kg.find_entity_exact(name, type="project")
            if ent:
                for edge in kg.get_outgoing(ent["id"]):
                    if edge["rel_type"] in ("depends_on", "requires", "uses", "blocked_by"):
                        kg_deps.append({
                            "name": edge["target_name"],
                            "type": edge["target_type"],
                            "rel": edge["rel_type"],
                        })
        except Exception:
            pass

        return {
            "found": True,
            "project": name,
            "hw_dependencies": hw_deps,
            "kg_dependencies": kg_deps,
            "total": len(hw_deps) + len(kg_deps),
        }

    # ── Cross-project ─────────────────────────────────────────────────────────

    def get_projects_using(self, component_name: str) -> list[dict]:
        """Which projects use a given component (by inventory name)?"""
        results = []
        seen: set[str] = set()

        # Search hardware tables
        try:
            with _hw_conn() as db:
                rows = db.execute("""
                    SELECT DISTINCT p.id, p.name, p.status, p.priority
                    FROM hw_projects p
                    JOIN hw_project_parts pp ON pp.project_id = p.id
                    JOIN hw_inventory i ON i.id = pp.part_id
                    WHERE lower(i.name) LIKE lower(?)
                       OR lower(COALESCE(i.normalized_name, '')) LIKE lower(?)
                    ORDER BY p.priority DESC, p.name
                """, (f"%{component_name}%", f"%{component_name}%")).fetchall()
                for r in rows:
                    key = r["id"]
                    if key not in seen:
                        seen.add(key)
                        results.append({
                            "name": r["name"],
                            "status": r["status"],
                            "priority": r["priority"],
                            "source": "inventory",
                        })
        except Exception:
            pass

        # Also check knowledge graph
        try:
            from backend.app.services.knowledge_graph import get_graph
            kg = get_graph()
            kg_hits = kg.find_projects_using_component(component_name)
            for h in kg_hits:
                if h["name"] not in {r["name"] for r in results}:
                    results.append({"name": h["name"], "status": "unknown", "priority": "normal", "source": "knowledge_graph"})
        except Exception:
            pass

        return results

    def get_blocked_projects(self) -> list[dict]:
        """All projects that are blocked (by status or missing parts)."""
        from backend.app.services.hardware_service import HardwareService
        hs = HardwareService()
        blocked_hw = hs.get_blocked_projects()
        results = []
        seen: set[str] = set()
        for b in blocked_hw:
            p = b.get("project", {})
            n = p.get("name", "")
            if n not in seen:
                seen.add(n)
                results.append({
                    "name": n,
                    "status": p.get("status"),
                    "priority": p.get("priority"),
                    "reason": b.get("reason"),
                    "blocking_parts": [pp.get("name") for pp in (b.get("blocking_parts") or [])],
                })
        return results

    def get_startable_projects(self) -> list[dict]:
        """Projects with readiness >= 80% not in a done state."""
        from backend.app.services.hardware_service import HardwareService
        hs = HardwareService()
        all_readiness = hs.get_all_readiness()
        startable = []
        for r in all_readiness:
            if r.get("readiness_pct", 0) >= 80 and r.get("project_status") not in _DONE_STATUSES:
                startable.append({
                    "name": r["project_name"],
                    "status": r["project_status"],
                    "priority": r.get("priority", "normal"),
                    "readiness_pct": r["readiness_pct"],
                    "missing_count": len(r.get("missing", [])),
                })
        return startable

    def get_projects_needing_orders(self) -> list[dict]:
        """Projects with missing parts that have no active order pending for those parts."""
        from backend.app.services.hardware_service import HardwareService
        hs = HardwareService()
        active_orders = hs.list_orders()
        ordered_names_lower = {o.get("part_name", "").lower() for o in active_orders
                               if o.get("status") not in ("delivered", "cancelled")}
        missing_all = hs.get_all_missing_parts()
        results = []
        for p in missing_all:
            unordered = []
            for part in p.get("missing", []):
                part_lower = part["name"].lower()
                if not any(part_lower in n or n in part_lower for n in ordered_names_lower):
                    unordered.append(part["name"])
            if unordered:
                results.append({
                    "name": p["project_name"],
                    "status": p["project_status"],
                    "priority": p["priority"],
                    "unordered_parts": unordered,
                })
        return results

    # ── Recommendation ────────────────────────────────────────────────────────

    def _generate_recommended_action(
        self,
        build_status: str,
        missing_parts: list,
        pending_orders: list,
        status: str,
    ) -> str:
        if build_status == "ready":
            return "All required parts available. Ready to build."
        if status == "blocked":
            return "Resolve blocking issues before proceeding."
        if missing_parts and not pending_orders:
            names = ", ".join(p["name"] for p in missing_parts[:3])
            extra = f" (+{len(missing_parts)-3} more)" if len(missing_parts) > 3 else ""
            return f"Order {len(missing_parts)} missing part(s): {names}{extra}."
        if missing_parts and pending_orders:
            return f"Wait for {len(pending_orders)} in-transit order(s) to arrive."
        if build_status == "no_data" or build_status == "no_hw_data":
            return "Add parts to the Hardware Board to track readiness."
        return "Continue current work phase."
