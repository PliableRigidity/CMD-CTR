"""
Tool planning layer for SILVIA.

Mirrors the BespokeToMe dispatcher/planner pattern:
  query → Ollama (SYSTEM_RULES + FEW_SHOTS) → tool decision → tool execution

Ollama is the primary strategy. Regex is the fallback when Ollama is unavailable.
"""

from __future__ import annotations

import json
import logging
import re

import httpx

from backend.config import OLLAMA_CHAT_URL

logger = logging.getLogger(__name__)

_PLANNING_MODEL = "qwen2.5:3b"

# ---------------------------------------------------------------------------
# SYSTEM RULES — defines every tool SILVIA may call
# ---------------------------------------------------------------------------
SYSTEM_RULES = """You are SILVIA's tool dispatcher. Output ONLY valid JSON. No prose, no markdown.

Valid shapes:
1) {"action":"call_tool","name":"<tool>","args":{...}}
2) {"action":"call_tools","calls":[{"name":"<tool>","args":{...}}, ...]}
3) {"action":"final"}

TOOLS:
- get_time: args {}
  Use for: "what time is it", "current time", "what's the time"

- get_time_in: args {"place": string}
  Use for ANY time query that mentions a city or country.
  Examples: "time in tokyo", "what time is it in Singapore", "what's the time in New York"

- get_weather: args {"place": string}
  Use for ANY weather/temperature query that names a place.
  Examples: "weather in London", "is it raining in Paris", "temperature in Berlin"

- search_web: args {"query": string}
  Use for factual questions, news, people, definitions, events, how-things-work, prices, specs.
  Default to search_web when no other tool applies and an answer is needed.

RULES:
- Time + weather for same place → call_tools with both.
- Weather with no location → {"action":"final"}
- Open/launch/volume/navigate commands → {"action":"final"}  (handled elsewhere)
- Greetings, capability questions, casual chat → {"action":"final"}
- Output ONE JSON object only. Nothing else.
"""

# ---------------------------------------------------------------------------
# FEW-SHOT examples
# ---------------------------------------------------------------------------
FEW_SHOTS: list[dict] = [
    {"role": "user",      "content": "what time is it"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_time","args":{}}'},

    {"role": "user",      "content": "what time is it in singapore"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_time_in","args":{"place":"singapore"}}'},

    {"role": "user",      "content": "what's the time in tokyo"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_time_in","args":{"place":"tokyo"}}'},

    {"role": "user",      "content": "time in new york"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_time_in","args":{"place":"new york"}}'},

    {"role": "user",      "content": "current time in dubai"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_time_in","args":{"place":"dubai"}}'},

    {"role": "user",      "content": "weather in london"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_weather","args":{"place":"london"}}'},

    {"role": "user",      "content": "what's the weather in tokyo"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_weather","args":{"place":"tokyo"}}'},

    {"role": "user",      "content": "is it raining in paris"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_weather","args":{"place":"paris"}}'},

    {"role": "user",      "content": "temperature in berlin"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_weather","args":{"place":"berlin"}}'},

    {"role": "user",      "content": "what's the time and weather in paris"},
    {"role": "assistant", "content": '{"action":"call_tools","calls":[{"name":"get_time_in","args":{"place":"paris"}},{"name":"get_weather","args":{"place":"paris"}}]}'},

    {"role": "user",      "content": "who is elon musk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_web","args":{"query":"elon musk"}}'},

    {"role": "user",      "content": "latest news on nvidia"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_web","args":{"query":"latest news nvidia"}}'},

    {"role": "user",      "content": "what is quantum computing"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_web","args":{"query":"what is quantum computing"}}'},

    {"role": "user",      "content": "how does a jet engine work"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_web","args":{"query":"how does a jet engine work"}}'},

    {"role": "user",      "content": "price of rtx 4090"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_web","args":{"query":"RTX 4090 price"}}'},

    {"role": "user",      "content": "hello"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "what can you do"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "brief me"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "open spotify"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "volume up"},
    {"role": "assistant", "content": '{"action":"final"}'},
]

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    t = text.strip()
    t = re.sub(r"^```[a-z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _parse(raw: str) -> dict:
    cleaned = _strip_fences(raw)
    obj = json.loads(cleaned)
    if isinstance(obj, dict) and "action" in obj:
        return obj
    # Sometimes the model wraps it: {"message":{"content":"..."}}
    if "message" in obj and "content" in obj.get("message", {}):
        inner = _strip_fences(obj["message"]["content"])
        return json.loads(inner)
    raise ValueError(f"No 'action' key in parsed JSON: {obj}")


# ---------------------------------------------------------------------------
# Regex fallback (used when Ollama is unavailable)
# ---------------------------------------------------------------------------

_TIME_IN_RE  = re.compile(r"time\s+(?:is\s+it\s+)?in\s+([a-zA-Z\s\-,]+?)[\?\.!]?$")
_WEATHER_RE  = re.compile(r"(?:weather|climate)\s+(?:in|at|for|like\s+in)\s+([a-zA-Z\s\-,]+?)[\?\.!]?$")
_TEMP_RE     = re.compile(r"temperature\s+in\s+([a-zA-Z\s\-,]+?)[\?\.!]?$")
_RAIN_RE     = re.compile(r"(?:is\s+it\s+)?raining\s+in\s+([a-zA-Z\s\-,]+?)[\?\.!]?$")
_HOT_COLD_RE = re.compile(r"(?:is\s+it\s+)?(?:hot|cold|warm|freezing|sunny)\s+in\s+([a-zA-Z\s\-,]+?)[\?\.!]?$")


def _regex_fallback(query: str) -> dict:
    text = query.lower().strip()

    m = _TIME_IN_RE.search(text)
    if m:
        return {"action": "call_tool", "name": "get_time_in", "args": {"place": m.group(1).strip()}}

    if re.search(r"\btime\b", text) and "in" not in text:
        return {"action": "call_tool", "name": "get_time", "args": {}}

    m = _WEATHER_RE.search(text) or _TEMP_RE.search(text) or _RAIN_RE.search(text) or _HOT_COLD_RE.search(text)
    if m:
        return {"action": "call_tool", "name": "get_weather", "args": {"place": m.group(1).strip()}}

    return {"action": "final"}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def plan(query: str, allow_web: bool = False) -> dict:
    """
    Route a query to a tool decision.

    Fast path: regex handles time/weather instantly. The LLM planner is only
    invoked when web search is enabled AND regex didn't match a tool, so that
    the planner can disambiguate factual questions that need web search. For
    pure conversation, we skip the LLM entirely.
    """
    regex_result = _regex_fallback(query)
    if regex_result.get("action") != "final":
        logger.info("Planner (regex): %s", regex_result)
        return regex_result

    if not allow_web:
        return {"action": "final"}

    # Only reach here when web is enabled and regex didn't match a specific tool.
    messages = (
        [{"role": "system", "content": SYSTEM_RULES}]
        + FEW_SHOTS
        + [{"role": "user", "content": query}]
    )
    payload = {
        "model": _PLANNING_MODEL,
        "messages": messages,
        "options": {"temperature": 0.1},
        "format": "json",
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(OLLAMA_CHAT_URL, json=payload)
            resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        result = _parse(raw)
        logger.info("Planner (llm): %s", result)
        return result
    except Exception as exc:
        logger.warning("Planner LLM call failed (%s), using regex fallback", exc)
        return _regex_fallback(query)
