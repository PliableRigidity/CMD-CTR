"""Hardware tool functions — called by conversation_service._run_tool()."""
from __future__ import annotations

from backend.app.services.hardware_service import HardwareService
from backend.app.services.hardware_import_service import HardwareImportService

_svc: HardwareService | None = None


def _hw() -> HardwareService:
    global _svc
    if _svc is None:
        _svc = HardwareService()
    return _svc


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def add_component(
    name: str,
    category: str = "misc",
    quantity: int = 1,
    subcategory: str = "",
    manufacturer: str = "",
    part_number: str = "",
    location: str = "",
    notes: str = "",
    datasheet_url: str = "",
) -> dict:
    if not name.strip():
        return {"ok": False, "summary": "Part name is required."}
    if quantity < 0:
        quantity = 0
    part = _hw().add_part(
        name=name.strip(),
        category=category.strip() or "misc",
        quantity=quantity,
        subcategory=subcategory,
        manufacturer=manufacturer,
        part_number=part_number,
        location=location,
        notes=notes,
        datasheet_url=datasheet_url,
    )
    return {
        "ok": True,
        "part": part,
        "summary": (
            f"Added {part['name']} to inventory — "
            f"qty:{part['quantity']} · category:{part['category']}."
        ),
    }


def list_components(category: str = "", search: str = "") -> dict:
    parts = _hw().list_parts(category=category, search=search)
    if not parts:
        ctx = f" in category '{category}'" if category else ""
        ctx += f" matching '{search}'" if search else ""
        return {"ok": True, "parts": [], "count": 0, "summary": f"No parts found{ctx}."}

    # Group by category for display
    groups: dict[str, list[dict]] = {}
    for p in parts:
        cat = p.get("category", "misc")
        groups.setdefault(cat, []).append(p)

    lines = []
    for cat, items in sorted(groups.items()):
        total_qty = sum(p.get("quantity", 0) for p in items)
        lines.append(f"\n{cat.upper()} ({len(items)} types · {total_qty} units)")
        for p in items:
            status_tag = ""
            if p.get("status") != "in-stock":
                status_tag = f" [{p['status']}]"
            lines.append(f"  · {p['name']}  qty:{p['quantity']}{status_tag}")

    summary = f"HARDWARE INVENTORY — {len(parts)} part types\n" + "\n".join(lines)
    return {"ok": True, "parts": parts, "count": len(parts), "summary": summary}


def get_component(name: str) -> dict:
    part = _hw().find_part(name)
    if not part:
        return {"ok": False, "summary": f"No component found matching '{name}'."}
    lines = [
        f"COMPONENT: {part['name']}",
        f"  Category:     {part['category']}" + (f" / {part['subcategory']}" if part.get('subcategory') else ""),
        f"  Quantity:     {part['quantity']}",
        f"  Status:       {part['status']}",
    ]
    if part.get("manufacturer"):
        lines.append(f"  Manufacturer: {part['manufacturer']}")
    if part.get("part_number"):
        lines.append(f"  Part number:  {part['part_number']}")
    if part.get("location"):
        lines.append(f"  Location:     {part['location']}")
    if part.get("notes"):
        lines.append(f"  Notes:        {part['notes']}")
    if part.get("datasheet_url"):
        lines.append(f"  Datasheet:    {part['datasheet_url']}")

    # Also show projects that use this part
    projects = _hw().get_part_projects(part["id"])
    if projects:
        lines.append(f"  Used by:      " + ", ".join(p["name"] for p in projects))
    return {"ok": True, "part": part, "summary": "\n".join(lines)}


def update_component(name: str, **fields) -> dict:
    part = _hw().find_part(name)
    if not part:
        return {"ok": False, "summary": f"No component found matching '{name}'."}
    updated = _hw().update_part(part["id"], **fields)
    if not updated:
        return {"ok": False, "summary": f"Update failed for '{name}'."}
    changes = ", ".join(f"{k}={v}" for k, v in fields.items())
    return {
        "ok": True,
        "part": updated,
        "summary": f"Updated {updated['name']}: {changes}.",
    }


def delete_component(name: str) -> dict:
    part = _hw().find_part(name)
    if not part:
        return {"ok": False, "summary": f"No component found matching '{name}'."}
    _hw().delete_part(part["id"])
    return {"ok": True, "summary": f"Removed {part['name']} from inventory."}


def search_hardware(query: str) -> dict:
    return list_components(search=query)


def hw_inventory_summary() -> dict:
    summary = _hw().summary()
    cats = summary.get("categories", [])
    lines = [
        f"HARDWARE SUMMARY — {summary['total_parts']} part types · {summary['total_qty']} units",
        f"  Projects:     {summary['projects']} total · {summary['active_projects']} active",
        f"  Pending orders: {summary['pending_orders']}",
        "",
        "INVENTORY BY CATEGORY:",
    ]
    for cat in cats:
        lines.append(f"  {cat['category'].capitalize():<20} {cat['count']} types  {cat['total_qty']} units")
    return {"ok": True, "summary_data": summary, "summary": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

def create_hw_project(
    name: str,
    description: str = "",
    status: str = "active",
    priority: str = "normal",
    notes: str = "",
) -> dict:
    if not name.strip():
        return {"ok": False, "summary": "Project name is required."}
    existing = _hw().find_project(name)
    if existing and existing["name"].lower() == name.strip().lower():
        return {"ok": False, "summary": f"Project '{existing['name']}' already exists."}
    project = _hw().create_project(
        name=name.strip(),
        description=description,
        status=status,
        priority=priority,
        notes=notes,
    )
    return {
        "ok": True,
        "project": project,
        "summary": f"Created hardware project '{project['name']}' — status:{project['status']} · priority:{project['priority']}.",
    }


def list_hw_projects(status: str = "") -> dict:
    projects = _hw().list_projects(status=status)
    if not projects:
        ctx = f" with status '{status}'" if status else ""
        return {"ok": True, "projects": [], "summary": f"No hardware projects found{ctx}."}

    lines = [f"HARDWARE PROJECTS — {len(projects)} total"]
    status_icons = {"active": "●", "paused": "○", "complete": "✓", "abandoned": "✗"}
    for p in projects:
        icon = status_icons.get(p["status"], "·")
        part_count = len(_hw().get_project_parts(p["id"]))
        prio_tag = f" [{p['priority']}]" if p.get("priority") and p["priority"] != "normal" else ""
        lines.append(
            f"  {icon} {p['name']:<20} [{p['status']}]{prio_tag}  {part_count} parts"
        )
        if p.get("description"):
            lines.append(f"      {p['description'][:80]}")
    return {"ok": True, "projects": projects, "summary": "\n".join(lines)}


def get_hw_project(name: str) -> dict:
    project = _hw().find_project(name)
    if not project:
        return {"ok": False, "summary": f"No hardware project found matching '{name}'."}
    detail = _hw().get_project_with_parts(project["id"])
    lines = [
        f"PROJECT: {detail['name']}",
        f"  Status:   {detail['status']}",
        f"  Priority: {detail['priority']}",
    ]
    if detail.get("description"):
        lines.append(f"  Desc:     {detail['description']}")
    if detail.get("notes"):
        lines.append(f"  Notes:    {detail['notes']}")
    lines.append(f"\nPARTS ({detail['part_count']}):")
    for p in detail.get("parts", []):
        stock_ok = p.get("stock_qty", 0) >= p.get("quantity_required", 1)
        check = "✓" if stock_ok else "✗"
        lines.append(
            f"  {check} {p['name']:<24} need:{p['quantity_required']}  have:{p.get('stock_qty', 0)}"
        )
    if detail.get("missing"):
        lines.append(f"\nMISSING / LOW STOCK: {len(detail['missing'])} part(s)")
    return {"ok": True, "project": detail, "summary": "\n".join(lines)}


def update_hw_project_status(name: str, status: str) -> dict:
    project = _hw().find_project(name)
    if not project:
        return {"ok": False, "summary": f"No hardware project found matching '{name}'."}
    updated = _hw().update_project(project["id"], status=status)
    return {
        "ok": True,
        "project": updated,
        "summary": f"Project '{updated['name']}' marked as {updated['status']}.",
    }


def delete_hw_project(name: str) -> dict:
    project = _hw().find_project(name)
    if not project:
        return {"ok": False, "summary": f"No hardware project found matching '{name}'."}
    _hw().delete_project(project["id"])
    return {"ok": True, "summary": f"Deleted hardware project '{project['name']}'."}


# ---------------------------------------------------------------------------
# Project-Part Links
# ---------------------------------------------------------------------------

def assign_part_to_project(part: str, project: str, quantity_required: int = 1) -> dict:
    part_obj = _hw().find_part(part)
    if not part_obj:
        return {"ok": False, "summary": f"No component found matching '{part}'."}
    proj_obj = _hw().find_project(project)
    if not proj_obj:
        return {"ok": False, "summary": f"No hardware project found matching '{project}'."}
    _hw().assign_part_to_project(proj_obj["id"], part_obj["id"], quantity_required)
    return {
        "ok": True,
        "summary": f"Assigned {part_obj['name']} (×{quantity_required}) to project '{proj_obj['name']}'.",
    }


def unassign_part_from_project(part: str, project: str) -> dict:
    part_obj = _hw().find_part(part)
    proj_obj = _hw().find_project(project)
    if not part_obj:
        return {"ok": False, "summary": f"No component matching '{part}'."}
    if not proj_obj:
        return {"ok": False, "summary": f"No project matching '{project}'."}
    ok = _hw().unassign_part_from_project(proj_obj["id"], part_obj["id"])
    if not ok:
        return {"ok": False, "summary": f"{part_obj['name']} is not assigned to '{proj_obj['name']}'."}
    return {"ok": True, "summary": f"Removed {part_obj['name']} from project '{proj_obj['name']}'."}


def list_project_parts(project: str) -> dict:
    proj_obj = _hw().find_project(project)
    if not proj_obj:
        return {"ok": False, "summary": f"No hardware project found matching '{project}'."}
    parts = _hw().get_project_parts(proj_obj["id"])
    if not parts:
        return {"ok": True, "parts": [], "summary": f"No parts assigned to '{proj_obj['name']}' yet."}
    lines = [f"PARTS FOR '{proj_obj['name'].upper()}' ({len(parts)} assigned):"]
    for p in parts:
        ok_marker = "✓" if p.get("stock_qty", 0) >= p.get("quantity_required", 1) else "✗"
        lines.append(
            f"  {ok_marker} {p['name']:<24} need:{p['quantity_required']}  "
            f"have:{p.get('stock_qty', 0)}  [{p.get('stock_status', '')}]"
        )
    return {"ok": True, "parts": parts, "summary": "\n".join(lines)}


def list_part_projects(part: str) -> dict:
    part_obj = _hw().find_part(part)
    if not part_obj:
        return {"ok": False, "summary": f"No component found matching '{part}'."}
    projects = _hw().get_part_projects(part_obj["id"])
    if not projects:
        return {
            "ok": True, "projects": [],
            "summary": f"{part_obj['name']} is not assigned to any project.",
        }
    lines = [f"{part_obj['name']} is used in {len(projects)} project(s):"]
    for p in projects:
        lines.append(f"  · {p['name']}  [{p['project_status']}]  ×{p['quantity_required']}")
    return {"ok": True, "projects": projects, "summary": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def add_order(part_name: str, vendor: str = "", quantity: int = 1, notes: str = "") -> dict:
    if not part_name.strip():
        return {"ok": False, "summary": "Part name is required for an order."}
    order = _hw().add_order(part_name=part_name, vendor=vendor, quantity=quantity, notes=notes)
    vendor_tag = f" from {vendor}" if vendor else ""
    return {
        "ok": True,
        "order": order,
        "summary": f"Order logged: {part_name} ×{quantity}{vendor_tag} — status: ordered. (ID: {order['id']})",
    }


def list_orders(status: str = "") -> dict:
    orders = _hw().list_orders(status=status)
    if not orders:
        ctx = f" with status '{status}'" if status else ""
        return {"ok": True, "orders": [], "summary": f"No orders found{ctx}."}

    # Group by status
    groups: dict[str, list[dict]] = {}
    for o in orders:
        groups.setdefault(o["status"], []).append(o)

    status_order = ["ordered", "manufacturing", "shipped", "delivered", "cancelled"]
    lines = [f"ORDERS — {len(orders)} total"]
    for s in status_order:
        items = groups.get(s, [])
        if not items:
            continue
        lines.append(f"\n  {s.upper()} ({len(items)}):")
        for o in items:
            vendor_tag = f"  ← {o['vendor']}" if o.get("vendor") else ""
            lines.append(f"    [{o['id']}] {o['part_name']}  ×{o['quantity']}{vendor_tag}")
    return {"ok": True, "orders": orders, "summary": "\n".join(lines)}


def update_order_status(query: str, status: str) -> dict:
    order = _hw().find_order(query)
    if not order:
        return {"ok": False, "summary": f"No order found matching '{query}'."}
    updated = _hw().update_order_status(order["id"], status)
    if not updated:
        return {"ok": False, "summary": f"Invalid status '{status}'. Use: ordered, manufacturing, shipped, delivered, cancelled."}
    return {
        "ok": True,
        "order": updated,
        "summary": f"Order [{updated['id']}] {updated['part_name']} marked as {updated['status']}.",
    }


def delete_order(query: str) -> dict:
    order = _hw().find_order(query)
    if not order:
        return {"ok": False, "summary": f"No order found matching '{query}'."}
    _hw().delete_order(order["id"])
    return {"ok": True, "summary": f"Deleted order [{order['id']}] {order['part_name']}."}


# ---------------------------------------------------------------------------
# Phase 12B — Project Intelligence
# ---------------------------------------------------------------------------

def build_readiness_check(project: str) -> dict:
    proj = _hw().find_project(project)
    if not proj:
        return {"ok": False, "summary": f"No hardware project found matching '{project}'."}
    r = _hw().get_build_readiness(proj["id"])
    if not r:
        return {"ok": False, "summary": f"Could not compute readiness for '{project}'."}
    lines = [
        f"BUILD READINESS: {r['project_name']}",
        f"  Status:      {r['status'].replace('_', ' ').upper()}",
        f"  Readiness:   {r['readiness_pct']}% ({r['fulfilled_required']}/{r['total_required']} required parts in stock)",
    ]
    if r["missing"]:
        lines.append(f"\nMISSING PARTS ({len(r['missing'])}):")
        for m in r["missing"]:
            lines.append(
                f"  ✗ {m['name']:<24} need:{m['quantity_required']}  have:{m['stock_qty']}  short:{m['shortfall']}"
            )
    else:
        lines.append("\n  ✓ All required parts are in stock — ready to build!")
    return {"ok": True, "readiness": r, "summary": "\n".join(lines)}


def show_project_readiness() -> dict:
    readiness = _hw().get_all_readiness()
    if not readiness:
        return {"ok": True, "readiness": [], "summary": "No active hardware projects with readiness data."}
    lines = [f"PROJECT READINESS — {len(readiness)} active project(s):"]
    for item in readiness:
        lines.append(
            f"  - {item['project_name']}: {item['readiness_pct']}% "
            f"({item['fulfilled_required']}/{item['total_required']}) [{item['status']}]"
        )
    return {"ok": True, "readiness": readiness, "summary": "\n".join(lines)}


def show_missing_parts(project: str = "") -> dict:
    if project:
        proj = _hw().find_project(project)
        if not proj:
            return {"ok": False, "summary": f"No hardware project found matching '{project}'."}
        r = _hw().get_build_readiness(proj["id"])
        if not r or not r["missing"]:
            return {"ok": True, "summary": f"No missing parts for '{proj['name']}' — all required components in stock."}
        lines = [f"MISSING PARTS FOR '{proj['name'].upper()}':"]
        for m in r["missing"]:
            lines.append(
                f"  ✗ {m['name']:<24} need:{m['quantity_required']}  have:{m['stock_qty']}  short:{m['shortfall']}"
            )
        return {"ok": True, "summary": "\n".join(lines)}
    # All active projects
    data = _hw().get_all_missing_parts()
    if not data:
        return {"ok": True, "summary": "No missing parts — all required components are in stock across active projects."}
    lines = [f"MISSING PARTS ACROSS ACTIVE PROJECTS ({len(data)} projects affected):"]
    for entry in data:
        lines.append(f"\n  {entry['project_name'].upper()} [{entry['project_status']}] — {entry['readiness_pct']}% ready")
        for m in entry["missing"]:
            lines.append(
                f"    ✗ {m['name']:<22} need:{m['quantity_required']}  have:{m['stock_qty']}  short:{m['shortfall']}"
            )
    return {"ok": True, "data": data, "summary": "\n".join(lines)}


def show_blocked_projects() -> dict:
    blocked = _hw().get_blocked_projects()
    if not blocked:
        return {"ok": True, "summary": "No blocked projects — all active projects have at least some required stock."}
    lines = [f"BLOCKED PROJECTS ({len(blocked)}):"]
    for b in blocked:
        p = b["project"]
        reason = "explicitly blocked" if b["reason"] == "status_blocked" else "zero stock for required parts"
        lines.append(f"\n  ✗ {p['name'].upper()} [{p['status']}] [{p['priority']} priority] — {reason}")
        for pp in b["blocking_parts"][:5]:
            lines.append(
                f"      {pp['name']:<24} need:{pp.get('quantity_required',1)}  have:{pp.get('stock_qty',0)}"
            )
        if len(b["blocking_parts"]) > 5:
            lines.append(f"      … and {len(b['blocking_parts'])-5} more")
    return {"ok": True, "blocked": blocked, "summary": "\n".join(lines)}


def component_usage_stats(part: str = "") -> dict:
    stats = _hw().get_component_usage_stats()
    if part:
        needle = part.lower()
        stats = [s for s in stats if needle in s["part_name"].lower()]
    if not stats:
        ctx = f" matching '{part}'" if part else ""
        return {"ok": True, "summary": f"No components found{ctx}."}
    lines = [f"COMPONENT USAGE STATS — {len(stats)} parts"]
    for s in stats[:30]:
        proj_tag = (
            f"  ← {', '.join(s['project_names'][:3])}" + (" …" if len(s["project_names"]) > 3 else "")
            if s["project_names"] else ""
        )
        lines.append(
            f"  {s['part_name']:<28} [{s['category']:<14}] qty:{s['stock_qty']:<4}  {s['project_count']} project(s){proj_tag}"
        )
    return {"ok": True, "stats": stats, "summary": "\n".join(lines)}


def recommend_orders() -> dict:
    recs = _hw().get_order_recommendations()
    if not recs:
        return {"ok": True, "summary": "No purchase recommendations — all required parts for active projects are sufficiently stocked."}
    lines = [f"RECOMMENDED PURCHASES ({len(recs)} items):"]
    urgency_labels = {"critical": "CRITICAL", "high": "HIGH", "normal": "NORMAL"}
    for r in recs:
        projects_str = ", ".join(p["project_name"] for p in r["affected_projects"][:3])
        if len(r["affected_projects"]) > 3:
            projects_str += f" +{len(r['affected_projects'])-3}"
        lines.append(
            f"\n  [{urgency_labels.get(r['urgency'], 'NORMAL')}] Buy {r['buy_quantity']}× {r['part_name']}"
        )
        lines.append(f"    stock:{r['stock_qty']}  total needed:{r['total_needed']}  shortfall:{r['shortfall']}")
        lines.append(f"    Needed by: {projects_str}")
    return {"ok": True, "recommendations": recs, "summary": "\n".join(lines)}


def what_should_i_work_on() -> dict:
    priorities = _hw().get_project_priorities()
    if not priorities:
        return {"ok": True, "summary": "No active hardware projects found."}
    lines = [f"PROJECT PRIORITY RANKING ({len(priorities)} active projects):"]
    rec_labels = {
        "can_build": "CAN BUILD NOW",
        "nearly_ready": "NEARLY READY",
        "needs_parts": "NEEDS PARTS",
        "many_missing": "MANY MISSING",
    }
    for i, p in enumerate(priorities, 1):
        label = rec_labels.get(p["recommendation"], "")
        lines.append(
            f"\n  {i}. {p['project_name'].upper()} [{p['project_status']}] [{p['priority']}]"
        )
        lines.append(
            f"     Readiness: {p['readiness_pct']}%  Score: {p['score']}  → {label}"
        )
        if p["missing_count"]:
            lines.append(f"     Missing: {p['missing_count']} required part(s)")
    return {"ok": True, "priorities": priorities, "summary": "\n".join(lines)}


# ---------------------------------------------------------------------------
# Phase 12C — BOM / Inventory Import
# ---------------------------------------------------------------------------

def import_bom(path: str, project: str = "") -> dict:
    if not path.strip():
        return {"ok": False, "summary": "BOM path or filename is required."}
    try:
        result = HardwareImportService(_hw()).import_file(
            path.strip(),
            source_type="bom",
            project_name=project.strip(),
        )
    except Exception as exc:
        return {"ok": False, "error": "import_failed", "summary": f"BOM import failed: {exc}"}
    info = result["summary"]
    project_info = result.get("project") or {}
    readiness = result.get("readiness") or {}
    lines = [
        f"BOM IMPORTED: {info['imported_count']} component type(s)",
        f"  Source:  {info['source_path']}",
        f"  Project: {project_info.get('name', 'none')}" + (" (created)" if result.get("project_created") else ""),
        f"  Parts:   {info['created_parts']} created · {info['updated_parts']} matched/updated · {info['linked_parts']} linked",
    ]
    if readiness:
        lines.append(f"  Readiness: {readiness['readiness_pct']}% ({readiness['fulfilled_required']}/{readiness['total_required']} required in stock)")
        if readiness.get("missing"):
            lines.append("  Missing:")
            for item in readiness["missing"][:8]:
                lines.append(f"    - {item['name']} need:{item['quantity_required']} have:{item['stock_qty']}")
    if result.get("errors"):
        lines.append(f"  Validation warnings: {len(result['errors'])}")
    return {"ok": True, **result, "summary": "\n".join(lines)}


def import_inventory(path: str) -> dict:
    if not path.strip():
        return {"ok": False, "summary": "Inventory path or filename is required."}
    try:
        result = HardwareImportService(_hw()).import_file(
            path.strip(),
            source_type="inventory",
        )
    except Exception as exc:
        return {"ok": False, "error": "import_failed", "summary": f"Inventory import failed: {exc}"}
    info = result["summary"]
    lines = [
        f"INVENTORY IMPORTED: {info['imported_count']} component type(s)",
        f"  Source: {info['source_path']}",
        f"  Parts:  {info['created_parts']} created · {info['updated_parts']} updated",
    ]
    if result.get("errors"):
        lines.append(f"  Validation warnings: {len(result['errors'])}")
    return {"ok": True, **result, "summary": "\n".join(lines)}


def list_imports(limit: int = 10) -> dict:
    imports = _hw().list_imports(limit=limit)
    if not imports:
        return {"ok": True, "imports": [], "summary": "No BOM or inventory imports recorded yet."}
    lines = [f"IMPORT HISTORY — {len(imports)} recent import(s):"]
    for item in imports:
        project = f" → {item['project_name']}" if item.get("project_name") else ""
        lines.append(
            f"  [{item['id']}] {item['source_type']} {item['imported_count']} parts{project} · {item['source_path']}"
        )
    return {"ok": True, "imports": imports, "summary": "\n".join(lines)}


def show_imported_components(import_id: str = "") -> dict:
    imports = _hw().list_imports(limit=1)
    target_id = import_id.strip() or (imports[0]["id"] if imports else "")
    if not target_id:
        return {"ok": True, "items": [], "summary": "No imported components recorded yet."}
    items = _hw().list_import_items(target_id)
    if not items:
        return {"ok": True, "items": [], "summary": f"No imported components found for import {target_id}."}
    lines = [f"IMPORTED COMPONENTS [{target_id}] — {len(items)} item(s):"]
    for item in items[:40]:
        pn = f" pn:{item['part_number']}" if item.get("part_number") else ""
        lines.append(f"  - {item['raw_name']} x{item['quantity']}{pn} [{item['action']}]")
    return {"ok": True, "items": items, "summary": "\n".join(lines)}


def show_imported_projects() -> dict:
    imports = [item for item in _hw().list_imports(limit=50) if item.get("project_name")]
    if not imports:
        return {"ok": True, "projects": [], "summary": "No imported BOM projects recorded yet."}
    seen = {}
    for item in imports:
        seen[item["project_name"]] = item
    lines = [f"IMPORTED PROJECTS — {len(seen)} project(s):"]
    for name, item in sorted(seen.items()):
        lines.append(f"  - {name}: {item['imported_count']} imported part type(s), latest import {item['id']}")
    return {"ok": True, "projects": list(seen.values()), "summary": "\n".join(lines)}


def show_inventory_impact(project: str) -> dict:
    proj = _hw().find_project(project)
    if not proj:
        return {"ok": False, "summary": f"No hardware project found matching '{project}'."}
    impact = _hw().get_inventory_impact(proj["id"])
    if not impact:
        return {"ok": False, "summary": f"Could not compute inventory impact for '{project}'."}
    lines = [f"INVENTORY IMPACT: {impact['project_name']}"]
    for part in impact["parts"]:
        marker = "✓" if part["ok"] else "✗"
        lines.append(
            f"  {marker} {part['name']:<24} consume:{part['quantity_required']} stock:{part['stock_qty']} remaining:{part['remaining_after_build']}"
        )
    if impact["missing"]:
        lines.append(f"\nBlocked by {len(impact['missing'])} missing/short part(s).")
    return {"ok": True, "impact": impact, "summary": "\n".join(lines)}
