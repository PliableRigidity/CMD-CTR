"""Restricted Hardware Assistant for Hardware Board operations only."""
from __future__ import annotations

import re
from typing import Any

from backend.app.services.hardware_category_classifier import (
    classify_component,
    should_apply_classification,
)
from backend.app.services.hardware_import_service import HardwareImportService
from backend.app.services.hardware_service import HardwareService, _status_for_quantity


_CONFIRM_RE = re.compile(r"^(?:confirm|yes|yep|yeah|do it|apply|commit|ok(?:ay)?)\.?$", re.I)
_CANCEL_RE = re.compile(r"^(?:cancel|no|stop|nevermind|never mind)\.?$", re.I)
_CATEGORY_CONFIDENCE_THRESHOLD = 0.65


def _clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" :-\t\r\n")).strip()


def _parse_items(text: str) -> list[dict]:
    items = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.lower().rstrip(":") in {"i bought", "i received", "received", "add", "remove", "vendor"}:
            continue
        raw = re.sub(r"^[-*•]\s*", "", raw)
        match = re.match(r"^(?P<qty>\d+)\s*[x×]?\s+(?P<name>.+?)$", raw, re.I)
        if not match:
            match = re.match(r"^(?P<name>.+?)\s+[x×]\s*(?P<qty>\d+)$", raw, re.I)
        if not match:
            continue
        name = _clean_name(match.group("name"))
        if name:
            items.append({"name": name, "quantity": max(0, int(match.group("qty")))})
    return items


def _parse_substitutes(text: str) -> list[str]:
    match = re.search(r"(?is)(?:acceptable\s+substitutes?|substitutes?|substitute):?\s*(.+)$", text)
    if not match:
        return []
    raw = re.sub(r"(?i)\bfor\s+.+$", "", match.group(1)).strip()
    return [_clean_name(item) for item in re.split(r"[,;\n]+", raw) if _clean_name(item)]


def _preview_response(reply: str, action: dict, lines: list[str]) -> dict:
    return {
        "ok": True,
        "reply": reply + "\n\n" + "\n".join(lines) + "\n\nReply `confirm` to apply, or `cancel`.",
        "preview": lines,
        "pending_action": action,
        "committed": False,
    }


def _done(reply: str, data: Any = None) -> dict:
    return {"ok": True, "reply": reply, "data": data, "pending_action": None, "committed": True}


def _info(reply: str, data: Any = None) -> dict:
    return {"ok": True, "reply": reply, "data": data, "pending_action": None, "committed": False}


def _category_label(category: str) -> str:
    return {
        "gps_gnss": "GPS/GNSS",
        "sbc": "single-board computer",
    }.get(category, category)


def _category_with_subcategory(category: str, subcategory: str = "") -> str:
    label = _category_label(category)
    return f"{label} / {subcategory}" if subcategory else label


def _classification_preview(name: str, part: dict | None = None) -> tuple[str, dict]:
    if part and (part.get("category") or "misc").lower() != "misc":
        return f"category: {_category_with_subcategory(part['category'], part.get('subcategory', ''))} existing", {
            "category": part["category"],
            "subcategory": part.get("subcategory", ""),
            "confidence": 1.0,
            "reason": "Existing inventory category.",
        }
    classification = classify_component(name)
    data = {
        "category": classification.category,
        "subcategory": classification.subcategory,
        "confidence": classification.confidence,
        "matched": list(classification.matched),
        "reason": classification.reason,
    }
    if should_apply_classification(classification, _CATEGORY_CONFIDENCE_THRESHOLD):
        return f"category: {_category_with_subcategory(classification.category, classification.subcategory)} ({classification.confidence:.0%})", data
    return "category unclear: misc unless confirmed", data


class HardwareAssistantService:
    """A tiny domain assistant with no access outside hardware registries."""

    def __init__(self, hardware: HardwareService | None = None) -> None:
        self.hardware = hardware or HardwareService()

    def handle(self, message: str, pending_action: dict | None = None) -> dict:
        text = message.strip()
        if not text:
            return _info("Tell me what to do with inventory, projects, orders, or BOMs.")
        if pending_action:
            if _CONFIRM_RE.match(text):
                return self.execute(pending_action)
            if _CANCEL_RE.match(text):
                return _info("Cancelled. No hardware registry changes were made.")
            return _info("I have a pending preview. Reply `confirm` to apply it, or `cancel`.")

        lowered = text.lower()
        if re.search(r"\bwhich projects are blocked\b|\bblocked projects\b", lowered):
            return self._blocked_projects()
        if re.search(r"\bwhich projects can i build\b|\bwhat can i build\b|\bbuild right now\b", lowered):
            return self._buildable_projects()
        if "missing" in lowered:
            return self._missing_parts(text)
        if re.search(r"\bcan i (?:build|make)\b|\bready to build\b|\bbuild readiness\b", lowered):
            return self._build_readiness(text)
        req_m = (
            re.search(r"(?i)^(?:show\s+)?(?:hardware\s+|project\s+)?requirements?\s+for\s+(.+)$", text)
            or re.search(r"(?i)^show\s+(.+?)\s+requirements?$", text)
            or re.search(r"(?i)^what\s+parts?\s+(?:does|do)\s+(.+?)\s+(?:need|require)", text)
        )
        if req_m:
            return self._show_project(f"show project {_clean_name(req_m.group(1))}")
        if re.search(r"show imported boms?|show bom status|what components were imported|show imported components", lowered):
            return self._show_imports()
        if (
            "inventory will be consumed" in lowered
            or "what inventory" in lowered
            or "what parts will be consumed" in lowered
            or re.search(r"\bwhat parts would .+ use\b", lowered)
            or re.search(r"\bif i build .+ inventory remains\b", lowered)
        ):
            return self._inventory_impact(text)
        if re.search(r"show\s+(?:recent\s+)?deliveries\b|recent\s+deliveries\b|show\s+delivered\b", lowered):
            return self._show_orders("delivered")
        if re.search(r"show pending orders|pending orders", lowered):
            return self._show_orders("ordered")
        if re.search(r"\bshow\s+active\s+orders\b|\bwhat.s\s+on\s+order\b|\bwhat\s+is\s+on\s+order\b|\bactive\s+orders?\b", lowered):
            return self._show_active_orders()
        if re.search(r"\bshow\s+orders\b|\blist\s+orders\b|\ball\s+orders\b", lowered):
            return self._show_orders("")
        if re.search(r"^show\s+components\s+for|^show\s+parts\s+for", lowered):
            return self._show_project_parts(text)
        if re.search(r"^show\s+project\s+", lowered):
            return self._show_project(text)
        if re.search(r"^(?:show|list)\s+(?:all\s+)?(?:hw\s+|hardware\s+)?projects?\b", lowered):
            return self._show_projects(text)
        if re.search(r"^(?:show|list)\s+(?:all\s+)?(?:boms?|imports?)\b", lowered):
            return self._show_imports()
        if re.search(
            r"\bwhat\s+should\s+i\s+order\b|\bgenerate\s+order\s+list\b|\bcreate\s+procurement\s+list\b"
            r"|\bprocurement\s+list\b|\brecommend(?:ed)?\s+orders?\b|\border\s+recommendations?\b",
            lowered,
        ):
            return self._show_recommendations()
        if re.search(r"\bshow\s+low\s+stock\b|\bwhat\s+am\s+i\s+running\s+out\b|\blow\s+stock\b|\bstock\s+alerts?\b", lowered):
            return self._show_low_stock()
        if re.search(
            r"\bwhat\s+(?:projects?\s+)?(?:becomes?\s+buildable|will\s+be\s+buildable)\b"
            r"|\bafter\s+(?:delivery|deliveries|orders?\s+(?:arrive|land))\b"
            r"|\bproject\s+(?:completion\s+)?forecast\b"
            r"|\bwhat\s+can\s+i\s+build\s+after\b",
            lowered,
        ):
            return self._after_delivery_readiness()
        if re.search(r"^show\s+(?:all\s+)?inventory\b", lowered):
            return self._show_all_inventory()
        if re.search(r"^show\s+all\s+|^show\s+", lowered):
            return self._show_inventory(text)
        if re.search(r"how many .+ do i (?:own|have)", lowered):
            return self._show_inventory(text)
        action = self.plan_mutation(text)
        if action:
            return self.preview(action)
        return _info(
            "I can manage hardware inventory, projects, orders, and BOMs only. "
            "Try `I bought:`, `remove 2 ESP32-S3`, `create project Rover`, or `can I build Rover`."
        )

    def plan_mutation(self, text: str) -> dict | None:
        lowered = text.lower()
        items = _parse_items(text)
        if re.search(r"\b(recategorize|categorize|reclassify|clean)\b.*\b(inventory|categories|category)\b", lowered):
            return {"type": "recategorize_inventory"}
        requirements_match = re.search(r"(?is)^(?P<project>.+?)\s+requires:?\s*(?P<body>.*)$", text)
        if requirements_match:
            project = _clean_name(requirements_match.group("project"))
            body = requirements_match.group("body")
            items = _parse_items(body)
            if items:
                return {
                    "type": "add_project_requirements",
                    "project": project,
                    "items": items,
                    "source": "Hardware Assistant chat",
                    "substitutes": {},
                }
        required_match = re.search(
            r"(?is)^add\s+(?P<part>.+?)\s+as\s+required\s+part\s+for\s+(?P<project>.+?)(?:\s+quantity\s+(?P<qty>\d+))?(?:\s+(?:substitute|substitutes|acceptable substitutes?)\s+(?P<subs>.+))?$",
            text,
        )
        if required_match:
            part = _clean_name(required_match.group("part"))
            substitutes = [
                _clean_name(item)
                for item in re.split(r"[,;]+", required_match.group("subs") or "")
                if _clean_name(item)
            ]
            return {
                "type": "add_project_requirements",
                "project": _clean_name(required_match.group("project")),
                "items": [{"name": part, "quantity": int(required_match.group("qty") or 1)}],
                "source": "Hardware Assistant chat",
                "substitutes": {part: substitutes} if substitutes else {},
            }
        # Single-item order: "order 5 ESP32-S3" / "order ESP32-S3 x5 from AliExpress"
        order_create_m = re.match(
            r"(?i)^order\s+(?P<qty>\d+)\s+(?P<part>.+?)(?:\s+from\s+(?P<vendor>.+))?$", text
        ) or re.match(
            r"(?i)^order\s+(?P<part>.+?)\s+x\s*(?P<qty>\d+)(?:\s+from\s+(?P<vendor>.+))?$", text
        )
        if order_create_m:
            part = _clean_name(order_create_m.group("part"))
            qty = int(order_create_m.group("qty"))
            vendor = _clean_name(order_create_m.group("vendor") or "")
            if part and qty > 0:
                return {"type": "create_order", "part": part, "quantity": qty, "vendor": vendor}
        # Reorder threshold: "set reorder threshold for ESP32-S3 to 5"
        threshold_m = re.search(
            r"(?i)^set\s+(?:reorder\s+)?threshold\s+(?:for\s+)?(.+?)\s+to\s+(\d+)$", text
        )
        if threshold_m:
            return {
                "type": "set_threshold",
                "part": _clean_name(threshold_m.group(1)),
                "threshold": int(threshold_m.group(2)),
            }
        if re.search(r"\b(import|ingest|load)\s+bom\b", lowered):
            path = re.sub(r"(?i)^.*?\b(?:import|ingest|load)\s+bom\s+", "", text).strip()
            return {"type": "import_bom", "path": path, "project": ""}
        if re.search(r"\b(import|ingest|load)\s+inventory\b", lowered):
            path = re.sub(r"(?i)^.*?\b(?:import|ingest|load)\s+inventory\s+", "", text).strip()
            return {"type": "import_inventory", "path": path}
        if re.search(r"\bmark order\b.*\bdelivered\b|\border delivered\b", lowered):
            query = re.sub(r"(?i)\bmark order\b|\bas delivered\b|\bdelivered\b", "", text).strip()
            return {"type": "mark_order_delivered", "query": query}
        if re.search(r"\b(?:log|create)\s+order\b|\border:\b|\bvendor:\b", lowered):
            vendor_match = re.search(r"(?im)^vendor:\s*(.+)$", text)
            vendor = _clean_name(vendor_match.group(1)) if vendor_match else ""
            order_items = items or _parse_items(re.sub(r"(?i)^log order:?", "", text))
            if order_items:
                return {"type": "log_order", "items": order_items, "vendor": vendor}
        assign_match = re.search(r"(?is)\bassign:?\s*(?P<part>.+?)\s+(?:to|for)\s+(?P<project>.+)$", text)
        if not assign_match:
            assign_match = re.search(r"(?is)^assign\s+(?P<part>.+?)\s+to\s+(?P<project>.+)$", text)
        if assign_match:
            return {
                "type": "assign_part",
                "part": _clean_name(assign_match.group("part")),
                "project": _clean_name(assign_match.group("project")),
                "quantity": 1,
            }
        project_match = re.search(r"(?i)^create\s+project:?\s*(?P<name>.+)$", text)
        if project_match:
            return {"type": "create_project", "name": _clean_name(project_match.group("name"))}
        if re.search(r"\bremove\b|\bconsume\b|\bused\b", lowered):
            remove_items = items or _parse_items(re.sub(r"(?i)^remove:?", "", text))
            if remove_items:
                return {"type": "bulk_remove_inventory", "items": remove_items}
        if re.search(r"\bi bought\b|\bi received\b|\breceived:\b|^add:|^add\s+", lowered):
            add_items = items or _parse_items(re.sub(r"(?i)^add:?", "", text))
            if add_items:
                return {"type": "bulk_add_inventory", "items": add_items}
        return None

    def preview(self, action: dict) -> dict:
        kind = action["type"]
        if kind == "bulk_add_inventory":
            lines = []
            for item in action["items"]:
                part = self.hardware.find_part_smart(item["name"])
                before = int(part["quantity"]) if part else 0
                category_text, classification = _classification_preview(item["name"], part)
                item["classification"] = classification
                lines.append(f"- {item['name']}: {before} → {before + item['quantity']} ({category_text})")
            return _preview_response("Inventory add preview:", action, lines)
        if kind == "bulk_remove_inventory":
            lines = []
            for item in action["items"]:
                part = self.hardware.find_part_smart(item["name"])
                before = int(part["quantity"]) if part else 0
                lines.append(f"- {item['name']}: {before} → {max(0, before - item['quantity'])}")
            return _preview_response("Inventory removal preview:", action, lines)
        if kind == "recategorize_inventory":
            suggestions = self._recategorization_suggestions()
            if not suggestions:
                return _info("No confident category fixes found for existing MISC inventory items.")
            action["suggestions"] = suggestions
            lines = [
                f"- {s['name']}: misc → {_category_with_subcategory(s['category'], s.get('subcategory', ''))} ({s['confidence']:.0%}; {s['reason']})"
                for s in suggestions
            ]
            return _preview_response("Inventory category cleanup preview:", action, lines)
        if kind == "add_project_requirements":
            project = action["project"]
            lines = []
            for item in action["items"]:
                substitutes = action.get("substitutes", {}).get(item["name"], [])
                suffix = f" substitutes: {', '.join(substitutes)}" if substitutes else ""
                lines.append(f"- {project} requires {item['name']} ×{item['quantity']}{suffix}")
            return _preview_response("Project requirements preview:", action, lines)
        if kind == "create_project":
            return _preview_response("Project creation preview:", action, [f"- Create project `{action['name']}`"])
        if kind == "assign_part":
            return _preview_response("Project assignment preview:", action, [f"- Assign {action['part']} ×{action['quantity']} to {action['project']}"])
        if kind == "log_order":
            vendor = f" from {action['vendor']}" if action.get("vendor") else ""
            return _preview_response("Order log preview:", action, [f"- {i['name']} ×{i['quantity']}{vendor}" for i in action["items"]])
        if kind == "mark_order_delivered":
            order = self._resolve_order(action.get("query", ""))
            if not order:
                return _info("No pending order matched that request.")
            action["order_id"] = order["id"]
            return _preview_response("Order delivery preview:", action, [f"- Mark [{order['id']}] {order['part_name']} ×{order['quantity']} delivered"])
        if kind == "import_bom":
            return _preview_response("BOM import preview:", action, [f"- Import BOM `{action['path']}`"])
        if kind == "import_inventory":
            return _preview_response("Inventory import preview:", action, [f"- Import inventory `{action['path']}`"])
        if kind == "create_order":
            vendor = f" from {action['vendor']}" if action.get("vendor") else ""
            part = self.hardware.find_part_smart(action["part"])
            stock = f" ({part['quantity']} in stock)" if part else " (not yet in inventory)"
            return _preview_response("Order preview:", action, [f"- {action['part']} ×{action['quantity']}{vendor}{stock}"])
        if kind == "set_threshold":
            part = self.hardware.find_part_smart(action["part"])
            if not part:
                return _info(f"No part found matching `{action['part']}`.")
            return _preview_response(
                "Reorder threshold preview:", action,
                [f"- {part['name']}: alert when quantity ≤ {action['threshold']} units"],
            )
        return _info("I could not preview that hardware action.")

    def execute(self, action: dict) -> dict:
        kind = action["type"]
        if kind == "bulk_add_inventory":
            changed = []
            for item in action["items"]:
                part = self.hardware.find_part_smart(item["name"])
                if part:
                    new_qty = int(part["quantity"]) + item["quantity"]
                    updates = {"quantity": new_qty, "status": _status_for_quantity(new_qty)}
                    classification = classify_component(
                        part["name"],
                        manufacturer=part.get("manufacturer", ""),
                        part_number=part.get("part_number", ""),
                        notes=part.get("notes", ""),
                    )
                    if (part.get("category") or "misc").lower() == "misc" and should_apply_classification(classification, _CATEGORY_CONFIDENCE_THRESHOLD):
                        updates["category"] = classification.category
                        if classification.subcategory:
                            updates["subcategory"] = classification.subcategory
                    updated = self.hardware.update_part(part["id"], **updates) or part
                    category_note = f" [{_category_with_subcategory(updated['category'], updated.get('subcategory', ''))}]" if updates.get("category") else ""
                    changed.append(f"{part['name']}: {part['quantity']} → {new_qty}{category_note}")
                else:
                    created = self.hardware.add_part(item["name"], quantity=item["quantity"], status=_status_for_quantity(item["quantity"]))
                    changed.append(f"{created['name']}: 0 → {created['quantity']} [{_category_with_subcategory(created['category'], created.get('subcategory', ''))}]")
            return _done("Inventory updated:\n" + "\n".join(f"- {line}" for line in changed))
        if kind == "bulk_remove_inventory":
            changed = []
            for item in action["items"]:
                part = self.hardware.find_part_smart(item["name"])
                if not part:
                    changed.append(f"{item['name']}: not found")
                    continue
                new_qty = max(0, int(part["quantity"]) - item["quantity"])
                self.hardware.update_part(part["id"], quantity=new_qty, status=_status_for_quantity(new_qty))
                changed.append(f"{part['name']}: {part['quantity']} → {new_qty}")
            return _done("Inventory updated:\n" + "\n".join(f"- {line}" for line in changed))
        if kind == "recategorize_inventory":
            suggestions = action.get("suggestions") or self._recategorization_suggestions()
            if not suggestions:
                return _info("No confident category fixes found for existing MISC inventory items.")
            changed = []
            for suggestion in suggestions:
                part = self.hardware.get_part_by_id(suggestion["part_id"])
                if not part or (part.get("category") or "").lower() != "misc":
                    continue
                updated = self.hardware.update_part(
                    part["id"],
                    category=suggestion["category"],
                    subcategory=suggestion.get("subcategory", ""),
                )
                if updated:
                    changed.append(f"{updated['name']}: misc → {_category_with_subcategory(updated['category'], updated.get('subcategory', ''))}")
            if not changed:
                return _info("No MISC inventory items still needed category cleanup.")
            return _done("Inventory categories updated:\n" + "\n".join(f"- {line}" for line in changed))
        if kind == "add_project_requirements":
            changed = []
            project = action["project"]
            substitutes_by_part = action.get("substitutes", {})
            for item in action["items"]:
                result = self.hardware.add_project_requirement(
                    project,
                    item["name"],
                    item["quantity"],
                    acceptable_substitutes=substitutes_by_part.get(item["name"], []),
                    source=action.get("source", "Hardware Assistant chat"),
                    notes="Recorded by Hardware Assistant",
                )
                changed.append(f"{result['project']['name']}: {result['part']['name']} ×{item['quantity']}")
            return _done("Project requirements updated:\n" + "\n".join(f"- {line}" for line in changed))
        if kind == "create_project":
            project, created = self.hardware.get_or_create_project(action["name"], notes="Created by Hardware Assistant")
            return _done(("Created" if created else "Found existing") + f" project `{project['name']}`.", project)
        if kind == "assign_part":
            part = self.hardware.find_part_smart(action["part"])
            project, _ = self.hardware.get_or_create_project(action["project"], notes="Created by Hardware Assistant assignment")
            if not part:
                return _info(f"No component matching `{action['part']}` exists in inventory.")
            self.hardware.assign_part_to_project(project["id"], part["id"], action.get("quantity", 1))
            return _done(f"Assigned {part['name']} to {project['name']}.")
        if kind == "log_order":
            orders = []
            for item in action["items"]:
                orders.append(self.hardware.add_order(item["name"], vendor=action.get("vendor", ""), quantity=item["quantity"]))
            return _done("Order(s) logged:\n" + "\n".join(f"- [{o['id']}] {o['part_name']} ×{o['quantity']}" for o in orders), orders)
        if kind == "mark_order_delivered":
            order = self.hardware.get_order(action.get("order_id", "")) or self._resolve_order(action.get("query", ""))
            if not order:
                return _info("No order matched that delivery request.")
            result = self.hardware.receive_order(order["id"])
            if not result:
                return _info("Failed to process delivery.")
            updated = result["order"]
            part = result["part"]
            return _done(
                f"Delivered [{updated['id']}] {updated['part_name']}. "
                f"Inventory: {part['name']} now {part['quantity']} in stock.",
                result,
            )
        if kind == "import_bom":
            result = HardwareImportService(self.hardware).import_file(action["path"], source_type="bom", project_name=action.get("project", ""))
            return _done(f"Imported BOM: {result['summary']['imported_count']} component type(s).", result)
        if kind == "import_inventory":
            result = HardwareImportService(self.hardware).import_file(action["path"], source_type="inventory")
            return _done(f"Imported inventory: {result['summary']['imported_count']} component type(s).", result)
        if kind == "create_order":
            order = self.hardware.add_order(
                action["part"], vendor=action.get("vendor", ""), quantity=action["quantity"]
            )
            return _done(f"Order created: [{order['id']}] {order['part_name']} ×{order['quantity']}", order)
        if kind == "set_threshold":
            part = self.hardware.find_part_smart(action["part"])
            if not part:
                return _info(f"No part found matching `{action['part']}`.")
            updated = self.hardware.update_part(part["id"], reorder_threshold=action["threshold"])
            return _done(f"Reorder threshold set: {updated['name']} → {action['threshold']} units", updated)
        return _info("I could not execute that hardware action.")

    def _recategorization_suggestions(self) -> list[dict]:
        suggestions = []
        for part in self.hardware.list_parts(category="misc"):
            classification = classify_component(
                part["name"],
                manufacturer=part.get("manufacturer", ""),
                part_number=part.get("part_number", ""),
                notes=part.get("notes", ""),
            )
            if should_apply_classification(classification, _CATEGORY_CONFIDENCE_THRESHOLD):
                suggestions.append({
                    "part_id": part["id"],
                    "name": part["name"],
                    "category": classification.category,
                    "subcategory": classification.subcategory,
                    "confidence": classification.confidence,
                    "matched": list(classification.matched),
                    "reason": classification.reason,
                })
        return suggestions

    def _resolve_order(self, query: str) -> dict | None:
        if query:
            return self.hardware.find_order(query)
        for status in ("ordered", "manufacturing", "shipped"):
            orders = self.hardware.list_orders(status=status)
            if orders:
                return orders[0]
        return None

    def _show_projects(self, text: str) -> dict:
        lowered = text.lower()
        status_match = re.search(
            r"(?i)\b(planned|researching|designing|ordering|waiting[_\s]for[_\s]parts|"
            r"building|testing|blocked|completed?|archived|active|paused?|abandoned)\b",
            lowered,
        )
        status = status_match.group(1).replace(" ", "_") if status_match else ""
        projects = self.hardware.list_projects(status=status)
        if not projects:
            label = f" with status '{status}'" if status else ""
            return _info(f"No hardware projects found{label}.")
        label = f" [{status}]" if status else ""
        lines = [f"Hardware projects ({len(projects)}){label}:"]
        for p in projects[:30]:
            lines.append(f"- {p['name']} [{p['status']}] priority:{p.get('priority', 'normal')}")
        return _info("\n".join(lines), projects)

    def _show_all_inventory(self) -> dict:
        parts = self.hardware.list_parts()
        if not parts:
            return _info("No inventory parts found.")
        return _info("Inventory:\n" + "\n".join(f"- {p['name']} qty:{p['quantity']} [{p['category']}]" for p in parts[:50]), parts)

    def _show_inventory(self, text: str) -> dict:
        query = re.sub(r"(?i)^show\s+(?:all\s+)?|^how many\s+|do i (?:own|have)\??", "", text).strip()
        query = query.replace("boards", "board").rstrip("?")
        category_query = {
            "microcontrollers": "microcontroller",
            "microcontroller": "microcontroller",
            "controllers": "microcontroller",
            "sensors": "sensor",
            "sensor": "sensor",
            "single board computers": "sbc",
            "single-board computers": "sbc",
            "single-board computer": "sbc",
            "sbc": "sbc",
            "sbcs": "sbc",
            "gps": "gps_gnss",
            "gnss": "gps_gnss",
            "gps modules": "gps_gnss",
            "radios": "radio",
            "radio": "radio",
            "displays": "display",
            "display": "display",
            "motors": "motor",
            "motor": "motor",
            "power": "power",
        }.get(query.lower())
        parts = self.hardware.list_parts(category=category_query) if category_query else self.hardware.list_parts(search=query)
        if not parts:
            return _info(f"No inventory parts found matching `{query}`.")
        return _info("Inventory:\n" + "\n".join(f"- {p['name']} qty:{p['quantity']} [{p['category']}]" for p in parts[:30]), parts)

    def _show_project(self, text: str) -> dict:
        name = _clean_name(re.sub(r"(?i)^show\s+project\s+", "", text))
        project = self.hardware.find_project(name)
        if not project:
            return _info(f"No hardware project found matching `{name}`.")
        detail = self.hardware.get_project_with_parts(project["id"])
        lines = [f"{detail['name']} [{detail['status']}]", f"Parts: {detail['part_count']}"]
        for part in detail["parts"][:20]:
            lines.append(f"- {part['name']} need:{part['quantity_required']} have:{part['stock_qty']}")
        return _info("\n".join(lines), detail)

    def _show_project_parts(self, text: str) -> dict:
        name = _clean_name(re.sub(r"(?i)^show\s+(?:components|parts)\s+for\s+", "", text))
        return self._show_project(f"show project {name}")

    def _missing_parts(self, text: str) -> dict:
        match = re.search(r"(?i)\bfor\s+(.+)$", text)
        if not match:
            match = re.search(r"(?i)\bmissing\s+(.+)$", text)
        if match:
            project = self.hardware.find_project(_clean_name(match.group(1)))
            if project:
                readiness = self.hardware.get_build_readiness(project["id"])
                if readiness and readiness.get("status") == "no_required_parts":
                    return _info(
                        f"I do not have requirements recorded for {project['name']} yet.\n"
                        "Add requirements manually or import a BOM.",
                        readiness,
                    )
                missing = readiness.get("missing", []) if readiness else []
                if not missing:
                    return _info(f"No missing parts for {project['name']}.")
                return _info(
                    f"Missing parts for {project['name']}:\n"
                    + "\n".join(f"- {m['name']} need:{m['quantity_required']} available:{m.get('available_qty', m.get('stock_qty', 0))} missing:{m['shortfall']}" for m in missing),
                    missing,
                )
        data = self.hardware.get_all_missing_parts()
        if not data:
            return _info("No missing parts across active hardware projects.")
        lines = []
        for entry in data:
            lines.append(f"{entry['project_name']}:")
            lines.extend(f"- {m['name']} need:{m['quantity_required']} have:{m['stock_qty']}" for m in entry["missing"])
        return _info("\n".join(lines), data)

    def _build_readiness(self, text: str) -> dict:
        name = _clean_name(re.sub(r"(?i)^.*?(?:build|make|for)\s+", "", text).rstrip("?"))
        name = _clean_name(re.sub(r"(?i)^another\s+", "", name))
        project = self.hardware.find_project(name)
        if not project:
            return _info(f"No hardware project found matching `{name}`.")
        readiness = self.hardware.get_build_readiness(project["id"])
        if readiness and readiness.get("status") == "no_required_parts":
            return _info(
                f"I do not have requirements recorded for {project['name']} yet.\n"
                "Add requirements manually or import a BOM.",
                readiness,
            )
        missing = readiness.get("missing", []) if readiness else []
        if not missing:
            lines = [f"Yes. {readiness['project_name']} is 100% ready: all required parts are available."]
        else:
            lines = [f"No. {readiness['project_name']} is {readiness['readiness_pct']}% ready ({readiness['status']})."]
            lines.append("Missing:")
            lines.extend(f"- {m['name']} ×{m['shortfall']} (need:{m['quantity_required']} available:{m.get('available_qty', m.get('stock_qty', 0))})" for m in missing)
        if readiness.get("available"):
            lines.append("Available:")
            lines.extend(f"- {p['name']} need:{p['quantity_required']} available:{p.get('available_qty', p.get('stock_qty', 0))}" for p in readiness["available"][:20])
        return _info("\n".join(lines), readiness)

    def _buildable_projects(self) -> dict:
        readiness = [
            item for item in self.hardware.get_all_readiness()
            if item.get("status") == "ready" and item.get("total_required", 0) > 0
        ]
        if not readiness:
            return _info("No projects with recorded requirements are fully build-ready right now.")
        return _info(
            "Build-ready projects:\n" + "\n".join(f"- {item['project_name']} ({item['total_required']} required part types)" for item in readiness),
            readiness,
        )

    def _blocked_projects(self) -> dict:
        readiness = [
            item for item in self.hardware.get_all_readiness()
            if item.get("status") not in {"ready", "no_required_parts"}
        ]
        if not readiness:
            return _info("No projects with recorded requirements are currently blocked by inventory.")
        lines = ["Projects blocked or missing parts:"]
        for item in readiness:
            lines.append(f"- {item['project_name']}: {item['readiness_pct']}% ready")
            lines.extend(f"  missing {m['name']} ×{m['shortfall']}" for m in item.get("missing", [])[:5])
        return _info("\n".join(lines), readiness)

    def _show_recommendations(self) -> dict:
        recs = self.hardware.get_order_recommendations()
        if not recs:
            return _info("No parts need ordering. All required components are sufficiently stocked.")
        urgency_label = {"critical": "CRITICAL", "high": "HIGH", "normal": ""}
        lines = [f"Recommended order ({len(recs)} item(s)):"]
        for r in recs[:20]:
            ul = urgency_label.get(r["urgency"], "")
            prefix = f"[{ul}] " if ul else ""
            projects = ", ".join(p["project_name"] for p in r["affected_projects"][:2])
            if len(r["affected_projects"]) > 2:
                projects += f" +{len(r['affected_projects']) - 2}"
            lines.append(f"- {prefix}{r['part_name']} x{r['buy_quantity']} (have:{r['stock_qty']} need:{r['total_needed']}) — {projects}")
        return _info("\n".join(lines), recs)

    def _show_low_stock(self) -> dict:
        items = self.hardware.get_low_stock()
        if not items:
            return _info("No items below reorder threshold. Set thresholds with: set reorder threshold for <part> to <qty>")
        lines = [f"Low stock alert ({len(items)} items):"]
        for item in items[:25]:
            lines.append(
                f"- {item['name']}: {item['quantity']} in stock "
                f"(threshold: {item['reorder_threshold']}, need {item['shortfall']} more)"
            )
        return _info("\n".join(lines), items)

    def _show_active_orders(self) -> dict:
        orders = self.hardware.get_active_orders()
        if not orders:
            return _info("No active orders. Use `order 5 ESP32-S3` to create one.")
        lines = [f"Active orders ({len(orders)}):"]
        for o in orders[:25]:
            vendor = f" [{o['vendor']}]" if o.get("vendor") else ""
            eta = f" ETA:{o['expected_delivery']}" if o.get("expected_delivery") else ""
            lines.append(f"- [{o['id']}] {o['part_name']} ×{o['quantity']} [{o['status']}]{vendor}{eta}")
        return _info("\n".join(lines), orders)

    def _after_delivery_readiness(self) -> dict:
        results = self.hardware.get_after_delivery_readiness()
        if not results:
            return _info("No active orders pending. Place orders first.")
        buildable = [r for r in results if r["becomes_buildable"]]
        still_blocked = [r for r in results if not r["becomes_buildable"]]
        lines = []
        if buildable:
            lines.append(f"Becomes buildable after delivery ({len(buildable)} project(s)):")
            for r in buildable:
                lines.append(f"  ✓ {r['project_name']} — all parts covered by incoming orders")
        if still_blocked:
            lines.append(f"\nStill missing parts after delivery ({len(still_blocked)} project(s)):")
            for r in still_blocked:
                for m in r["still_missing"][:3]:
                    lines.append(f"  ✗ {r['project_name']}: {m['name']} still need ×{m['remaining']}")
        if not lines:
            lines.append("No active projects with recorded requirements found.")
        return _info("\n".join(lines), results)

    def _show_orders(self, status: str) -> dict:
        orders = self.hardware.list_orders(status=status)
        if not orders:
            label = f"{status} " if status else ""
            return _info(f"No {label}orders found.")
        return _info("Orders:\n" + "\n".join(f"- [{o['id']}] {o['part_name']} ×{o['quantity']} [{o['status']}]" for o in orders[:25]), orders)

    def _show_imports(self) -> dict:
        imports = self.hardware.list_imports(limit=10)
        if not imports:
            return _info("No BOM or inventory imports recorded yet.")
        return _info("Recent imports:\n" + "\n".join(f"- [{i['id']}] {i['source_type']} {i['imported_count']} parts → {i.get('project_name') or 'inventory'}" for i in imports), imports)

    def _inventory_impact(self, text: str) -> dict:
        name = text
        patterns = [
            r"(?is)^what\s+parts\s+would\s+(.+?)\s+use\??$",
            r"(?is)^if\s+i\s+build\s+(.+?),?\s+what\s+inventory\s+remains\??$",
            r"(?is)^.*?(?:for|by)\s+(.+?)\??$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1)
                break
        name = _clean_name(name.rstrip("?"))
        project = self.hardware.find_project(name)
        if not project:
            return _info(f"No hardware project found matching `{name}`.")
        impact = self.hardware.get_inventory_impact(project["id"])
        if not impact["parts"]:
            return _info(
                f"I do not have requirements recorded for {project['name']} yet.\n"
                "Add requirements manually or import a BOM.",
                impact,
            )
        lines = [f"Inventory impact for {impact['project_name']}:"]
        lines.extend(
            f"- {p['name']} use:{p['quantity_required']} available:{p.get('available_qty', p.get('stock_qty', 0))} remaining:{p['remaining_after_build']}"
            for p in impact["parts"]
        )
        return _info("\n".join(lines), impact)
