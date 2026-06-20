"""Project Reconciler — Phase 15A+.

Reconciles Brain63 reference data, SILVIA inventory, orders, project
requirements, and engineering memory into a single operational truth
for any project.

Source priority (highest → lowest):
  1. Explicit user statement (chat updates)
  2. SILVIA inventory (hw_inventory)
  3. SILVIA orders (hw_orders)
  4. Project requirements (hw_project_parts)
  5. Project memory (project_memories)
  6. Brain63 documents (read-only reference)

Brain63 informs but never overrides operational data.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

_ITEM_STATES = frozenset({
    "required", "missing", "owned", "ordered", "received", "blocked", "optional",
})
_ITEM_SOURCES = frozenset({
    "inventory", "order", "brain63", "user", "bom", "memory", "reconciler",
})


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _normalize(name: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for matching."""
    s = re.sub(r"[^a-z0-9\s]", "", name.lower())
    return re.sub(r"\s+", " ", s).strip()


class ProjectReconciler:
    """Reconciles all data sources into per-project item state."""

    def __init__(self) -> None:
        self._init_tables()

    def _init_tables(self) -> None:
        with _conn() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS project_item_state (
                    id              TEXT PRIMARY KEY,
                    project_id      TEXT NOT NULL,
                    item_name       TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    state           TEXT NOT NULL DEFAULT 'required',
                    source          TEXT NOT NULL DEFAULT 'reconciler',
                    last_updated    TEXT NOT NULL,
                    notes           TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_pis_project ON project_item_state(project_id);
                CREATE INDEX IF NOT EXISTS idx_pis_norm    ON project_item_state(normalized_name);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_pis_proj_norm
                    ON project_item_state(project_id, normalized_name);
            """)

    def set_item_state(
        self,
        project_id: str,
        item_name: str,
        state: str,
        source: str = "user",
        notes: str = "",
    ) -> dict:
        """Set the operational state of an item for a project."""
        if state not in _ITEM_STATES:
            state = "required"
        norm = _normalize(item_name)
        now = _now()
        with _conn() as db:
            existing = db.execute(
                "SELECT id FROM project_item_state WHERE project_id=? AND normalized_name=?",
                (project_id, norm),
            ).fetchone()
            if existing:
                db.execute(
                    "UPDATE project_item_state SET state=?, source=?, notes=?, last_updated=?, item_name=? WHERE id=?",
                    (state, source, notes, now, item_name, existing["id"]),
                )
                return {"id": existing["id"], "item_name": item_name, "state": state, "updated": True}
            iid = f"pis_{uuid.uuid4().hex[:8]}"
            db.execute(
                """INSERT INTO project_item_state
                   (id, project_id, item_name, normalized_name, state, source, last_updated, notes)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (iid, project_id, item_name, norm, state, source, now, notes),
            )
            return {"id": iid, "item_name": item_name, "state": state, "updated": False}

    def get_item_state(self, project_id: str, item_name: str) -> Optional[dict]:
        norm = _normalize(item_name)
        with _conn() as db:
            row = db.execute(
                "SELECT * FROM project_item_state WHERE project_id=? AND normalized_name=?",
                (project_id, norm),
            ).fetchone()
        return dict(row) if row else None

    def get_project_items(self, project_id: str) -> list[dict]:
        with _conn() as db:
            rows = db.execute(
                "SELECT * FROM project_item_state WHERE project_id=? ORDER BY state, item_name",
                (project_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def reconcile_project(self, project_name: str) -> dict:
        """Build a fully reconciled item state for a project.

        Merges data from: Brain63 roadmap/status, hw_inventory, hw_orders,
        hw_project_parts, project_item_state (user overrides), and project_memory.

        Returns categorized items with stale-reference detection.
        """
        from backend.app.services.project_intelligence import ProjectIntelligence
        pi = ProjectIntelligence()
        meta = pi.find_project_meta(project_name)
        if not meta:
            return {"found": False, "project": project_name, "error": f"Project '{project_name}' not found."}

        name = meta["name"]
        hw_proj = meta.get("hw_project")
        project_id = (hw_proj or {}).get("id", name.lower().replace(" ", "-"))

        items: dict[str, dict] = {}

        # 1. Brain63 reference items (lowest priority)
        b63_items = self._brain63_items(name, meta.get("brain63_key"))
        for item in b63_items:
            norm = _normalize(item["name"])
            items[norm] = {
                "name": item["name"],
                "state": "owned" if item.get("checked") else "required",
                "source": "brain63",
                "brain63_checked": item.get("checked", False),
                "phase": item.get("phase", ""),
                "notes": "",
                "stale": False,
            }

        # 2. Project requirements from hw_project_parts (overrides Brain63)
        if hw_proj:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()
            parts = hs.get_project_parts(hw_proj["id"])
            for part in parts:
                norm = _normalize(part["name"])
                stock = int(part.get("stock_qty", 0) or 0)
                needed = int(part.get("quantity_required", 1) or 1)
                state = "owned" if stock >= needed else "missing"
                entry = items.get(norm, {"name": part["name"], "brain63_checked": False, "phase": "", "stale": False})
                entry.update({
                    "name": part["name"],
                    "state": state,
                    "source": "inventory",
                    "inventory_qty": stock,
                    "required_qty": needed,
                    "notes": part.get("notes", ""),
                })
                # Stale detection: Brain63 says needed but inventory says owned
                if entry.get("brain63_checked") is False and state == "owned":
                    entry["stale"] = True
                    entry["stale_note"] = f"Brain63 lists as needed, but inventory shows {stock} in stock."
                items[norm] = entry

        # 3. Inventory fuzzy scan (catch items owned but not in project_parts)
        self._scan_inventory_for_project(name, items)

        # 4. Orders (items in transit)
        self._scan_orders(items)

        # 5. User overrides from project_item_state (highest priority)
        overrides = self.get_project_items(project_id)
        for ov in overrides:
            norm = ov["normalized_name"]
            entry = items.get(norm, {"name": ov["item_name"], "brain63_checked": False, "phase": "", "stale": False})
            entry.update({
                "name": ov["item_name"],
                "state": ov["state"],
                "source": ov["source"],
                "notes": ov.get("notes", ""),
            })
            if entry.get("brain63_checked") is False and ov["state"] in ("owned", "received"):
                entry["stale"] = True
                entry["stale_note"] = f"Brain63 lists as needed, but user confirmed as {ov['state']}."
            items[norm] = entry

        # Categorize
        buy_now = []
        buy_soon = []
        optional = []
        already_owned = []
        already_ordered = []
        stale_entries = []

        for norm, item in sorted(items.items(), key=lambda x: x[1]["name"]):
            if item["state"] in ("owned", "received"):
                already_owned.append(item)
                if item.get("stale"):
                    stale_entries.append(item)
            elif item["state"] == "ordered":
                already_ordered.append(item)
            elif item["state"] == "optional":
                optional.append(item)
            elif item["state"] == "blocked":
                buy_now.append(item)
            elif item["state"] in ("required", "missing"):
                phase = item.get("phase", "")
                if "priority" in phase.lower() or "core" in phase.lower() or not phase:
                    buy_now.append(item)
                else:
                    buy_soon.append(item)

        # Build source trace — which subsystems contributed data
        sources_used = ["project_registry"]
        if b63_items:
            sources_used.append("brain63")
        if hw_proj:
            sources_used.append("inventory")
            sources_used.append("requirements")
        if any(i.get("source") == "order" for i in items.values()):
            sources_used.append("orders")
        if overrides:
            sources_used.append("user_overrides")
        try:
            from backend.app.services.knowledge_graph import get_graph
            kg = get_graph()
            if kg.find_entity_exact(name, type="project"):
                sources_used.append("knowledge_graph")
        except Exception:
            pass
        try:
            from backend.app.services.project_memory import get_memory
            if get_memory().get_project_memories(name, limit=1):
                sources_used.append("memory")
        except Exception:
            pass

        return {
            "found": True,
            "project": name,
            "project_id": project_id,
            "handler": "DigitalTwinProjectPipeline",
            "sources_used": sources_used,
            "buy_now": buy_now,
            "buy_soon": buy_soon,
            "optional": optional,
            "already_owned": already_owned,
            "already_ordered": already_ordered,
            "stale_entries": stale_entries,
            "total_items": len(items),
            "summary": self._build_summary(buy_now, buy_soon, already_owned, already_ordered, stale_entries),
        }

    def mark_acquired(
        self,
        project_name: str,
        item_names: list[str],
        state: str = "owned",
    ) -> dict:
        """Mark one or more items as owned/received/ordered for a project."""
        from backend.app.services.project_intelligence import ProjectIntelligence
        pi = ProjectIntelligence()
        meta = pi.find_project_meta(project_name)
        if not meta:
            return {"ok": False, "error": f"Project '{project_name}' not found."}

        name = meta["name"]
        hw_proj = meta.get("hw_project")
        project_id = (hw_proj or {}).get("id", name.lower().replace(" ", "-"))
        results = []

        for item_name in item_names:
            item_name = item_name.strip()
            if not item_name:
                continue

            r = self.set_item_state(project_id, item_name, state, source="user")

            # Also update inventory if we can find a matching part
            if state in ("owned", "received") and hw_proj:
                self._update_inventory_if_found(item_name)

            # Record in project memory
            self._record_memory(name, item_name, state)

            # Update KG
            self._update_kg(name, item_name, state)

            results.append(r)

        return {
            "ok": True,
            "project": name,
            "updated": results,
            "summary": f"Marked {len(results)} item(s) as {state} for {name}.",
        }

    # ── Brain63 extraction ───────────────────────────────────────────────────

    def _brain63_items(self, project_name: str, brain63_key: str | None) -> list[dict]:
        """Extract items from Brain63 roadmap/status/overview files."""
        items = []
        try:
            from backend.config import BRAIN63_VAULT_PATH
            vault = Path(BRAIN63_VAULT_PATH)
            if not vault.exists():
                return items

            key = brain63_key or project_name
            for md_path in vault.glob(f"**/{key}/*.md"):
                if md_path.name.lower() not in ("roadmap.md", "status.md", "overview.md"):
                    continue
                items.extend(self._extract_checklist_items(md_path))
            # Also try case-insensitive folder match
            if not items:
                for md_path in vault.glob("**/*.md"):
                    if project_name.lower() in md_path.parent.name.lower():
                        if md_path.name.lower() in ("roadmap.md", "status.md", "overview.md"):
                            items.extend(self._extract_checklist_items(md_path))
        except Exception:
            pass
        return items

    def _extract_checklist_items(self, path: Path) -> list[dict]:
        """Extract hardware acquisition items from Brain63 roadmap checklists.

        Only extracts items that start with acquisition verbs (Acquire, Buy,
        Order, Get, Install) — task items like "Configure", "Test", "Design"
        are excluded since they're not procurable parts.
        """
        items = []
        current_phase = ""
        # Only match checklist items that begin with an acquisition verb
        acquire_re = re.compile(
            r"^-\s+\[(?P<check>[xX ])\]\s+"
            r"(?P<verb>Acquire|Buy|Order|Get)\s+"
            r"(?:and\s+(?:install|set\s*up|configure)\s+)?(?P<name>.+)$",
            re.I,
        )
        phase_re = re.compile(r"^##\s+(?P<phase>.+)$")

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return items

        for line in text.split("\n"):
            pm = phase_re.match(line.strip())
            if pm:
                current_phase = pm.group("phase").strip()
                continue
            m = acquire_re.match(line.strip())
            if m:
                name = m.group("name").strip()
                name = re.sub(r"\s*\(.*?\)\s*$", "", name)
                name = re.sub(r"\s*—.*$", "", name)
                name = re.sub(r"\s*[-–][-–]\s*.*$", "", name)
                name = name.strip(" *_`")
                if len(name) < 3 or len(name) > 120:
                    continue
                items.append({
                    "name": name,
                    "checked": m.group("check").strip().lower() == "x",
                    "phase": current_phase,
                    "source_file": path.name,
                })
        return items

    # ── Inventory/order scanning ─────────────────────────────────────────────

    def _scan_inventory_for_project(self, project_name: str, items: dict) -> None:
        """Check if any existing inventory items match unresolved items."""
        try:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()
            with _conn() as db:
                all_inv = db.execute("SELECT id, name, quantity, status FROM hw_inventory WHERE quantity > 0").fetchall()
            for inv in all_inv:
                inv_norm = _normalize(inv["name"])
                if inv_norm in items and items[inv_norm]["state"] in ("required", "missing"):
                    items[inv_norm]["state"] = "owned"
                    items[inv_norm]["source"] = "inventory"
                    items[inv_norm]["inventory_qty"] = inv["quantity"]
                    if not items[inv_norm].get("brain63_checked", True):
                        items[inv_norm]["stale"] = True
                        items[inv_norm]["stale_note"] = f"Brain63 lists as needed, but inventory shows {inv['quantity']} in stock."
        except Exception:
            pass

    def _scan_orders(self, items: dict) -> None:
        """Mark items as ordered if there's a matching active order."""
        try:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()
            orders = hs.list_orders()
            active_orders = [o for o in orders if o.get("status") not in ("delivered", "cancelled")]
            for order in active_orders:
                order_norm = _normalize(order.get("part_name", ""))
                if order_norm in items and items[order_norm]["state"] in ("required", "missing"):
                    items[order_norm]["state"] = "ordered"
                    items[order_norm]["source"] = "order"
                    items[order_norm]["notes"] = f"Order {order.get('id', '')}: {order.get('status', '')}"
        except Exception:
            pass

    # ── Side effects ─────────────────────────────────────────────────────────

    def _update_inventory_if_found(self, item_name: str) -> None:
        """If the item exists in inventory with qty 0, bump it to 1."""
        try:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()
            part = hs.find_part(item_name)
            if part and int(part.get("quantity", 0) or 0) == 0:
                hs.update_part(part["id"], quantity=1, status="in-stock")
        except Exception:
            pass

    def _record_memory(self, project_name: str, item_name: str, state: str) -> None:
        try:
            from backend.app.services.project_memory import get_memory
            pm = get_memory()
            pm.record(
                project=project_name,
                type="milestone" if state in ("owned", "received") else "decision",
                title=f"{item_name} marked as {state}",
                summary=f"User confirmed: {item_name} is now {state} for {project_name}.",
                source="user",
            )
        except Exception:
            pass

    def _update_kg(self, project_name: str, item_name: str, state: str) -> None:
        try:
            from backend.app.services.knowledge_graph import get_graph
            kg = get_graph()
            comp_id = kg.upsert_entity("component", item_name)
            proj_ent = kg.find_entity_exact(project_name, type="project")
            if proj_ent:
                rel = "has" if state in ("owned", "received") else "needs"
                kg.add_relationship(proj_ent["id"], comp_id, rel)
        except Exception:
            pass

    # ── Summary ──────────────────────────────────────────────────────────────

    def _build_summary(self, buy_now, buy_soon, owned, ordered, stale) -> str:
        parts = []
        if buy_now:
            parts.append(f"{len(buy_now)} to buy now")
        if buy_soon:
            parts.append(f"{len(buy_soon)} to buy soon")
        if owned:
            parts.append(f"{len(owned)} already owned")
        if ordered:
            parts.append(f"{len(ordered)} on order")
        if stale:
            parts.append(f"{len(stale)} stale Brain63 entries")
        return ", ".join(parts) if parts else "No items found."


_instance: Optional[ProjectReconciler] = None


def get_reconciler() -> ProjectReconciler:
    global _instance
    if _instance is None:
        _instance = ProjectReconciler()
    return _instance
