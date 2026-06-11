"""Hermes execution service — SILVIA's agentic execution layer.

Wraps Ollama with tool-calling format. Tries hermes3 first, then qwen2.5:7b.
Used for multi-step tasks that require conditional/sequential tool execution.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from backend.config import OLLAMA_CHAT_URL

logger = logging.getLogger(__name__)

# Models in preference order — hermes3 is fine-tuned for function calling
_EXECUTION_MODELS = ["hermes3", "qwen2.5:7b", "qwen2.5:3b"]

_HERMES_SYSTEM = (
    "You are SILVIA's execution engine. Execute tasks by calling tools in the correct order.\n"
    "STRICT RULES:\n"
    "- NEVER guess, infer, or assume any fact about nodes, devices, or systems. Always call a tool.\n"
    "- NEVER conclude a node is offline or unreachable without calling a tool first.\n"
    "- For any query involving node status, health, or telemetry: call get_node_telemetry DIRECTLY. "
    "It returns status AND metrics in one call. Do not call get_node_info first as a precondition.\n"
    "- If get_node_telemetry returns data, the node is reachable. Present the data.\n"
    "- Only call get_node_info when the user asks specifically for IP/network details, not for status checks.\n"
    "- When you have all needed results, give a concise direct answer. No step-by-step narration."
)

_available_model: str | None = None
_checked: bool = False


def reset_model_cache() -> None:
    """Force re-detection of available execution model on next call."""
    global _available_model, _checked
    _available_model = None
    _checked = False


async def get_execution_model() -> str | None:
    """Return the best available execution model (cached after first check)."""
    global _available_model, _checked
    if _checked:
        return _available_model

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            resp.raise_for_status()
        names = {m["name"].split(":")[0] for m in resp.json().get("models", [])}
        # Also check full names (e.g. hermes3:latest)
        full_names = {m["name"] for m in resp.json().get("models", [])}
        for candidate in _EXECUTION_MODELS:
            base = candidate.split(":")[0]
            if candidate in full_names or base in names:
                _available_model = candidate
                logger.info("Hermes execution model: %s", candidate)
                break
    except Exception as exc:
        logger.debug("Model availability check failed: %s", exc)

    _checked = True
    return _available_model


def _build_tools(tool_specs: list[dict]) -> list[dict]:
    """Convert simplified tool specs to Ollama function-calling format."""
    result = []
    for spec in tool_specs:
        result.append({
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec.get("parameters", {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }),
            },
        })
    return result


async def call_with_tools(
    task: str,
    tool_specs: list[dict],
    history: list[dict] | None = None,
    model: str | None = None,
) -> dict:
    """
    Send a task to the execution model with tools available.
    Returns:
      {"tool_calls": [...], "content": "...", "done": bool}
      tool_calls: list of {"name": ..., "arguments": {...}}
    """
    if model is None:
        model = await get_execution_model()
    if model is None:
        return {"tool_calls": [], "content": "", "done": True, "error": "No execution model available"}

    messages = [{"role": "system", "content": _HERMES_SYSTEM}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": task})

    payload = {
        "model": model,
        "messages": messages,
        "tools": _build_tools(tool_specs),
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(OLLAMA_CHAT_URL, json=payload)
            resp.raise_for_status()
        data = resp.json()
        msg = data.get("message", {})
        raw_calls = msg.get("tool_calls") or []
        parsed_calls = []
        for tc in raw_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            if name:
                parsed_calls.append({"name": name, "arguments": args})
        content = (msg.get("content") or "").strip()
        done = not parsed_calls  # done when no more tool calls
        return {"tool_calls": parsed_calls, "content": content, "done": done}
    except Exception as exc:
        logger.warning("Hermes call failed: %s", exc)
        return {"tool_calls": [], "content": "", "done": True, "error": str(exc)}


async def finish_with_results(
    task: str,
    tool_results: list[dict],
    model: str | None = None,
) -> str:
    """
    After tool execution, synthesize a final answer.
    tool_results: list of {"tool": name, "result": str}
    """
    if model is None:
        model = await get_execution_model()
    if model is None:
        results_text = "\n".join(f"- {r['tool']}: {r['result']}" for r in tool_results)
        return f"Task results:\n{results_text}"

    results_block = "\n".join(f"[{r['tool']}] {r['result']}" for r in tool_results)
    synthesis_prompt = (
        f"The user asked: {task}\n\n"
        f"Tool results:\n{results_block}\n\n"
        "Give a concise, direct answer based on these results. No prose about what tools were used."
    )
    messages = [
        {"role": "system", "content": _HERMES_SYSTEM},
        {"role": "user", "content": synthesis_prompt},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 256},
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(OLLAMA_CHAT_URL, json=payload)
            resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "").strip() or "Task completed."
    except Exception:
        results_text = "\n".join(f"- {r['tool']}: {r['result']}" for r in tool_results)
        return f"Task results:\n{results_text}"
