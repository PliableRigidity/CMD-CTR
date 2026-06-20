"""Rich Output Service — Phase 15C.

Transforms Digital Twin / reconciler data into structured outputs:
tables, mermaid diagrams, checklists, procurement reports, etc.

Returns both a markdown string (for chat) and a structured payload
(for frontend rich rendering).

All renderers use Digital Twin / Reconciler as primary source.
Brain63 is one input among many — never the sole source.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger("silvia.rich_output")

RENDER_TYPES = {
    "table", "markdown_report", "mermaid_flowchart", "mermaid_timeline",
    "mermaid_dependency_graph", "procurement_table", "checklist",
    "priority_matrix", "project_report", "build_workflow",
    "readiness_chart",
}


def detect_rich_intent(query: str) -> Optional[dict]:
    """Detect whether a query wants rich/structured output.

    Returns {"render_type": ..., "project": ..., "intent": ...} or None.
    """
    q = query.strip()
    ql = q.lower()

    project = _extract_project(q)

    # Shopping list / procurement
    if re.search(r"(?:detailed|full|complete)?\s*(?:shopping|procurement|buy|purchase)\s*(?:list|table)", ql):
        return {"render_type": "procurement_table", "project": project, "intent": "procurement_list"}
    if re.search(r"procurement\s+(?:table|list|report|plan)", ql):
        return {"render_type": "procurement_table", "project": project, "intent": "procurement_list"}
    if re.search(r"(?:detailed|full|complete)?\s*(?:parts?|component|missing)\s*(?:list|table|report)", ql):
        return {"render_type": "procurement_table", "project": project, "intent": "parts_list"}

    # Build workflow / build plan
    if re.search(r"build\s*(?:workflow|plan|sequence|order|steps)", ql):
        return {"render_type": "build_workflow", "project": project, "intent": "build_workflow"}
    if re.search(r"(?:roadmap|project)\s+workflow", ql):
        return {"render_type": "build_workflow", "project": project, "intent": "build_workflow"}

    # Dependency graph / diagram
    if re.search(r"(?:dependency|deps?)\s*(?:graph|diagram|chart|map)", ql):
        return {"render_type": "mermaid_dependency_graph", "project": project, "intent": "dependency_graph"}

    # Timeline
    if re.search(r"(?:project\s+)?(?:timeline|gantt|phase\s+timeline)", ql):
        return {"render_type": "mermaid_timeline", "project": project, "intent": "timeline"}

    # Roadmap
    if re.search(r"(?:detailed|full|complete)?\s*roadmap", ql):
        return {"render_type": "checklist", "project": project, "intent": "roadmap"}

    # Project report
    if re.search(r"(?:detailed|full|complete)?\s*(?:project\s+)?(?:report|summary|overview)\s+(?:for|of|on)", ql):
        return {"render_type": "project_report", "project": project, "intent": "project_report"}

    # Readiness chart / readiness table / status table / comparison
    if re.search(r"(?:readiness|status)\s+(?:chart|table|report|matrix|comparison|overview)", ql):
        return {"render_type": "readiness_chart", "project": None, "intent": "readiness_chart"}
    if re.search(r"compar(?:e|ison)\s+(?:projects?|readiness)|(?:readiness|project)\s+compar", ql):
        return {"render_type": "readiness_chart", "project": None, "intent": "comparison"}

    return None


def _extract_project(query: str) -> Optional[str]:
    m = re.search(r"(?:for|of|on)\s+([a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$", query, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(
        r"(?:show|display|generate)\s+([a-zA-Z0-9_\-]+)\s+"
        r"(?:build|roadmap|procurement|shopping|parts|dependency|timeline|report|workflow)",
        query, re.I,
    )
    if m:
        return m.group(1).strip()
    return None


# ── Renderers ────────────────────────────────────────────────────────────────
# Every renderer returns {"ok": bool, "markdown": str, "payload": dict}.
# On error it returns ok=False with a clean error message — never partial text.

def render(render_type: str, project: str) -> dict[str, Any]:
    """Dispatch to the correct renderer with full error handling."""
    try:
        if render_type == "procurement_table":
            return _safe(render_procurement_table, project, "procurement table")
        if render_type == "build_workflow":
            return _safe(render_build_workflow, project, "build workflow")
        if render_type == "mermaid_dependency_graph":
            return _safe(render_dependency_graph, project, "dependency graph")
        if render_type == "project_report":
            return _safe(render_project_report, project, "project report")
        if render_type == "checklist":
            return _safe(render_roadmap_checklist, project, "roadmap")
        if render_type in ("readiness_chart", "table"):
            return _safe_noproject(render_readiness_chart, "readiness chart")
        if render_type == "mermaid_timeline":
            return _safe(render_timeline, project, "timeline")
        return _error(f"Unknown render type: {render_type}")
    except Exception as exc:
        logger.exception("Rich output render error: %s", exc)
        return _error(f"Failed to generate {render_type}: {exc}")


def _safe(fn, project: str, label: str) -> dict[str, Any]:
    if not project:
        return _error(f"Which project? Try: '{label} for Cyberdeck'")
    try:
        return fn(project)
    except Exception as exc:
        logger.exception("Render %s failed for %s", label, project)
        return _error(f"Failed to generate {label} for {project}: {exc}")


def _safe_noproject(fn, label: str) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:
        logger.exception("Render %s failed", label)
        return _error(f"Failed to generate {label}: {exc}")


def _error(msg: str) -> dict[str, Any]:
    return {"ok": False, "markdown": msg, "payload": {}}


# ── Procurement ──────────────────────────────────────────────────────────────

def render_procurement_table(project: str) -> dict[str, Any]:
    from backend.app.services.project_reconciler import get_reconciler
    data = get_reconciler().reconcile_project(project)
    if not data.get("found"):
        return _error(f"Project '{project}' not found.")

    rows = []
    for item in data.get("buy_now", []):
        rows.append(["Buy now", item["name"], "Missing", item.get("source", "—"), "Order"])
    for item in data.get("buy_soon", []):
        rows.append(["Buy soon", item["name"], "Missing", item.get("source", "—"), "Order later"])
    for item in data.get("already_ordered", []):
        rows.append(["On order", item["name"], "Ordered", item.get("source", "—"), "Wait"])
    for item in data.get("already_owned", []):
        rows.append(["Owned", item["name"], "Owned", item.get("source", "—"), "No action"])

    headers = ["Priority", "Item", "Status", "Source", "Action"]
    md = _rows_to_markdown_table(headers, rows)

    stale = data.get("stale_entries", [])
    if stale:
        md += "\n\n**Stale Brain63 entries:**\n"
        for s in stale:
            md += f"- {s['name']} — {s.get('stale_note', 'may be outdated')}\n"

    sources = data.get("sources_used", [])
    md = f"## Procurement — {data['project']}\n\nSources: {', '.join(sources)}\n\n{md}"

    # Chart-ready summary
    chart_data = {
        "buy_now": len(data.get("buy_now", [])),
        "buy_soon": len(data.get("buy_soon", [])),
        "on_order": len(data.get("already_ordered", [])),
        "owned": len(data.get("already_owned", [])),
        "total": data.get("total_items", 0),
    }

    return {
        "ok": True,
        "markdown": md,
        "payload": {
            "rich_output": {
                "type": "table",
                "title": f"Procurement — {data['project']}",
                "headers": headers,
                "rows": rows,
                "sources": sources,
                "stale": [{"name": s["name"], "note": s.get("stale_note", "")} for s in stale],
                "chart_data": chart_data,
            }
        },
    }


# ── Build Workflow ───────────────────────────────────────────────────────────

def render_build_workflow(project: str) -> dict[str, Any]:
    phases = _get_project_phases(project)
    if not phases:
        return _error(f"No roadmap phases found for '{project}'.")

    mermaid_lines = ["flowchart TD"]
    prev_id = None
    for i, phase in enumerate(phases):
        node_id = chr(65 + i) if i < 26 else f"N{i}"
        label = phase["name"].replace('"', "'")
        done = phase.get("done", 0)
        total = phase.get("total", 0)
        status_str = f" ({done}/{total})" if total else ""
        mermaid_lines.append(f'    {node_id}["{label}{status_str}"]')
        if prev_id:
            mermaid_lines.append(f"    {prev_id} --> {node_id}")
        prev_id = node_id

    mermaid = "\n".join(mermaid_lines)
    md = f"## Build Workflow — {project}\n\n```mermaid\n{mermaid}\n```"

    return {
        "ok": True,
        "markdown": md,
        "payload": {
            "rich_output": {
                "type": "mermaid",
                "title": f"Build Workflow — {project}",
                "diagram": mermaid,
            }
        },
    }


# ── Dependency Graph ─────────────────────────────────────────────────────────

def render_dependency_graph(project: str) -> dict[str, Any]:
    """Mermaid dependency graph from Knowledge Graph relationships."""
    from backend.app.services.project_intelligence import ProjectIntelligence
    pi = ProjectIntelligence()
    meta = pi.find_project_meta(project)
    if not meta:
        return _error(f"Project '{project}' not found.")

    name = meta["name"]
    edges = []

    # KG dependencies
    try:
        from backend.app.services.knowledge_graph import get_graph
        kg = get_graph()
        ent = kg.find_entity_exact(name, type="project")
        if ent:
            for edge in kg.get_outgoing(ent["id"]):
                edges.append({
                    "from": name,
                    "to": edge["target_name"],
                    "rel": edge["rel_type"],
                    "target_type": edge["target_type"],
                })
            for edge in kg.get_incoming(ent["id"]):
                edges.append({
                    "from": edge["source_name"],
                    "to": name,
                    "rel": edge["rel_type"],
                    "target_type": edge.get("source_type", ""),
                })
    except Exception:
        pass

    # Hardware dependencies (missing parts = blocked_by)
    hw_proj = meta.get("hw_project")
    if hw_proj:
        try:
            from backend.app.services.hardware_service import HardwareService
            readiness = HardwareService().get_build_readiness(hw_proj["id"])
            if readiness:
                for part in readiness.get("missing", [])[:8]:
                    edges.append({
                        "from": name,
                        "to": part["name"],
                        "rel": "needs",
                        "target_type": "component",
                    })
        except Exception:
            pass

    if not edges:
        return _error(f"No dependencies found for '{name}' in Knowledge Graph or Hardware.")

    # Build Mermaid
    mermaid_lines = ["flowchart LR"]
    seen_nodes = set()
    node_ids: dict[str, str] = {}

    def _nid(n: str) -> str:
        if n not in node_ids:
            node_ids[n] = f"N{len(node_ids)}"
        return node_ids[n]

    for e in edges:
        fid = _nid(e["from"])
        tid = _nid(e["to"])
        label = e["rel"].replace("_", " ")
        if (fid, tid) not in seen_nodes:
            seen_nodes.add((fid, tid))
            safe_from = e["from"].replace('"', "'")
            safe_to = e["to"].replace('"', "'")
            if fid not in {n for pair in seen_nodes for n in pair} or True:
                mermaid_lines.append(f'    {fid}["{safe_from}"]')
                mermaid_lines.append(f'    {tid}["{safe_to}"]')
            mermaid_lines.append(f'    {fid} -->|{label}| {tid}')

    mermaid = "\n".join(mermaid_lines)
    md = f"## Dependencies — {name}\n\n```mermaid\n{mermaid}\n```"

    return {
        "ok": True,
        "markdown": md,
        "payload": {
            "rich_output": {
                "type": "mermaid",
                "title": f"Dependencies — {name}",
                "diagram": mermaid,
            }
        },
    }


# ── Timeline ─────────────────────────────────────────────────────────────────

def render_timeline(project: str) -> dict[str, Any]:
    """Mermaid timeline from project phases + engineering memory milestones."""
    phases = _get_project_phases(project)
    milestones = []
    try:
        from backend.app.services.project_memory import get_memory
        milestones = get_memory().get_project_memories(project, type="milestone", limit=10)
    except Exception:
        pass

    if not phases and not milestones:
        return _error(f"No timeline data found for '{project}'.")

    mermaid_lines = ["timeline", f"    title {project} Timeline"]
    for phase in phases:
        done = phase.get("done", 0)
        total = phase.get("total", 0)
        label = phase["name"].replace(":", " -")
        mermaid_lines.append(f"    {label} : {done}/{total} done")
    for m in milestones[:5]:
        title = m.get("title", "").replace(":", " -")[:50]
        date = m.get("date", "")
        mermaid_lines.append(f"    {title} : {date}")

    mermaid = "\n".join(mermaid_lines)
    md = f"## Timeline — {project}\n\n```mermaid\n{mermaid}\n```"

    return {
        "ok": True,
        "markdown": md,
        "payload": {
            "rich_output": {
                "type": "mermaid",
                "title": f"Timeline — {project}",
                "diagram": mermaid,
            }
        },
    }


# ── Project Report ───────────────────────────────────────────────────────────

def render_project_report(project: str) -> dict[str, Any]:
    from backend.app.services.project_reconciler import get_reconciler
    from backend.app.services.project_intelligence import ProjectIntelligence

    pi = ProjectIntelligence()
    briefing = pi.get_briefing(project)
    if not briefing.get("found"):
        return _error(f"Project '{project}' not found.")

    recon = get_reconciler().reconcile_project(project)
    sources = recon.get("sources_used", []) if recon.get("found") else ["project_registry"]

    name = briefing["project"]
    lines = [
        f"## Project Report — {name}",
        f"Sources: {', '.join(sources)}",
        "",
        f"**Status:** {briefing['status']}  |  **Priority:** {briefing['priority']}",
        f"**Readiness:** {briefing['readiness_pct']}%  |  **Build Status:** {briefing['build_status']}",
        "",
    ]

    parts = briefing.get("parts", {})
    if parts.get("total"):
        lines.append(f"### Parts ({parts['available']}/{parts['total']} available)")
        if parts.get("missing"):
            lines.append("")
            lines.append("| Missing Part | Qty Needed |")
            lines.append("|---|---|")
            for p in parts["missing"][:10]:
                lines.append(f"| {p['name']} | {p.get('quantity_required', 1)} |")
            lines.append("")

    blockers = briefing.get("blockers", [])
    if blockers:
        lines.append(f"### Blockers ({len(blockers)})")
        for b in blockers:
            lines.append(f"- {b['description']}")
        lines.append("")

    orders = briefing.get("orders", [])
    if orders:
        lines.append(f"### Pending Orders ({len(orders)})")
        for o in orders:
            lines.append(f"- {o.get('part_name', '')} [{o.get('status', '')}]")
        lines.append("")

    memory = briefing.get("memory", {})
    has_memory = any(memory.get(k) for k in ("decisions", "milestones", "risks", "failures"))
    if has_memory:
        lines.append("### Engineering Memory")
        for mtype, items in memory.items():
            if items:
                lines.append(f"**{mtype.title()}:**")
                for m in items[:3]:
                    lines.append(f"- {m.get('title', '')}")
        lines.append("")

    ra = briefing.get("recommended_action", "")
    if ra:
        lines.append(f"### Recommended Action\n{ra}")

    md = "\n".join(lines)
    return {
        "ok": True,
        "markdown": md,
        "payload": {
            "rich_output": {
                "type": "markdown_report",
                "title": f"Project Report — {name}",
                "content": md,
                "sources": sources,
            }
        },
    }


# ── Roadmap Checklist ────────────────────────────────────────────────────────

def render_roadmap_checklist(project: str) -> dict[str, Any]:
    phases = _get_project_phases(project)
    if not phases:
        return _error(f"No roadmap found for '{project}'.")

    lines = [f"## Roadmap — {project}", ""]
    checklist_data = []
    for phase in phases:
        done = phase.get("done", 0)
        total = phase.get("total", 0)
        pct = round(done / total * 100) if total else 0
        lines.append(f"### {phase['name']} ({pct}%)")
        phase_items = []
        for item in phase.get("items", []):
            check = "x" if item.get("checked") else " "
            lines.append(f"- [{check}] {item['name']}")
            phase_items.append({"name": item["name"], "checked": item.get("checked", False)})
        lines.append("")
        checklist_data.append({"phase": phase["name"], "done": done, "total": total, "items": phase_items})

    md = "\n".join(lines)
    return {
        "ok": True,
        "markdown": md,
        "payload": {
            "rich_output": {
                "type": "checklist",
                "title": f"Roadmap — {project}",
                "phases": checklist_data,
            }
        },
    }


# ── Readiness Chart ──────────────────────────────────────────────────────────

def render_readiness_chart() -> dict[str, Any]:
    """Cross-project readiness comparison — table + chart-ready JSON."""
    from backend.app.services.digital_twin import get_twin
    projects = get_twin().priorities()
    if not projects:
        return _error("No active projects.")

    headers = ["Project", "Score", "Readiness", "Status", "Blockers", "Open Tasks"]
    rows = []
    chart_data = []
    for p in projects:
        rows.append([
            p["name"], str(p["score"]), f"{p['readiness_pct']}%",
            p["status"], str(len(p.get("blockers", []))),
            str(p.get("open_tasks", 0)),
        ])
        chart_data.append({
            "project": p["name"],
            "score": p["score"],
            "readiness_pct": p["readiness_pct"],
            "status": p["status"],
            "blockers": len(p.get("blockers", [])),
            "open_tasks": p.get("open_tasks", 0),
        })

    md = "## Project Readiness Comparison\n\n" + _rows_to_markdown_table(headers, rows)
    return {
        "ok": True,
        "markdown": md,
        "payload": {
            "rich_output": {
                "type": "table",
                "title": "Project Readiness Comparison",
                "headers": headers,
                "rows": rows,
                "chart_data": chart_data,
            }
        },
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _rows_to_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "(no data)"
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    hdr = "| " + " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"
    sep = "|" + "|".join("-" * (w + 2) for w in col_widths) + "|"
    lines = [hdr, sep]
    for row in rows:
        padded = []
        for i, cell in enumerate(row):
            w = col_widths[i] if i < len(col_widths) else len(str(cell))
            padded.append(str(cell).ljust(w))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def _get_project_phases(project: str) -> list[dict]:
    """Extract phases from Brain63 roadmap for any project."""
    from pathlib import Path
    try:
        from backend.config import BRAIN63_VAULT_PATH
        vault = Path(BRAIN63_VAULT_PATH)
        if not vault.exists():
            return []

        from backend.app.services.project_intelligence import ProjectIntelligence
        pi = ProjectIntelligence()
        meta = pi.find_project_meta(project)
        key = (meta.get("brain63_key") if meta else None) or project

        roadmap_path = None
        for p in vault.glob(f"**/{key}/Roadmap.md"):
            roadmap_path = p
            break
        if not roadmap_path:
            for p in vault.glob("**/Roadmap.md"):
                if key.lower() in p.parent.name.lower():
                    roadmap_path = p
                    break
        if not roadmap_path:
            return []

        text = roadmap_path.read_text(encoding="utf-8", errors="ignore")
        phases = []
        current = None

        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("## "):
                if current:
                    phases.append(current)
                phase_name = stripped[3:].strip()
                current = {"name": phase_name, "items": [], "done": 0, "total": 0}
            elif current and re.match(r"^-\s+\[([xX ])\]\s+(.+)$", stripped):
                m = re.match(r"^-\s+\[([xX ])\]\s+(.+)$", stripped)
                checked = m.group(1).strip().lower() == "x"
                name = m.group(2).strip()
                name = re.sub(r"\s*\(.*?\)\s*$", "", name)
                name = re.sub(r"\s*—.*$", "", name)
                current["items"].append({"name": name, "checked": checked})
                current["total"] += 1
                if checked:
                    current["done"] += 1

        if current:
            phases.append(current)
        return phases
    except Exception:
        return []
