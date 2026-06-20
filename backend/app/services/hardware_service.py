"""Hardware Operations Registry — inventory, projects, project-part links, orders.

Four tables stored in the shared cmdctr.db:
  hw_inventory       — physical parts and components
  hw_projects        — maker / robotics / electronics projects
  hw_project_parts   — many-to-many: which parts a project uses
  hw_orders          — pending/shipped/delivered orders
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import json
import re

from backend.app.services.hardware_category_classifier import (
    classify_component,
    should_apply_classification,
)

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

# Valid enum values — enforced in Python, not SQLite, so the schema stays generic.
VALID_PART_STATUSES  = {"in-stock", "low-stock", "out-of-stock", "on-order"}
VALID_ORDER_STATUSES = {"ordered", "manufacturing", "shipped", "in_transit", "delivered", "cancelled"}
VALID_PROJECT_STATUSES = {
    # 10-state model (Phase 12B)
    "planned", "researching", "designing", "ordering",
    "waiting_for_parts", "building", "testing", "blocked",
    "completed", "archived",
    # Legacy aliases (Phase 12A, kept for backwards compat)
    "active", "paused", "complete", "abandoned",
}
VALID_PRIORITIES     = {"low", "normal", "high", "critical"}

# Statuses that are "still in progress" — included in intelligence queries
_ACTIVE_STATUSES = frozenset({
    "planned", "researching", "designing", "ordering",
    "waiting_for_parts", "building", "testing", "blocked",
    "active", "paused",
})
# Statuses that mean "done" — excluded from intelligence queries
_DONE_STATUSES = frozenset({"completed", "archived", "complete", "abandoned"})

_STATUS_WEIGHT   = {
    "building": 10, "testing": 9, "waiting_for_parts": 7,
    "ordering": 6, "designing": 4, "researching": 3,
    "planned": 2, "active": 3, "paused": 1, "blocked": 1,
}
_PRIORITY_WEIGHT = {"critical": 4, "high": 3, "normal": 2, "low": 1}


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _init_db() -> None:
    c = _conn()
    try:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS hw_inventory (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                normalized_name TEXT,
                aliases       TEXT NOT NULL DEFAULT '[]',
                category      TEXT NOT NULL DEFAULT 'misc',
                subcategory   TEXT NOT NULL DEFAULT '',
                quantity      INTEGER NOT NULL DEFAULT 0,
                status        TEXT NOT NULL DEFAULT 'in-stock',
                location      TEXT NOT NULL DEFAULT '',
                manufacturer  TEXT NOT NULL DEFAULT '',
                part_number   TEXT NOT NULL DEFAULT '',
                notes         TEXT NOT NULL DEFAULT '',
                datasheet_url TEXT NOT NULL DEFAULT '',
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hw_inv_name     ON hw_inventory (name COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_hw_inv_category ON hw_inventory (category COLLATE NOCASE);

            CREATE TABLE IF NOT EXISTS hw_projects (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'active',
                description TEXT NOT NULL DEFAULT '',
                priority    TEXT NOT NULL DEFAULT 'normal',
                notes       TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hw_proj_name ON hw_projects (name COLLATE NOCASE);

            CREATE TABLE IF NOT EXISTS hw_project_parts (
                id                TEXT PRIMARY KEY,
                project_id        TEXT NOT NULL REFERENCES hw_projects(id) ON DELETE CASCADE,
                part_id           TEXT NOT NULL REFERENCES hw_inventory(id) ON DELETE CASCADE,
                quantity_required INTEGER NOT NULL DEFAULT 1,
                is_required       INTEGER NOT NULL DEFAULT 1,
                acceptable_substitutes TEXT NOT NULL DEFAULT '[]',
                source            TEXT NOT NULL DEFAULT 'manual',
                notes             TEXT NOT NULL DEFAULT '',
                created_at        TEXT NOT NULL,
                UNIQUE(project_id, part_id)
            );

            CREATE TABLE IF NOT EXISTS hw_orders (
                id          TEXT PRIMARY KEY,
                part_name   TEXT NOT NULL,
                vendor      TEXT NOT NULL DEFAULT '',
                quantity    INTEGER NOT NULL DEFAULT 1,
                status      TEXT NOT NULL DEFAULT 'ordered',
                notes       TEXT NOT NULL DEFAULT '',
                ordered_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hw_orders_status ON hw_orders (status);

            CREATE TABLE IF NOT EXISTS hw_imports (
                id             TEXT PRIMARY KEY,
                source_path    TEXT NOT NULL,
                source_type    TEXT NOT NULL,
                project_id     TEXT,
                project_name   TEXT NOT NULL DEFAULT '',
                rows_total     INTEGER NOT NULL DEFAULT 0,
                imported_count INTEGER NOT NULL DEFAULT 0,
                created_parts  INTEGER NOT NULL DEFAULT 0,
                updated_parts  INTEGER NOT NULL DEFAULT 0,
                linked_parts   INTEGER NOT NULL DEFAULT 0,
                errors_json    TEXT NOT NULL DEFAULT '[]',
                created_at     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hw_imports_created ON hw_imports (created_at);

            CREATE TABLE IF NOT EXISTS hw_import_items (
                id             TEXT PRIMARY KEY,
                import_id      TEXT NOT NULL REFERENCES hw_imports(id) ON DELETE CASCADE,
                part_id        TEXT REFERENCES hw_inventory(id) ON DELETE SET NULL,
                raw_name       TEXT NOT NULL DEFAULT '',
                quantity       INTEGER NOT NULL DEFAULT 0,
                value          TEXT NOT NULL DEFAULT '',
                footprint      TEXT NOT NULL DEFAULT '',
                manufacturer   TEXT NOT NULL DEFAULT '',
                part_number    TEXT NOT NULL DEFAULT '',
                action         TEXT NOT NULL DEFAULT '',
                raw_json       TEXT NOT NULL DEFAULT '{}',
                created_at     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hw_import_items_import ON hw_import_items (import_id);
        """)
        _migrate_inventory(c)
        c.execute("CREATE INDEX IF NOT EXISTS idx_hw_inv_norm ON hw_inventory (normalized_name)")
        c.commit()
    finally:
        c.close()
    # Phase 12B migration: add is_required to existing hw_project_parts rows
    c = _conn()
    try:
        c.execute(
            "ALTER TABLE hw_project_parts ADD COLUMN is_required INTEGER NOT NULL DEFAULT 1"
        )
        c.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    finally:
        c.close()
    c = _conn()
    try:
        c.execute("ALTER TABLE hw_project_parts ADD COLUMN acceptable_substitutes TEXT NOT NULL DEFAULT '[]'")
        c.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        c.close()
    c = _conn()
    try:
        c.execute("ALTER TABLE hw_project_parts ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
        c.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        c.close()
    # Phase 12E migrations
    for stmt in [
        "ALTER TABLE hw_inventory ADD COLUMN reorder_threshold INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE hw_orders ADD COLUMN expected_delivery TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE hw_orders ADD COLUMN date_received TEXT NOT NULL DEFAULT ''",
    ]:
        c = _conn()
        try:
            c.execute(stmt)
            c.commit()
        except sqlite3.OperationalError:
            pass
        finally:
            c.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row) -> dict:
    return dict(row) if row else {}


def _rows(rows) -> list[dict]:
    return [dict(r) for r in rows]


def normalize_component_name(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text.strip()


def _status_for_quantity(quantity: int) -> str:
    return "in-stock" if quantity > 0 else "out-of-stock"


def _merge_notes(existing: str, addition: str) -> str:
    existing = (existing or "").strip()
    addition = (addition or "").strip()
    if not addition or addition in existing:
        return existing
    return f"{existing}\n{addition}".strip()


def _resolve_part_category(
    category: str,
    name: str,
    *,
    manufacturer: str = "",
    part_number: str = "",
    notes: str = "",
) -> str:
    category_value = (category or "misc").strip().lower()
    if category_value and category_value != "misc":
        return category_value
    classification = classify_component(
        name,
        manufacturer=manufacturer,
        part_number=part_number,
        notes=notes,
    )
    if should_apply_classification(classification):
        return classification.category
    return "misc"


def _resolve_part_classification(
    category: str,
    subcategory: str,
    name: str,
    *,
    manufacturer: str = "",
    part_number: str = "",
    notes: str = "",
) -> tuple[str, str]:
    category_value = _resolve_part_category(
        category,
        name,
        manufacturer=manufacturer,
        part_number=part_number,
        notes=notes,
    )
    subcategory_value = (subcategory or "").strip().lower()
    if category_value != "misc" and not subcategory_value:
        classification = classify_component(
            name,
            manufacturer=manufacturer,
            part_number=part_number,
            notes=notes,
        )
        if classification.category == category_value and should_apply_classification(classification):
            subcategory_value = classification.subcategory
    return category_value, subcategory_value


def _migrate_inventory(c: sqlite3.Connection) -> None:
    columns = {row["name"] for row in c.execute("PRAGMA table_info(hw_inventory)").fetchall()}
    if "normalized_name" not in columns:
        c.execute("ALTER TABLE hw_inventory ADD COLUMN normalized_name TEXT")
    if "aliases" not in columns:
        c.execute("ALTER TABLE hw_inventory ADD COLUMN aliases TEXT NOT NULL DEFAULT '[]'")
    rows = c.execute("SELECT id, name FROM hw_inventory WHERE normalized_name IS NULL OR normalized_name=''").fetchall()
    for row in rows:
        c.execute(
            "UPDATE hw_inventory SET normalized_name=? WHERE id=?",
            (normalize_component_name(row["name"]), row["id"]),
        )


# ---------------------------------------------------------------------------
# HardwareService
# ---------------------------------------------------------------------------

class HardwareService:
    def __init__(self) -> None:
        _init_db()

    # ── Inventory ────────────────────────────────────────────────────────────

    def add_part(
        self,
        name: str,
        category: str = "misc",
        quantity: int = 1,
        *,
        subcategory: str = "",
        manufacturer: str = "",
        part_number: str = "",
        location: str = "",
        notes: str = "",
        datasheet_url: str = "",
        status: str = "in-stock",
    ) -> dict:
        if status not in VALID_PART_STATUSES:
            status = "in-stock"
        part_id = str(uuid.uuid4())[:8]
        now = _now()
        normalized = normalize_component_name(part_number or name)
        category_value, subcategory_value = _resolve_part_classification(
            category,
            subcategory,
            name,
            manufacturer=manufacturer,
            part_number=part_number,
            notes=notes,
        )
        c = _conn()
        try:
            c.execute(
                """INSERT INTO hw_inventory
                   (id, name, normalized_name, aliases, category, subcategory, quantity, status,
                    location, manufacturer, part_number, notes, datasheet_url,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (part_id, name.strip(), normalized, "[]", category_value, subcategory_value,
                 quantity, status, location.strip(), manufacturer.strip(),
                 part_number.strip(), notes.strip(), datasheet_url.strip(), now, now),
            )
            c.commit()
        finally:
            c.close()
        return self.get_part_by_id(part_id)

    def get_part_by_id(self, part_id: str) -> Optional[dict]:
        c = _conn()
        try:
            row = c.execute("SELECT * FROM hw_inventory WHERE id = ?", (part_id,)).fetchone()
            return _row(row) or None
        finally:
            c.close()

    def find_part(self, query: str) -> Optional[dict]:
        """Find a part by exact name/normalized key, then partial name."""
        needle = query.strip().lower()
        normalized = normalize_component_name(query)
        c = _conn()
        try:
            # exact
            row = c.execute(
                "SELECT * FROM hw_inventory WHERE lower(name) = ? OR normalized_name = ?",
                (needle, normalized),
            ).fetchone()
            if row:
                return _row(row)
            rows = c.execute("SELECT * FROM hw_inventory").fetchall()
            for row in rows:
                aliases = json.loads(row["aliases"] or "[]") if "aliases" in row.keys() else []
                if normalized and normalized in {normalize_component_name(a) for a in aliases}:
                    return _row(row)
            # partial
            row = c.execute(
                "SELECT * FROM hw_inventory WHERE lower(name) LIKE ? ORDER BY name LIMIT 1",
                (f"%{needle}%",),
            ).fetchone()
            return _row(row) if row else None
        finally:
            c.close()

    def find_part_smart(
        self,
        name: str,
        manufacturer: str = "",
        part_number: str = "",
    ) -> Optional[dict]:
        """Match by manufacturer+part number, part number, normalized name, or alias."""
        normalized_name = normalize_component_name(name)
        normalized_part_number = normalize_component_name(part_number)
        manufacturer_lower = manufacturer.strip().lower()
        c = _conn()
        try:
            if part_number:
                if manufacturer_lower:
                    row = c.execute(
                        """SELECT * FROM hw_inventory
                           WHERE lower(manufacturer)=? AND lower(part_number)=?
                           LIMIT 1""",
                        (manufacturer_lower, part_number.strip().lower()),
                    ).fetchone()
                    if row:
                        return _row(row)
                row = c.execute(
                    "SELECT * FROM hw_inventory WHERE lower(part_number)=? OR normalized_name=? LIMIT 1",
                    (part_number.strip().lower(), normalized_part_number),
                ).fetchone()
                if row:
                    return _row(row)
            row = c.execute(
                "SELECT * FROM hw_inventory WHERE normalized_name=? OR lower(name)=? LIMIT 1",
                (normalized_name, name.strip().lower()),
            ).fetchone()
            if row:
                return _row(row)
            rows = c.execute("SELECT * FROM hw_inventory").fetchall()
            for row in rows:
                aliases = json.loads(row["aliases"] or "[]") if "aliases" in row.keys() else []
                if normalized_name in {normalize_component_name(a) for a in aliases}:
                    return _row(row)
            return None
        finally:
            c.close()

    def upsert_import_part(
        self,
        *,
        name: str,
        quantity: int = 0,
        source_type: str,
        manufacturer: str = "",
        part_number: str = "",
        value: str = "",
        footprint: str = "",
        category: str = "misc",
    ) -> tuple[dict, str]:
        """Create/update a part during import. Inventory imports set stock; BOM imports do not fabricate stock."""
        existing = self.find_part_smart(name, manufacturer=manufacturer, part_number=part_number)
        aliases = sorted({
            item for item in [name, value, part_number]
            if item and normalize_component_name(item) != normalize_component_name(name)
        })
        if existing:
            existing_aliases = json.loads(existing.get("aliases") or "[]")
            merged_aliases = sorted(set(existing_aliases) | set(aliases))
            updates: dict = {
                "aliases": json.dumps(merged_aliases),
                "manufacturer": manufacturer or existing.get("manufacturer", ""),
                "part_number": part_number or existing.get("part_number", ""),
                "notes": _merge_notes(existing.get("notes", ""), f"Imported from {source_type}; value={value}; footprint={footprint}".strip()),
            }
            if source_type == "inventory":
                updates["quantity"] = max(0, int(quantity))
                updates["status"] = _status_for_quantity(int(quantity))
            if (existing.get("category") or "misc").lower() == "misc":
                classification = classify_component(
                    name,
                    manufacturer=manufacturer or existing.get("manufacturer", ""),
                    part_number=part_number or existing.get("part_number", ""),
                    notes=updates["notes"],
                )
                if should_apply_classification(classification):
                    updates["category"] = classification.category
                    if classification.subcategory and not existing.get("subcategory"):
                        updates["subcategory"] = classification.subcategory
            updated = self.update_part(existing["id"], **updates)
            return updated or existing, "updated"

        stock_qty = max(0, int(quantity)) if source_type == "inventory" else 0
        part = self.add_part(
            name=name,
            category=category or "misc",
            quantity=stock_qty,
            manufacturer=manufacturer,
            part_number=part_number,
            notes=f"Imported from {source_type}; value={value}; footprint={footprint}".strip(),
            status=_status_for_quantity(stock_qty),
        )
        if aliases:
            part = self.update_part(part["id"], aliases=json.dumps(aliases)) or part
        return part, "created"

    def list_parts(self, category: str = "", search: str = "") -> list[dict]:
        c = _conn()
        try:
            if category and search:
                rows = c.execute(
                    """SELECT * FROM hw_inventory
                       WHERE lower(category) = ?
                         AND (lower(name) LIKE ? OR lower(notes) LIKE ? OR lower(manufacturer) LIKE ?)
                       ORDER BY category, name""",
                    (category.lower(), f"%{search.lower()}%", f"%{search.lower()}%", f"%{search.lower()}%"),
                ).fetchall()
            elif category:
                rows = c.execute(
                    "SELECT * FROM hw_inventory WHERE lower(category) = ? ORDER BY name",
                    (category.lower(),),
                ).fetchall()
            elif search:
                rows = c.execute(
                    """SELECT * FROM hw_inventory
                       WHERE lower(name) LIKE ? OR lower(category) LIKE ?
                          OR lower(manufacturer) LIKE ? OR lower(notes) LIKE ?
                          OR lower(part_number) LIKE ?
                       ORDER BY category, name""",
                    tuple(f"%{search.lower()}%" for _ in range(5)),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM hw_inventory ORDER BY category, name"
                ).fetchall()
            return _rows(rows)
        finally:
            c.close()

    def update_part(self, part_id: str, **fields) -> Optional[dict]:
        allowed = {
            "name", "normalized_name", "aliases", "category", "subcategory", "quantity", "status",
            "location", "manufacturer", "part_number", "notes", "datasheet_url", "reorder_threshold",
        }
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "name" in updates and "normalized_name" not in updates:
            updates["normalized_name"] = normalize_component_name(updates["name"])
        if "category" in updates:
            updates["category"] = str(updates["category"] or "misc").strip().lower() or "misc"
        if "subcategory" in updates:
            updates["subcategory"] = str(updates["subcategory"] or "").strip().lower()
        if not updates:
            return self.get_part_by_id(part_id)
        updates["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [part_id]
        c = _conn()
        try:
            c.execute(f"UPDATE hw_inventory SET {cols} WHERE id = ?", vals)
            c.commit()
        finally:
            c.close()
        return self.get_part_by_id(part_id)

    def delete_part(self, part_id: str) -> bool:
        c = _conn()
        try:
            cur = c.execute("DELETE FROM hw_inventory WHERE id = ?", (part_id,))
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()

    def category_summary(self) -> list[dict]:
        """Return [{category, count, total_qty}] sorted by category."""
        c = _conn()
        try:
            rows = c.execute(
                """SELECT category, COUNT(*) as count, SUM(quantity) as total_qty
                   FROM hw_inventory
                   GROUP BY category
                   ORDER BY category"""
            ).fetchall()
            return _rows(rows)
        finally:
            c.close()

    # ── Projects ─────────────────────────────────────────────────────────────

    def create_project(
        self,
        name: str,
        description: str = "",
        status: str = "active",
        priority: str = "normal",
        notes: str = "",
    ) -> dict:
        if status not in VALID_PROJECT_STATUSES:
            status = "active"
        if priority not in VALID_PRIORITIES:
            priority = "normal"
        pid = str(uuid.uuid4())[:8]
        now = _now()
        c = _conn()
        try:
            c.execute(
                """INSERT INTO hw_projects (id, name, status, description, priority, notes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (pid, name.strip(), status, description.strip(), priority, notes.strip(), now, now),
            )
            c.commit()
        finally:
            c.close()
        return self.get_project_by_id(pid)

    def get_project_by_id(self, project_id: str) -> Optional[dict]:
        c = _conn()
        try:
            row = c.execute("SELECT * FROM hw_projects WHERE id = ?", (project_id,)).fetchone()
            return _row(row) or None
        finally:
            c.close()

    def find_project(self, query: str) -> Optional[dict]:
        needle = query.strip().lower()
        c = _conn()
        try:
            row = c.execute(
                "SELECT * FROM hw_projects WHERE lower(name) = ?", (needle,)
            ).fetchone()
            if row:
                return _row(row)
            row = c.execute(
                "SELECT * FROM hw_projects WHERE lower(name) LIKE ? ORDER BY name LIMIT 1",
                (f"%{needle}%",),
            ).fetchone()
            return _row(row) if row else None
        finally:
            c.close()

    def list_projects(self, status: str = "") -> list[dict]:
        c = _conn()
        try:
            if status:
                rows = c.execute(
                    "SELECT * FROM hw_projects WHERE status = ? ORDER BY priority DESC, name",
                    (status.lower(),),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM hw_projects ORDER BY status, priority DESC, name"
                ).fetchall()
            return _rows(rows)
        finally:
            c.close()

    def update_project(self, project_id: str, **fields) -> Optional[dict]:
        allowed = {"name", "status", "description", "priority", "notes"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return self.get_project_by_id(project_id)
        updates["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [project_id]
        c = _conn()
        try:
            c.execute(f"UPDATE hw_projects SET {cols} WHERE id = ?", vals)
            c.commit()
        finally:
            c.close()
        return self.get_project_by_id(project_id)

    def delete_project(self, project_id: str) -> bool:
        c = _conn()
        try:
            cur = c.execute("DELETE FROM hw_projects WHERE id = ?", (project_id,))
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()

    # ── Project-Part Links ───────────────────────────────────────────────────

    def assign_part_to_project(
        self, project_id: str, part_id: str, quantity_required: int = 1,
        notes: str = "", is_required: int = 1,
        acceptable_substitutes: list[str] | None = None,
        source: str = "manual",
    ) -> dict:
        link_id = str(uuid.uuid4())[:8]
        now = _now()
        substitutes_json = json.dumps([s.strip() for s in (acceptable_substitutes or []) if s.strip()])
        c = _conn()
        try:
            c.execute(
                """INSERT INTO hw_project_parts
                   (id, project_id, part_id, quantity_required, is_required, acceptable_substitutes, source, notes, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(project_id, part_id) DO UPDATE
                   SET quantity_required = excluded.quantity_required,
                       is_required = excluded.is_required,
                       acceptable_substitutes = excluded.acceptable_substitutes,
                       source = excluded.source,
                       notes = excluded.notes""",
                (link_id, project_id, part_id, quantity_required, is_required, substitutes_json, source.strip() or "manual", notes.strip(), now),
            )
            c.commit()
        finally:
            c.close()
        return {
            "project_id": project_id, "part_id": part_id,
            "quantity_required": quantity_required, "is_required": is_required,
            "acceptable_substitutes": acceptable_substitutes or [],
            "source": source.strip() or "manual",
        }

    def add_project_requirement(
        self,
        project_name: str,
        part_name: str,
        quantity_required: int = 1,
        *,
        acceptable_substitutes: list[str] | None = None,
        notes: str = "",
        source: str = "Hardware Assistant chat",
    ) -> dict:
        project, _ = self.get_or_create_project(project_name, notes="Created by hardware requirement entry")
        part = self.find_part_smart(part_name)
        if not part:
            part = self.add_part(
                part_name,
                quantity=0,
                status="out-of-stock",
                notes=f"Requirement placeholder for {project['name']}",
            )
        link = self.assign_part_to_project(
            project["id"],
            part["id"],
            max(1, int(quantity_required or 1)),
            notes=notes,
            is_required=1,
            acceptable_substitutes=acceptable_substitutes or [],
            source=source,
        )
        return {"project": project, "part": part, "link": link}

    def get_or_create_project(self, name: str, notes: str = "") -> tuple[dict, bool]:
        existing = self.find_project(name)
        if existing:
            return existing, False
        project = self.create_project(
            name=name,
            status="planned",
            priority="normal",
            notes=notes,
        )
        return project, True

    def unassign_part_from_project(self, project_id: str, part_id: str) -> bool:
        c = _conn()
        try:
            cur = c.execute(
                "DELETE FROM hw_project_parts WHERE project_id = ? AND part_id = ?",
                (project_id, part_id),
            )
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()

    def get_project_parts(self, project_id: str) -> list[dict]:
        c = _conn()
        try:
            rows = c.execute(
                """SELECT pp.*, i.name, i.category, i.quantity as stock_qty, i.status as stock_status
                   FROM hw_project_parts pp
                   JOIN hw_inventory i ON i.id = pp.part_id
                   WHERE pp.project_id = ?
                   ORDER BY i.category, i.name""",
                (project_id,),
            ).fetchall()
            parts = _rows(rows)
            for part in parts:
                try:
                    part["acceptable_substitutes"] = json.loads(part.get("acceptable_substitutes") or "[]")
                except (TypeError, json.JSONDecodeError):
                    part["acceptable_substitutes"] = []
            return parts
        finally:
            c.close()

    def get_part_projects(self, part_id: str) -> list[dict]:
        c = _conn()
        try:
            rows = c.execute(
                """SELECT pp.*, p.name, p.status as project_status, p.priority
                   FROM hw_project_parts pp
                   JOIN hw_projects p ON p.id = pp.project_id
                   WHERE pp.part_id = ?
                   ORDER BY p.status, p.name""",
                (part_id,),
            ).fetchall()
            return _rows(rows)
        finally:
            c.close()

    def get_project_with_parts(self, project_id: str) -> Optional[dict]:
        project = self.get_project_by_id(project_id)
        if not project:
            return None
        parts = self.get_project_parts(project_id)
        for part in parts:
            availability = self._requirement_availability(part)
            part["available_qty"] = availability["available_qty"]
            part["substitute_matches"] = availability["substitute_matches"]
            part["shortfall"] = max(0, int(part.get("quantity_required", 1) or 1) - availability["available_qty"])
        project["parts"] = parts
        project["part_count"] = len(parts)
        # Missing: only required parts where stock is insufficient
        project["missing"] = [
            p for p in parts
            if p.get("is_required", 1) == 1
            and p.get("available_qty", p.get("stock_qty", 0)) < p.get("quantity_required", 1)
        ]
        return project

    # ── Orders ───────────────────────────────────────────────────────────────

    def add_order(
        self,
        part_name: str,
        vendor: str = "",
        quantity: int = 1,
        notes: str = "",
        status: str = "ordered",
        expected_delivery: str = "",
    ) -> dict:
        if status not in VALID_ORDER_STATUSES:
            status = "ordered"
        order_id = str(uuid.uuid4())[:8]
        now = _now()
        c = _conn()
        try:
            c.execute(
                """INSERT INTO hw_orders (id, part_name, vendor, quantity, status, notes,
                   expected_delivery, ordered_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (order_id, part_name.strip(), vendor.strip(), quantity, status,
                 notes.strip(), expected_delivery.strip(), now, now),
            )
            c.commit()
        finally:
            c.close()
        return self.get_order(order_id)

    def get_order(self, order_id: str) -> Optional[dict]:
        c = _conn()
        try:
            row = c.execute("SELECT * FROM hw_orders WHERE id = ?", (order_id,)).fetchone()
            return _row(row) or None
        finally:
            c.close()

    def list_orders(self, status: str = "") -> list[dict]:
        c = _conn()
        try:
            if status:
                rows = c.execute(
                    "SELECT * FROM hw_orders WHERE status = ? ORDER BY ordered_at DESC",
                    (status.lower(),),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM hw_orders ORDER BY ordered_at DESC"
                ).fetchall()
            return _rows(rows)
        finally:
            c.close()

    def update_order_status(self, order_id: str, status: str) -> Optional[dict]:
        if status not in VALID_ORDER_STATUSES:
            return None
        c = _conn()
        try:
            c.execute(
                "UPDATE hw_orders SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), order_id),
            )
            c.commit()
        finally:
            c.close()
        return self.get_order(order_id)

    def find_order(self, query: str) -> Optional[dict]:
        """Find order by ID prefix or part_name match."""
        needle = query.strip().lower()
        c = _conn()
        try:
            # ID prefix
            row = c.execute(
                "SELECT * FROM hw_orders WHERE lower(id) LIKE ? ORDER BY ordered_at DESC LIMIT 1",
                (f"{needle}%",),
            ).fetchone()
            if row:
                return _row(row)
            # part name
            row = c.execute(
                "SELECT * FROM hw_orders WHERE lower(part_name) LIKE ? ORDER BY ordered_at DESC LIMIT 1",
                (f"%{needle}%",),
            ).fetchone()
            return _row(row) if row else None
        finally:
            c.close()

    def update_order(self, order_id: str, **fields) -> Optional[dict]:
        allowed = {"vendor", "status", "notes", "expected_delivery", "date_received", "quantity"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "status" in updates and updates["status"] not in VALID_ORDER_STATUSES:
            updates.pop("status")
        if not updates:
            return self.get_order(order_id)
        updates["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [order_id]
        c = _conn()
        try:
            c.execute(f"UPDATE hw_orders SET {cols} WHERE id = ?", vals)
            c.commit()
        finally:
            c.close()
        return self.get_order(order_id)

    def receive_order(self, order_id: str) -> Optional[dict]:
        """Mark order delivered and credit quantity to inventory."""
        order = self.get_order(order_id)
        if not order:
            return None
        now = _now()
        part = self.find_part_smart(order["part_name"])
        if part:
            new_qty = int(part["quantity"]) + int(order["quantity"])
            part = self.update_part(part["id"], quantity=new_qty, status=_status_for_quantity(new_qty)) or part
        else:
            part = self.add_part(order["part_name"], quantity=int(order["quantity"]), status="in-stock")
        c = _conn()
        try:
            c.execute(
                "UPDATE hw_orders SET status='delivered', date_received=?, updated_at=? WHERE id=?",
                (now, now, order_id),
            )
            c.commit()
        finally:
            c.close()
        return {"order": self.get_order(order_id), "part": part}

    def get_low_stock(self) -> list[dict]:
        """Parts where reorder_threshold > 0 and quantity <= threshold."""
        c = _conn()
        try:
            rows = c.execute(
                """SELECT * FROM hw_inventory
                   WHERE reorder_threshold > 0 AND quantity <= reorder_threshold
                   ORDER BY (reorder_threshold - quantity) DESC, name"""
            ).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["shortfall"] = max(0, d["reorder_threshold"] - d["quantity"])
                result.append(d)
            return result
        finally:
            c.close()

    def get_active_orders(self) -> list[dict]:
        """Orders not yet delivered or cancelled."""
        return self.list_orders_by_statuses({"ordered", "manufacturing", "shipped", "in_transit"})

    def list_orders_by_statuses(self, statuses: set) -> list[dict]:
        placeholders = ",".join("?" * len(statuses))
        c = _conn()
        try:
            rows = c.execute(
                f"SELECT * FROM hw_orders WHERE status IN ({placeholders}) ORDER BY ordered_at DESC",
                tuple(statuses),
            ).fetchall()
            return _rows(rows)
        finally:
            c.close()

    def get_after_delivery_readiness(self) -> list[dict]:
        """Simulate build readiness after all active orders arrive."""
        active_orders = self.get_active_orders()
        if not active_orders:
            return []
        # Map part_id → incoming quantity (using find_part_smart for name matching)
        sim_extra: dict[str, int] = {}
        sim_unmatched: list[dict] = []
        for order in active_orders:
            part = self.find_part_smart(order["part_name"])
            if part:
                pid = part["id"]
                sim_extra[pid] = sim_extra.get(pid, 0) + int(order["quantity"])
            else:
                sim_unmatched.append({"name": order["part_name"].lower(), "qty": int(order["quantity"])})
        results = []
        for proj in self.list_projects():
            if proj["status"] in _DONE_STATUSES:
                continue
            r = self.get_build_readiness(proj["id"])
            if not r or r["status"] == "no_required_parts":
                continue
            still_missing = []
            resolved = []
            for m in r["missing"]:
                incoming = sim_extra.get(m["part_id"], 0)
                if incoming == 0:
                    part_lower = m["name"].lower()
                    for un in sim_unmatched:
                        if un["name"] in part_lower or part_lower in un["name"]:
                            incoming = un["qty"]
                            break
                remaining = max(0, m["shortfall"] - incoming)
                entry = {**m, "incoming_qty": incoming}
                if remaining > 0:
                    entry["remaining"] = remaining
                    still_missing.append(entry)
                else:
                    resolved.append(entry)
            becomes_buildable = len(still_missing) == 0 and len(r["missing"]) > 0
            results.append({
                "project_id": proj["id"],
                "project_name": proj["name"],
                "project_status": proj["status"],
                "priority": proj["priority"],
                "current_readiness": r["readiness_pct"],
                "current_status": r["status"],
                "after_status": "ready" if becomes_buildable else r["status"],
                "becomes_buildable": becomes_buildable,
                "resolved_parts": resolved,
                "still_missing": still_missing,
            })
        results.sort(key=lambda x: (0 if x["becomes_buildable"] else 1, -x["current_readiness"]))
        return results

    def delete_order(self, order_id: str) -> bool:
        c = _conn()
        try:
            cur = c.execute("DELETE FROM hw_orders WHERE id = ?", (order_id,))
            c.commit()
            return cur.rowcount > 0
        finally:
            c.close()

    # ── Summary ──────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        c = _conn()
        try:
            total_parts = c.execute("SELECT COUNT(*) FROM hw_inventory").fetchone()[0]
            total_qty   = c.execute("SELECT COALESCE(SUM(quantity),0) FROM hw_inventory").fetchone()[0]
            projects    = c.execute("SELECT COUNT(*) FROM hw_projects").fetchone()[0]
            active_proj = c.execute(
                "SELECT COUNT(*) FROM hw_projects WHERE status NOT IN "
                "('completed','archived','complete','abandoned')"
            ).fetchone()[0]
            pending_ord = c.execute(
                "SELECT COUNT(*) FROM hw_orders WHERE status IN ('ordered','manufacturing','shipped','in_transit')"
            ).fetchone()[0]
            cats = self.category_summary()
            return {
                "total_parts": total_parts,
                "total_qty": total_qty,
                "projects": projects,
                "active_projects": active_proj,
                "pending_orders": pending_ord,
                "categories": cats,
            }
        finally:
            c.close()

    # ── Import History ─────────────────────────────────────────────────────

    def record_import(
        self,
        *,
        source_path: str,
        source_type: str,
        project: Optional[dict],
        rows_total: int,
        imported_count: int,
        created_parts: int,
        updated_parts: int,
        linked_parts: int,
        errors: list[str],
        items: list[dict],
    ) -> dict:
        import_id = str(uuid.uuid4())[:8]
        now = _now()
        c = _conn()
        try:
            c.execute(
                """INSERT INTO hw_imports
                   (id, source_path, source_type, project_id, project_name, rows_total,
                    imported_count, created_parts, updated_parts, linked_parts, errors_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    import_id,
                    source_path,
                    source_type,
                    project["id"] if project else None,
                    project["name"] if project else "",
                    rows_total,
                    imported_count,
                    created_parts,
                    updated_parts,
                    linked_parts,
                    json.dumps(errors),
                    now,
                ),
            )
            for item in items:
                c.execute(
                    """INSERT INTO hw_import_items
                       (id, import_id, part_id, raw_name, quantity, value, footprint,
                        manufacturer, part_number, action, raw_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4())[:8],
                        import_id,
                        item.get("part_id"),
                        item.get("raw_name", ""),
                        int(item.get("quantity", 0) or 0),
                        item.get("value", ""),
                        item.get("footprint", ""),
                        item.get("manufacturer", ""),
                        item.get("part_number", ""),
                        item.get("action", ""),
                        json.dumps(item.get("raw", {})),
                        now,
                    ),
                )
            c.commit()
        finally:
            c.close()
        return self.get_import(import_id) or {}

    def get_import(self, import_id: str) -> Optional[dict]:
        c = _conn()
        try:
            row = c.execute("SELECT * FROM hw_imports WHERE id=?", (import_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["errors"] = json.loads(data.pop("errors_json") or "[]")
            return data
        finally:
            c.close()

    def list_imports(self, limit: int = 25) -> list[dict]:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT * FROM hw_imports ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            result = []
            for row in rows:
                data = dict(row)
                data["errors"] = json.loads(data.pop("errors_json") or "[]")
                result.append(data)
            return result
        finally:
            c.close()

    def list_import_items(self, import_id: str) -> list[dict]:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT * FROM hw_import_items WHERE import_id=? ORDER BY raw_name",
                (import_id,),
            ).fetchall()
            result = []
            for row in rows:
                data = dict(row)
                data["raw"] = json.loads(data.pop("raw_json") or "{}")
                result.append(data)
            return result
        finally:
            c.close()

    def get_inventory_impact(self, project_id: str) -> Optional[dict]:
        project = self.get_project_by_id(project_id)
        if not project:
            return None
        parts = [part for part in self.get_project_parts(project_id) if part.get("is_required", 1) == 1]
        consumed = []
        for part in parts:
            availability = self._requirement_availability(part)
            required = int(part.get("quantity_required", 0) or 0)
            stock = availability["available_qty"]
            consumed.append({
                "part_id": part["part_id"],
                "name": part["name"],
                "quantity_required": required,
                "stock_qty": int(part.get("stock_qty", 0) or 0),
                "available_qty": stock,
                "remaining_after_build": stock - required,
                "shortfall": max(0, required - stock),
                "ok": stock >= required,
                "source": part.get("source", "manual"),
                "acceptable_substitutes": part.get("acceptable_substitutes", []),
                "substitute_matches": availability["substitute_matches"],
            })
        return {
            "project_id": project_id,
            "project_name": project["name"],
            "parts": consumed,
            "missing": [part for part in consumed if not part["ok"]],
        }

    # ?? Intelligence (Phase 12B) ???????????????????????????????????????????

    def _requirement_availability(self, part: dict) -> dict:
        stock = int(part.get("stock_qty", 0) or 0)
        substitute_matches = []
        for substitute in part.get("acceptable_substitutes", []) or []:
            match = self.find_part_smart(substitute)
            if not match:
                continue
            qty = int(match.get("quantity", 0) or 0)
            stock += qty
            substitute_matches.append({
                "name": match["name"],
                "quantity": qty,
                "part_id": match["id"],
            })
        return {"available_qty": stock, "substitute_matches": substitute_matches}

    def get_build_readiness(self, project_id: str) -> Optional[dict]:
        """Compute build readiness for a single project from recorded requirements only."""
        project = self.get_project_by_id(project_id)
        if not project:
            return None
        parts = self.get_project_parts(project_id)
        required = [p for p in parts if p.get("is_required", 1) == 1]
        if not required:
            return {
                "project_id": project_id,
                "project_name": project["name"],
                "project_status": project["status"],
                "priority": project["priority"],
                "status": "no_required_parts",
                "total_required": 0,
                "fulfilled_required": 0,
                "readiness_pct": 0,
                "required_parts": [],
                "available": [],
                "missing": [],
            }
        evaluated = []
        for part in required:
            availability = self._requirement_availability(part)
            required_qty = int(part.get("quantity_required", 1) or 1)
            available_qty = availability["available_qty"]
            evaluated.append({
                "part_id": part["part_id"],
                "name": part["name"],
                "category": part.get("category", "misc"),
                "quantity_required": required_qty,
                "stock_qty": int(part.get("stock_qty", 0) or 0),
                "available_qty": available_qty,
                "shortfall": max(0, required_qty - available_qty),
                "ok": available_qty >= required_qty,
                "source": part.get("source", "manual"),
                "notes": part.get("notes", ""),
                "acceptable_substitutes": part.get("acceptable_substitutes", []),
                "substitute_matches": availability["substitute_matches"],
            })
        missing = [part for part in evaluated if not part["ok"]]
        fulfilled = len(evaluated) - len(missing)
        pct = round(fulfilled / len(evaluated) * 100)
        if pct == 100:
            build_status = "ready"
        elif pct >= 50:
            build_status = "partially_ready"
        elif pct > 0:
            build_status = "missing_parts"
        else:
            build_status = "blocked"
        return {
            "project_id": project_id,
            "project_name": project["name"],
            "project_status": project["status"],
            "priority": project["priority"],
            "status": build_status,
            "total_required": len(evaluated),
            "fulfilled_required": fulfilled,
            "readiness_pct": pct,
            "required_parts": evaluated,
            "available": [part for part in evaluated if part["ok"]],
            "missing": missing,
        }

    def get_all_readiness(self) -> list[dict]:
        """Build readiness for every non-completed project."""
        projects = self.list_projects()
        results = []
        for p in projects:
            if p["status"] in _DONE_STATUSES:
                continue
            r = self.get_build_readiness(p["id"])
            if r:
                results.append(r)
        results.sort(key=lambda r: -r["readiness_pct"])
        return results

    def get_all_missing_parts(self) -> list[dict]:
        """All projects that have missing required parts, sorted by priority."""
        projects = self.list_projects()
        results = []
        for p in projects:
            if p["status"] in _DONE_STATUSES:
                continue
            r = self.get_build_readiness(p["id"])
            if r and r["missing"]:
                results.append({
                    "project_id": p["id"],
                    "project_name": p["name"],
                    "project_status": p["status"],
                    "priority": p["priority"],
                    "readiness_pct": r["readiness_pct"],
                    "missing": r["missing"],
                })
        results.sort(key=lambda r: (_PRIORITY_WEIGHT.get(r["priority"], 2) * -1, -len(r["missing"])))
        return results

    def get_blocked_projects(self) -> list[dict]:
        """Projects with status=blocked or any required part with zero stock."""
        projects = self.list_projects()
        blocked = []
        for p in projects:
            if p["status"] in _DONE_STATUSES:
                continue
            parts = self.get_project_parts(p["id"])
            if p["status"] == "blocked":
                zero = [pp for pp in parts if pp.get("is_required", 1) == 1
                        and pp.get("stock_qty", 0) < pp.get("quantity_required", 1)]
                blocked.append({"project": p, "blocking_parts": zero, "reason": "status_blocked"})
            else:
                zero = [pp for pp in parts if pp.get("is_required", 1) == 1
                        and pp.get("stock_qty", 0) == 0]
                if zero:
                    blocked.append({"project": p, "blocking_parts": zero, "reason": "zero_stock"})
        return blocked

    def get_component_usage_stats(self) -> list[dict]:
        """Parts sorted by number of projects they appear in."""
        c = _conn()
        try:
            rows = c.execute("""
                SELECT i.id as part_id, i.name as part_name, i.category,
                       i.quantity as stock_qty,
                       COUNT(DISTINCT pp.project_id) as project_count,
                       GROUP_CONCAT(DISTINCT p.name) as project_names_str
                FROM hw_inventory i
                LEFT JOIN hw_project_parts pp ON pp.part_id = i.id
                LEFT JOIN hw_projects p ON p.id = pp.project_id
                GROUP BY i.id
                ORDER BY project_count DESC, i.name
            """).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["project_names"] = d.pop("project_names_str", "") or ""
                d["project_names"] = [n for n in d["project_names"].split(",") if n] if d["project_names"] else []
                result.append(d)
            return result
        finally:
            c.close()

    def get_order_recommendations(self) -> list[dict]:
        """Parts that need ordering: required by active projects but insufficient in stock."""
        part_needs: dict[str, dict] = {}
        for proj in self.list_projects():
            if proj["status"] in _DONE_STATUSES:
                continue
            for pp in self.get_project_parts(proj["id"]):
                if pp.get("is_required", 1) != 1:
                    continue
                pid = pp["part_id"]
                if pid not in part_needs:
                    part_needs[pid] = {
                        "part_id": pid,
                        "part_name": pp["name"],
                        "category": pp.get("category", "misc"),
                        "stock_qty": pp.get("stock_qty", 0),
                        "total_needed": 0,
                        "affected_projects": [],
                    }
                part_needs[pid]["total_needed"] += pp["quantity_required"]
                part_needs[pid]["affected_projects"].append({
                    "project_id": proj["id"],
                    "project_name": proj["name"],
                    "quantity_needed": pp["quantity_required"],
                    "priority": proj["priority"],
                })
        recs = []
        for info in part_needs.values():
            shortfall = info["total_needed"] - info["stock_qty"]
            if shortfall <= 0:
                continue
            if info["stock_qty"] == 0:
                urgency = "critical"
            elif info["stock_qty"] < info["total_needed"] // 2:
                urgency = "high"
            else:
                urgency = "normal"
            recs.append({**info, "shortfall": shortfall, "buy_quantity": shortfall, "urgency": urgency})
        urgency_order = {"critical": 0, "high": 1, "normal": 2}
        recs.sort(key=lambda r: (urgency_order.get(r["urgency"], 2), -r["shortfall"]))
        return recs

    def get_project_priorities(self) -> list[dict]:
        """Rank active projects by build readiness + status phase + priority."""
        result = []
        for proj in self.list_projects():
            if proj["status"] in _DONE_STATUSES:
                continue
            r = self.get_build_readiness(proj["id"])
            r_pct = r["readiness_pct"] if r else 0
            score = (
                r_pct * 0.4
                + _STATUS_WEIGHT.get(proj["status"], 2) * 4
                + _PRIORITY_WEIGHT.get(proj["priority"], 2) * 2
            )
            if r_pct == 100:
                recommendation = "can_build"
            elif r_pct >= 75:
                recommendation = "nearly_ready"
            elif r_pct >= 25:
                recommendation = "needs_parts"
            else:
                recommendation = "many_missing"
            result.append({
                "project_id": proj["id"],
                "project_name": proj["name"],
                "project_status": proj["status"],
                "priority": proj["priority"],
                "readiness_pct": r_pct,
                "missing_count": (r["total_required"] - r["fulfilled_required"]) if r else 0,
                "score": round(score, 1),
                "recommendation": recommendation,
            })
        result.sort(key=lambda r: -r["score"])
        return result
