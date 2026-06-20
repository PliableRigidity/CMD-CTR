"""Capability Verification Layer.

Prevents SILVIA from hallucinating infrastructure state. Every response about
system state must come from verified tool output — never from LLM inference.

Three responsibilities:
1. Track SSH terminal sessions (SILVIA opens a window but has no command channel)
2. Intercept infrastructure state queries that lack verified data
3. Record CapabilityExecutionResult for every tool execution (audit + attribution)
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class CapabilityExecutionResult:
    """Structured result from every capability execution."""
    success: bool
    executed: bool
    source: str        # "ssh_terminal", "http", "local", "run_command", "capability_executor", "not_executed"
    raw_output: str
    timestamp: str
    node: str = ""
    capability: str = ""
    tool: str = ""
    error: str = ""


# ── Infrastructure query detection ───────────────────────────────────────────
# Bare system commands that MUST return verified output or refuse.
_INFRA_BARE_CMD = re.compile(
    r"^(?:hostname|uptime|whoami|uname(?:\s+-[a-z]+)?|"
    r"df(?:\s+-[a-z]+)?|free(?:\s+-[a-z]+)?|top|htop|"
    r"ps(?:\s+aux)?|docker\s+(?:ps|images|stats)|"
    r"systemctl(?:\s+(?:status|list-units))?|journalctl(?:\s+.+)?|"
    r"ip\s+(?:addr|route|link)|ifconfig|netstat(?:\s+-[a-z]+)?|"
    r"ss(?:\s+-[a-z]+)?|lsblk|mount|lscpu|cat\s+/etc/\S+|"
    r"service\s+\w+\s+status|which\s+\w+)\s*\??\s*$",
    re.I,
)

# Queries about node/system state that need verified data.
_INFRA_STATE_QUERY = re.compile(
    r"(?:what(?:'s|s|\s+is|\s+are)\s+(?:the\s+)?(?:hostname|uptime|ip|status|running|"
    r"services?|containers?|processes?|disk|memory|cpu|load|temperature|os|kernel)"
    r"|show\s+(?:services?|containers?|docker|processes?|running|status)"
    r"|list\s+(?:services?|containers?|docker|processes?|running)"
    r"|check\s+(?:disk|memory|cpu|services?|status|health)"
    r"|how\s+(?:much\s+(?:disk|ram|memory|storage)|many\s+(?:containers?|services?|processes?)))",
    re.I,
)

# Node reference: "on X", "of X", "for X" at end of query.
_NODE_REF = re.compile(r"\b(?:on|of|for|from)\s+([a-zA-Z][\w\-_.]*)\s*\??\s*$", re.I)


class CapabilityVerificationService:
    """Anti-hallucination layer for infrastructure state."""

    _MAX_RESULTS = 500

    def __init__(self) -> None:
        self._results: list[CapabilityExecutionResult] = []
        self._ssh_terminals: dict[str, dict] = {}

    # ── SSH terminal tracking ────────────────────────────────────────────────

    def record_ssh_terminal(self, node: str) -> None:
        self._ssh_terminals[node.lower()] = {
            "opened_at": _now(),
            "type": "terminal_window",
            "has_command_channel": False,
        }

    def clear_ssh_terminal(self, node: str) -> None:
        self._ssh_terminals.pop(node.lower(), None)

    def has_ssh_terminal(self, node: str) -> bool:
        return node.lower() in self._ssh_terminals

    def get_recent_ssh_node(self) -> Optional[str]:
        if not self._ssh_terminals:
            return None
        return max(self._ssh_terminals, key=lambda n: self._ssh_terminals[n]["opened_at"])

    def get_ssh_terminals(self) -> dict[str, dict]:
        return dict(self._ssh_terminals)

    # ── Result recording ─────────────────────────────────────────────────────

    def record_result(self, result: CapabilityExecutionResult) -> None:
        self._results.append(result)
        if len(self._results) > self._MAX_RESULTS:
            self._results = self._results[-self._MAX_RESULTS:]

    def get_last_result(self, *, node: str = "", tool: str = "") -> Optional[CapabilityExecutionResult]:
        for r in reversed(self._results):
            if node and r.node.lower() != node.lower():
                continue
            if tool and r.tool != tool:
                continue
            return r
        return None

    # ── Infrastructure query interception ────────────────────────────────────

    def intercept_unverified_query(self, query: str, known_nodes: set[str] | None = None) -> Optional[str]:
        """Return a refusal message if the query would require fabrication.

        Returns None if the query can proceed through normal routing (local
        execution or other verified path).
        """
        text = query.strip()
        known = known_nodes or set()

        # Bare infrastructure commands (hostname, uptime, docker ps, etc.)
        # These MUST come from actual command execution, not LLM inference.
        # Users should say "run hostname" for local execution.
        if _INFRA_BARE_CMD.match(text):
            recent_node = self.get_recent_ssh_node()
            if recent_node:
                cmd = text.split()[0]
                return (
                    f"I opened an SSH terminal to **{recent_node}**, but I don't have "
                    f"a command channel to run `{text}` on it remotely. "
                    f"Run the command in the SSH terminal window.\n\n"
                    f"To run `{cmd}` on **this machine**, say: **run {text}**"
                )
            return (
                f"I can't answer `{text}` from inference — infrastructure state must come "
                f"from actual command output.\n\n"
                f"To run on **this machine**: **run {text}**\n"
                f"To check a **remote node**: connect to it first, then run the command in the SSH window."
            )

        # State queries referencing a specific node
        if _INFRA_STATE_QUERY.search(text):
            node_match = _NODE_REF.search(text)
            if node_match:
                ref_node = node_match.group(1).lower()
                if ref_node in known or self.has_ssh_terminal(ref_node):
                    if self.has_ssh_terminal(ref_node):
                        return (
                            f"I opened an SSH terminal to **{ref_node}**, but I can't "
                            f"query its state from here. Run commands in the SSH terminal window.\n\n"
                            f"If {ref_node} runs a SILVIA agent, I can query it through the node protocol."
                        )

        return None

    def format_source_attribution(self, result: CapabilityExecutionResult) -> str:
        parts = []
        if result.node:
            parts.append(f"Node: {result.node}")
        parts.append(f"Source: {result.source}")
        if result.tool:
            parts.append(f"Tool: {result.tool}")
        parts.append(f"Executed: {'yes' if result.executed else 'no'}")
        parts.append(f"Timestamp: {result.timestamp}")
        return " | ".join(parts)


# ── Anti-hallucination guard for LLM fallback ────────────────────────────────

_LLM_INFRA_GUARD = re.compile(
    r"(?:what(?:'s|s|\s+is)\s+(?:the\s+)?(?:hostname|ip\s+address|os|kernel|uptime|mac\s+address)"
    r"(?:\s+(?:of|on|for)\s+\w+)?"
    r"|tell\s+me\s+(?:the\s+)?(?:hostname|ip|status|uptime)"
    r"(?:\s+(?:of|on|for)\s+\w+)?"
    r"|(?:hostname|ip|status|uptime|os)\s+(?:of|on|for)\s+\w+)",
    re.I,
)


def guard_llm_fallback(query: str, verification_service: CapabilityVerificationService) -> Optional[str]:
    """Last-resort guard before the LLM generates a free-text response.

    If the query asks for infrastructure facts, refuse rather than
    letting the LLM fabricate an answer.
    """
    if _LLM_INFRA_GUARD.search(query):
        return (
            "I do not have verified data for that request. "
            "Infrastructure state must come from actual command output, not inference.\n\n"
            "To get real data, try:\n"
            "- **run [command]** to execute on this machine\n"
            "- **ping [node]** to check if a node is reachable\n"
            "- **probe [node]** for node telemetry"
        )
    return None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


_instance: Optional[CapabilityVerificationService] = None


def get_verification_service() -> CapabilityVerificationService:
    global _instance
    if _instance is None:
        _instance = CapabilityVerificationService()
    return _instance
