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

- get_node_ip: args {"node": string}
  Use when user asks for the IP or address of a node/device/machine.
  Examples: "what's the IP of nighthawk", "nighthawk IP address", "address of server1"

- ping_node: args {"node": string}
  Use when user asks to ping a node or check if it's reachable/online.
  Examples: "ping nighthawk", "is nighthawk online", "check server1 connectivity"

- list_nodes: args {}
  Use when user asks what nodes are registered, online, or on the network.
  Examples: "what nodes are online", "list my devices", "what machines do I have"

- get_node_info: args {"node": string}
  Use when user asks about a specific node's status, details, or info.
  Examples: "status of nighthawk", "nighthawk info", "what's the status of server1"

- update_node_ip: args {"node": string, "ip": string}
  Use when user asks to update/set a node's IP address.
  Examples: "update nighthawk IP to 192.168.1.50", "set server1 address to 10.0.0.1"

- delete_node: args {"node": string}
  Use when user asks to delete or remove a node from the registry.
  Examples: "delete nighthawk", "remove server1 from the registry"

- add_node: args {"node": string, "hostname": string}
  Use when user asks to add, register, or create a new node/device.
  Examples: "add laptop", "register server1 at 192.168.1.10", "add nighthawk at 100.64.1.5"
  If no hostname given, use hostname="" and SILVIA will ask for it.

- ssh_node: args {"node": string, "username": string}
  Use when user wants to SSH into a node or open a remote terminal.
  Examples: "ssh into nighthawk", "connect to server1", "ssh nighthawk as admin"
  If no username given, use username="" and SILVIA will ask for it.

- get_system_specs: args {}
  Use when user asks about their system, machine, hardware, CPU, RAM, GPU, disk, or OS.
  Examples: "what are my system specs", "system configuration", "cpu info", "how much RAM", "what GPU do I have", "system information"

- get_network_info: args {}
  Use when user asks about their local network interfaces, local IP addresses, or adapters.
  Examples: "what are my network interfaces", "show my IP address", "network adapters", "local IP", "ipconfig"
  NOTE: For IPs of registered NODES use get_node_ip instead. This tool is for the local machine's own interfaces.

- get_process_info: args {}
  Use when user asks what processes or applications are running on the local machine.
  Examples: "show running processes", "what's running", "list processes", "top processes", "what apps are running"

- run_command: args {"cmd": string}
  Use when user wants to run a specific shell or terminal command.
  Examples: "run ipconfig", "execute netstat -an", "terminal systeminfo", "run Get-Service", "run tasklist"
  Extract the command verbatim into the cmd argument. Do NOT add 'powershell' prefix.

RULES:
- Time + weather for same place → call_tools with both.
- Weather with no location → {"action":"final"}
- Open/launch/volume/navigate commands → {"action":"final"}  (handled elsewhere)
- Greetings, capability questions, casual chat → {"action":"final"}
- Node queries MUST use node tools — never answer from memory.
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

    {"role": "user",      "content": "what's the IP of nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_ip","args":{"node":"nighthawk"}}'},

    {"role": "user",      "content": "nighthawk IP address"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_ip","args":{"node":"nighthawk"}}'},

    {"role": "user",      "content": "ping nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"ping_node","args":{"node":"nighthawk"}}'},

    {"role": "user",      "content": "is nighthawk online"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"ping_node","args":{"node":"nighthawk"}}'},

    {"role": "user",      "content": "what nodes are online"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_nodes","args":{}}'},

    {"role": "user",      "content": "list my devices"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_nodes","args":{}}'},

    {"role": "user",      "content": "status of nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_info","args":{"node":"nighthawk"}}'},

    {"role": "user",      "content": "update nighthawk IP to 192.168.1.50"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_node_ip","args":{"node":"nighthawk","ip":"192.168.1.50"}}'},

    {"role": "user",      "content": "delete nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"delete_node","args":{"node":"nighthawk"}}'},

    {"role": "user",      "content": "add laptop"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_node","args":{"node":"laptop","hostname":""}}'},

    {"role": "user",      "content": "register server1 at 192.168.1.10"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_node","args":{"node":"server1","hostname":"192.168.1.10"}}'},

    {"role": "user",      "content": "add a node"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_node","args":{"node":"","hostname":""}}'},

    {"role": "user",      "content": "ssh into nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"ssh_node","args":{"node":"nighthawk","username":""}}'},

    {"role": "user",      "content": "connect to server1"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"ssh_node","args":{"node":"server1","username":""}}'},

    {"role": "user",      "content": "ssh nighthawk as admin"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"ssh_node","args":{"node":"nighthawk","username":"admin"}}'},

    {"role": "user",      "content": "open terminal on nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"ssh_node","args":{"node":"nighthawk","username":""}}'},

    {"role": "user",      "content": "what are my system specs"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_system_specs","args":{}}'},

    {"role": "user",      "content": "system configuration"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_system_specs","args":{}}'},

    {"role": "user",      "content": "how much RAM do I have"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_system_specs","args":{}}'},

    {"role": "user",      "content": "what GPU do I have"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_system_specs","args":{}}'},

    {"role": "user",      "content": "cpu usage"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_system_specs","args":{}}'},

    {"role": "user",      "content": "what are my network interfaces"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_network_info","args":{}}'},

    {"role": "user",      "content": "what's my local IP address"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_network_info","args":{}}'},

    {"role": "user",      "content": "show running processes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_process_info","args":{}}'},

    {"role": "user",      "content": "what's running on my machine"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_process_info","args":{}}'},

    {"role": "user",      "content": "run ipconfig"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"run_command","args":{"cmd":"ipconfig"}}'},

    {"role": "user",      "content": "run netstat -an"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"run_command","args":{"cmd":"netstat -an"}}'},

    {"role": "user",      "content": "execute systeminfo"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"run_command","args":{"cmd":"systeminfo"}}'},

    {"role": "user",      "content": "terminal tasklist"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"run_command","args":{"cmd":"tasklist"}}'},
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

# Node / networking regexes — single-word node names (alphanumeric + dash/underscore)
_N = r"([a-z0-9][a-z0-9_\-]*)"   # node name capture group
_IP = r"([\d\.a-z0-9\-]+)"        # IP/hostname value

_NODE_IP_OF    = re.compile(rf"(?:ip(?:\s+address)?|address)\s+of\s+{_N}[\?\.!]?$", re.I)
_NODE_IP_NAME  = re.compile(rf"what(?:'s| is)\s+(?:the\s+)?ip(?:\s+address)?\s+of\s+{_N}[\?\.!]?$", re.I)
_NODE_IP_POSS  = re.compile(rf"{_N}'s\s+(?:ip(?:\s+address)?|address)[\?\.!]?$", re.I)
_NODE_PING     = re.compile(rf"^ping\s+{_N}[\?\.!]?$", re.I)
_NODE_IS_UP    = re.compile(rf"is\s+{_N}\s+(?:online|up|reachable|alive|running)[\?\.!]?$", re.I)
_NODE_PROBE    = re.compile(rf"^(?:probe|check|test)\s+{_N}[\?\.!]?$", re.I)
_NODE_LIST     = re.compile(r"(?:list|show)\s+(?:my\s+)?(?:nodes|devices|machines|hosts|servers)[\?\.!]?$", re.I)
_NODE_LIST2    = re.compile(r"what\s+(?:nodes|devices|machines)\s+(?:(?:do\s+i\s+have|are\s+(?:online|registered|available)))[\?\.!]?$", re.I)
_NODE_WHATS_ON = re.compile(r"what(?:'s|\s+is)?\s+(?:nodes?\s+)?(?:are\s+)?online[\?\.!]?$", re.I)
_NODE_STATUS   = re.compile(rf"(?:status|info)\s+(?:of|on|for)\s+{_N}[\?\.!]?$", re.I)
_NODE_STATUS2  = re.compile(rf"{_N}\s+(?:status|info)[\?\.!]?$", re.I)
_NODE_UPD_IP   = re.compile(rf"(?:update|set|change|assign)\s+{_N}(?:'s)?\s+(?:ip(?:\s+address)?|address)\s+to\s+{_IP}[\?\.!]?$", re.I)
_NODE_DELETE   = re.compile(rf"^(?:delete|remove)\s+{_N}(?:\s+(?:node|from\s+(?:the\s+)?registry))?[\?\.!]?$", re.I)
_NODE_ADD      = re.compile(
    rf"^(?:add|register|create)\s+"
    rf"(?:a\s+(?:new\s+)?node(?:\s+called)?\s+)?"
    rf"{_N}"
    rf"(?:\s+(?:at|as|with\s+(?:ip|hostname|address)?)\s+{_IP})?[\?\.!]?$",
    re.I,
)
_NODE_ADD_GENERIC = re.compile(r"^(?:add|register|create)\s+a(?:\s+new)?\s+node[\?\.!]?$", re.I)

# System / terminal regexes
_SYS_SPECS    = re.compile(
    r"(?:what(?:'s|\s+are|\s+is)?\s+)?(?:my\s+)?(?:system|machine|computer|workstation|hardware|pc)\s+"
    r"(?:specs?|specifications?|config(?:uration)?|info(?:rmation)?|details?)[\?\.!]?$",
    re.I,
)
_SYS_SPECS2   = re.compile(r"^(?:show|get|display|check)\s+(?:system|hardware|machine)\s+(?:specs?|info|config)", re.I)
_SYS_CPU      = re.compile(r"(?:what(?:'s|\s+is)?\s+)?(?:my\s+)?(?:cpu|processor)(?:\s+(?:model|info|usage|speed|load))?[\?\.!]?$", re.I)
_SYS_RAM      = re.compile(
    r"(?:how\s+much\s+(?:ram|memory)(?:\s+do\s+i\s+have)?|"
    r"what(?:'s|\s+is)?\s+(?:my\s+)?(?:ram|memory)(?:\s+(?:usage|info|available|size))?)[\?\.!]?$",
    re.I,
)
_SYS_GPU      = re.compile(r"(?:what(?:\s+gpu|\s+graphics\s+card)?\s+(?:do\s+i\s+have|is\s+installed)|(?:my\s+)?gpu(?:\s+info)?)[\?\.!]?$", re.I)
_SYS_DISK     = re.compile(r"(?:how\s+much\s+(?:disk(?:\s+space)?|storage)|(?:disk|storage)\s+(?:usage|info|available|space))[\?\.!]?$", re.I)
_SYS_SYSINFO  = re.compile(r"^systeminfo[\?\.!]?$", re.I)

_SYS_NET      = re.compile(
    r"(?:(?:my\s+)?(?:network\s+(?:interfaces?|adapters?|info(?:rmation)?|config(?:uration)?)|"
    r"local\s+ip(?:\s+address)?|"
    r"what(?:'s|\s+is)?\s+my\s+(?:local\s+)?ip(?:\s+address)?|"
    r"ip\s+config(?:uration)?))[\?\.!]?$",
    re.I,
)
_SYS_IFCONFIG = re.compile(r"^(?:ifconfig|ipconfig|ip\s+addr)[\?\.!]?$", re.I)

_SYS_PROCS    = re.compile(
    r"(?:show|list|what(?:'s|\s+is)?|display)?\s*(?:running\s+)?(?:processes?|apps?|programs?|tasks?)"
    r"(?:\s+(?:list|running|info|that\s+are\s+running))?[\?\.!]?$",
    re.I,
)
_SYS_PROCS2   = re.compile(r"what(?:'s|\s+is)?\s+running(?:\s+on\s+my\s+(?:machine|computer|system))?[\?\.!]?$", re.I)
_SYS_TOP      = re.compile(r"^(?:top|tasklist|get-process|ps\s+aux)[\?\.!]?$", re.I)

_SYS_RUN      = re.compile(r"^(?:run|execute|terminal|cmd|shell)\s+(.+)$", re.I)


def _regex_system(query: str) -> dict | None:
    text = query.strip()

    # run_command — must check first so "run ipconfig" doesn't leak to other patterns
    m = _SYS_RUN.match(text)
    if m:
        return {"action": "call_tool", "name": "run_command", "args": {"cmd": m.group(1).strip()}}

    # system specs
    if (_SYS_SPECS.search(text) or _SYS_SPECS2.match(text)
            or _SYS_CPU.match(text) or _SYS_RAM.search(text)
            or _SYS_GPU.search(text) or _SYS_DISK.search(text)
            or _SYS_SYSINFO.match(text)):
        return {"action": "call_tool", "name": "get_system_specs", "args": {}}

    # network info (local machine only — node IPs handled by _regex_node)
    if _SYS_NET.search(text) or _SYS_IFCONFIG.match(text):
        return {"action": "call_tool", "name": "get_network_info", "args": {}}

    # process list
    if _SYS_PROCS.search(text) or _SYS_PROCS2.search(text) or _SYS_TOP.match(text):
        return {"action": "call_tool", "name": "get_process_info", "args": {}}

    return None


def _regex_node(query: str) -> dict | None:
    text = query.strip()

    m = _NODE_IP_NAME.search(text) or _NODE_IP_OF.search(text) or _NODE_IP_POSS.search(text)
    if m:
        return {"action": "call_tool", "name": "get_node_ip", "args": {"node": m.group(1).strip()}}

    m = _NODE_PING.match(text) or _NODE_IS_UP.search(text) or _NODE_PROBE.match(text)
    if m:
        return {"action": "call_tool", "name": "ping_node", "args": {"node": m.group(1).strip()}}

    if _NODE_LIST.search(text) or _NODE_LIST2.search(text) or _NODE_WHATS_ON.search(text):
        return {"action": "call_tool", "name": "list_nodes", "args": {}}

    m = _NODE_STATUS.search(text) or _NODE_STATUS2.search(text)
    if m:
        return {"action": "call_tool", "name": "get_node_info", "args": {"node": m.group(1).strip()}}

    m = _NODE_UPD_IP.search(text)
    if m:
        return {"action": "call_tool", "name": "update_node_ip", "args": {"node": m.group(1).strip(), "ip": m.group(2).strip()}}

    m = _NODE_DELETE.match(text)
    if m:
        return {"action": "call_tool", "name": "delete_node", "args": {"node": m.group(1).strip()}}

    # SSH
    m = re.match(
        rf"^(?:ssh(?:\s+into?)?|connect(?:\s+to)?|open\s+(?:ssh|terminal)(?:\s+(?:on|to))?)\s+{_N}"
        rf"(?:\s+as\s+([a-zA-Z0-9_.\-]+))?[\?\.!]?$",
        text, re.I,
    )
    if m:
        return {"action": "call_tool", "name": "ssh_node", "args": {
            "node": m.group(1).strip(),
            "username": m.group(2).strip() if m.lastindex and m.lastindex >= 2 and m.group(2) else "",
        }}

    if _NODE_ADD_GENERIC.match(text):
        return {"action": "call_tool", "name": "add_node", "args": {"node": "", "hostname": ""}}

    m = _NODE_ADD.match(text)
    if m:
        return {"action": "call_tool", "name": "add_node", "args": {
            "node": m.group(1).strip(),
            "hostname": m.group(2).strip() if m.lastindex and m.lastindex >= 2 and m.group(2) else "",
        }}

    return None


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

    system_result = _regex_system(query)
    if system_result:
        return system_result

    node_result = _regex_node(query)
    if node_result:
        return node_result

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
