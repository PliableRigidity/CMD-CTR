"""Project Memory — Engineering memory store for SILVIA.

Stores decisions, lessons, milestones, failures, experiments, design notes,
and retrospectives for each project. Phase 14C.
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

MEMORY_TYPES = frozenset({
    "decision", "lesson", "milestone", "failure", "success",
    "experiment", "design_note", "engineering_note", "risk", "assumption", "retrospective",
})

_KNOWN_PROJECTS = [
    "Cyberdeck", "DroneHive", "KOI", "Storage Node", "MAGI", "Artoo",
    "FPV_Aircraft", "BespokeToMe", "ProjFreeGuy", "CMD-CTR", "SILVIA",
    "Brain63", "HiveFC", "University",
]

_PROJECT_ALIASES: dict[str, str] = {
    "hive-fc": "DroneHive", "hivefc": "DroneHive", "drone hive": "DroneHive",
    "hive": "DroneHive", "silvia": "CMD-CTR", "cmdctr": "CMD-CTR",
    "cmd-ctr": "CMD-CTR", "cmd ctr": "CMD-CTR", "fpv": "FPV_Aircraft",
    "freeguy": "ProjFreeGuy", "free guy": "ProjFreeGuy",
    "bespoketome": "BespokeToMe", "bespoke": "BespokeToMe",
}


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def _now_date() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _now_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class ProjectMemory:
    """Engineering memory store — decisions, lessons, milestones, failures, etc."""

    def __init__(self) -> None:
        self._init_tables()

    def _init_tables(self) -> None:
        with _conn() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS project_memories (
                    id              TEXT PRIMARY KEY,
                    project         TEXT NOT NULL,
                    type            TEXT NOT NULL,
                    title           TEXT NOT NULL,
                    summary         TEXT NOT NULL DEFAULT '',
                    reasoning       TEXT NOT NULL DEFAULT '',
                    date            TEXT NOT NULL,
                    tags            TEXT NOT NULL DEFAULT '[]',
                    linked_entities TEXT NOT NULL DEFAULT '[]',
                    source          TEXT NOT NULL DEFAULT 'manual',
                    created_at      TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_pm_project ON project_memories (project COLLATE NOCASE);
                CREATE INDEX IF NOT EXISTS idx_pm_type    ON project_memories (type);
                CREATE INDEX IF NOT EXISTS idx_pm_date    ON project_memories (date);
            """)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def record(
        self,
        project: str,
        type: str,
        title: str,
        summary: str = "",
        reasoning: str = "",
        date: Optional[str] = None,
        tags: Optional[list[str]] = None,
        linked_entities: Optional[list[str]] = None,
        source: str = "manual",
    ) -> str:
        """Insert a new memory record. Returns the new ID."""
        if type not in MEMORY_TYPES:
            raise ValueError(f"Unknown memory type: {type}")
        mem_id = f"mem_{uuid.uuid4().hex[:8]}"
        with _conn() as db:
            db.execute(
                """INSERT INTO project_memories
                   (id, project, type, title, summary, reasoning, date, tags, linked_entities, source, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    mem_id, project, type, title,
                    summary or title, reasoning,
                    date or _now_date(),
                    json.dumps(tags or []),
                    json.dumps(linked_entities or []),
                    source, _now_ts(),
                ),
            )
        self._link_kg(project, mem_id, title)
        return mem_id

    def _link_kg(self, project: str, mem_id: str, title: str) -> None:
        try:
            from backend.app.services.knowledge_graph import get_graph
            kg = get_graph()
            ent_id = kg.upsert_entity("document", f"Memory:{title[:60]}", external_id=mem_id)
            proj_ent = kg.find_entity_exact(project, type="project")
            if proj_ent:
                kg.add_relationship(proj_ent["id"], ent_id, "contains")
        except Exception:
            pass

    def get(self, mem_id: str) -> Optional[dict]:
        with _conn() as db:
            row = db.execute("SELECT * FROM project_memories WHERE id=?", (mem_id,)).fetchone()
        return self._row(row) if row else None

    def delete(self, mem_id: str) -> bool:
        with _conn() as db:
            cur = db.execute("DELETE FROM project_memories WHERE id=?", (mem_id,))
        return cur.rowcount > 0

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_project_memories(
        self,
        project: Optional[str],
        type: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        # Empty/None project = all projects
        proj_pat = f"%{project}%" if project else "%"
        q = "SELECT * FROM project_memories WHERE lower(project) LIKE lower(?) "
        params: list = [proj_pat]
        if type:
            q += "AND type=? "
            params.append(type)
        q += "ORDER BY date DESC, created_at DESC LIMIT ?"
        params.append(limit)
        with _conn() as db:
            rows = db.execute(q, params).fetchall()
        return [self._row(r) for r in rows]

    def get_timeline(self, project: str, limit: int = 100) -> list[dict]:
        with _conn() as db:
            rows = db.execute(
                """SELECT * FROM project_memories WHERE lower(project) LIKE lower(?)
                   ORDER BY date ASC, created_at ASC LIMIT ?""",
                (f"%{project}%", limit),
            ).fetchall()
        return [self._row(r) for r in rows]

    def search(self, query: str, project: Optional[str] = None, limit: int = 20) -> list[dict]:
        tokens = re.findall(r"\w+", query.lower())
        if not tokens:
            return []
        conditions = " AND ".join(
            ["(lower(title)||lower(summary)||lower(reasoning) LIKE ?)"] * len(tokens)
        )
        params: list = [f"%{t}%" for t in tokens]
        if project:
            conditions = f"lower(project) LIKE lower(?) AND ({conditions})"
            params = [f"%{project}%"] + params
        params.append(limit)
        with _conn() as db:
            rows = db.execute(
                f"SELECT * FROM project_memories WHERE {conditions} ORDER BY date DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row(r) for r in rows]

    def get_all(self, limit: int = 200) -> list[dict]:
        with _conn() as db:
            rows = db.execute(
                "SELECT * FROM project_memories ORDER BY date DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row(r) for r in rows]

    def get_recent(self, days: int = 30, limit: int = 30) -> list[dict]:
        cutoff = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
        with _conn() as db:
            rows = db.execute(
                "SELECT * FROM project_memories WHERE date>=? ORDER BY date DESC LIMIT ?",
                (cutoff, limit),
            ).fetchall()
        return [self._row(r) for r in rows]

    def list_projects(self) -> list[str]:
        with _conn() as db:
            rows = db.execute(
                "SELECT DISTINCT project FROM project_memories ORDER BY project"
            ).fetchall()
        return [r["project"] for r in rows]

    def get_counts_by_type(self, project: str) -> dict[str, int]:
        with _conn() as db:
            rows = db.execute(
                "SELECT type, count(*) as c FROM project_memories WHERE lower(project) LIKE lower(?) GROUP BY type",
                (f"%{project}%",),
            ).fetchall()
        return {r["type"]: r["c"] for r in rows}

    # ── Brain63 Import ────────────────────────────────────────────────────────

    def import_from_brain63(self, project: Optional[str] = None) -> dict:
        """Scan Brain63 vault for decision/lesson/milestone files and import them."""
        from backend.config import BRAIN63_VAULT_PATH
        vault = Path(BRAIN63_VAULT_PATH)
        if not vault.exists():
            return {"ok": False, "error": "Brain63 vault not found", "imported": 0}

        file_type_map = [
            ("Decisions.md",          "decision"),
            ("HiveFC_Decisions.md",   "decision"),
            ("Lessons_Learned.md",    "lesson"),
            ("LessonsLearned.md",     "lesson"),
            ("Milestones.md",         "milestone"),
            ("Retrospectives.md",     "retrospective"),
            ("Engineering_Notes.md",  "engineering_note"),
            ("EngineeringNotes.md",   "engineering_note"),
            ("Failures.md",           "failure"),
            ("Risks.md",              "risk"),
        ]

        imported = 0
        errors: list[str] = []

        for filename, mem_type in file_type_map:
            for path in vault.glob(f"**/{filename}"):
                if "TEMPLATE" in path.name.upper():
                    continue
                proj_name = self._infer_project(path, vault)
                if project and proj_name.lower() != project.lower():
                    continue
                try:
                    count = self._import_file(path, proj_name, mem_type)
                    imported += count
                except Exception as e:
                    errors.append(f"{path.name}: {e}")

        return {"ok": True, "imported": imported, "errors": errors}

    def _infer_project(self, file_path: Path, vault: Path) -> str:
        try:
            rel = file_path.relative_to(vault)
            parts = rel.parts
            # Walk up past numbered folders (e.g. "01_Projects")
            for i in range(len(parts) - 1, -1, -1):
                folder = parts[i]
                if not re.match(r"^\d+_", folder) and folder != file_path.name:
                    return folder
        except Exception:
            pass
        return "Unknown"

    def _import_file(self, path: Path, project: str, mem_type: str) -> int:
        text = path.read_text(encoding="utf-8", errors="ignore")
        items = self._extract_bullets(text)
        count = 0
        for title, detail in items:
            if not title or len(title) < 8:
                continue
            with _conn() as db:
                exists = db.execute(
                    "SELECT id FROM project_memories WHERE lower(project)=lower(?) AND lower(title)=lower(?) AND source='brain63'",
                    (project, title[:200]),
                ).fetchone()
            if exists:
                continue
            self.record(
                project=project, type=mem_type,
                title=title[:200], summary=detail[:500] if detail else title,
                source="brain63",
            )
            count += 1
        return count

    def _extract_bullets(self, text: str) -> list[tuple[str, str]]:
        """Extract (title, detail) pairs from a markdown file's bullet lists."""
        items: list[tuple[str, str]] = []
        cur_title = ""
        cur_detail: list[str] = []
        in_frontmatter = False
        fm_count = 0

        for line in text.split("\n"):
            stripped = line.strip()
            if stripped == "---":
                fm_count += 1
                in_frontmatter = fm_count == 1
                if fm_count == 2:
                    in_frontmatter = False
                continue
            if in_frontmatter:
                continue
            if stripped.startswith("#"):
                if cur_title:
                    items.append((cur_title, " ".join(cur_detail).strip()))
                    cur_title, cur_detail = "", []
                continue
            if stripped.startswith(("- ", "* ", "+ ")):
                if cur_title:
                    items.append((cur_title, " ".join(cur_detail).strip()))
                cur_title = stripped[2:].strip()
                cur_detail = []
            elif re.match(r"^\d+\.\s", stripped):
                if cur_title:
                    items.append((cur_title, " ".join(cur_detail).strip()))
                cur_title = stripped.split(". ", 1)[1].strip()
                cur_detail = []
            elif cur_title and stripped:
                cur_detail.append(stripped)

        if cur_title:
            items.append((cur_title, " ".join(cur_detail).strip()))
        return items

    @staticmethod
    def _row(row) -> dict:
        d = dict(row)
        d["tags"] = json.loads(d.get("tags") or "[]")
        d["linked_entities"] = json.loads(d.get("linked_entities") or "[]")
        return d


_instance: Optional[ProjectMemory] = None


def get_memory() -> ProjectMemory:
    global _instance
    if _instance is None:
        _instance = ProjectMemory()
    return _instance


def infer_project_from_text(text: str) -> Optional[str]:
    """Extract a known project name from free text."""
    tl = text.lower()
    # Check aliases first (longest match wins for multi-word)
    for alias, canonical in sorted(_PROJECT_ALIASES.items(), key=lambda x: -len(x[0])):
        if alias in tl:
            return canonical
    for proj in _KNOWN_PROJECTS:
        if proj.lower() in tl:
            return proj
    return None
