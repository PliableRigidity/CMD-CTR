"""Cognitive event schema + bus (Phase 4).

A CognitiveEvent describes ONE piece of observable system activity — a memory
query, a retrieved object, a relationship traversal, an agent/tool/workflow step,
a decision, a provider health change. It carries only short, inspectable,
system-level explanations (reason codes). It NEVER contains private
language-model chain-of-thought.

The CognitiveEventBus keeps a bounded rolling buffer (so late-joining UIs get a
snapshot — the WS transport does not replay), maintains a decaying activation
graph, and pushes each event to any registered publisher (wired to the existing
WebSocket fan-out at app startup). It is a general SILVIA facility, not KOSINE-
specific.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.app.services.cognition.graph_state import CognitiveGraphState

logger = logging.getLogger("silvia.cognition.events")

_BUFFER_SIZE = 500  # bounded — we never persist every reasoning event


class CognitiveEventType:
    """Stable event-type vocabulary (see docs/cognitive_graph.md)."""
    SESSION_STARTED = "session_started"
    INTENT_DETECTED = "intent_detected"
    MEMORY_QUERY_PLANNED = "memory_query_planned"
    MEMORY_SEARCH_STARTED = "memory_search_started"
    MEMORY_RESULT_RECEIVED = "memory_result_received"
    MEMORY_ACTIVATED = "memory_activated"
    RELATION_TRAVERSED = "relation_traversed"
    MEMORY_RERANKED = "memory_reranked"
    CONTEXT_SELECTED = "context_selected"
    CONTEXT_REJECTED = "context_rejected"
    AGENT_STARTED = "agent_started"
    AGENT_DELEGATED = "agent_delegated"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_STEP_STARTED = "workflow_step_started"
    WORKFLOW_STEP_COMPLETED = "workflow_step_completed"
    WORKFLOW_BLOCKED = "workflow_blocked"
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"
    EXTERNAL_OBSERVATION = "external_observation"
    DECISION_PROPOSED = "decision_proposed"
    DECISION_CONFIRMED = "decision_confirmed"
    CONTRADICTION_DETECTED = "contradiction_detected"
    SIMULATION_STARTED = "simulation_started"
    SIMULATION_NODE_CREATED = "simulation_node_created"
    SIMULATION_COMPLETED = "simulation_completed"
    MEMORY_WRITE_PROPOSED = "memory_write_proposed"
    MEMORY_WRITE_APPROVED = "memory_write_approved"
    MEMORY_WRITE_APPLIED = "memory_write_applied"
    PROVIDER_DEGRADED = "provider_degraded"
    PROVIDER_RECOVERED = "provider_recovered"
    ERROR = "error"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CognitiveEvent:
    """One observable system-activity event."""
    event_type: str
    event_id: str = field(default_factory=lambda: "ev_" + uuid.uuid4().hex[:12])
    timestamp: str = field(default_factory=_now)
    session_id: str = "default"
    task_id: str = ""
    parent_event_id: str = ""
    actor_type: str = "system"          # system | memory | agent | workflow | tool | user
    actor_id: str = ""
    provider: str = ""
    status: str = "ok"                  # ok | started | completed | rejected | blocked | error | simulated | proposed | confirmed
    activation: float = 0.0
    confidence: Optional[float] = None
    reason_code: str = ""               # short machine tag, e.g. 'matched_current_project'
    explanation: str = ""               # short safe human string — NO chain-of-thought
    duration_ms: Optional[float] = None
    error: str = ""
    # Graph delta this event contributes (upserted into the activation graph):
    nodes: list[dict] = field(default_factory=list)  # {id,type,label,provider,state,meta}
    edges: list[dict] = field(default_factory=list)  # {id,source,target,type}
    metadata: dict = field(default_factory=dict)

    @property
    def node_ids(self) -> list[str]:
        return [n.get("id", "") for n in self.nodes if n.get("id")]

    @property
    def edge_ids(self) -> list[str]:
        return [e.get("id", "") for e in self.edges if e.get("id")]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["node_ids"] = self.node_ids
        d["edge_ids"] = self.edge_ids
        return d


class CognitiveEventBus:
    """Bounded buffer + activation graph + fan-out for cognitive events."""

    def __init__(self, buffer_size: int = _BUFFER_SIZE) -> None:
        self._buffer: deque[CognitiveEvent] = deque(maxlen=buffer_size)
        self._graph = CognitiveGraphState()
        self._publishers: list[Callable[[dict], Any]] = []
        self._lock = threading.Lock()

    # ── wiring ────────────────────────────────────────────────────────────

    def register_publisher(self, publisher: Callable[[dict], Any]) -> None:
        """Register a sink for live events (e.g. the WS ``emit_ws_only``).

        The publisher may be an async callable; it is scheduled on the running
        loop when one exists, and skipped (buffer-only) when called from sync
        code with no loop — the snapshot still reflects the event.
        """
        self._publishers.append(publisher)

    def clear_publishers(self) -> None:
        self._publishers.clear()

    # ── emit ──────────────────────────────────────────────────────────────

    def emit(self, event: CognitiveEvent) -> CognitiveEvent:
        with self._lock:
            self._buffer.append(event)
            self._graph.ingest(event)
        payload = {"type": "cognitive", "event": event.to_dict()}
        for pub in list(self._publishers):
            self._dispatch(pub, payload)
        return event

    def emit_event(self, event_type: str, **kw: Any) -> CognitiveEvent:
        """Convenience: build + emit in one call."""
        return self.emit(CognitiveEvent(event_type=event_type, **kw))

    @staticmethod
    def _dispatch(publisher: Callable[[dict], Any], payload: dict) -> None:
        try:
            result = publisher(payload)
            if asyncio.iscoroutine(result):
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(result)
                except RuntimeError:
                    result.close()  # no loop (sync context) — buffer-only
        except Exception as e:  # a bad sink must never break cognition
            logger.debug("cognitive publisher failed: %s", e)

    # ── read / snapshot ───────────────────────────────────────────────────

    def recent(self, limit: int = 200, session_id: str = "") -> list[dict]:
        with self._lock:
            items = list(self._buffer)
        if session_id:
            items = [e for e in items if e.session_id == session_id]
        return [e.to_dict() for e in items[-limit:]]

    def snapshot(self, session_id: str = "", limit: int = 200) -> dict:
        """Full state for a late-joining UI: current activation graph + recent
        events + the event-type legend."""
        with self._lock:
            graph = self._graph.snapshot()
        return {
            "graph": graph,
            "events": self.recent(limit=limit, session_id=session_id),
            "generated_at": _now(),
        }

    def reset(self) -> None:
        """Clear transient visual state (buffer + activation) — never touches
        any persistent memory provider."""
        with self._lock:
            self._buffer.clear()
            self._graph = CognitiveGraphState()


_bus: Optional[CognitiveEventBus] = None


def get_cognitive_bus() -> CognitiveEventBus:
    global _bus
    if _bus is None:
        _bus = CognitiveEventBus()
    return _bus
