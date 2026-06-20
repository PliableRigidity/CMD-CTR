"""
SILVIA Capability Map — authoritative record of what is implemented,
what is partial, and what is unavailable.

This is a static data structure updated alongside the codebase, not a
dynamic runtime check. SILVIA uses it to answer self-reflection queries
honestly. The goal is zero hallucination: SILVIA describes real gaps and
real improvements, never invented status changes.
"""
from __future__ import annotations

AVAILABLE   = "available"
PARTIAL     = "partial"
UNAVAILABLE = "unavailable"
CONDITIONAL = "conditional"   # available, but requires external config

# ---------------------------------------------------------------------------
# Capability map — ground truth
# ---------------------------------------------------------------------------

CAPABILITY_MAP: dict[str, dict] = {
    "time": {
        "status": AVAILABLE,
        "label": "Time & Timezones",
        "description": "Current local time, world timezone lookup, user timezone preference.",
        "gaps": [],
    },
    "weather": {
        "status": CONDITIONAL,
        "label": "Weather",
        "description": "Live weather for any city. Requires OPENWEATHER_API_KEY in .env.",
        "gaps": [
            "Current conditions only — no multi-day forecast",
        ],
    },
    "web_search": {
        "status": CONDITIONAL,
        "label": "Web Search",
        "description": "Live web search for news, facts, and current events. Requires SEARXNG_URL in .env.",
        "gaps": [
            "SearXNG must be self-hosted and configured — disabled by default",
            "No result freshness filtering",
        ],
    },
    "stock_prices": {
        "status": AVAILABLE,
        "label": "Stock Prices",
        "description": "Live quotes, price, and daily change via Yahoo Finance. No key required.",
        "gaps": [
            "Yahoo Finance delay applies (~15–20 min)",
            "No portfolio tracking or alerts",
        ],
    },
    "node_registry": {
        "status": AVAILABLE,
        "label": "Node Registry",
        "description": "Register, list, update, and delete network nodes. IP resolution via Tailscale, DNS, and direct.",
        "gaps": [],
    },
    "node_monitoring": {
        "status": PARTIAL,
        "label": "Node Monitoring",
        "description": "Real-time telemetry (CPU, RAM, disk, temperature) from registered nodes.",
        "gaps": [
            "Only nodes with silvia-agent installed report live telemetry",
            "Nodes without an agent are registered but dark — no metrics",
            "7-day history only; no trend analysis or anomaly detection",
        ],
    },
    "node_control": {
        "status": PARTIAL,
        "label": "Node Control",
        "description": "Send commands (reboot, arm/disarm, emergency stop) to registered nodes.",
        "gaps": [
            "Requires silvia-agent on the target node",
            "No command result confirmation — success is assumed if the agent accepts",
            "Destructive commands require manual 'yes' confirmation",
        ],
    },
    "watch_officer": {
        "status": PARTIAL,
        "label": "Watch Officer",
        "description": "Monitors node metrics against thresholds. Raises alerts for high CPU, RAM, temperature.",
        "gaps": [
            "Threshold-only — no anomaly detection or baseline comparison",
            "Only covers nodes with active silvia-agent",
            "Cannot monitor external services, websites, or APIs",
        ],
    },
    "proactive_notifications": {
        "status": PARTIAL,
        "label": "Proactive Notifications",
        "description": "Watch Officer can push alerts to a Discord or Slack webhook.",
        "gaps": [
            "Webhook-only delivery — no mobile push",
            "Cannot proactively contact the user outside a triggered threshold",
            "No scheduled briefings or status digests",
        ],
    },
    "voice": {
        "status": AVAILABLE,
        "label": "Voice",
        "description": (
            "Speech-to-text via Whisper or Speaches. Text-to-speech via Piper or Speaches. "
            "Wake word detection via OpenWakeWord ('hey_silvia'). "
            "Hands-free loop: wake → auto-record → transcribe → chat → synthesize → play → listen."
        ),
        "gaps": [
            "Hands-free loop must be activated manually — not passive by default",
            "Accuracy degrades with background noise and soft speech",
            "Wake word model is fixed — no in-UI customisation",
        ],
    },
    "reminders": {
        "status": AVAILABLE,
        "label": "Reminders",
        "description": "Time-based and recurring reminders. One-time, daily, weekly, monthly.",
        "gaps": [
            "Local only — no cross-device sync or mobile delivery",
        ],
    },
    "tasks": {
        "status": AVAILABLE,
        "label": "Tasks",
        "description": "Local task list with project grouping and priority.",
        "gaps": [
            "No sync with external task managers (Notion, Linear, Jira, etc.)",
        ],
    },
    "calendar": {
        "status": PARTIAL,
        "label": "Calendar",
        "description": "Local calendar events stored in SQLite. Basic create, list, delete.",
        "gaps": [
            "No sync with Google Calendar, Outlook, or iCloud",
            "Events exist only inside CMD-CTR — no external access",
            "No recurring event support",
        ],
    },
    "memory": {
        "status": AVAILABLE,
        "label": "Memory",
        "description": "Conversation history and key-value preference storage that persists across sessions.",
        "gaps": [
            "History grows unbounded — no automatic summarization",
        ],
    },
    "semantic_memory": {
        "status": CONDITIONAL,
        "label": "Semantic Memory",
        "description": "Past conversations indexed for topic-based recall. Accessed via 'what did I say about...'",
        "gaps": [
            "Requires an embedding model configured in Ollama",
            "No proactive surfacing — the user must query explicitly",
        ],
    },
    "scheduled_tasks": {
        "status": AVAILABLE,
        "label": "Scheduled Tasks",
        "description": "Recurring tasks run on a fixed interval via the Hermes execution engine.",
        "gaps": [
            "Interval-based only — no cron-style scheduling",
            "No failure alerts if a task errors",
        ],
    },
    "world_intelligence": {
        "status": PARTIAL,
        "label": "World Intelligence",
        "description": "World events feed via RSS ingestors, scored by priority. Accessible via 'world brief'.",
        "gaps": [
            "RSS latency — not real-time",
            "No user-configurable topic watchlists",
            "No alerts for specific geographies or keywords",
        ],
    },
    "hermes": {
        "status": AVAILABLE,
        "label": "Hermes Multi-step Engine",
        "description": "Chains multiple tool calls for complex multi-step operations.",
        "gaps": [
            "Only as reliable as its constituent tools",
        ],
    },
    "email": {
        "status": UNAVAILABLE,
        "label": "Email",
        "description": "Not implemented.",
        "gaps": ["Cannot read, send, or manage email"],
    },
    "browser_automation": {
        "status": UNAVAILABLE,
        "label": "Browser Automation",
        "description": "Not implemented.",
        "gaps": ["Cannot interact with websites, fill forms, or scrape beyond search results"],
    },
    "external_integrations": {
        "status": UNAVAILABLE,
        "label": "External Integrations",
        "description": "No third-party SaaS integrations.",
        "gaps": ["No GitHub, Notion, Linear, Slack (inbound), or similar"],
    },
}

# ---------------------------------------------------------------------------
# Improvement priorities — ordered by expected impact.
# Used when SILVIA is asked what she would most want improved.
# These are reasoned, not invented — each maps to a real gap above.
# ---------------------------------------------------------------------------

IMPROVEMENT_PRIORITIES: list[dict] = [
    {
        "area": "node coverage",
        "priority": 1,
        "reasoning": (
            "Most of the infrastructure is dark. Nodes without silvia-agent don't "
            "report telemetry or accept commands. Wider agent deployment would give "
            "real visibility into the whole network, not just the few nodes that have it."
        ),
    },
    {
        "area": "proactive notification reach",
        "priority": 2,
        "reasoning": (
            "I can raise Watch Officer alerts, but only to a webhook. If you're away from "
            "CMD-CTR when a node goes offline or a threshold is breached, nothing reaches you. "
            "Mobile push would close that gap."
        ),
    },
    {
        "area": "web search configuration",
        "priority": 3,
        "reasoning": (
            "News and current-events queries fail silently without SearXNG. A configured "
            "search backend would make news, tech developments, and live data retrieval reliable "
            "rather than conditional."
        ),
    },
    {
        "area": "calendar sync",
        "priority": 4,
        "reasoning": (
            "The calendar is local-only — no Google Calendar or Outlook sync. I can't see "
            "scheduled meetings, deadlines, or context from your actual schedule. That limits "
            "how much situational awareness I can provide."
        ),
    },
    {
        "area": "Watch Officer scope",
        "priority": 5,
        "reasoning": (
            "Current monitoring is threshold-based and covers only agent nodes. No anomaly "
            "detection, no external service monitoring. I can't tell you when a website is "
            "down or a third-party API is failing."
        ),
    },
    {
        "area": "semantic memory",
        "priority": 6,
        "reasoning": (
            "Past conversation search requires an embedding model. Without it, I can retrieve "
            "recent history but not search by topic across older context. "
            "That limits how well I can reference things we discussed weeks ago."
        ),
    },
]


# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------

def get_capability_block() -> str:
    """Compact capability block injected into capability-query prompts.

    Gives the LLM an accurate list to reason from so it doesn't invent
    capabilities or deny real ones.
    """
    by_status: dict[str, list[str]] = {
        AVAILABLE: [], CONDITIONAL: [], PARTIAL: [], UNAVAILABLE: []
    }
    for cap in CAPABILITY_MAP.values():
        by_status[cap["status"]].append(cap["label"])

    parts = [
        "ACTUAL CAPABILITIES (use only these when describing what you can do):",
        f"Available: {', '.join(by_status[AVAILABLE])}",
        f"Available if configured: {', '.join(by_status[CONDITIONAL])}",
        f"Partial (limited): {', '.join(by_status[PARTIAL])}",
        f"Not implemented: {', '.join(by_status[UNAVAILABLE])}",
    ]
    return "\n".join(parts)


def get_gap_summary() -> str:
    """All notable gaps, one per capability. Used for limitation queries."""
    lines = []
    for cap in CAPABILITY_MAP.values():
        if cap["gaps"] and cap["status"] != AVAILABLE:
            lines.append(f"{cap['label']}: {cap['gaps'][0]}")
    return "\n".join(lines)


def get_improvement_context() -> str:
    """Numbered improvement priorities for self-reflection queries."""
    lines = []
    for item in IMPROVEMENT_PRIORITIES:
        lines.append(f"{item['priority']}. {item['area'].title()}: {item['reasoning']}")
    return "\n".join(lines)
