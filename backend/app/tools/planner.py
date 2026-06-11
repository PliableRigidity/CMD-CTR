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

- get_node_telemetry: args {"node": string}
  Use for ANY query about node telemetry, metrics, CPU, RAM, disk, temperature, health, or status display.
  Set node to the node name for a specific node. Set node="all" (or leave empty) for all nodes.
  Examples: "show workstation telemetry", "workstation cpu", "workstation ram", "pi5 telemetry",
            "show all node telemetry", "show hottest node", "node health", "infrastructure status",
            "show nighthawk metrics", "workstation status", "show workstation health"
  IMPORTANT: Always call this tool immediately — never say "I need to check the registry."
  If the data exists, display it. If it does not, explain exactly why (e.g. no agent configured).

- verify_node: args {"node": string}
  Run the full verification chain on a named node: silvia-agent → tailscale → DNS → ping.
  Updates last_verified and verification_source in the registry.
  Examples: "verify nighthawk", "confirm pi5 is online", "check workstation connectivity", "verify server1"

- refresh_nodes: args {}
  Verify all registered nodes using the full chain.
  Examples: "verify all nodes", "refresh nodes", "check all nodes", "run verification"

- get_node_info: args {"node": string}
  Use when user asks for network details: IP address, connectivity, probe results of a node.
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

- get_stock_price: args {"query": string}
  Use for ANY stock price, share price, or market quote query.
  query should be the company name or ticker symbol exactly as said.
  Examples: "price of Apple", "AAPL stock price", "how much is Tesla", "NVDA quote", "what is Microsoft trading at"
  NEVER use search_web for stock price queries — always use get_stock_price.

- get_watch_alerts: args {}
  Return all active Watch Officer alerts. Use for any query about alerts, watch officer status, or what's being monitored.
  Examples: "show alerts", "active alerts", "watch officer status", "any alerts", "what alerts are active", "show watch alerts"

- set_reminder: args {"raw": string}
  Set a reminder. raw is the full reminder text after "remind me".
  Examples: raw="in 10 minutes to check pi5", raw="tomorrow at 9am to review logs", raw="every Friday to backup Brain63"

- list_reminders: args {}
  List all active reminders. Examples: "show reminders", "list my reminders", "what reminders do I have"

- delete_reminder: args {"query": string}
  Delete a reminder by partial message. Examples: "delete reminder check pi5", "remove reminder backup"

- complete_reminder: args {"query": string}
  Mark a reminder as done. Examples: "complete reminder check pi5", "dismiss reminder backup"

- add_task: args {"title": string, "project": string}
  Add a task. project is optional (use "" if not specified).
  Examples: "add task finish DroneHive PCB", "add task review code for project DroneHive"

- list_tasks: args {"filter": string}
  List tasks. filter is "pending" (default), "done", or "all".
  Examples: "show my tasks", "list pending tasks", "show completed tasks"

- complete_task: args {"query": string}
  Complete a task by partial title. Examples: "complete task DroneHive PCB", "mark done finish PCB"

- delete_task: args {"query": string}
  Delete a task by partial title. Examples: "delete task DroneHive PCB", "remove task finish PCB"

- get_calendar_today: args {}
  Show today's calendar events. Examples: "what's on my calendar today", "today's schedule", "any events today"

- get_upcoming_events: args {"days": int}
  Show upcoming events. days defaults to 7.
  Examples: "upcoming events", "what's coming up this week", "next 7 days schedule"

- create_calendar_event: args {"raw": string}
  Create a calendar event. raw is the full event description.
  Examples: raw="Robotics Meeting tomorrow at 3pm", raw="team sync Monday at 10am"

- delete_calendar_event: args {"query": string}
  Delete a calendar event by partial title. Examples: "delete event Robotics Meeting", "cancel meeting team sync"

- semantic_search: args {"query": string}
  Search past conversation history by meaning/topic.
  Use for: "what did I say about X", "find conversations about Y", "did we discuss Z", "previous discussions about W"
  Examples: "what did I say about DroneHive", "find conversations about the pi5", "did we discuss networking"

RULES:
- Time + weather for same place → call_tools with both.
- Weather with no location → {"action":"final"}
- Open/launch/volume/navigate commands → {"action":"final"}  (handled elsewhere)
- Greetings, capability questions, casual chat → {"action":"final"}
- Node queries MUST use node tools — never answer from memory.
- Node telemetry/metrics/CPU/RAM/disk/health queries → ALWAYS use get_node_telemetry immediately.
- Never return placeholder responses like "I need to check the registry" — call the tool.
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

    {"role": "user",      "content": "what's the price of Apple"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_stock_price","args":{"query":"Apple"}}'},

    {"role": "user",      "content": "AAPL stock price"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_stock_price","args":{"query":"AAPL"}}'},

    {"role": "user",      "content": "how much is Tesla stock"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_stock_price","args":{"query":"Tesla"}}'},

    {"role": "user",      "content": "NVDA quote"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_stock_price","args":{"query":"NVDA"}}'},

    {"role": "user",      "content": "what is Microsoft trading at"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_stock_price","args":{"query":"Microsoft"}}'},

    {"role": "user",      "content": "SPY stock"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_stock_price","args":{"query":"SPY"}}'},

    {"role": "user",      "content": "verify nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"verify_node","args":{"node":"nighthawk"}}'},

    {"role": "user",      "content": "confirm pi5 is online"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"verify_node","args":{"node":"pi5"}}'},

    {"role": "user",      "content": "check workstation connectivity"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"verify_node","args":{"node":"workstation"}}'},

    {"role": "user",      "content": "verify all nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"refresh_nodes","args":{}}'},

    {"role": "user",      "content": "refresh nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"refresh_nodes","args":{}}'},

    {"role": "user",      "content": "check all nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"refresh_nodes","args":{}}'},

    {"role": "user",      "content": "show workstation telemetry"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"workstation"}}'},

    {"role": "user",      "content": "workstation telemetry"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"workstation"}}'},

    {"role": "user",      "content": "show workstation cpu"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"workstation"}}'},

    {"role": "user",      "content": "show workstation ram"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"workstation"}}'},

    {"role": "user",      "content": "show workstation status"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"workstation"}}'},

    {"role": "user",      "content": "pi5 telemetry"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"pi5"}}'},

    {"role": "user",      "content": "show nighthawk metrics"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"nighthawk"}}'},

    {"role": "user",      "content": "show all node telemetry"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"all"}}'},

    {"role": "user",      "content": "show hottest node"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"all"}}'},

    {"role": "user",      "content": "show node health"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"all"}}'},

    {"role": "user",      "content": "show infrastructure status"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_node_telemetry","args":{"node":"all"}}'},

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

    {"role": "user",      "content": "show alerts"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_watch_alerts","args":{}}'},

    {"role": "user",      "content": "active alerts"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_watch_alerts","args":{}}'},

    {"role": "user",      "content": "watch officer status"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_watch_alerts","args":{}}'},

    {"role": "user",      "content": "what alerts are active"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_watch_alerts","args":{}}'},

    {"role": "user",      "content": "show watch alerts"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_watch_alerts","args":{}}'},

    {"role": "user",      "content": "any alerts"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_watch_alerts","args":{}}'},

    # ── Reminders ──────────────────────────────────────────────────────────────
    {"role": "user",      "content": "remind me in 10 minutes to check the pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"set_reminder","args":{"raw":"in 10 minutes to check the pi5"}}'},

    {"role": "user",      "content": "remind me tomorrow at 9am to review the logs"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"set_reminder","args":{"raw":"tomorrow at 9am to review the logs"}}'},

    {"role": "user",      "content": "remind me every Friday to backup Brain63"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"set_reminder","args":{"raw":"every Friday to backup Brain63"}}'},

    {"role": "user",      "content": "remind me to call mom tomorrow at 3pm"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"set_reminder","args":{"raw":"to call mom tomorrow at 3pm"}}'},

    {"role": "user",      "content": "show reminders"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_reminders","args":{}}'},

    {"role": "user",      "content": "list my reminders"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_reminders","args":{}}'},

    {"role": "user",      "content": "delete reminder check pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"delete_reminder","args":{"query":"check pi5"}}'},

    {"role": "user",      "content": "complete reminder backup"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"complete_reminder","args":{"query":"backup"}}'},

    # ── Tasks ──────────────────────────────────────────────────────────────────
    {"role": "user",      "content": "add task: finish DroneHive PCB"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_task","args":{"title":"finish DroneHive PCB","project":""}}'},

    {"role": "user",      "content": "add task review motor controller code"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_task","args":{"title":"review motor controller code","project":""}}'},

    {"role": "user",      "content": "show my tasks"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_tasks","args":{"filter":"pending"}}'},

    {"role": "user",      "content": "list pending tasks"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_tasks","args":{"filter":"pending"}}'},

    {"role": "user",      "content": "complete task DroneHive PCB"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"complete_task","args":{"query":"DroneHive PCB"}}'},

    {"role": "user",      "content": "delete task review code"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"delete_task","args":{"query":"review code"}}'},

    # ── Calendar ───────────────────────────────────────────────────────────────
    {"role": "user",      "content": "what's on my calendar today"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_calendar_today","args":{}}'},

    {"role": "user",      "content": "today's schedule"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_calendar_today","args":{}}'},

    {"role": "user",      "content": "upcoming events"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_upcoming_events","args":{"days":7}}'},

    {"role": "user",      "content": "what's coming up this week"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_upcoming_events","args":{"days":7}}'},

    {"role": "user",      "content": "create an event Robotics Meeting tomorrow at 3pm"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"create_calendar_event","args":{"raw":"Robotics Meeting tomorrow at 3pm"}}'},

    {"role": "user",      "content": "schedule team sync Monday at 10am"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"create_calendar_event","args":{"raw":"team sync Monday at 10am"}}'},

    {"role": "user",      "content": "delete event Robotics Meeting"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"delete_calendar_event","args":{"query":"Robotics Meeting"}}'},

    # ── Semantic memory ────────────────────────────────────────────────────────
    {"role": "user",      "content": "what did I say about DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"semantic_search","args":{"query":"DroneHive"}}'},

    {"role": "user",      "content": "find conversations about the pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"semantic_search","args":{"query":"pi5"}}'},

    {"role": "user",      "content": "did we discuss networking"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"semantic_search","args":{"query":"networking"}}'},

    {"role": "user",      "content": "show previous discussions about nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"semantic_search","args":{"query":"nodes"}}'},

    {"role": "user",      "content": "what have we talked about regarding the weather"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"semantic_search","args":{"query":"weather"}}'},
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

# Stock price — matches "AAPL stock", "price of Tesla", "how much is NVDA", "Microsoft quote"
_STOCK_RE = re.compile(
    r"(?:"
    r"(?:what(?:'s|\s+is)?\s+(?:the\s+)?)?(?:stock\s+)?(?:price|quote|value)\s+(?:of|for)\s+([A-Za-z][A-Za-z0-9\s.\-&]{1,30}?)|"
    r"([A-Za-z][A-Za-z0-9\s.\-&]{0,25}?)\s+(?:stock\s+)?(?:price|quote|share\s+price)|"
    r"how\s+much\s+is\s+([A-Za-z][A-Za-z0-9\s.\-&]{1,25}?)(?:\s+(?:stock|shares?|trading))?|"
    r"([A-Za-z][A-Za-z0-9\s.\-&]{0,20}?)\s+(?:is\s+)?trading\s+at|"
    r"([A-Z]{1,6})\s+stock"
    r")[\?\.!]?$",
    re.I,
)

# Node / networking regexes — single-word node names (alphanumeric + dash/underscore)
_N = r"([a-z0-9][a-z0-9_\-]*)"   # node name capture group
_IP = r"([\d\.a-z0-9\-]+)"        # IP/hostname value

# Telemetry / metrics keyword group
_TKW = r"(?:telemetry|metrics?|stats?|health|status|cpu|ram|memory|disk|temperature|temp|uptime|load)"

# "[show] <node> <metric>" — e.g. "show workstation telemetry", "workstation cpu"
_NODE_TELEM = re.compile(
    rf"^(?:(?:show|get|display|check)\s+)?{_N}(?:'s)?\s+{_TKW}[\?\.!]?$", re.I
)
# "show <metric> [for/of] <node>" — e.g. "show telemetry for pi5", "check cpu of nighthawk"
_NODE_TELEM_FOR = re.compile(
    rf"^(?:show|get|display|check)\s+{_TKW}(?:\s+(?:for|of|on|from))?\s+{_N}[\?\.!]?$", re.I
)
# All-node queries — "show all node telemetry", "node health", "infrastructure status"
_ALL_TELEM = re.compile(
    r"^(?:show\s+)?(?:all\s+)?(?:node|nodes?|infrastructure)\s+" + _TKW + r"[\?\.!]?$", re.I
)
# "show hottest node" / "hottest node"
_HOTTEST_NODE = re.compile(r"^(?:show\s+)?hottest(?:\s+node)?[\?\.!]?$", re.I)

# Verification
_NODE_VERIFY = re.compile(
    rf"^(?:verify|confirm|validate)\s+{_N}(?:\s+(?:is\s+)?(?:online|up|reachable|active))?[\?\.!]?$", re.I
)
_REFRESH_NODES = re.compile(
    r"^(?:verify|refresh|check|run)\s+(?:all\s+)?(?:nodes?|devices?|machines?|verification)[\?\.!]?$", re.I
)

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

# ── Personal ops regexes ─────────────────────────────────────────────────────

_REMIND_SET = re.compile(r'^(?:remind\s+me|set\s+(?:a\s+)?reminder(?:\s+for)?)\s+(.+)$', re.I)

_REMIND_LIST = re.compile(
    r'^(?:show|list|display|get|what)\s+(?:my\s+)?reminders?[\?\.!]?$'
    r'|^(?:do\s+i\s+have\s+)?any\s+reminders?[\?\.!]?$',
    re.I,
)
_REMIND_DELETE = re.compile(r'^(?:delete|remove|cancel)\s+reminder\s+(.+?)[\?\.!]?$', re.I)
_REMIND_COMPLETE = re.compile(r'^(?:complete|dismiss|done\s+with)\s+reminder\s+(.+?)[\?\.!]?$', re.I)

_TASK_ADD = re.compile(r'^(?:add|create|new)\s+(?:a\s+)?task[:\s]+(.+?)[\?\.!]?$', re.I)
_TASK_LIST = re.compile(
    r'^(?:show|list|display|get)\s+(?:my\s+)?(?:pending\s+)?tasks?[\?\.!]?$'
    r'|^(?:what(?:\s+tasks?)?(?:\s+do\s+i\s+have)?|my\s+tasks?)[\?\.!]?$',
    re.I,
)
_TASK_LIST_ALL = re.compile(r'^(?:show|list)\s+all\s+tasks?[\?\.!]?$', re.I)
_TASK_LIST_DONE = re.compile(r'^(?:show|list)\s+(?:done|completed|finished)\s+tasks?[\?\.!]?$', re.I)
_TASK_COMPLETE = re.compile(r'^(?:complete|finish|mark\s+(?:done|complete))\s+task\s+(.+?)[\?\.!]?$', re.I)
_TASK_DELETE = re.compile(r'^(?:delete|remove)\s+task\s+(.+?)[\?\.!]?$', re.I)

_CAL_TODAY = re.compile(
    r"(?:what(?:'s|\s+is)?\s+(?:on\s+)?(?:my\s+)?calendar\s+today"
    r"|today(?:'s)?\s+(?:schedule|events?|calendar|agenda)"
    r"|(?:any|show)\s+events?\s+today"
    r"|(?:show|get)\s+(?:my\s+)?(?:today(?:'s)?\s+)?calendar)",
    re.I,
)
_CAL_UPCOMING = re.compile(
    r"(?:upcoming\s+(?:events?|meetings?|schedule|appointments?)"
    r"|(?:what(?:'s|\s+is)?\s+)?coming\s+up"
    r"|(?:next|this)\s+week(?:'s)?\s+(?:schedule|events?|calendar)"
    r"|(?:show|get)\s+(?:my\s+)?upcoming\s+(?:events?|schedule))",
    re.I,
)
_CAL_CREATE = re.compile(
    r'^(?:create|add|schedule|book)\s+(?:a[n]?\s+)?(?:new\s+)?(?:event|meeting|appointment|call)\s+(.+)$',
    re.I,
)
_CAL_DELETE = re.compile(
    r'^(?:delete|cancel|remove)\s+(?:event|meeting|appointment)\s+(.+?)[\?\.!]?$', re.I
)

# Watch Officer alerts
_WATCH_ALERTS_RE = re.compile(
    r"^(?:"
    r"(?:show\s+)?(?:watch\s+(?:officer\s+)?alerts?|active\s+alerts?|alerts?\s+list|ops\s+alerts?)|"
    r"watch\s+officer\s+status|"
    r"what(?:'s|\s+is)?\s+(?:on\s+the\s+)?watch(?:\s+officer)?|"
    r"what\s+alerts?\s+(?:are\s+)?(?:active|there)|"
    r"any\s+(?:active\s+)?alerts?|"
    r"show\s+alerts?"
    r")[\?\.!]?$",
    re.I,
)


# Semantic memory search
_SEMANTIC_SEARCH_RE = re.compile(
    r"(?:"
    r"what\s+(?:did\s+(?:I|we)\s+(?:say|mention|discuss|write|ask|talk\s+about)?\s*|have\s+(?:I|we)\s+(?:talked?|discussed?|said|mentioned?)\s+)(?:about|regarding|on|for)?\s+(.+?)"
    r"|find\s+(?:conversations?|discussions?|chats?)\s+(?:about|regarding|on)\s+(.+?)"
    r"|(?:show|search)\s+(?:previous|past|prior|my)\s+(?:conversations?|discussions?|messages?|history)\s+(?:about|regarding|on)\s+(.+?)"
    r"|did\s+(?:we|I)\s+(?:discuss|talk\s+about|mention)\s+(.+?)"
    r"|search\s+(?:memory|history|conversations?)\s+(?:for|about)?\s*(.+?)"
    r")[\?\.!]?$",
    re.I,
)


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

    # Verification — check before telemetry/status patterns
    if _REFRESH_NODES.match(text):
        return {"action": "call_tool", "name": "refresh_nodes", "args": {}}

    m = _NODE_VERIFY.match(text)
    if m:
        return {"action": "call_tool", "name": "verify_node", "args": {"node": m.group(1).strip()}}

    # Telemetry / metrics — checked before generic status so "show workstation status" hits this
    if _ALL_TELEM.match(text) or _HOTTEST_NODE.match(text):
        return {"action": "call_tool", "name": "get_node_telemetry", "args": {"node": "all"}}

    m = _NODE_TELEM.match(text)
    if m:
        return {"action": "call_tool", "name": "get_node_telemetry", "args": {"node": m.group(1).strip()}}

    m = _NODE_TELEM_FOR.match(text)
    if m:
        return {"action": "call_tool", "name": "get_node_telemetry", "args": {"node": m.group(1).strip()}}

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

    m = _STOCK_RE.search(query)
    if m:
        raw = next((g for g in m.groups() if g), "").strip()
        if raw:
            return {"action": "call_tool", "name": "get_stock_price", "args": {"query": raw}}

    if _WATCH_ALERTS_RE.match(text):
        return {"action": "call_tool", "name": "get_watch_alerts", "args": {}}

    # ── Semantic memory search ────────────────────────────────────────────────
    m = _SEMANTIC_SEARCH_RE.search(query)
    if m:
        q = next((g for g in m.groups() if g), "").strip()
        if q:
            return {"action": "call_tool", "name": "semantic_search", "args": {"query": q}}

    # ── Personal ops ─────────────────────────────────────────────────────────
    m = _REMIND_SET.match(query)
    if m:
        return {"action": "call_tool", "name": "set_reminder", "args": {"raw": m.group(1).strip()}}

    if _REMIND_LIST.match(text):
        return {"action": "call_tool", "name": "list_reminders", "args": {}}

    m = _REMIND_DELETE.match(text)
    if m:
        return {"action": "call_tool", "name": "delete_reminder", "args": {"query": m.group(1).strip()}}

    m = _REMIND_COMPLETE.match(text)
    if m:
        return {"action": "call_tool", "name": "complete_reminder", "args": {"query": m.group(1).strip()}}

    m = _TASK_ADD.match(query)
    if m:
        return {"action": "call_tool", "name": "add_task", "args": {"title": m.group(1).strip(), "project": ""}}

    if _TASK_LIST_ALL.match(text):
        return {"action": "call_tool", "name": "list_tasks", "args": {"filter": "all"}}
    if _TASK_LIST_DONE.match(text):
        return {"action": "call_tool", "name": "list_tasks", "args": {"filter": "done"}}
    if _TASK_LIST.match(text):
        return {"action": "call_tool", "name": "list_tasks", "args": {"filter": "pending"}}

    m = _TASK_COMPLETE.match(text)
    if m:
        return {"action": "call_tool", "name": "complete_task", "args": {"query": m.group(1).strip()}}

    m = _TASK_DELETE.match(text)
    if m:
        return {"action": "call_tool", "name": "delete_task", "args": {"query": m.group(1).strip()}}

    if _CAL_TODAY.search(text):
        return {"action": "call_tool", "name": "get_calendar_today", "args": {}}

    if _CAL_UPCOMING.search(text):
        return {"action": "call_tool", "name": "get_upcoming_events", "args": {"days": 7}}

    m = _CAL_CREATE.match(query)
    if m:
        return {"action": "call_tool", "name": "create_calendar_event", "args": {"raw": m.group(1).strip()}}

    m = _CAL_DELETE.match(text)
    if m:
        return {"action": "call_tool", "name": "delete_calendar_event", "args": {"query": m.group(1).strip()}}

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
