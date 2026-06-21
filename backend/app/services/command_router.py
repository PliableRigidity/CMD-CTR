"""Command Router v2 — classify every command before execution.

Every query is classified into exactly one category with one owner.
The classification gates routing: Web Search never fires unless
the command is explicitly classified as web_search.

Categories:
  conversation        — greetings, opinions, social chat
  application_control — open/launch/close apps, SSH, volume, boards
  infrastructure      — nodes, telemetry, hardware, diagnostics, fleet
  knowledge           — KG, project memory, decisions, lessons, Brain63
  productivity        — email, calendar, reminders, tasks, briefings
  web_search          — news, prices, factual lookups, "search for X"
"""
from __future__ import annotations

import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger("silvia.router")

_ROUTE_LOG: deque[dict] = deque(maxlen=50)


@dataclass
class CommandRoute:
    category: str
    owner: str
    confidence: int
    query: str
    intents: list[dict] = field(default_factory=list)
    timestamp: str = ""


# ── Wake word prefix stripping ──────────────────────────────────────────────
_WAKE_PREFIX_RE = re.compile(
    r"^(?:hey\s+silvia|hey\s+sil|yo\s+sil(?:via)?|silvia|sil|hey\s+there)\s*,?\s*",
    re.I,
)


def strip_wake_prefix(q: str) -> str:
    """Remove wake word prefix so downstream handlers see pure intent."""
    stripped = _WAKE_PREFIX_RE.sub("", q).strip()
    return stripped if stripped else q


# ── Productivity targets — excluded from app-control verb matching ───────────
_PROD_NOUNS = (
    r"(?:my\s+)?(?:emails?|gmail|inbox|unread|calendar|schedule|events?|meetings?|"
    r"reminders?|tasks?|contacts?|drive|briefing|review|focus)"
)

# ── Pattern groups ───────────────────────────────────────────────────────────

def _is_show_routing(q: str) -> bool:
    return bool(re.match(
        r"^(?:show\s+)?(?:command\s+routing|last\s+route)[\s\.\?!]*$", q, re.I
    ))


def _is_productivity(q: str) -> tuple[bool, str]:
    if re.search(r"\b(?:email|gmail|inbox|unread)\b", q):
        return True, "Gmail"
    if re.match(r"^(?:check|show|get|display|read)\s+(?:my\s+)?(?:emails?|inbox|mail|unread)", q):
        return True, "Gmail"
    if re.search(r"\b(?:send|draft|compose)\s+(?:an?\s+)?email\b", q):
        return True, "Gmail"
    if re.match(r"^(?:connect\s+to\s+google|google\s+auth|sign\s+in\s+to\s+google)", q):
        return True, "GoogleAuth"
    if re.match(r"^(?:productivity|gmail|google)\s+status", q):
        return True, "GoogleAuth"
    if re.search(r"\b(?:calendar|schedule|appointment)\b", q) and not re.search(r"\bcalibrat", q):
        return True, "Calendar"
    if re.match(r"^(?:what'?s?\s+on\s+my\s+(?:calendar|schedule)|today'?s?\s+schedule)", q):
        return True, "Calendar"
    if re.match(r"^(?:create|book|schedule)\s+(?:a\s+)?(?:event|meeting|appointment)\b", q):
        return True, "Calendar"
    if re.match(r"^(?:delete|cancel)\s+(?:event|meeting|appointment)\b", q):
        return True, "Calendar"
    if re.search(r"\bremind(?:er|ers|)\b", q) and not re.match(r"^(?:dismiss|clear|pause|resume)\s+", q):
        if re.match(r"^(?:remind\s+me|show\s+reminder|list\s+reminder|delete\s+reminder|complete\s+reminder)", q):
            return True, "Reminders"
    if re.match(r"^(?:add|show|list|complete|delete|mark)\s+(?:my\s+)?(?:pending\s+|completed?\s+|all\s+)?tasks?\b", q):
        return True, "Tasks"
    if re.match(r"^(?:my\s+)?tasks?\s*\??$", q):
        return True, "Tasks"
    if re.match(r"^(?:morning\s+briefing|evening\s+review|daily\s+focus|weekly\s+review|"
                r"forgotten\s+items|project\s+health|what\s+should\s+i\s+(?:focus|work)\s+on|"
                r"good\s+morning|day\s+review|wrap\s+up|eod|what\s+did\s+i\s+accomplish)", q):
        return True, "MissionControl"
    if re.match(r"^(?:list|show|my|what\s+are)\s+(?:my\s+)?(?:current\s+)?(?:ongoing\s+)?projects?\s*\??$", q):
        return True, "Projects"
    if re.match(r"^(?:what\s+(?:projects?|work)\s+(?:am\s+i|do\s+i)\s+(?:working\s+on|doing))", q):
        return True, "Projects"
    if re.match(r"^(?:active|blocked|paused)\s+projects?\s*\??$", q):
        return True, "Projects"
    if re.match(r"^(?:let'?s?\s+)?(?:work\s+on|focus\s+on|switch\s+to|working\s+on|set\s+focus\s+to)\s+", q):
        return True, "Presence"
    if re.match(r"^set\s+\w+\s+as\s+active\b", q):
        return True, "Presence"
    if re.match(r"^(?:start|begin|end|stop|wrap\s+up)\s+(?:a\s+)?(?:work\s+)?session\b", q):
        return True, "Presence"
    if re.match(r"^focus\s+mode\s+(?:on|off)\s*$", q):
        return True, "Presence"
    if re.match(r"^(?:show\s+)?(?:presence|conversation)\s+(?:status|context)\s*$", q):
        return True, "Presence"
    if re.match(r"^reset\s+(?:conversation\s+)?context\s*$", q):
        return True, "Presence"
    if re.match(r"^(?:what|show|list)\s+(?:scheduled|recurring)\s+tasks?", q):
        return True, "ScheduledTasks"
    if re.match(r"^(?:schedule\s+task|disable\s+scheduled|delete\s+scheduled)", q):
        return True, "ScheduledTasks"
    if re.match(r"^(?:what\s+time|what'?s?\s+the\s+time|current\s+time)", q):
        return True, "Time"
    if re.match(r"^(?:time\s+in\s+|what\s+time\s+is\s+it\s+in\s+)", q):
        return True, "Time"
    if re.match(r"^(?:set|change|update|switch|use)\s+(?:my\s+)?(?:time\s*zone|timezone|tz)\b", q):
        return True, "Time"
    return False, ""


def _is_infrastructure(q: str) -> tuple[bool, str]:
    if re.match(r"^(?:show\s+)?ssh\s+diagnostics[\s\.\?!]*$", q):
        return True, "SSHDiagnostics"
    if re.match(r"^(?:deep\s+system\s+check|(?:run\s+)?(?:silvia\s+)?diagnostics|"
                r"system\s+(?:health|diagnostics)|health\s+check|check\s+all\s+systems)", q):
        return True, "Diagnostics"
    if re.match(r"^(?:show\s+)?reminder\s+(?:diagnostics|health|status)\s*$", q):
        return True, "Diagnostics"
    if re.match(r"^(?:dismiss|clear|fix|reset|pause|resume|mute|unmute|stop\s+all)\s+"
                r"(?:stuck\s+)?reminders?\b", q):
        return True, "Diagnostics"
    if re.match(r"^(?:ping|verify|probe)\s+(?!my\s+(?:email|inbox|calendar))", q):
        return True, "NodeService"
    if re.match(r"^(?:list|show)\s+(?:all\s+)?(?:nodes?|drones?|robots?|devices?|machines?|sensors?)\b", q):
        return True, "NodeService"
    if re.match(r"^(?:add|register)\s+(?:node|device)\b", q):
        return True, "NodeService"
    if re.match(r"^(?:delete|remove)\s+(?:node|device)\b", q):
        return True, "NodeService"
    if re.match(r"^(?:merge|deduplicate|consolidate)\s+(?:nodes?|devices?)", q):
        return True, "NodeService"
    if re.match(r"^(?:verify|refresh)\s+(?:all\s+)?nodes", q):
        return True, "NodeService"
    if re.match(r"^(?:arm|disarm|land|reboot|emergency[\s_]?stop)\s+", q):
        return True, "NodeCommand"
    if re.match(r"^(?:land|disarm|arm|reboot|emergency[\s_]?stop)\s+all\s+", q):
        return True, "FleetCommand"
    if re.search(r"\btelemetry\b", q):
        return True, "Telemetry"
    if re.match(r"^(?:show|get|display)\s+(?:\w+\s+)?(?:cpu|ram|disk|temperature|battery|metrics)\b", q):
        return True, "Telemetry"
    if re.match(r"^(?:show|get|what(?:'s|\s+are)\s+my)\s+(?:system\s+)?(?:specs?|info|configuration)", q):
        return True, "SystemInfo"
    if re.match(r"^(?:show|get|what)\s+(?:are\s+)?(?:my\s+)?(?:network\s+)?(?:interfaces?|adapters?|ip\b)", q):
        return True, "SystemInfo"
    if re.match(r"^(?:show|list)\s+(?:running\s+)?processes\b", q):
        return True, "SystemInfo"
    if re.match(r"^(?:run|execute)\s+(?:command|cmd)\b", q):
        return True, "Terminal"
    if re.search(r"\b(?:inventory|parts?\s+list|hardware\s+(?:inventory|projects?))\b", q):
        return True, "Hardware"
    if re.match(r"^(?:show|list|get)\s+(?:all\s+)?(?:parts?|inventory|orders?|BOM)\b", q):
        return True, "Hardware"
    if re.match(r"^(?:add|remove|update)\s+(?:part|item|order)\b", q):
        return True, "Hardware"
    if re.search(r"\b(?:node|fleet|infrastructure)\s+(?:status|health|overview)\b", q):
        return True, "FleetManager"
    if re.match(r"^(?:list|show)\s+(?:all\s+)?services?\b", q):
        return True, "ServiceRegistry"
    if re.match(r"^(?:add|register|remove|delete)\s+\w+\s+service\b", q):
        return True, "ServiceRegistry"
    if re.match(r"^(?:what\s+(?:nodes?|devices?)\s+(?:are|do\s+I\s+have))", q):
        return True, "NodeService"
    if re.match(r"^(?:show|get)\s+\w+\s+(?:info|details|status)\s*$", q):
        if not re.search(r"\b(?:email|calendar|app|launch|gmail)\b", q):
            return True, "NodeService"
    if re.match(r"^(?:configure|setup|set\s+up|assign)\s+\w+\s+(?:service\s+)?as\s+", q):
        return True, "ServiceRegistry"
    return False, ""


def _is_knowledge(q: str) -> tuple[bool, str]:
    if re.match(r"^(?:show|display|view)\s+(?:the\s+)?(?:knowledge\s+graph|engineering\s+graph|kg|project\s+graph)", q):
        return True, "KnowledgeGraph"
    if re.match(r"^(?:record|add|log|note|save|capture)\s+(?:decision|lesson|milestone|failure|success|experiment)", q):
        return True, "ProjectMemory"
    if re.match(r"^(?:show|list|display|get|what)\s+(?:(?:all\s+)?(?:decisions?|lessons?|milestones?|failures?))", q):
        return True, "ProjectMemory"
    if re.match(r"^(?:show|display)\s+(?:project\s+)?(?:history|timeline)\s+", q):
        return True, "ProjectMemory"
    if re.search(r"\bproject\s+memory\b", q):
        return True, "ProjectMemory"
    if re.search(r"\bengineering\s+memory\b", q):
        return True, "ProjectMemory"
    if re.match(r"^what\s+(?:did\s+(?:we|i)\s+(?:decide|learn|discover)|failed|went\s+wrong)\b", q):
        return True, "ProjectMemory"
    if re.match(r"^why\s+did\s+we\s+(?:choose|switch|use|adopt|pick|select)", q):
        return True, "ProjectMemory"
    if re.match(r"^(?:import|sync|load)\s+(?:memories?|decisions?|lessons?)\b", q):
        return True, "Brain63"
    if re.match(r"^(?:brain63|brain\s+63|vault)\s+", q):
        return True, "Brain63"
    if re.match(r"^(?:show|display)\s+(?:the\s+)?(?:graph|entity|relationship)", q):
        return True, "KnowledgeGraph"
    if re.search(r"\bsemantic\s+search\b", q):
        return True, "SemanticMemory"
    if re.match(r"^(?:what\s+did\s+(?:i|we)\s+(?:say|discuss|talk)\s+about|find\s+conversations?\s+about)", q):
        return True, "SemanticMemory"
    return False, ""


_BOARD_NAMES = (
    r"(?:hardware|fleet|intel(?:ligence)?|mission|knowledge|planner|workspace|"
    r"observability|projects?|infrastructure|memory|workflows?|command)"
)

def _is_app_control(q: str) -> tuple[bool, str]:
    # SSH targets — must be checked BEFORE the generic "open X" Launcher catch-all
    if re.match(r"^(?:ssh(?:\s+into?)?|connect(?:\s+to)?)\s+\w+", q):
        return True, "SSH"
    if re.match(r"^(?:open\s+(?:(?:the\s+)?(?:ssh|remote)\s+)?(?:terminal|session)\s+(?:on|to))\s+", q):
        return True, "SSH"
    if re.match(r"^(?:open|launch)\s+(?:the\s+)?(?:ssh|remote)\s+(?:terminal|session|connection)[\s\.\?!]*$", q):
        return True, "SSH"
    if re.match(r"^(?:open|launch)\s+ssh[\s\.\?!]*$", q):
        return True, "SSH"
    if re.match(r"^ssh\s+(?:terminal|session|in)[\s\.\?!]*$", q):
        return True, "SSH"
    if re.match(r"^connect[\s\.\?!]*$", q):
        return True, "SSH"
    if re.match(r"^(?:set|update|change|configure)\s+(?:ssh\s+)?(?:username|key)\b", q):
        return True, "SSH"
    if re.match(r"^(?:open|launch|start|run)\s+", q):
        if re.match(rf"^(?:open|launch|start|run)\s+{_PROD_NOUNS}", q, re.I):
            return False, ""
        if re.match(rf"^(?:open|go\s+to|navigate\s+to|switch\s+to|take\s+me\s+to|launch)\s+"
                    rf"(?:the\s+)?{_BOARD_NAMES}\s*(?:board|dashboard|panel)?[\s\.\?!]*$", q, re.I):
            return True, "BoardRouter"
        return True, "Launcher"
    if re.match(r"^(?:close|quit|exit)\s+", q):
        return True, "Launcher"
    if re.match(r"^(?:volume|mute|unmute|play|pause|next\s+track|prev|skip)\b", q):
        return True, "MediaControl"
    if re.match(r"^(?:set|turn)\s+(?:the\s+)?volume\b", q):
        return True, "MediaControl"
    if re.match(r"^(?:show|list)\s+(?:(?:all|my)\s+)?(?:running|installed|launched|active)\s+"
                r"(?:apps?|applications?|programs?)", q):
        return True, "Launcher"
    if re.match(r"^(?:scan|rescan|discover|refresh)\s+(?:installed\s+)?(?:apps?|applications?)", q):
        return True, "Launcher"
    if re.match(r"^is\s+\w+\s+(?:running|open|active|launched)\b", q):
        return True, "Launcher"
    if re.match(r"^(?:app\s+)?status\s+(?:of\s+)?\w+", q):
        return True, "Launcher"
    if re.match(r"^(?:show|navigate|go)\s+(?:to\s+)?(?:the\s+)?(?:\w+\s+)?(?:board|dashboard|panel)\b", q):
        return True, "BoardRouter"
    if re.match(r"^(?:open|go\s+to|navigate\s+to|switch\s+to|take\s+me\s+to)\s+"
                r"(?:the\s+)?(?:\w+\s+)*(?:board|dashboard|panel)\b", q):
        return True, "BoardRouter"
    if re.match(r"^(?:find|search\s+for|locate)\s+(?:files?\s+)?", q) and not re.search(r"\b(?:email|conversation)", q):
        if re.search(r"\bfiles?\b", q):
            return True, "FileSearch"
    if re.match(r"^(?:show|list)\s+(?:latest|recent|newest)\s+files?\b", q):
        return True, "FileSearch"
    if re.match(r"^(?:prefer|set\s+preference|default)\s+\w+\s+(?:web|app|desktop|folder)", q):
        return True, "Launcher"
    if re.match(r"^(?:show\s+)?(?:launch\s+)?(?:target|preference)", q):
        return True, "Launcher"
    return False, ""


def _is_web_search(q: str) -> tuple[bool, str]:
    if re.match(r"^(?:search\s+(?:for|the\s+web|online)\s+|look\s+up\s+|find\s+out\s+)", q):
        return True, "WebSearch"
    if re.search(r"\b(?:latest|breaking|recent)\s+(?:news|headlines)\b", q):
        return True, "WebSearch"
    if re.search(r"\b(?:current\s+events?|what\s+happened\s+(?:today|yesterday|this\s+week))\b", q):
        return True, "WebSearch"
    if re.search(r"\b(?:stock|price\s+of|market\s+cap)\b", q):
        return True, "WebSearch"
    if re.match(r"^(?:how\s+much\s+(?:is|does|are))\s+", q):
        return True, "WebSearch"
    if re.match(r"^(?:who\s+(?:is|was|are|were))\s+", q):
        if not re.search(r"\b(?:nighthawk|cyberdeck|drone|koi|brain|silvia|cmd|artoo|magi)\b", q, re.I):
            return True, "WebSearch"
    if re.search(r"\bcrypto\b", q):
        return True, "WebSearch"
    return False, ""


def _is_conversation(q: str) -> tuple[bool, str]:
    if re.match(r"^(?:hey|hi|hello|yo|sup|good\s+(?:evening|afternoon|night))\b", q):
        return True, "SocialEngine"
    if re.match(r"^(?:how\s+are\s+you|what'?s?\s+up|thanks|thank\s+you|bye|goodbye)\b", q):
        return True, "SocialEngine"
    if len(q.split()) <= 3 and not re.match(r"^(?:ping|ssh|arm|land|mute|open|close|list)\b", q):
        return True, "SocialEngine"
    return False, ""


# ── Multi-app detection ──────────────────────────────────────────────────────

def parse_multi_targets(target_str: str) -> list[str] | None:
    """Split 'X and Y' or 'X, Y, and Z' into individual targets.

    Returns None if there's no conjunction/comma (single target).
    """
    if " and " not in target_str.lower() and "," not in target_str:
        return None
    parts = re.split(r"\s*,\s*(?:and\s+)?|\s+and\s+", target_str, flags=re.I)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if len(parts) > 1 else None


# ── Public API ───────────────────────────────────────────────────────────────

def classify(query: str) -> CommandRoute:
    """Classify a query into exactly one category with one owner."""
    q = strip_wake_prefix(query.strip())
    low = q.lower()
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if _is_show_routing(low):
        return CommandRoute("infrastructure", "RoutingLog", 99, q, timestamp=ts)

    ok, owner = _is_productivity(low)
    if ok:
        return CommandRoute("productivity", owner, 92, q, timestamp=ts)

    ok, owner = _is_infrastructure(low)
    if ok:
        return CommandRoute("infrastructure", owner, 90, q, timestamp=ts)

    ok, owner = _is_knowledge(low)
    if ok:
        return CommandRoute("knowledge", owner, 88, q, timestamp=ts)

    ok, owner = _is_app_control(low)
    if ok:
        intents = []
        m = re.match(r"^(?:open|launch|start)\s+(.+?)[\.\?!]*$", q, re.I)
        if m:
            targets = parse_multi_targets(m.group(1).strip())
            if targets:
                intents = [{"action": "open_app", "target": t} for t in targets]
        return CommandRoute("application_control", owner, 96, q, intents=intents, timestamp=ts)

    ok, owner = _is_web_search(low)
    if ok:
        return CommandRoute("web_search", owner, 85, q, timestamp=ts)

    return CommandRoute("conversation", "SocialEngine", 70, q, timestamp=ts)


def log_route(route: CommandRoute) -> None:
    """Record a routing decision and emit a log line."""
    entry = {
        "timestamp": route.timestamp,
        "query": route.query,
        "category": route.category,
        "owner": route.owner,
        "confidence": route.confidence,
        "intents": route.intents,
    }
    _ROUTE_LOG.append(entry)
    logger.info(
        "ROUTE category=%s owner=%s confidence=%d query=%r",
        route.category, route.owner, route.confidence, route.query,
    )


def update_last_route(handler: str, status: str = "ok") -> None:
    """Annotate the most recent route entry with handler and response status."""
    if _ROUTE_LOG:
        _ROUTE_LOG[-1]["handler"] = handler
        _ROUTE_LOG[-1]["response_status"] = status


def format_last_route() -> str:
    """Render the last route classification as readable text."""
    if not _ROUTE_LOG:
        return "No commands routed yet."
    e = _ROUTE_LOG[-1]
    lines = [
        "Last Command Route",
        "=" * 40,
        f"Input: {e['query']}",
        f"Classification: {e['category'].replace('_', ' ').title()}",
        f"Owner: {e['owner']}",
        f"Confidence: {e['confidence']}%",
    ]
    if e.get("handler"):
        lines.append(f"Handler: {e['handler']}")
    if e.get("response_status"):
        lines.append(f"Response: {e['response_status']}")
    if e.get("intents"):
        targets = [i.get("target", "?") for i in e["intents"]]
        lines.append(f"Targets: {', '.join(targets)}")
    return "\n".join(lines)


def get_routing_log() -> list[dict]:
    return list(_ROUTE_LOG)


def format_routing_log(limit: int = 20) -> str:
    """Render the last N routing decisions as readable text."""
    entries = list(_ROUTE_LOG)[-limit:]
    if not entries:
        return "No commands routed yet."
    lines = [
        "Command Routing Log",
        "=" * 50,
        "",
    ]
    cat_counts: dict[str, int] = {}
    for e in entries:
        cat_counts[e["category"]] = cat_counts.get(e["category"], 0) + 1

    for e in reversed(entries):
        intents_str = ""
        if e["intents"]:
            targets = [i.get("target", "?") for i in e["intents"]]
            intents_str = f"  Execution: {', '.join(targets)}"
        lines.append(
            f"Input: {e['query']}\n"
            f"  Classification: {e['category'].replace('_', ' ').title()}\n"
            f"  Owner: {e['owner']}\n"
            f"  Confidence: {e['confidence']}%"
            + (f"\n{intents_str}" if intents_str else "")
        )
        lines.append("")

    lines.append("-" * 50)
    lines.append("Distribution:")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {cat.replace('_', ' ').title()}: {count}")

    return "\n".join(lines)
