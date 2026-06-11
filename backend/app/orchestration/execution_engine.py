"""Execution Engine — agentic multi-step task executor via Hermes.

Routes multi-step queries to the execution model (hermes3 / qwen2.5:7b),
which can call SILVIA tools iteratively until the task is complete.
"""
from __future__ import annotations

import logging
import time

from backend.app.models.assistant import AgentStatus, AssistantResponse, CommandLogEntry
from backend.app.services.hermes_service import call_with_tools, finish_with_results, get_execution_model
from backend.app.services.speech_sanitizer import sanitize_for_speech

logger = logging.getLogger(__name__)

_MAX_ITERATIONS = 5

# Tools exposed to Hermes — matches the tools wired in conversation_service._run_tool
_HERMES_TOOLS = [
    {"name": "get_time", "description": "Get current local time", "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_time_in", "description": "Get time in a city/country", "parameters": {"type": "object", "properties": {"place": {"type": "string"}}, "required": ["place"]}},
    {"name": "get_weather", "description": "Get weather for a place", "parameters": {"type": "object", "properties": {"place": {"type": "string"}}, "required": ["place"]}},
    {"name": "get_stock_price", "description": "Get stock price", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "list_nodes", "description": "List all registered nodes", "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_node_info", "description": "Get a node's status and info from the registry. Use this to check if a node is online before acting on it conditionally.", "parameters": {"type": "object", "properties": {"node": {"type": "string"}}, "required": ["node"]}},
    {"name": "get_node_telemetry", "description": "Get status AND telemetry (CPU/RAM/disk/battery/mission) for a node. Use this for ANY query about whether a node is online or its health — it returns status in one call. Use node='all' for all nodes.", "parameters": {"type": "object", "properties": {"node": {"type": "string"}}, "required": ["node"]}},
    {"name": "get_watch_alerts", "description": "Get active Watch Officer alerts", "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "list_reminders", "description": "List active reminders", "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "list_tasks", "description": "List tasks", "parameters": {"type": "object", "properties": {"filter": {"type": "string", "enum": ["pending", "done", "all"]}}, "required": []}},
    {"name": "get_calendar_today", "description": "Get today's calendar events", "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_upcoming_events", "description": "Get upcoming events", "parameters": {"type": "object", "properties": {"days": {"type": "integer"}}, "required": []}},
    {"name": "get_system_specs", "description": "Get local system hardware specs", "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "get_network_info", "description": "Get local network interfaces", "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "run_command", "description": "Run a shell command", "parameters": {"type": "object", "properties": {"cmd": {"type": "string"}}, "required": ["cmd"]}},
    {"name": "semantic_search", "description": "Search past conversations semantically", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]


def is_multistep(query: str) -> bool:
    """Detect if a query requires multi-step execution."""
    lowered = query.lower()
    multistep_signals = [
        " then ", " after that", " followed by", " and then ",
        "if it's online", "if it is online", "if it's offline", "if they're",
        "when it", "once you", "first check", "check if",
        " also ", "and show me", "and tell me", "give me both",
    ]
    # Need at least 2 distinct intent phrases
    found = sum(1 for s in multistep_signals if s in lowered)
    return found >= 1 and len(query.split()) > 8


class ExecutionEngine:
    def __init__(self, conversation_service=None) -> None:
        self._cs = conversation_service

    async def run(self, task: str, request) -> AssistantResponse | None:
        """
        Run an agentic execution loop for a multi-step task.
        Returns AssistantResponse or None if execution model unavailable.
        """
        model = await get_execution_model()
        if model is None:
            return None

        started = time.perf_counter()
        tool_results: list[dict] = []
        iterations = 0
        history: list[dict] = []
        final_content = ""

        await self._emit(f"[HERMES] {model}", f"Executing: {task[:80]}")

        while iterations < _MAX_ITERATIONS:
            iterations += 1

            step = await call_with_tools(task, _HERMES_TOOLS, history=history, model=model)

            if step.get("error"):
                logger.warning("Hermes step error: %s", step["error"])
                break

            # Hermes returned content (final answer) with no more tool calls
            if step["done"] and step["content"]:
                final_content = step["content"]
                break

            # No tool calls and no content — done
            if not step["tool_calls"] and not step["content"]:
                break

            # Execute each tool call
            step_results = []
            for tc in step["tool_calls"]:
                tool_name = tc["name"]
                tool_args = tc["arguments"]
                await self._emit(f"[HERMES] {tool_name}", str(tool_args)[:80])

                tool_resp = await self._execute_tool(tool_name, tool_args)
                result_str = tool_resp.answer if tool_resp else f"[{tool_name}: no result]"
                step_results.append({"tool": tool_name, "result": result_str[:500]})
                tool_results.append({"tool": tool_name, "result": result_str[:500]})

            # Feed tool results back into the conversation
            history.append({"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in step["tool_calls"]
            ]})
            for r in step_results:
                history.append({
                    "role": "tool",
                    "content": r["result"],
                })

        # Synthesize final answer if Hermes didn't provide one
        if not final_content and tool_results:
            final_content = await finish_with_results(task, tool_results, model=model)
        elif not final_content:
            return None  # Let normal flow handle it

        elapsed = (time.perf_counter() - started) * 1000
        tool_names = list({r["tool"] for r in tool_results})

        return AssistantResponse(
            mode="conversation",
            title="Execution Engine",
            answer=final_content,
            confidence=0.88,
            reasoning=f"Hermes multi-step execution ({iterations} iteration{'s' if iterations != 1 else ''}, {len(tool_results)} tool call{'s' if len(tool_results) != 1 else ''})",
            processing_time_ms=elapsed,
            sources=[],
            agents=[AgentStatus(
                name=f"Hermes ({model})",
                role="execution",
                state="complete",
                confidence=88,
                summary=f"Executed {len(tool_results)} tool calls: {', '.join(tool_names) or 'none'}",
            )],
            logs=[CommandLogEntry(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                title="Hermes Execution",
                detail=f"{iterations} iter · {len(tool_results)} calls · {elapsed:.0f}ms",
            )],
            payload={"speech_text": sanitize_for_speech(final_content), "tool_results": tool_results},
        )

    async def _execute_tool(self, name: str, args: dict):
        if self._cs is None:
            return None
        try:
            return await self._cs._run_tool(name, args)
        except Exception as exc:
            logger.warning("Hermes tool execution failed %s(%s): %s", name, args, exc)
            return None

    async def _emit(self, title: str, detail: str, level: str = "info") -> None:
        if self._cs and self._cs.event_service:
            await self._cs.event_service.emit(title, detail, level)
