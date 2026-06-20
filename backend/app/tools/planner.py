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
            "show nighthawk metrics", "workstation status", "show workstation health",
            "show drone-01 battery", "drone-01 mission state", "show robot telemetry"
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

- merge_nodes: args {"source": string, "target": string}
  Use when user asks to merge, consolidate, or combine two nodes. Source is deleted; its name becomes an alias on the target.
  Examples: "merge VPS into carrera", "consolidate nighthawk and nas", "merge pi_ai into pi-ai"

- deduplicate_nodes: args {}
  Use when user asks to find, clean up, or deduplicate the node registry.
  Examples: "deduplicate nodes", "clean up the registry", "find duplicate nodes", "show duplicate nodes"

- add_node: args {"node": string, "hostname": string}
  Use when user asks to add, register, or create a new node/device.
  Examples: "add laptop", "register server1 at 192.168.1.10", "add nighthawk at 100.64.1.5"
  If no hostname given, use hostname="" and SILVIA will ask for it.

- ssh_node: args {"node": string, "username": string}
  Use when user wants to SSH into a node or open a remote terminal.
  Examples: "ssh into nighthawk", "connect to server1", "ssh nighthawk as admin"
  If no username given, use username="" — SILVIA will use the stored SSH profile or ask.

- update_ssh_profile: args {"node": string, "username": string, "key_path": string}
  Use when user wants to set or change the SSH username or key for a node.
  Examples: "set ssh username for carrera to ishaan", "configure nighthawk ssh as pi",
            "update pi_ai ssh to use key ~/.ssh/id_ed25519", "set carrera ssh key to default"
  Use key_path="" if no key change requested. Use username="" if no username change requested.

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

- list_emails: args {"folder": string, "search": string, "limit": int}
  List emails from Gmail. folder: "inbox" (default) or "unread". search: Gmail query string (optional).
  Use for: "show my emails", "show unread emails", "emails from X", "important emails", "latest emails"
  Examples: folder="inbox" search="" limit=10 | folder="unread" search="" | folder="inbox" search="from:YTL"

- search_emails: args {"query": string, "limit": int}
  Search Gmail by keyword or sender. Use for: "find emails about X", "search for emails from Y"
  Examples: query="DroneHive" | query="internship" | query="from:hayley@"

- draft_email: args {"to": string, "subject": string, "body": string}
  Create a Gmail draft. DO NOT call this if the user wants to SEND — use send_email for sending.
  subject and body may be left empty if the user didn't specify them (SILVIA will fill them in later).
  Use for: "draft email to Yoke", "write email to Hayley about DroneHive"

- send_email: args {"to": string, "subject": string, "body": string}
  Send an email via Gmail. ALWAYS REQUIRES USER CONFIRMATION — SILVIA will ask before sending.
  Use for: "send email to Hayley", "email Yoke about the meeting"

- connect_google: args {}
  Start Google OAuth flow. Use for: "connect to Google", "sign in to Google", "authorize Google"

- show_productivity_status: args {}
  Show current Google/Gmail/Calendar connection status. Use for: "productivity status", "is Google connected", "gmail status", "show google status"

- list_gcal_events: args {"date": string, "days": int}
  List Google Calendar events. date: "today" or "YYYY-MM-DD". days: number of days to show (default 1).
  Use for: "show my Google calendar", "what's on my calendar", "calendar for this week", "what do I have tomorrow"
  Examples: date="today" days=1 | date="today" days=7 | date="2026-06-17" days=1

- create_gcal_event: args {"title": string, "start_iso": string, "end_iso": string, "description": string, "location": string}
  Create a Google Calendar event. start_iso and end_iso are ISO 8601 datetimes (UTC).
  Convert natural language dates using context. end_iso defaults to 1 hour after start if empty.
  Use for: "create meeting tomorrow at 3pm", "schedule call with Yoke Friday at 10am", "book DroneHive review next Monday"

- delete_gcal_event: args {"event_id": string, "title": string}
  Delete a Google Calendar event. REQUIRES USER CONFIRMATION.
  Use for: "cancel event DroneHive review", "delete meeting tomorrow"

- semantic_search: args {"query": string}
  Search past conversation history by meaning/topic.
  Use for: "what did I say about X", "find conversations about Y", "did we discuss Z", "previous discussions about W"
  Examples: "what did I say about DroneHive", "find conversations about the pi5", "did we discuss networking"

- list_nodes_by_type: args {"type": string}
  List all registered nodes of a specific type. type can be: drone, robot, esp32, sensor-network, workstation, server, etc.
  Examples: "list drones", "show all robots", "what drones do I have", "list esp32 nodes", "show all sensor nodes"

- send_node_command: args {"node": string, "command": string, "payload": dict}
  Send a command to a node via its silvia-agent. Allowed commands: arm, disarm, land, home, emergency_stop, reboot, restart_service.
  Destructive commands (arm, disarm, reboot, emergency_stop) will prompt for confirmation before executing.
  payload is optional — use {} if not needed.
  Examples: "arm drone-01", "disarm drone-01", "land drone-01", "send drone-01 home", "emergency stop drone-01", "reboot pi5"

- send_bulk_command: args {"type": string, "command": string}
  Send a command to ALL nodes of a given type simultaneously. Destructive commands require confirmation.
  type can be: drone, robot, esp32, sensor-network, vps, server, etc.
  Examples: "land all drones", "disarm all robots", "emergency stop all drones", "reboot all vps"

- schedule_task: args {"name": string, "prompt": string, "interval_minutes": int}
  Schedule a recurring Hermes task. name is a short label, prompt is what SILVIA will run, interval_minutes is how often.
  Examples: "schedule task: check node health every 60 minutes", "schedule a task to list all nodes every 30 minutes"

- list_scheduled_tasks: args {}
  Show all scheduled tasks with their status and last result.
  Examples: "show scheduled tasks", "list scheduled tasks", "what scheduled tasks do I have"

- disable_scheduled_task: args {"name": string}
  Disable (pause) a scheduled task by name.
  Examples: "disable scheduled task node health", "pause task node health"

- delete_scheduled_task: args {"name": string}
  Delete a scheduled task permanently.
  Examples: "delete scheduled task node health", "remove task node health"

- morning_briefing: args {}
  Generate a grounded morning briefing from real data: active projects, pending tasks, due reminders, today's calendar, alerts, offline nodes.
  Use for: "morning briefing", "good morning", "daily briefing", "what's happening today", "briefing", "status report"
  NEVER invent content — only data from the system is shown.

- evening_review: args {}
  End-of-day review: tasks completed today, projects touched, alerts generated, outstanding work and overdue reminders.
  Use for: "evening review", "end of day", "day review", "what did I accomplish today", "how did today go", "today summary", "wrap up", "EOD"

- daily_focus: args {}
  Priority-ranked list of what to work on today, sourced from tasks, reminders, projects, and alerts.
  Use for: "what should I focus on today", "what should I work on", "daily focus", "focus today", "what's my priority", "what should I do today", "what's most important today"

- weekly_review: args {}
  Summary of the past 7 days and upcoming week, from tasks, projects, calendar, and alerts.
  Use for: "weekly review", "week review", "weekly summary", "how was my week", "what happened this week", "week in review"

- forgotten_items: args {}
  Scan for stale projects, overdue reminders, long-pending tasks, and old unresolved alerts.
  Use for: "what am I forgetting", "what have I forgotten", "forgotten items", "what's overdue", "overdue items", "what's stale"

- project_health: args {}
  Per-project health report with status, tasks, reminders, and alerts for each project.
  Use for: "project health", "show project health", "project status", "health report", "project overview", "how are my projects"

- list_projects: args {"status": string}
  List registered projects. status can be "active", "blocked", "paused", "complete", or "" for all.
  Use for: "list projects", "show projects", "my projects", "active projects", "what projects are active", "what projects do I have"

- create_project: args {"name": string, "status": string, "priority": string, "brain63_key": string, "notes": string}
  Create a new project. status: active/paused/complete/blocked. priority: critical/high/normal/low.
  Use for: "create project X", "add project X", "new project X", "start project X"

- update_project_status: args {"name": string, "status": string}
  Update a project's status. status: active|paused|complete|blocked
  Use for: "mark project X as complete", "set project X to paused", "project X is blocked", "complete project X"

- list_services: args {"node": string}
  List all registered services on a node (and their capabilities).
  node is optional — omit to list all services across all nodes.
  Examples: "show services on nighthawk", "what services does pi5 have", "list all services"

- register_node_preset: args {"node": string, "preset": string}
  Register a named service preset on a node. Presets: nas, media-player, robot, esp32, web-server, drone.
  Examples: "register nighthawk as NAS", "register pi-zero as media-player", "set up drone-01 as drone",
            "configure nighthawk as a NAS", "nighthawk should run NAS services"

- add_node_service: args {"node": string, "service": string, "type": string, "description": string}
  Add or update a single named service on a node (upsert — safe for existing services).
  type and description are optional; leave empty if not specified.
  Examples: "add samba service to nighthawk", "nighthawk runs file-storage", "assign media-player to pi-zero",
            "add ssh service to carrera", "pi5 has a sensor service"

- remove_node_service: args {"node": string, "service": string}
  Remove a named service from a node.
  Examples: "remove samba service from nighthawk", "remove ssh from carrera", "delete media-player from pi-zero",
            "unregister samba from nighthawk"

- rename_node_service: args {"node": string, "old": string, "new": string}
  Rename a service on a node.
  Examples: "rename service samba to file-sharing on nighthawk", "rename ssh to remote-access on carrera"

- open_location: args {"name": string}
  Open a trusted folder or project in File Explorer. name is a location name or alias.
  Examples: "open CMD-CTR folder", "show Downloads", "open DroneHive", "where is Brain63", "navigate to GitHub", "open Desktop"

- find_files: args {"query": string, "extension": string, "location": string}
  Search for files. extension is optional (stl, pdf, py, kicad_pcb, etc.). location is an optional trusted location name.
  Examples: "find STL files", "find PCB files", "find python files in CMD-CTR", "find latest PDF", "find files related to nighthawk", "show all KiCad projects", "find STL in DroneHive"

- recent_files: args {"location": string}
  Show newest files from trusted locations. location is optional.
  Examples: "show recent files", "latest files in CMD-CTR", "recent DroneHive files"

- open_kicad_project: args {"query": string, "latest": bool}
  Open a KiCad .kicad_pro project file by resolving indexed files first, then launching KiCad with the project path.
  Examples: "open Hive-FC project", "open MP3-Player project", "open keyboard_v1.3 project", "open latest KiCad project", "open KiCad project Hive-FC"

- open_app: args {"name": string}
  Launch a discovered or registered application by name or alias.
  Examples: "open VS Code", "launch KiCad", "start Fusion 360", "open Chrome", "open obs", "open unity hub"

- scan_apps: args {}
  Rescan Windows Start Menu shortcuts, desktop shortcuts, uninstall registry entries, and common install paths.
  Examples: "scan installed apps", "rescan apps", "discover programs"

- show_app: args {"name": string}
  Show registry metadata and launch candidates for a discovered app.
  Examples: "show app obs", "show app unity", "lookup app blender"

- list_locations: args {}
  List all trusted locations (projects, important folders).
  Examples: "show my folders", "list locations", "show trusted locations", "what folders do you know", "list projects"

- list_apps: args {}
  List all registered applications.
  Examples: "show installed apps", "list my apps", "what apps can you open", "show applications", "what can you launch"

- add_location: args {"name": string, "path": string, "aliases": string, "tags": string}
  Register a new trusted folder. path must be absolute.
  Examples: "add Cyberdeck folder at C:\\Users\\IshaanV\\Documents\\GitHub\\Cyberdeck"

- add_app: args {"name": string, "executable": string, "aliases": string, "category": string}
  Register a new application in the app registry.
  Examples: "add Blender app at C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe"

- close_app: args {"name": string}
  Gracefully close a running application. Sends WM_CLOSE, waits, verifies it actually exited.
  Works for ANY registered app — no per-app logic.
  Examples: "close Bambu Studio", "close Fusion 360", "quit OBS", "exit KiCad"

- app_status: args {"name": string}
  Check whether a registered application is currently running. Returns process count and PIDs.
  Examples: "is Fusion running?", "app status OBS", "is KiCad open?", "check if Chrome is running"

- list_running_apps: args {}
  List all registered apps that are currently running. Registry-driven — no hardcoded names.
  Examples: "show running apps", "what apps are running", "show launched apps", "list active applications"

- show_app_runtime: args {"name": string}
  Show detailed runtime state for a specific app: PID, window title, launch time, command.
  Examples: "show app runtime Spotify", "show runtime for OBS", "show app runtime fusion"

- open_url: args {"url": string}
  Open an explicit URL or bare domain in the default browser.
  Examples: "open github.com", "open https://youtube.com", "visit stackoverflow.com"

- open_target: args {"target": string, "modifier": string}
  Preference-aware resolver for "open X", "open X web", "open X app", "open X folder".
  modifier: "" | "web" | "app" | "folder". Checks preferences → web aliases → app registry → locations.
  Examples: "open github" (preference web), "open spotify web", "open spotify app", "open CMD-CTR"

- set_launch_preference: args {"target": string, "preferred": string}
  Set the launch preference for a named target. preferred: "web" | "app" | "folder" | "auto".
  Examples: "prefer github web", "prefer spotify desktop", "default obs to app"

- show_launch_target: args {"target": string}
  Show all configured targets (web URL, app name, folder path) and current preference.
  Examples: "show target github", "show target spotify", "show target obs"

- list_launch_preferences: args {}
  List all configured launch preferences.
  Examples: "show launch preferences", "list preferences"

- execute_capability: args {"capability": string, "node": string, "args": dict}
  Execute a named capability on a node's service. capability is a dotted name like "media.play".
  node is optional — if omitted, SILVIA will find the right service automatically.
  args is optional extra parameters (e.g. {volume: 50} for media.volume).
  Confirmation is required for risk_level high or critical capabilities.

  Capability namespaces:
  - media: media.play, media.pause, media.stop, media.next, media.previous, media.volume
  - motion: motion.forward, motion.backward, motion.stop, motion.turn_left, motion.turn_right, motion.hover
  - camera: camera.capture, camera.stream, camera.stream_stop
  - system: system.start, system.stop, system.restart, system.status, system.reload
  - sensor: sensor.read, sensor.calibrate
  - battery: battery.status
  - gpio: gpio.set, gpio.get
  - navigation: navigation.goto, navigation.home, navigation.waypoint
  - audio: audio.play, audio.stop, audio.volume

  Examples:
  "play music on nighthawk" → execute_capability with capability="media.play", node="nighthawk"
  "pause music" → execute_capability with capability="media.pause", node=""
  "skip track on nighthawk" → execute_capability with capability="media.next", node="nighthawk"
  "stop the music" → execute_capability with capability="media.stop", node=""
  "set volume to 50 on nighthawk" → execute_capability with capability="media.volume", node="nighthawk", args={"volume": 50}
  "move drone-01 forward" → execute_capability with capability="motion.forward", node="drone-01"
  "stop rover" → execute_capability with capability="motion.stop", node="rover"
  "take a photo on pi5" → execute_capability with capability="camera.capture", node="pi5"
  "start camera stream on pi5" → execute_capability with capability="camera.stream", node="pi5"
  "restart nginx on carrera" → execute_capability with capability="system.restart", node="carrera", args={"service": "nginx"}
  "start mysql on nighthawk" → execute_capability with capability="system.start", node="nighthawk", args={"service": "mysql"}
  "read sensor on esp32-01" → execute_capability with capability="sensor.read", node="esp32-01"
  "battery status on drone-01" → execute_capability with capability="battery.status", node="drone-01"

- add_component: args {"name": string, "category": string, "quantity": int, "manufacturer": string, "part_number": string, "location": string, "notes": string}
  Add a part/component to the hardware inventory. category is free-text (e.g. microcontroller, sensor, display, motor, radio, battery, pcb, sbc, misc).
  Examples: "add ESP32-S3 quantity 5", "add MPU6050 sensor 3", "add component VL53L0X category sensor qty 2"

- list_components: args {"category": string, "search": string}
  List hardware inventory. category and search are optional filters.
  Examples: "show components", "show all sensors", "show microcontrollers", "list inventory", "show all displays", "show batteries"

- get_component: args {"name": string}
  Get details and project assignments for a specific component.
  Examples: "show ESP32-S3", "get component MPU6050", "details for VL53L0X"

- update_component: args {"name": string, "quantity": int, "status": string, "location": string, "notes": string}
  Update component fields. status: in-stock | low-stock | out-of-stock | on-order.
  Examples: "update ESP32-S3 quantity 10", "set MPU6050 status low-stock", "update location of ESP32 to drawer 3"

- delete_component: args {"name": string}
  Remove a component from inventory.
  Examples: "delete component ESP32-S3", "remove VL53L0X from inventory"

- search_hardware: args {"query": string}
  Search inventory by name, category, manufacturer, or notes.
  Examples: "search hardware gps", "find IMU sensors", "search component nrf", "how many esp32 do I own"

- hw_inventory_summary: args {}
  Show a summary of all hardware: counts by category, projects, and pending orders.
  Examples: "hardware summary", "show hardware inventory", "hardware overview", "what hardware do I have"

- create_hw_project: args {"name": string, "description": string, "status": string, "priority": string}
  Create a hardware project. status: active|paused|complete|abandoned. priority: low|normal|high|critical.
  Examples: "create hardware project DroneHive", "new hw project Cyberdeck priority high", "add hardware project MP3 Player"

- list_hw_projects: args {"status": string}
  List hardware projects. status filter is optional.
  Examples: "show hardware projects", "list active hardware projects", "show all hw projects"

- get_hw_project: args {"name": string}
  Show project details, assigned parts, and missing components.
  Examples: "show hardware project DroneHive", "DroneHive project status", "parts for DroneHive"

- update_hw_project_status: args {"name": string, "status": string}
  Update the status of a hardware project.
  status: planned|researching|designing|ordering|waiting_for_parts|building|testing|blocked|completed|archived|active|paused
  Examples: "mark DroneHive building", "set Cyberdeck to designing", "mark DroneHive completed", "mark project MP3 Player blocked"

- delete_hw_project: args {"name": string}
  Delete a hardware project.
  Examples: "delete hardware project test", "remove hw project Prototype"

- assign_part_to_project: args {"part": string, "project": string, "quantity_required": int}
  Assign a component to a hardware project (creates a project-part link).
  Examples: "assign MPU6050 to DroneHive", "assign ESP32-C3 to Cyberdeck quantity 2"

- unassign_part_from_project: args {"part": string, "project": string}
  Remove a component from a project.
  Examples: "unassign MPU6050 from DroneHive", "remove ESP32 from Cyberdeck"

- list_project_parts: args {"project": string}
  Show all components assigned to a project, with stock status.
  Examples: "show components for DroneHive", "list parts for Cyberdeck", "what parts does MP3 Player use"

- list_part_projects: args {"part": string}
  Show all projects that use a specific component.
  Examples: "show projects using ESP32-S3", "which projects use MPU6050", "where is VL53L0X used"

- add_order: args {"part_name": string, "vendor": string, "quantity": int, "notes": string}
  Log a new parts order.
  Examples: "order ESP32-S3 quantity 5", "order MPU6050 from AliExpress qty 10", "log order for Pi Pico 3"

- list_orders: args {"status": string}
  List orders. status: ordered|manufacturing|shipped|delivered|cancelled (optional).
  Examples: "show orders", "show pending orders", "show shipped orders", "show delivered parts"

- update_order_status: args {"query": string, "status": string}
  Update order status. query can be order ID or part name.
  Examples: "mark order ESP32 delivered", "mark order abc123 shipped", "update order MPU6050 to delivered"

- delete_order: args {"query": string}
  Delete an order by ID or part name.
  Examples: "delete order abc123", "remove order ESP32"

- build_readiness_check: args {"project": string}
  Check build readiness for a specific hardware project. Reports what fraction of required parts are in stock.
  Examples: "can I build DroneHive", "build readiness for Cyberdeck", "is DroneHive ready to build", "check DroneHive readiness"

- show_missing_parts: args {"project": string}
  Show missing required parts. If project is empty, shows all missing parts across active projects.
  Examples: "show missing parts", "what am I missing for DroneHive", "missing parts for Cyberdeck", "show missing components"

- show_blocked_projects: args {}
  Show projects that are blocked — either marked blocked or have zero-stock required parts.
  Examples: "show blocked projects", "which projects are blocked", "what's blocking my projects"

- component_usage_stats: args {"part": string}
  Show how many projects each component is used in, sorted by usage frequency.
  part is optional — omit to see all, or filter to one part.
  Examples: "show component usage", "how many projects use ESP32", "which components are used most", "show shared components"

- recommend_orders: args {}
  Recommend parts to order based on shortfalls across all active projects. Shows urgency + affected projects.
  Examples: "what should I order", "show order recommendations", "what do I need to buy", "show critical shortages"

- what_should_i_work_on: args {}
  Rank active projects by composite priority score using the workspace digital twin.
  Examples: "what should I work on", "what should I work on tonight", "which project is closest to completion", "show project priorities", "what can I build now", "show recommended work"

- workspace_status: args {}
  Show the live workspace digital twin — projects, infrastructure, orders, tasks, alerts.
  Examples: "workspace status", "show workspace", "show workspace status", "how is the workspace"

- workspace_priorities: args {}
  Show all projects ranked by composite priority score.
  Examples: "show workspace priorities", "rank projects", "project rankings", "show priority ranking"

- daily_briefing: args {}
  Full engineering daily briefing — workspace state, priorities, blockers, orders, calendar, recent changes.
  Use for: "daily briefing", "daily engineering briefing", "engineering briefing", "full briefing"

- show_blocked_projects: args {}
  Show all projects that are currently blocked by missing parts, dependencies, or status.
  Examples: "show blocked projects", "what is blocked", "which projects are blocked"

- show_ready_projects: args {}
  Show projects that have all required parts and are ready to build.
  Examples: "show ready projects", "what can I continue right now", "what projects can I continue", "what is available"

- what_to_order: args {}
  Recommend parts to order — missing parts across all projects with no active order.
  Examples: "what should I order next", "what do I need to order", "show order needs"

- reconcile_project_orders: args {"project": string}
  Reconciled order recommendations for a specific project — merges Brain63, inventory, orders, and user overrides.
  Excludes already-owned and already-ordered items. Detects stale Brain63 references.
  Examples: "what should I order next for cyberdeck", "what parts am I still missing for dronehive",
            "what do I need for cyberdeck", "what have I already bought for cyberdeck",
            "order status for cyberdeck"

- mark_item_acquired: args {"project": string, "items": string, "state": string}
  Mark one or more items as owned/ordered/received for a project. Updates inventory, project memory, and knowledge graph.
  state: owned, ordered, received
  Examples: "I already bought the screen and SD card for cyberdeck", "mark screen as acquired for cyberdeck",
            "I received the USB hub for cyberdeck", "I ordered PiSugar for cyberdeck",
            "mark screen as acquired for dronehive"

- rich_output: args {"project": string, "render_type": string}
  Generate rich structured output: procurement table, build workflow, project report, roadmap checklist, or readiness table.
  render_type: procurement_table, build_workflow, project_report, checklist, table
  Use for: "detailed shopping list for X", "shopping list for X", "procurement list for X",
           "build workflow for X", "build plan for X", "show build steps for X",
           "project report for X", "full report on X", "detailed summary of X",
           "roadmap for X", "show roadmap for X", "detailed roadmap for X",
           "readiness table", "readiness comparison", "compare project readiness"

- closest_to_completion: args {}
  Which project is nearest to being finished.
  Examples: "what project is closest to completion", "which project is almost done", "nearest to done"

- show_recent_actions: args {"limit": int, "node": string, "status": string}
  Show recent execution log entries. node and status are optional filters.
  Use for: "show recent actions", "show last 10 actions", "what did you do", "show activity",
            "show actions on pi5", "show failed actions", "what happened today", "show actions today"

- show_failures: args {"limit": int}
  Show the failure log — exceptions, timeouts, and errors.
  Use for: "show failures", "show errors", "what failed", "show recent errors", "show exceptions"

- show_planner_trace: args {"limit": int}
  Show the planner decision log — how queries were routed to tools.
  Use for: "show planner decisions", "show planner trace", "how did you decide", "show routing decisions"

- show_capability_health: args {}
  Show per-capability success rates, most used, and most failed.
  Use for: "show capability health", "capability success rates", "what capabilities are working",
            "show system health", "show execution health"

- explain_last_action: args {}
  Explain the most recent action SILVIA took — why it was triggered and what happened.
  Use for: "why did you do that", "why did you do this", "explain that", "what was that",
            "why did you restart docker", "why did you open vscode", "what just happened"

- project_briefing: args {"project": string}
  Generate a full Project Intelligence Report: readiness, blockers, tasks, Brain63 context, related nodes, recommended action.
  Use for: "project briefing cyberdeck", "what's the update on dronehive", "status of koi", "how is cyberdeck going",
            "brief me on dronehive", "give me a briefing on silvia"

- project_blockers: args {"project": string}
  Show what is blocking a project: missing parts, status issues, knowledge graph edges.
  Use for: "project blockers cyberdeck", "what's blocking dronehive", "what is blocking koi"

- project_readiness: args {"project": string}
  Show build readiness for a project — parts availability and what's missing.
  Use for: "project readiness cyberdeck", "can i build dronehive", "can i build cyberdeck", "how ready is koi"

- project_dependencies: args {"project": string}
  Show dependency tree for a project from hardware parts and knowledge graph edges.
  Use for: "project dependencies cyberdeck", "show cyberdeck dependencies", "show dronehive dependencies"

- projects_using: args {"component": string}
  Find all projects that use a given component or part.
  Use for: "what projects use esp32-c3", "which projects use raspberry pi", "what projects need gps",
            "what projects depend on esp32", "which projects use nrf52840"

- blocked_projects: args {}
  List all projects that are blocked by missing parts or status.
  Use for: "which projects are blocked", "show blocked projects", "what projects are blocked", "what's blocked"

- startable_projects: args {}
  List projects that have >= 80% parts available and can be started now.
  Use for: "which projects can i start", "which projects can start now", "what projects are ready", "what can i build now"

- open_board: args {"board": string, "route": string}
  Open an internal SILVIA board or page. board is the board identifier; route is the URL path.
  NEVER use open_app or open_location for internal SILVIA boards.
  Use for: "open intel board", "open hardware board", "open knowledge graph", "open voice diagnostics",
            "go to hardware", "navigate to fleet", "open observability", "launch mission control",
            "show intel board", "show hardware board", "show fleet dashboard", "show voice diagnostics",
            "open command center", "go home"

- show_knowledge_graph: args {"project": string}
  Show the engineering knowledge graph — entities, relationships, and connectivity summary.
  project is optional; if provided, shows the subgraph for that project.
  Use for: "show knowledge graph", "show graph", "show project graph",
            "show engineering graph", "what's in the knowledge graph", "show kg",
            "show cyberdeck graph", "show dronehive in the graph"

- record_project_memory: args {"project": string, "type": string, "title": string, "summary": string, "reasoning": string}
  Record an engineering memory entry — decision, lesson, milestone, failure, success, etc.
  type must be one of: decision, lesson, milestone, failure, success, experiment, design_note, engineering_note, risk, assumption, retrospective
  project is inferred from the text if not given explicitly.
  Use for: "record decision: ...", "add decision: ...", "log decision: ...",
            "record lesson: ...", "add lesson: ...", "note lesson: ...",
            "record milestone: ...", "log milestone: ...",
            "record failure: ...", "log failure: ...",
            "record success: ...", "record risk: ...", "record assumption: ..."

- get_project_memory: args {"project": string, "type": string, "query": string}
  Retrieve engineering memory entries for a project, optionally filtered by type or search query.
  type is optional filter (decision/lesson/milestone/failure/etc). query is optional search term.
  Use for: "show decisions for cyberdeck", "show lessons for dronehive",
            "show project memory cyberdeck", "show failures for dronehive",
            "show milestones for cyberdeck", "show engineering notes",
            "what decisions have we made for hive-fc", "show risks for koi",
            "what lessons have we learned", "show all decisions"

- get_project_timeline: args {"project": string}
  Show chronological project history — all memory entries sorted oldest to newest.
  Use for: "show project history cyberdeck", "show timeline cyberdeck",
            "show cyberdeck timeline", "show dronehive history",
            "what happened with cyberdeck", "show history for dronehive"

- search_project_memory: args {"query": string, "project": string}
  Search across all engineering memories by keyword.
  project is optional to scope the search.
  Use for: "why did we choose arch linux", "why did we switch to esp32",
            "why did we use pisugar", "what failed on dronehive",
            "what did we decide about the power system",
            "find decisions about linux", "search memory for esp32"

- plan_project: args {"description": string}
  Design a full project plan: architecture, BOM, gap analysis, roadmap. Uses inventory + templates.
  Use for: "plan a gps tracker", "plan rover", "design a lora node", "design a remote environmental monitor",
            "plan a drone swarm node", "I want to build a rover", "I want to build a GPS tracker"

- generate_bom: args {"project": string}
  Generate a Bill of Materials for a project, checking against inventory.
  Use for: "generate bom for rover", "create bom for cyberdeck", "show bom for gps tracker",
            "bill of materials for drone", "bom for sensor node"

- generate_roadmap_plan: args {"project": string}
  Generate a phased roadmap/build plan for a project.
  Use for: "generate roadmap for rover", "create roadmap for gps tracker", "build plan for drone"

- planner_gap_analysis: args {"project": string}
  Show what's missing vs owned for a project.
  Use for: "what am I missing for gps tracker", "gap analysis for rover", "what do I still need for drone"

- planner_can_i_build: args {"project": string}
  Check if you have enough parts to build a project.
  Use for: "can I build a gps tracker", "can I build a rover", "do I have what I need for drone"

- planner_what_can_i_build: args {}
  Suggest projects based on current inventory — template matches + custom ideas.
  Use for: "what can I build with my inventory", "what can I build today",
            "what projects can I make with what I have", "suggest projects from my parts"

- planner_architecture: args {"project": string}
  Show architecture for a project — components, connections, purpose.
  Use for: "show project architecture for drone", "architecture for rover",
            "show architecture for gps tracker"

- planner_procurement: args {"project": string}
  Generate prioritized procurement plan — buy now / buy soon / optional.
  Use for: "generate procurement plan for rover", "what do I need to buy for drone",
            "create purchasing list for gps tracker"

- planner_create_project: args {"name": string, "template_id": string}
  Create a new project, optionally from a template. Registers in project service, hardware, KG, memory.
  template_id is optional — if omitted, tries to match name to a template.
  Use for: "create project rover", "create lora sensor node project", "create gps tracker project"

- list_project_templates: args {}
  Show all available project templates with difficulty and item counts.
  Use for: "list project templates", "show templates", "what templates are available"

- show_workspace_context: args {}
  Show what the user is currently working on — active app, project, file, session type.
  Use for: "what am I working on", "show workspace context", "show current context",
            "what's on my screen", "what am I doing", "what project am I in"

- show_active_project: args {}
  Show the currently active project detected from the screen.
  Use for: "show active project", "what project am I working on", "current project"

- show_active_file: args {}
  Show the currently active file detected from the screen.
  Use for: "show active file", "what file am I editing", "current file"

- show_active_application: args {}
  Show the currently active application.
  Use for: "show active application", "what app am I using", "what application is open"

- show_recent_sessions: args {}
  Show recent engineering sessions — project, duration, tools used.
  Use for: "show recent sessions", "show my sessions", "what sessions have I had",
            "show session history", "show project sessions"

- show_last_session: args {"project": string}
  Show the last session, optionally for a specific project. project is optional.
  Use for: "show last session", "what was I doing", "what was I working on",
            "what was I doing last night", "what was I doing yesterday"

- continue_project: args {"project": string}
  Resume work on a project — show status, last session, open tasks, recommended next step, and offer workspace restore.
  Use for: "continue cyberdeck", "resume cmd-ctr", "continue dronehive work",
            "resume dronehive", "continue project cyberdeck"

- restore_workspace: args {"project": string}
  Open a project workspace — launch VS Code, SILVIA boards, and project resources.
  Use for: "open cyberdeck workspace", "restore cmd-ctr workspace", "restore workspace",
            "open dronehive workspace", "restore yesterday's session"

- show_accomplishments: args {"hours": int}
  Show what was accomplished recently — projects, sessions, milestones.
  hours defaults to 24.
  Use for: "show what I accomplished today", "what did I do today",
            "what did I work on this week", "show today's activity"

- import_brain63_memory: args {"project": string}
  Import engineering memories from Brain63 vault (decisions, lessons, milestones files).
  project is optional — omit to import all projects.
  Use for: "import memories from brain63", "sync decisions from brain63",
            "import cyberdeck decisions", "load memories from vault"

- fleet_status: args {}
  Get fleet health score, online/offline/warning/critical counts, and average metrics.
  Use for: "show fleet status", "fleet health", "infrastructure health", "fleet overview", "how are my nodes doing"

- show_fleet_offline: args {}
  List all nodes currently offline.
  Use for: "show offline nodes", "which nodes are down", "what's offline", "show all offline nodes"

- show_fleet_unhealthy: args {}
  List nodes in warning or critical health state.
  Use for: "show unhealthy nodes", "show problem nodes", "nodes with issues", "show degraded nodes", "nodes with warnings"

- show_fleet_groups: args {}
  Group all nodes by type, tag, and running service.
  Use for: "show node groups", "group nodes by type", "list node groups", "how are nodes organized"

- fleet_action: args {"capability": string, "filter_type": string, "filter_value": string, "service_name": string}
  Execute a capability across multiple nodes matching a fleet filter. Always shows impact preview first.
  filter_type: "all" | "type" | "tag" | "service" | "status"
  filter_value: e.g. "raspberry-pi", "production", "docker", "online"
  service_name is the systemd service for system.* capabilities.
  Use for: "restart docker on all raspberry pis", "stop samba on all nas servers", "restart nginx everywhere"
  Examples:
  "restart docker on all raspberry pis" → fleet_action capability="system.restart" filter_type="type" filter_value="raspberry-pi" service_name="docker"
  "restart samba on all nas servers" → fleet_action capability="system.restart" filter_type="type" filter_value="nas" service_name="samba"
  "stop nginx on all production nodes" → fleet_action capability="system.stop" filter_type="tag" filter_value="production" service_name="nginx"
  "restart docker everywhere" → fleet_action capability="system.restart" filter_type="all" filter_value="" service_name="docker"

- show_brain63_health: args {}
  Show Brain63 documentation health — coverage, missing files, projects.
  Use for: "show brain63 health", "documentation health", "brain63 health"

- show_brain63_coverage: args {"project": string}
  Show documentation coverage. project is optional.
  Use for: "show documentation coverage", "show cyberdeck documentation coverage", "brain63 coverage"

- show_brain63_drafts: args {}
  Show pending Brain63 draft workflows.
  Use for: "show brain63 drafts", "pending documentation updates", "brain63 drafts"

- update_brain63_roadmap: args {"project": string, "change": string}
  Update a project's Brain63 roadmap. Creates a draft workflow requiring approval.
  Use for: "update cyberdeck roadmap", "update roadmap for dronehive", "move power system to phase 1 on cyberdeck roadmap"

- show_memory_providers: args {}
  Show all registered memory providers and their status.
  Use for: "show memory providers", "show providers", "list providers", "memory providers"

- show_memory_health: args {}
  Show health status of all memory providers.
  Use for: "show memory health", "memory health", "show provider status", "provider status"

- show_memory_timeline: args {"project": string}
  Show unified memory timeline across all providers. project is optional.
  Use for: "show memory timeline", "show cyberdeck timeline", "show engineering history", "memory timeline"

- show_memory_relationships: args {"entity": string}
  Show memory relationships and connections. entity is optional.
  Use for: "show related memories", "show relationships", "show memory graph", "show related decisions"

- unified_memory_search: args {"query": string, "project": string}
  Search across all memory providers. project is optional.
  Use for: "why did we choose arch linux", "search memory for esp32", "find memories about power system"

- list_workflows: args {}
  Show all workflows (change requests). Examples: "show workflows", "list workflows", "show change requests"

- show_pending_workflows: args {}
  Show pending workflows awaiting review. Examples: "show pending workflows", "pending changes", "show waiting approvals"

- show_workflow_history: args {}
  Show completed/rejected/cancelled workflow history. Examples: "show workflow history", "completed workflows"

- get_workflow: args {"code": string}
  Show details for a specific workflow. Examples: "show WF-001", "get workflow WF-001"

- approve_workflow: args {"code": string}
  Approve a pending workflow. Examples: "approve WF-001", "approve workflow WF-001"

- reject_workflow: args {"code": string}
  Reject a pending workflow. Examples: "reject WF-001", "reject workflow WF-001"

- cancel_workflow: args {"code": string}
  Cancel a workflow. Examples: "cancel WF-001", "cancel workflow WF-001"

- approve_all_workflows: args {"max_risk": string}
  Approve all pending workflows. max_risk optional: "low", "moderate" to limit.
  Examples: "approve all workflows", "approve all pending changes", "approve all low risk"

- reject_all_workflows: args {}
  Reject all pending workflows. Examples: "reject all workflows", "reject all pending changes"

- system_diagnostics: args {}
  Run a deep system health check across all SILVIA subsystems. Reports OK/Warning/Failed/Disabled for each.
  Examples: "deep system check", "run silvia diagnostics", "system health", "diagnostics", "check all systems", "health check"

- dismiss_reminder: args {"query": string}
  Dismiss (complete) a reminder by ID or partial message. Same as complete_reminder but also resolves Watch Officer alerts.
  Examples: "dismiss reminder check pi5", "dismiss reminder 3a2b", "stop reminder about backup"

- clear_stuck_reminders: args {}
  Find and clear all stuck reminders (one-time reminders that are past due but not completed).
  Examples: "clear stuck reminders", "fix stuck reminders", "reset reminders"

- pause_reminders: args {}
  Temporarily pause all reminder notifications. Reminders are not deleted but will not fire until resumed.
  Examples: "pause reminders", "stop all reminders", "mute reminders"

- resume_reminders: args {}
  Resume paused reminder notifications.
  Examples: "resume reminders", "unpause reminders", "unmute reminders"

- show_reminder_diagnostics: args {}
  Show detailed reminder system diagnostics: active, due, stuck, recurring, total.
  Examples: "show reminder diagnostics", "reminder status", "reminder health"

RULES:
- Time + weather for same place → call_tools with both.
- Weather with no location → {"action":"final"}
- Open/launch/volume/navigate commands → {"action":"final"}  (handled elsewhere)
- Greetings, capability questions, casual chat → {"action":"final"}
- Node queries MUST use node tools — never answer from memory.
- Node telemetry/metrics/CPU/RAM/disk/health queries → ALWAYS use get_node_telemetry immediately.
- Service/capability queries → use list_services or execute_capability.
- Fleet queries → use fleet_status, show_fleet_offline, show_fleet_unhealthy, show_fleet_groups, or fleet_action.
- Hardware/inventory/component/order/project queries → use hardware tools.
- Workflow queries → use workflow tools. "approve WF-001" uses approve_workflow.
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

    {"role": "user",      "content": "merge VPS into carrera"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"merge_nodes","args":{"source":"VPS","target":"carrera"}}'},

    {"role": "user",      "content": "consolidate nighthawk and nas"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"merge_nodes","args":{"source":"nighthawk","target":"nas"}}'},

    {"role": "user",      "content": "deduplicate nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"deduplicate_nodes","args":{}}'},

    {"role": "user",      "content": "find duplicate nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"deduplicate_nodes","args":{}}'},

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

    {"role": "user",      "content": "connect carrera"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"ssh_node","args":{"node":"carrera","username":""}}'},

    {"role": "user",      "content": "set ssh username for carrera to ishaan"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_ssh_profile","args":{"node":"carrera","username":"ishaan","key_path":""}}'},

    {"role": "user",      "content": "configure nighthawk ssh as pi"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_ssh_profile","args":{"node":"nighthawk","username":"pi","key_path":""}}'},

    {"role": "user",      "content": "set carrera ssh key to default"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_ssh_profile","args":{"node":"carrera","username":"","key_path":"default"}}'},

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

    # ── Email / Gmail (Phase 12G) ───────────────────────────────────────────────
    {"role": "user",      "content": "check my email"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"category:primary","limit":10}}'},

    {"role": "user",      "content": "check email"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"category:primary","limit":10}}'},

    {"role": "user",      "content": "show my emails"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"category:primary","limit":10}}'},

    {"role": "user",      "content": "show unread emails"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"category:primary is:unread","limit":10}}'},

    {"role": "user",      "content": "do I have any unread emails"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"category:primary is:unread","limit":10}}'},

    {"role": "user",      "content": "show latest emails"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"category:primary","limit":10}}'},

    {"role": "user",      "content": "check promotions"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"category:promotions","limit":10}}'},

    {"role": "user",      "content": "check social"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"category:social","limit":10}}'},

    {"role": "user",      "content": "check updates"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"category:updates","limit":10}}'},

    {"role": "user",      "content": "check all email"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"","limit":10}}'},

    {"role": "user",      "content": "check for mail from Yoke"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"from:Yoke","limit":10}}'},

    {"role": "user",      "content": "show emails from YTL"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"from:YTL","limit":10}}'},

    {"role": "user",      "content": "show important emails"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_emails","args":{"folder":"inbox","search":"is:important","limit":10}}'},

    {"role": "user",      "content": "find emails about DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_emails","args":{"query":"DroneHive","limit":10}}'},

    {"role": "user",      "content": "search email for internship"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_emails","args":{"query":"internship","limit":10}}'},

    {"role": "user",      "content": "search for internship emails"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_emails","args":{"query":"internship","limit":10}}'},

    {"role": "user",      "content": "productivity status"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_productivity_status","args":{}}'},

    {"role": "user",      "content": "show productivity status"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_productivity_status","args":{}}'},

    {"role": "user",      "content": "is Google connected"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_productivity_status","args":{}}'},

    {"role": "user",      "content": "gmail status"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_productivity_status","args":{}}'},

    {"role": "user",      "content": "draft email to Yoke"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"draft_email","args":{"to":"Yoke","subject":"","body":""}}'},

    {"role": "user",      "content": "write email to Hayley about DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"draft_email","args":{"to":"Hayley","subject":"DroneHive","body":""}}'},

    {"role": "user",      "content": "send email to Hayley"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_email","args":{"to":"Hayley","subject":"","body":""}}'},

    {"role": "user",      "content": "connect to Google"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"connect_google","args":{}}'},

    {"role": "user",      "content": "sign in to Google"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"connect_google","args":{}}'},

    {"role": "user",      "content": "authorize Google"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"connect_google","args":{}}'},

    # ── Google Calendar (Phase 12G) ───────────────────────────────────────────
    {"role": "user",      "content": "show my Google calendar today"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_gcal_events","args":{"date":"today","days":1}}'},

    {"role": "user",      "content": "what do I have tomorrow"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_gcal_events","args":{"date":"today","days":2}}'},

    {"role": "user",      "content": "show this week's events"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_gcal_events","args":{"date":"today","days":7}}'},

    {"role": "user",      "content": "when am I free tomorrow"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_gcal_events","args":{"date":"today","days":2}}'},

    {"role": "user",      "content": "delete event Robotics Meeting"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"delete_calendar_event","args":{"query":"Robotics Meeting"}}'},

    # ── Robotics ──────────────────────────────────────────────────────────────
    {"role": "user",      "content": "list drones"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_nodes_by_type","args":{"type":"drone"}}'},

    {"role": "user",      "content": "show all robots"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_nodes_by_type","args":{"type":"robot"}}'},

    {"role": "user",      "content": "what drones do I have"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_nodes_by_type","args":{"type":"drone"}}'},

    {"role": "user",      "content": "list esp32 nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_nodes_by_type","args":{"type":"esp32"}}'},

    {"role": "user",      "content": "arm drone-01"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_node_command","args":{"node":"drone-01","command":"arm","payload":{}}}'},

    {"role": "user",      "content": "disarm drone-01"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_node_command","args":{"node":"drone-01","command":"disarm","payload":{}}}'},

    {"role": "user",      "content": "land drone-01"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_node_command","args":{"node":"drone-01","command":"land","payload":{}}}'},

    {"role": "user",      "content": "send drone-01 home"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_node_command","args":{"node":"drone-01","command":"home","payload":{}}}'},

    {"role": "user",      "content": "emergency stop drone-01"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_node_command","args":{"node":"drone-01","command":"emergency_stop","payload":{}}}'},

    {"role": "user",      "content": "reboot pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_node_command","args":{"node":"pi5","command":"reboot","payload":{}}}'},

    # ── Bulk commands ──────────────────────────────────────────────────────────
    {"role": "user",      "content": "land all drones"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_bulk_command","args":{"type":"drone","command":"land"}}'},

    {"role": "user",      "content": "disarm all robots"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_bulk_command","args":{"type":"robot","command":"disarm"}}'},

    {"role": "user",      "content": "emergency stop all drones"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_bulk_command","args":{"type":"drone","command":"emergency_stop"}}'},

    {"role": "user",      "content": "reboot all vps"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_bulk_command","args":{"type":"vps","command":"reboot"}}'},

    {"role": "user",      "content": "send all drones home"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"send_bulk_command","args":{"type":"drone","command":"home"}}'},

    # ── Scheduled tasks ────────────────────────────────────────────────────────
    {"role": "user",      "content": "schedule task: check node health every 60 minutes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"schedule_task","args":{"name":"check node health","prompt":"check node health","interval_minutes":60}}'},

    {"role": "user",      "content": "show scheduled tasks"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_scheduled_tasks","args":{}}'},

    {"role": "user",      "content": "disable scheduled task node health"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"disable_scheduled_task","args":{"name":"node health"}}'},

    {"role": "user",      "content": "delete scheduled task node health"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"delete_scheduled_task","args":{"name":"node health"}}'},

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

    # ── Market/entity queries — require live data, never answer from model memory ────
    {"role": "user",      "content": "which stock is performing best today"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_web","args":{"query":"best performing stocks today"}}'},

    {"role": "user",      "content": "what are the top gainers today"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_web","args":{"query":"top stock gainers today"}}'},

    {"role": "user",      "content": "what does NovaTech focus on"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_web","args":{"query":"NovaTech company focus"}}'},

    {"role": "user",      "content": "who is the CEO of OpenAI"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_web","args":{"query":"CEO of OpenAI"}}'},

    {"role": "user",      "content": "what are my current projects"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_projects","args":{"status":"active"}}'},

    {"role": "user",      "content": "what projects am I working on"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_projects","args":{"status":"active"}}'},

    # ── Mission Control ────────────────────────────────────────────────────────
    {"role": "user",      "content": "morning briefing"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"morning_briefing","args":{}}'},

    {"role": "user",      "content": "good morning"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"morning_briefing","args":{}}'},

    {"role": "user",      "content": "daily briefing"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"morning_briefing","args":{}}'},

    {"role": "user",      "content": "what should I focus on today"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"daily_focus","args":{}}'},

    {"role": "user",      "content": "what should I work on today"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"daily_focus","args":{}}'},

    {"role": "user",      "content": "what's my priority today"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"daily_focus","args":{}}'},

    {"role": "user",      "content": "weekly review"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"weekly_review","args":{}}'},

    {"role": "user",      "content": "how was my week"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"weekly_review","args":{}}'},

    {"role": "user",      "content": "evening review"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"evening_review","args":{}}'},

    {"role": "user",      "content": "end of day"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"evening_review","args":{}}'},

    {"role": "user",      "content": "what did I accomplish today"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"evening_review","args":{}}'},

    {"role": "user",      "content": "how did today go"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"evening_review","args":{}}'},

    {"role": "user",      "content": "what am I forgetting"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"forgotten_items","args":{}}'},

    {"role": "user",      "content": "what's overdue"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"forgotten_items","args":{}}'},

    {"role": "user",      "content": "stale projects"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"forgotten_items","args":{}}'},

    {"role": "user",      "content": "what's falling behind"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"forgotten_items","args":{}}'},

    {"role": "user",      "content": "project health"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"project_health","args":{}}'},

    {"role": "user",      "content": "show project health"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"project_health","args":{}}'},

    {"role": "user",      "content": "show projects"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_projects","args":{"status":""}}'},

    {"role": "user",      "content": "active projects"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_projects","args":{"status":"active"}}'},

    {"role": "user",      "content": "create project Cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"create_project","args":{"name":"Cyberdeck","status":"active","priority":"normal","brain63_key":"","notes":""}}'},

    {"role": "user",      "content": "mark project KOI as complete"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_project_status","args":{"name":"KOI","status":"complete"}}'},

    # ── Service registry (Phase 10) ───────────────────────────────────────────
    {"role": "user",      "content": "show services on nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_services","args":{"node":"nighthawk"}}'},

    # ── Service assignment (Phase 10B) ────────────────────────────────────────
    {"role": "user",      "content": "register nighthawk service as NAS"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"register_node_preset","args":{"node":"nighthawk","preset":"NAS"}}'},

    {"role": "user",      "content": "register nighthawk as NAS"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"register_node_preset","args":{"node":"nighthawk","preset":"NAS"}}'},

    {"role": "user",      "content": "configure pi-zero as media-player"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"register_node_preset","args":{"node":"pi-zero","preset":"media-player"}}'},

    {"role": "user",      "content": "assign media-player preset to pi-zero"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"register_node_preset","args":{"node":"pi-zero","preset":"media-player"}}'},

    {"role": "user",      "content": "set up drone-01 as a drone"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"register_node_preset","args":{"node":"drone-01","preset":"drone"}}'},

    {"role": "user",      "content": "nighthawk should run NAS services"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"register_node_preset","args":{"node":"nighthawk","preset":"NAS"}}'},

    {"role": "user",      "content": "add samba service to nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_node_service","args":{"node":"nighthawk","service":"samba","type":"","description":""}}'},

    {"role": "user",      "content": "add ssh service to nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_node_service","args":{"node":"nighthawk","service":"ssh","type":"","description":""}}'},

    {"role": "user",      "content": "nighthawk runs file-storage"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_node_service","args":{"node":"nighthawk","service":"file-storage","type":"","description":""}}'},

    {"role": "user",      "content": "assign media-player service to pi-zero"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_node_service","args":{"node":"pi-zero","service":"media-player","type":"","description":""}}'},

    {"role": "user",      "content": "remove samba service from nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"remove_node_service","args":{"node":"nighthawk","service":"samba"}}'},

    {"role": "user",      "content": "remove ssh from carrera"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"remove_node_service","args":{"node":"carrera","service":"ssh"}}'},

    {"role": "user",      "content": "unregister samba from nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"remove_node_service","args":{"node":"nighthawk","service":"samba"}}'},

    {"role": "user",      "content": "rename service samba to file-sharing on nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"rename_node_service","args":{"node":"nighthawk","old":"samba","new":"file-sharing"}}'},

    {"role": "user",      "content": "rename ssh to remote-access on carrera"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"rename_node_service","args":{"node":"carrera","old":"ssh","new":"remote-access"}}'},

    {"role": "user",      "content": "what services does pi5 have"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_services","args":{"node":"pi5"}}'},

    {"role": "user",      "content": "list all services"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_services","args":{"node":""}}'},

    {"role": "user",      "content": "play music on nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"media.play","node":"nighthawk","args":{}}}'},

    {"role": "user",      "content": "pause music"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"media.pause","node":"","args":{}}}'},

    {"role": "user",      "content": "skip track on nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"media.next","node":"nighthawk","args":{}}}'},

    {"role": "user",      "content": "stop the music"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"media.stop","node":"","args":{}}}'},

    {"role": "user",      "content": "set volume to 50 on nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"media.volume","node":"nighthawk","args":{"volume":50}}}'},

    {"role": "user",      "content": "move drone-01 forward"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"motion.forward","node":"drone-01","args":{}}}'},

    {"role": "user",      "content": "stop rover"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"motion.stop","node":"rover","args":{}}}'},

    {"role": "user",      "content": "take a photo on pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"camera.capture","node":"pi5","args":{}}}'},

    {"role": "user",      "content": "start camera stream on pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"camera.stream","node":"pi5","args":{}}}'},

    {"role": "user",      "content": "restart nginx on carrera"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"system.restart","node":"carrera","args":{"service":"nginx"}}}'},

    {"role": "user",      "content": "start mysql on nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"system.start","node":"nighthawk","args":{"service":"mysql"}}}'},

    {"role": "user",      "content": "stop apache on carrera"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"system.stop","node":"carrera","args":{"service":"apache"}}}'},

    {"role": "user",      "content": "battery status on drone-01"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"battery.status","node":"drone-01","args":{}}}'},

    {"role": "user",      "content": "read sensor on esp32-01"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"sensor.read","node":"esp32-01","args":{}}}'},

    # ── Capability discovery (Phase 13A) ──────────────────────────────────────
    {"role": "user",      "content": "show capabilities on pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_services","args":{"node":"pi5"}}'},

    {"role": "user",      "content": "what can nighthawk do"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_services","args":{"node":"nighthawk"}}'},

    {"role": "user",      "content": "what capabilities does pi5 have"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_services","args":{"node":"pi5"}}'},

    {"role": "user",      "content": "capabilities on nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_services","args":{"node":"nighthawk"}}'},

    # ── Systemd service execution via capability (Phase 13A) ─────────────────
    {"role": "user",      "content": "restart docker on pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"system.restart","node":"pi5","args":{"service":"docker"}}}'},

    {"role": "user",      "content": "restart samba on nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"system.restart","node":"nighthawk","args":{"service":"samba"}}}'},

    {"role": "user",      "content": "stop samba on nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"system.stop","node":"nighthawk","args":{"service":"samba"}}}'},

    {"role": "user",      "content": "start docker on pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"execute_capability","args":{"capability":"system.start","node":"pi5","args":{"service":"docker"}}}'},

    # ── Desktop control (Phase 11) ────────────────────────────────────────────
    {"role": "user",      "content": "open CMD-CTR folder"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_location","args":{"name":"CMD-CTR"}}'},

    {"role": "user",      "content": "open Downloads"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_location","args":{"name":"Downloads"}}'},

    {"role": "user",      "content": "show DroneHive folder"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_location","args":{"name":"DroneHive"}}'},

    {"role": "user",      "content": "where is Brain63"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_location","args":{"name":"Brain63"}}'},

    {"role": "user",      "content": "open the CMD-CTR repository"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_location","args":{"name":"CMD-CTR"}}'},

    {"role": "user",      "content": "navigate to GitHub"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_location","args":{"name":"GitHub"}}'},

    {"role": "user",      "content": "find STL files"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"find_files","args":{"query":"","extension":"stl","location":""}}'},

    {"role": "user",      "content": "find PCB files"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"find_files","args":{"query":"","extension":"kicad_pcb","location":""}}'},

    {"role": "user",      "content": "find all STL files"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"find_files","args":{"query":"","extension":"stl","location":""}}'},

    {"role": "user",      "content": "find STL in DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"find_files","args":{"query":"","extension":"stl","location":"DroneHive"}}'},

    {"role": "user",      "content": "find python files in CMD-CTR"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"find_files","args":{"query":"","extension":"py","location":"CMD-CTR"}}'},

    {"role": "user",      "content": "find latest PDF"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"find_files","args":{"query":"","extension":"pdf","location":""}}'},

    {"role": "user",      "content": "find files related to nighthawk"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"find_files","args":{"query":"nighthawk","extension":"","location":""}}'},

    {"role": "user",      "content": "search DroneHive files"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"find_files","args":{"query":"","extension":"","location":"DroneHive"}}'},

    {"role": "user",      "content": "show all KiCad projects"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"find_files","args":{"query":"","extension":"kicad_pcb","location":""}}'},

    {"role": "user",      "content": "open VS Code"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_app","args":{"name":"VS Code"}}'},

    {"role": "user",      "content": "launch KiCad"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_app","args":{"name":"KiCad"}}'},

    {"role": "user",      "content": "start Fusion 360"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_app","args":{"name":"Fusion 360"}}'},

    {"role": "user",      "content": "open Fusion"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_app","args":{"name":"Fusion 360"}}'},

    {"role": "user",      "content": "open Chrome"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_app","args":{"name":"Chrome"}}'},

    {"role": "user",      "content": "open browser"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_app","args":{"name":"Chrome"}}'},

    {"role": "user",      "content": "show installed apps"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_apps","args":{}}'},

    {"role": "user",      "content": "what apps can you open"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_apps","args":{}}'},

    {"role": "user",      "content": "show my folders"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_locations","args":{}}'},

    {"role": "user",      "content": "list trusted locations"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_locations","args":{}}'},

    # ── App lifecycle (Phase 11D) ──────────────────────────────────────────────
    {"role": "user",      "content": "close Bambu Studio"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"close_app","args":{"name":"Bambu Studio"}}'},

    {"role": "user",      "content": "close Fusion 360"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"close_app","args":{"name":"Fusion 360"}}'},

    {"role": "user",      "content": "close fusion"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"close_app","args":{"name":"fusion"}}'},

    {"role": "user",      "content": "close OBS"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"close_app","args":{"name":"OBS"}}'},

    {"role": "user",      "content": "quit KiCad"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"close_app","args":{"name":"KiCad"}}'},

    {"role": "user",      "content": "exit Chrome"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"close_app","args":{"name":"Chrome"}}'},

    {"role": "user",      "content": "close Steam"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"close_app","args":{"name":"Steam"}}'},

    {"role": "user",      "content": "is Fusion running"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"app_status","args":{"name":"Fusion 360"}}'},

    {"role": "user",      "content": "is KiCad open"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"app_status","args":{"name":"KiCad"}}'},

    {"role": "user",      "content": "app status OBS"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"app_status","args":{"name":"OBS"}}'},

    {"role": "user",      "content": "check if Chrome is running"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"app_status","args":{"name":"Chrome"}}'},

    {"role": "user",      "content": "show running apps"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_running_apps","args":{}}'},

    {"role": "user",      "content": "what apps are running"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_running_apps","args":{}}'},

    {"role": "user",      "content": "show launched apps"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_running_apps","args":{}}'},

    {"role": "user",      "content": "list active applications"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_running_apps","args":{}}'},

    {"role": "user",      "content": "show app runtime Spotify"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_app_runtime","args":{"name":"Spotify"}}'},

    {"role": "user",      "content": "show runtime for OBS"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_app_runtime","args":{"name":"OBS"}}'},

    {"role": "user",      "content": "show app runtime fusion"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_app_runtime","args":{"name":"fusion"}}'},

    # ── Phase 11F: URL / modifier / preference ────────────────────────────────
    {"role": "user",      "content": "open github.com"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_url","args":{"url":"github.com"}}'},

    {"role": "user",      "content": "open https://youtube.com"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_url","args":{"url":"https://youtube.com"}}'},

    {"role": "user",      "content": "open github"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_target","args":{"target":"github","modifier":""}}'},

    {"role": "user",      "content": "open github web"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_target","args":{"target":"github","modifier":"web"}}'},

    {"role": "user",      "content": "open github desktop"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_target","args":{"target":"github","modifier":"app"}}'},

    {"role": "user",      "content": "open github folder"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_target","args":{"target":"github","modifier":"folder"}}'},

    {"role": "user",      "content": "open spotify"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_target","args":{"target":"spotify","modifier":""}}'},

    {"role": "user",      "content": "open spotify web"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_target","args":{"target":"spotify","modifier":"web"}}'},

    {"role": "user",      "content": "open spotify app"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_target","args":{"target":"spotify","modifier":"app"}}'},

    {"role": "user",      "content": "prefer github web"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"set_launch_preference","args":{"target":"github","preferred":"web"}}'},

    {"role": "user",      "content": "prefer spotify desktop"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"set_launch_preference","args":{"target":"spotify","preferred":"desktop"}}'},

    {"role": "user",      "content": "show target github"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_launch_target","args":{"target":"github"}}'},

    {"role": "user",      "content": "show launch preferences"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_launch_preferences","args":{}}'},

    # ── Entity registry queries — handled by device/project registry, not web/LLM ──
    {"role": "user",      "content": "what sensors does nighthawk have"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "does nighthawk have a camera"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "does nighthawk have thermal imaging"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "nighthawk specs"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "nighthawk hardware"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "what is nighthawk"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "what is cyberdeck"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "what is droneHive"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "how is droneHive going"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "what is droneHive working on"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "status of brain63"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "what is the status of KOI"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "cyberdeck progress"},
    {"role": "assistant", "content": '{"action":"final"}'},

    {"role": "user",      "content": "how many nodes are online"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_nodes","args":{}}'},

    {"role": "user",      "content": "how many nodes do I have"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_nodes","args":{}}'},

    # ── Hardware inventory ─────────────────────────────────────────────────────
    {"role": "user",      "content": "add ESP32-S3 quantity 5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_component","args":{"name":"ESP32-S3","category":"microcontroller","quantity":5}}'},

    {"role": "user",      "content": "add component MPU6050 category sensor quantity 3"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_component","args":{"name":"MPU6050","category":"sensor","quantity":3}}'},

    {"role": "user",      "content": "show components"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_components","args":{}}'},

    {"role": "user",      "content": "show all sensors"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_components","args":{"category":"sensor"}}'},

    {"role": "user",      "content": "show microcontrollers"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_components","args":{"category":"microcontroller"}}'},

    {"role": "user",      "content": "list inventory"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_components","args":{}}'},

    {"role": "user",      "content": "show all displays"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_components","args":{"category":"display"}}'},

    {"role": "user",      "content": "search component gps"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_hardware","args":{"query":"gps"}}'},

    {"role": "user",      "content": "how many esp32 boards do i own"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_hardware","args":{"query":"esp32"}}'},

    {"role": "user",      "content": "hardware summary"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"hw_inventory_summary","args":{}}'},

    {"role": "user",      "content": "what hardware do I have"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"hw_inventory_summary","args":{}}'},

    # ── Hardware projects ──────────────────────────────────────────────────────
    {"role": "user",      "content": "create hardware project DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"create_hw_project","args":{"name":"DroneHive"}}'},

    {"role": "user",      "content": "show hardware projects"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_hw_projects","args":{}}'},

    {"role": "user",      "content": "show hardware project DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_hw_project","args":{"name":"DroneHive"}}'},

    {"role": "user",      "content": "mark DroneHive complete"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_hw_project_status","args":{"name":"DroneHive","status":"complete"}}'},

    {"role": "user",      "content": "set Cyberdeck to paused"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_hw_project_status","args":{"name":"Cyberdeck","status":"paused"}}'},

    # ── Project-part linking ───────────────────────────────────────────────────
    {"role": "user",      "content": "assign MPU6050 to DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"assign_part_to_project","args":{"part":"MPU6050","project":"DroneHive","quantity_required":1}}'},

    {"role": "user",      "content": "assign ESP32-C3 to DroneHive quantity 2"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"assign_part_to_project","args":{"part":"ESP32-C3","project":"DroneHive","quantity_required":2}}'},

    {"role": "user",      "content": "show components for DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_project_parts","args":{"project":"DroneHive"}}'},

    {"role": "user",      "content": "show projects using ESP32-S3"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_part_projects","args":{"part":"ESP32-S3"}}'},

    # ── Orders ────────────────────────────────────────────────────────────────
    {"role": "user",      "content": "order ESP32-S3 quantity 5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_order","args":{"part_name":"ESP32-S3","quantity":5}}'},

    {"role": "user",      "content": "order MPU6050 from AliExpress qty 10"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"add_order","args":{"part_name":"MPU6050","vendor":"AliExpress","quantity":10}}'},

    {"role": "user",      "content": "show pending orders"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_orders","args":{"status":"ordered"}}'},

    {"role": "user",      "content": "show orders"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_orders","args":{}}'},

    {"role": "user",      "content": "mark order ESP32-S3 delivered"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_order_status","args":{"query":"ESP32-S3","status":"delivered"}}'},

    # Phase 12B — Project Intelligence
    {"role": "user",      "content": "can I build DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"build_readiness_check","args":{"project":"DroneHive"}}'},

    {"role": "user",      "content": "is DroneHive ready to build"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"build_readiness_check","args":{"project":"DroneHive"}}'},

    {"role": "user",      "content": "check build readiness for Cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"build_readiness_check","args":{"project":"Cyberdeck"}}'},

    {"role": "user",      "content": "show missing parts"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_missing_parts","args":{"project":""}}'},

    {"role": "user",      "content": "what am I missing for DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_missing_parts","args":{"project":"DroneHive"}}'},

    {"role": "user",      "content": "missing parts for Cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_missing_parts","args":{"project":"Cyberdeck"}}'},

    {"role": "user",      "content": "show blocked projects"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_blocked_projects","args":{}}'},

    {"role": "user",      "content": "which projects are blocked"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_blocked_projects","args":{}}'},

    {"role": "user",      "content": "show component usage"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"component_usage_stats","args":{"part":""}}'},

    {"role": "user",      "content": "how many projects use ESP32"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"component_usage_stats","args":{"part":"ESP32"}}'},

    {"role": "user",      "content": "show shared components"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"component_usage_stats","args":{"part":""}}'},

    {"role": "user",      "content": "what should I order"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"recommend_orders","args":{}}'},

    {"role": "user",      "content": "show order recommendations"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"recommend_orders","args":{}}'},

    {"role": "user",      "content": "show critical shortages"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"recommend_orders","args":{}}'},

    {"role": "user",      "content": "what should I work on"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"what_should_i_work_on","args":{}}'},

    {"role": "user",      "content": "what should I work on tonight"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"what_should_i_work_on","args":{}}'},

    {"role": "user",      "content": "which project is closest to completion"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"closest_to_completion","args":{}}'},

    {"role": "user",      "content": "show project priorities"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"what_should_i_work_on","args":{}}'},

    {"role": "user",      "content": "workspace status"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"workspace_status","args":{}}'},

    {"role": "user",      "content": "daily briefing"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"daily_briefing","args":{}}'},

    {"role": "user",      "content": "show blocked projects"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_blocked_projects","args":{}}'},

    {"role": "user",      "content": "show ready projects"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_ready_projects","args":{}}'},

    {"role": "user",      "content": "show workspace priorities"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"workspace_priorities","args":{}}'},

    {"role": "user",      "content": "what should I order next"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"what_to_order","args":{}}'},

    {"role": "user",      "content": "what project is closest to completion"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"closest_to_completion","args":{}}'},

    {"role": "user",      "content": "what should I order next for cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"reconcile_project_orders","args":{"project":"cyberdeck"}}'},

    {"role": "user",      "content": "what parts am I still missing for dronehive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"reconcile_project_orders","args":{"project":"dronehive"}}'},

    {"role": "user",      "content": "I already bought the screen and SD card for cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"mark_item_acquired","args":{"project":"cyberdeck","items":"the screen and SD card","state":"owned"}}'},

    {"role": "user",      "content": "I ordered PiSugar for cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"mark_item_acquired","args":{"project":"cyberdeck","items":"PiSugar","state":"ordered"}}'},

    {"role": "user",      "content": "I received the USB hub for cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"mark_item_acquired","args":{"project":"cyberdeck","items":"USB hub","state":"received"}}'},

    {"role": "user",      "content": "mark screen as acquired for cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"mark_item_acquired","args":{"project":"cyberdeck","items":"screen","state":"owned"}}'},

    {"role": "user",      "content": "show me a detailed shopping list for cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"rich_output","args":{"project":"cyberdeck","render_type":"procurement_table"}}'},

    {"role": "user",      "content": "shopping list for dronehive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"rich_output","args":{"project":"dronehive","render_type":"procurement_table"}}'},

    {"role": "user",      "content": "show cyberdeck build workflow"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"rich_output","args":{"project":"cyberdeck","render_type":"build_workflow"}}'},

    {"role": "user",      "content": "project report for cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"rich_output","args":{"project":"cyberdeck","render_type":"project_report"}}'},

    {"role": "user",      "content": "show roadmap for cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"rich_output","args":{"project":"cyberdeck","render_type":"checklist"}}'},

    {"role": "user",      "content": "readiness comparison"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"rich_output","args":{"project":"","render_type":"table"}}'},

    {"role": "user",      "content": "mark DroneHive building"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_hw_project_status","args":{"name":"DroneHive","status":"building"}}'},

    {"role": "user",      "content": "set Cyberdeck to designing"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_hw_project_status","args":{"name":"Cyberdeck","status":"designing"}}'},

    {"role": "user",      "content": "mark MP3 Player waiting for parts"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_hw_project_status","args":{"name":"MP3 Player","status":"waiting_for_parts"}}'},

    # ── Project Intelligence (Phase 14A) ─────────────────────────────────────
    {"role": "user",      "content": "project briefing cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"project_briefing","args":{"project":"cyberdeck"}}'},

    {"role": "user",      "content": "what's the update on dronehive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"project_briefing","args":{"project":"dronehive"}}'},

    {"role": "user",      "content": "how is koi going"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"project_briefing","args":{"project":"koi"}}'},

    {"role": "user",      "content": "project blockers cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"project_blockers","args":{"project":"cyberdeck"}}'},

    {"role": "user",      "content": "what's blocking dronehive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"project_blockers","args":{"project":"dronehive"}}'},

    {"role": "user",      "content": "project readiness cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"project_readiness","args":{"project":"cyberdeck"}}'},

    {"role": "user",      "content": "can i build cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"project_readiness","args":{"project":"cyberdeck"}}'},

    {"role": "user",      "content": "show cyberdeck dependencies"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"project_dependencies","args":{"project":"cyberdeck"}}'},

    {"role": "user",      "content": "what projects use esp32-c3"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"projects_using","args":{"component":"esp32-c3"}}'},

    {"role": "user",      "content": "which projects need gps"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"projects_using","args":{"component":"gps"}}'},

    {"role": "user",      "content": "which projects are blocked"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"blocked_projects","args":{}}'},

    {"role": "user",      "content": "which projects can i start now"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"startable_projects","args":{}}'},

    {"role": "user",      "content": "what can i build now"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"startable_projects","args":{}}'},

    # ── Internal Board Router ─────────────────────────────────────────────────
    {"role": "user",      "content": "open intel board"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_board","args":{"board":"intel","route":"/intel"}}'},

    {"role": "user",      "content": "show intel board"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_board","args":{"board":"intel","route":"/intel"}}'},

    {"role": "user",      "content": "open hardware board"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_board","args":{"board":"hardware","route":"/hardware"}}'},

    {"role": "user",      "content": "open knowledge graph"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_board","args":{"board":"knowledge_graph","route":"/knowledge"}}'},

    {"role": "user",      "content": "open knowledge graph board"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_board","args":{"board":"knowledge_graph","route":"/knowledge"}}'},

    {"role": "user",      "content": "open voice diagnostics"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_board","args":{"board":"voice","route":"/voice"}}'},

    {"role": "user",      "content": "open fleet dashboard"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_board","args":{"board":"fleet","route":"/"}}'},

    {"role": "user",      "content": "open observability"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_board","args":{"board":"observability","route":"/"}}'},

    {"role": "user",      "content": "open mission control"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"open_board","args":{"board":"mission","route":"/"}}'},

    # ── Engineering Memory (Phase 14C) ───────────────────────────────────────
    {"role": "user",      "content": "record decision: Use PiSugar for Cyberdeck power system"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"record_project_memory","args":{"project":"Cyberdeck","type":"decision","title":"Use PiSugar for Cyberdeck power system","summary":"Use PiSugar for Cyberdeck power system","reasoning":""}}'},

    {"role": "user",      "content": "record lesson: Grounding DAC SCK eliminated MP3 player audio noise"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"record_project_memory","args":{"project":"","type":"lesson","title":"Grounding DAC SCK eliminated MP3 player audio noise","summary":"Grounding DAC SCK eliminated MP3 player audio noise","reasoning":""}}'},

    {"role": "user",      "content": "record milestone: Cyberdeck Arch Linux installation complete"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"record_project_memory","args":{"project":"Cyberdeck","type":"milestone","title":"Cyberdeck Arch Linux installation complete","summary":"Cyberdeck Arch Linux installation complete","reasoning":""}}'},

    {"role": "user",      "content": "record failure: Hermes Docker mount permissions blocked startup"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"record_project_memory","args":{"project":"","type":"failure","title":"Hermes Docker mount permissions blocked startup","summary":"Hermes Docker mount permissions blocked startup","reasoning":""}}'},

    {"role": "user",      "content": "add decision: Move SILVIA memory to provider model"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"record_project_memory","args":{"project":"CMD-CTR","type":"decision","title":"Move SILVIA memory to provider model","summary":"Move SILVIA memory to provider model","reasoning":""}}'},

    {"role": "user",      "content": "show decisions for cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_project_memory","args":{"project":"cyberdeck","type":"decision","query":""}}'},

    {"role": "user",      "content": "show lessons for dronehive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_project_memory","args":{"project":"dronehive","type":"lesson","query":""}}'},

    {"role": "user",      "content": "show failures for dronehive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_project_memory","args":{"project":"dronehive","type":"failure","query":""}}'},

    {"role": "user",      "content": "show project memory cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_project_memory","args":{"project":"cyberdeck","type":"","query":""}}'},

    {"role": "user",      "content": "show milestones for cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_project_memory","args":{"project":"cyberdeck","type":"milestone","query":""}}'},

    {"role": "user",      "content": "show project history cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_project_timeline","args":{"project":"cyberdeck"}}'},

    {"role": "user",      "content": "show timeline dronehive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_project_timeline","args":{"project":"dronehive"}}'},

    {"role": "user",      "content": "why did we choose Arch Linux"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_project_memory","args":{"query":"Arch Linux","project":""}}'},

    {"role": "user",      "content": "why did we switch to ESP32-C3"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"search_project_memory","args":{"query":"ESP32-C3","project":""}}'},

    {"role": "user",      "content": "what failed on DroneHive"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_project_memory","args":{"project":"DroneHive","type":"failure","query":""}}'},

    {"role": "user",      "content": "import memories from brain63"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"import_brain63_memory","args":{"project":""}}'},

    # ── Knowledge Graph (Phase 14A) ───────────────────────────────────────────
    {"role": "user",      "content": "show knowledge graph"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_knowledge_graph","args":{}}'},

    {"role": "user",      "content": "open knowledge graph"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_knowledge_graph","args":{}}'},

    {"role": "user",      "content": "show engineering graph"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_knowledge_graph","args":{}}'},

    {"role": "user",      "content": "show cyberdeck graph"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_knowledge_graph","args":{"project":"cyberdeck"}}'},

    # ── Observability (Phase 13C) ─────────────────────────────────────────────
    {"role": "user",      "content": "show recent actions"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_recent_actions","args":{"limit":20}}'},

    {"role": "user",      "content": "what did you do"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_recent_actions","args":{"limit":10}}'},

    {"role": "user",      "content": "show last 10 actions"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_recent_actions","args":{"limit":10}}'},

    {"role": "user",      "content": "show actions on pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_recent_actions","args":{"node":"pi5","limit":20}}'},

    {"role": "user",      "content": "show actions today"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_recent_actions","args":{"limit":50}}'},

    {"role": "user",      "content": "show failures"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_failures","args":{"limit":20}}'},

    {"role": "user",      "content": "what failed"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_failures","args":{"limit":20}}'},

    {"role": "user",      "content": "show planner decisions"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_planner_trace","args":{"limit":10}}'},

    {"role": "user",      "content": "show capability health"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_capability_health","args":{}}'},

    {"role": "user",      "content": "show system health"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_capability_health","args":{}}'},

    {"role": "user",      "content": "why did you do that"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"explain_last_action","args":{}}'},

    {"role": "user",      "content": "explain that"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"explain_last_action","args":{}}'},

    {"role": "user",      "content": "what just happened"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"explain_last_action","args":{}}'},

    # ── Fleet management (Phase 13B) ──────────────────────────────────────────
    {"role": "user",      "content": "show fleet status"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"fleet_status","args":{}}'},

    {"role": "user",      "content": "fleet health"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"fleet_status","args":{}}'},

    {"role": "user",      "content": "how are my nodes doing"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"fleet_status","args":{}}'},

    {"role": "user",      "content": "show offline nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_fleet_offline","args":{}}'},

    {"role": "user",      "content": "which nodes are down"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_fleet_offline","args":{}}'},

    {"role": "user",      "content": "show unhealthy nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_fleet_unhealthy","args":{}}'},

    {"role": "user",      "content": "show nodes with issues"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_fleet_unhealthy","args":{}}'},

    {"role": "user",      "content": "show node groups"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_fleet_groups","args":{}}'},

    {"role": "user",      "content": "restart docker on all raspberry pis"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"fleet_action","args":{"capability":"system.restart","filter_type":"type","filter_value":"raspberry-pi","service_name":"docker"}}'},

    {"role": "user",      "content": "restart samba on all nas servers"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"fleet_action","args":{"capability":"system.restart","filter_type":"type","filter_value":"nas","service_name":"samba"}}'},

    {"role": "user",      "content": "stop nginx on all production nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"fleet_action","args":{"capability":"system.stop","filter_type":"tag","filter_value":"production","service_name":"nginx"}}'},

    {"role": "user",      "content": "restart docker everywhere"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"fleet_action","args":{"capability":"system.restart","filter_type":"all","filter_value":"","service_name":"docker"}}'},

    {"role": "user",      "content": "start mosquitto on all nodes"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"fleet_action","args":{"capability":"system.start","filter_type":"all","filter_value":"","service_name":"mosquitto"}}'},

    # ── Engineering Planner (Phase 15B) ──────────────────────────────────────
    {"role": "user",      "content": "I want to build a GPS tracker"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"plan_project","args":{"description":"gps tracker"}}'},

    {"role": "user",      "content": "plan a rover"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"plan_project","args":{"description":"rover"}}'},

    {"role": "user",      "content": "design a lora sensor node"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"plan_project","args":{"description":"lora node"}}'},

    {"role": "user",      "content": "generate bom for rover"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"generate_bom","args":{"project":"rover"}}'},

    {"role": "user",      "content": "generate roadmap for gps tracker"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"generate_roadmap_plan","args":{"project":"gps tracker"}}'},

    {"role": "user",      "content": "what am I missing for gps tracker"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"planner_gap_analysis","args":{"project":"gps tracker"}}'},

    {"role": "user",      "content": "can I build a lora node"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"planner_can_i_build","args":{"project":"lora node"}}'},

    {"role": "user",      "content": "what can I build with my inventory"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"planner_what_can_i_build","args":{}}'},

    {"role": "user",      "content": "create project rover"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"planner_create_project","args":{"name":"Rover","template_id":"rover"}}'},

    {"role": "user",      "content": "show project architecture for drone"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"planner_architecture","args":{"project":"drone"}}'},

    {"role": "user",      "content": "generate procurement plan for rover"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"planner_procurement","args":{"project":"rover"}}'},

    {"role": "user",      "content": "list project templates"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_project_templates","args":{}}'},

    # ── Screen Awareness (Phase 16A) ─────────────────────────────────────────
    {"role": "user",      "content": "what am I working on"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_workspace_context","args":{}}'},

    {"role": "user",      "content": "show workspace context"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_workspace_context","args":{}}'},

    {"role": "user",      "content": "what project am I in"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_active_project","args":{}}'},

    {"role": "user",      "content": "what file am I editing"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_active_file","args":{}}'},

    {"role": "user",      "content": "what app am I using"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_active_application","args":{}}'},

    # ── Session Continuity (Phase 16B) ───────────────────────────────────────
    {"role": "user",      "content": "show recent sessions"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_recent_sessions","args":{}}'},

    {"role": "user",      "content": "what was I doing last night"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_last_session","args":{"project":""}}'},

    {"role": "user",      "content": "continue cyberdeck"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"continue_project","args":{"project":"cyberdeck"}}'},

    {"role": "user",      "content": "open cyberdeck workspace"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"restore_workspace","args":{"project":"cyberdeck"}}'},

    {"role": "user",      "content": "resume cmd-ctr"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"continue_project","args":{"project":"cmd-ctr"}}'},

    {"role": "user",      "content": "what did I accomplish today"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_accomplishments","args":{"hours":24}}'},

    {"role": "user",      "content": "restore yesterday's session"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"restore_workspace","args":{"project":""}}'},

    # ── Workflows (Phase 17B) ──────────────────────────────────────────────
    {"role": "user",      "content": "show workflows"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"list_workflows","args":{}}'},

    {"role": "user",      "content": "show pending workflows"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_pending_workflows","args":{}}'},

    {"role": "user",      "content": "show workflow history"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_workflow_history","args":{}}'},

    {"role": "user",      "content": "show WF-001"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"get_workflow","args":{"code":"WF-001"}}'},

    {"role": "user",      "content": "approve WF-001"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"approve_workflow","args":{"code":"WF-001"}}'},

    {"role": "user",      "content": "reject WF-001"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"reject_workflow","args":{"code":"WF-001"}}'},

    {"role": "user",      "content": "cancel WF-001"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"cancel_workflow","args":{"code":"WF-001"}}'},

    {"role": "user",      "content": "approve all workflows"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"approve_all_workflows","args":{"max_risk":""}}'},

    # ── Memory Providers (Phase 18A) ───────────────────────────────────────
    {"role": "user",      "content": "show memory providers"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_memory_providers","args":{}}'},

    {"role": "user",      "content": "show memory health"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_memory_health","args":{}}'},

    {"role": "user",      "content": "show memory timeline"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_memory_timeline","args":{"project":""}}'},

    {"role": "user",      "content": "show cyberdeck timeline"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_memory_timeline","args":{"project":"cyberdeck"}}'},

    {"role": "user",      "content": "show engineering history"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_memory_timeline","args":{"project":""}}'},

    {"role": "user",      "content": "show related memories"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_memory_relationships","args":{"entity":""}}'},

    # ── Brain63 Steward (Phase 18B) ────────────────────────────────────────
    {"role": "user",      "content": "show brain63 health"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_brain63_health","args":{}}'},

    {"role": "user",      "content": "show documentation coverage"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_brain63_coverage","args":{"project":""}}'},

    {"role": "user",      "content": "show pending documentation updates"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_brain63_drafts","args":{}}'},

    {"role": "user",      "content": "update cyberdeck roadmap"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"update_brain63_roadmap","args":{"project":"cyberdeck","change":""}}'},

    # ── System Diagnostics + Reminder Management ────────────────────────────
    {"role": "user",      "content": "deep system check"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"system_diagnostics","args":{}}'},

    {"role": "user",      "content": "run silvia diagnostics"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"system_diagnostics","args":{}}'},

    {"role": "user",      "content": "health check"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"system_diagnostics","args":{}}'},

    {"role": "user",      "content": "dismiss reminder check pi5"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"dismiss_reminder","args":{"query":"check pi5"}}'},

    {"role": "user",      "content": "clear stuck reminders"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"clear_stuck_reminders","args":{}}'},

    {"role": "user",      "content": "pause reminders"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"pause_reminders","args":{}}'},

    {"role": "user",      "content": "show reminder diagnostics"},
    {"role": "assistant", "content": '{"action":"call_tool","name":"show_reminder_diagnostics","args":{}}'},
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

# News / current events — route directly to search_web; these always need live data.
# Broad-match: if a query survives the social-engine veto (which blocks social uses
# of "news", "standings", etc.) and contains one of these words, it needs search.
_NEWS_RE = re.compile(r"\bnews\b", re.I)

_CURRENT_EVENTS_RE = re.compile(
    r"\b(?:standings?|rankings?|scores?|results?|playoff|bracket|championship|"
    r"tournament|league\s+table)\b|"
    r"\bcurrent\s+events?\b|"
    r"\bwho\s+won\s+",
    re.I,
)

_TIME_IN_RE  = re.compile(r"time\s+(?:is\s+it\s+)?in\s+([a-zA-Z\s\-,]+?)[\?\.!]?$")
_WEATHER_RE  = re.compile(r"(?:weather|climate)\s+(?:in|at|for|like\s+in)\s+([a-zA-Z\s\-,]+?)[\?\.!]?$")
_TEMP_RE     = re.compile(r"temperature\s+in\s+([a-zA-Z\s\-,]+?)[\?\.!]?$")
_RAIN_RE     = re.compile(r"(?:is\s+it\s+)?raining\s+in\s+([a-zA-Z\s\-,]+?)[\?\.!]?$")
_HOT_COLD_RE = re.compile(r"(?:is\s+it\s+)?(?:hot|cold|warm|freezing|sunny)\s+in\s+([a-zA-Z\s\-,]+?)[\?\.!]?$")

# Market comparison / "best stock" queries — need live data, never answerable from model memory.
# Route to search_web even in regex fallback so the LLM never gets a chance to invent data.
_BEST_STOCK_RE = re.compile(
    r"(?:best|top|highest?|biggest?|strongest?|leading)\s+(?:performing|gainer|mover|(?:stocks?))|"
    r"(?:performing|doing)\s+(?:best|worst|highest?|most)\s+(?:today|right\s+now|currently)?|"
    r"(?:which|what)\s+stock\s+is\s+(?:doing\s+)?(?:best|up|highest?|performing)|"
    r"(?:market|stocks?|shares?)\s+(?:today|right\s+now|currently|update|wrap|summary)|"
    r"today(?:'s)?\s+(?:market|gainers?|movers?|winners?|best\s+stocks?)",
    re.I,
)

# Date queries — route to get_time, not the LLM
_DATE_RE = re.compile(
    r"\b(?:what(?:'s|\s+is)?\s+(?:the\s+)?(?:current\s+)?(?:date|day)|"
    r"today(?:'s)?\s+date|"
    r"what\s+day\s+is\s+(?:it|today))\b",
    re.I,
)

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

# ── Mission Control patterns ──────────────────────────────────────────────────
_GIVE_ME_PFX = r"(?:(?:give|get|pull\s+up)\s+me(?:\s+(?:my|a|the))?\s+)?"

_BRIEFING_RE = re.compile(
    r"^" + _GIVE_ME_PFX +
    r"(?:morning\s+briefing|daily\s+briefing|good\s+morning|status\s+report|briefing|"
    r"what(?:'s|\s+is)?\s+happening\s+today|sitrep)[\?\.!]?$",
    re.I,
)
_FOCUS_RE = re.compile(
    r"^" + _GIVE_ME_PFX +
    r"(?:what\s+should\s+I\s+(?:focus\s+on|work\s+on)(?:\s+today)?|daily\s+focus|focus\s+today|"
    r"what(?:'s|\s+is)?\s+(?:my\s+)?(?:priority|top\s+priority)(?:\s+today)?|"
    r"what\s+should\s+I\s+do\s+(?:today|next)|"
    r"what(?:'s|\s+is)?\s+most\s+important\s+today)[\?\.!]?$",
    re.I,
)
_EVENING_RE = re.compile(
    r"^" + _GIVE_ME_PFX +
    r"(?:evening\s+review|end\s+of\s+day|eod|day\s+review|day\s+summary|"
    r"what\s+(?:did\s+I|have\s+I)\s+(?:accomplish|do|done|complete[d]?)\s+today|"
    r"how\s+did\s+(?:my\s+)?today\s+go|today(?:'s|\s+)?\s+(?:review|summary|recap)|"
    r"what\s+happened\s+today|wrap\s+up(?:\s+today)?)[\?\.!]?$",
    re.I,
)
_WEEKLY_RE = re.compile(
    r"^" + _GIVE_ME_PFX +
    r"(?:weekly\s+review|week(?:ly)?\s+(?:review|summary|recap)|"
    r"how\s+was\s+my\s+week|what\s+happened\s+this\s+week|week\s+in\s+review)[\?\.!]?$",
    re.I,
)
_FORGOTTEN_RE = re.compile(
    r"^(?:what\s+am\s+I\s+forgetting|what\s+have\s+I\s+forgotten|forgotten\s+items?|"
    r"what(?:'s|\s+is)?\s+overdue|overdue\s+items?|what\s+did\s+I\s+miss|"
    r"what(?:'s|\s+is)?\s+falling\s+behind|what(?:'s|\s+is)?\s+stale)[\?\.!]?$",
    re.I,
)
_STALE_PROJECTS_RE = re.compile(
    r"^(?:stale\s+projects?|show\s+stale\s+projects?|which\s+projects?\s+(?:are\s+)?stale|"
    r"inactive\s+projects?|abandoned\s+projects?|projects?\s+with\s+no\s+activity|"
    r"what(?:'s|\s+is)?\s+(?:been\s+)?(?:neglected|abandoned)|what\s+am\s+I\s+falling\s+behind\s+on)[\?\.!]?$",
    re.I,
)
_PROJECT_HEALTH_RE = re.compile(
    r"^(?:project\s+health|show\s+project\s+health|project\s+status|project\s+overview|"
    r"health\s+report|how\s+are\s+my\s+projects|project\s+report)[\?\.!]?$",
    re.I,
)
_LIST_PROJECTS_RE = re.compile(
    r"^(?:(?:list|show|display)\s+(?:all\s+)?(?:my\s+)?projects?|"
    r"(?:my\s+)?active\s+projects?|what\s+projects?\s+(?:are\s+)?(?:active|do\s+I\s+have)|"
    r"(?:all\s+)?projects?)[\?\.!]?$",
    re.I,
)
_CREATE_PROJECT_RE = re.compile(
    r"^(?:create|add|new|start)\s+project\s+(.+?)[\?\.!]?$",
    re.I,
)
_UPDATE_PROJECT_STATUS_RE = re.compile(
    r"^(?:mark|set|update)\s+project\s+(.+?)\s+(?:as|to)\s+(active|paused|complete|blocked)[\?\.!]?$",
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
_NODE_MERGE    = re.compile(
    rf"^(?:merge|consolidate|combine)\s+{_N}\s+into\s+{_N}[\?\.!]?$",
    re.I,
)
_NODE_DEDUP    = re.compile(
    r"^(?:deduplicate\s+(?:the\s+)?nodes?|clean\s+up\s+(?:the\s+)?(?:node\s+)?registry|"
    r"find\s+duplicate\s+nodes?|show\s+duplicate\s+nodes?|"
    r"(?:are\s+there\s+)?duplicate\s+nodes?)[\?\.!]?$",
    re.I,
)
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
    r"(?:show|list|what(?:'s|\s+is)?|display)?\s*(?:running\s+)?(?:processes?|programs?)"
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

# "How many nodes are online/registered/do I have" — route to list_nodes
_NODE_COUNT_RE = re.compile(
    r"\bhow\s+many\s+(?:nodes?|devices?|machines?)\s+"
    r"(?:are\s+(?:online|registered|up|active|there)|do\s+i\s+have|have\s+i\s+(?:got|registered))\b",
    re.I,
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


# ── Robotics regexes ─────────────────────────────────────────────────────────

_ROBOTICS_TYPE_RE = re.compile(
    r"^(?:list|show|get|what)\s+(?:all\s+)?(?:my\s+)?(drone|robot|esp32|sensor[\s\-]?network)s?[\?\.!]?$",
    re.I,
)
_CMD_ARM_RE    = re.compile(rf"^arm\s+{_N}[\?\.!]?$", re.I)
_CMD_DISARM_RE = re.compile(rf"^disarm\s+{_N}[\?\.!]?$", re.I)
_CMD_LAND_RE   = re.compile(rf"^land\s+{_N}[\?\.!]?$", re.I)
_CMD_HOME_RE   = re.compile(rf"^(?:send|return)\s+{_N}\s+(?:home|to\s+(?:home|base))[\?\.!]?$", re.I)
_CMD_ESTOP_RE  = re.compile(rf"^(?:emergency\s+stop|e[\-\.]?stop|estop)\s+{_N}[\?\.!]?$", re.I)
_CMD_REBOOT_RE = re.compile(rf"^reboot\s+{_N}[\?\.!]?$", re.I)

# ── Bulk commands ─────────────────────────────────────────────────────────────
_TYPE_KW = r"(drone|robot|esp32|sensor[\s\-]?network|vps|server|node)s?"
_BULK_LAND_RE   = re.compile(rf"^land\s+all\s+{_TYPE_KW}[\?\.!]?$", re.I)
_BULK_DISARM_RE = re.compile(rf"^disarm\s+all\s+{_TYPE_KW}[\?\.!]?$", re.I)
_BULK_ARM_RE    = re.compile(rf"^arm\s+all\s+{_TYPE_KW}[\?\.!]?$", re.I)
_BULK_ESTOP_RE  = re.compile(rf"^(?:emergency\s+stop|e[\-\.]?stop|estop)\s+all\s+{_TYPE_KW}[\?\.!]?$", re.I)
_BULK_REBOOT_RE = re.compile(rf"^reboot\s+all\s+{_TYPE_KW}[\?\.!]?$", re.I)
_BULK_HOME_RE   = re.compile(rf"^(?:send|return)\s+all\s+{_TYPE_KW}\s+(?:home|to\s+(?:home|base))[\?\.!]?$", re.I)

# ── Scheduled tasks ───────────────────────────────────────────────────────────
_SCHED_LIST_RE = re.compile(
    r"^(?:show|list|display|get|what)\s+(?:my\s+)?scheduled\s+tasks?[\?\.!]?$",
    re.I,
)
_SCHED_DISABLE_RE = re.compile(
    r"^(?:disable|pause|stop)\s+(?:scheduled\s+)?task\s+(.+?)[\?\.!]?$", re.I
)
_SCHED_DELETE_RE = re.compile(
    r"^(?:delete|remove|cancel)\s+(?:scheduled\s+)?task\s+(.+?)[\?\.!]?$", re.I
)
_SCHED_CREATE_RE = re.compile(
    r"^schedule\s+(?:a\s+)?(?:task|job)(?:\s*:)?\s+(.+?)\s+every\s+(\d+)\s+(?:minute|min)s?[\?\.!]?$",
    re.I,
)

# ── Productivity — Gmail (Phase 12G) ─────────────────────────────────────────
# Default queries always filter to category:primary (closest to user expectations).
_EMAIL_CHECK_RE = re.compile(
    r"^(?:check|get|show|read|view|open|see|fetch|pull)\s+(?:my\s+)?(?:email|emails|mail|inbox|gmail)[\?\.!]?$",
    re.I,
)
_EMAIL_UNREAD_RE = re.compile(
    r"^(?:check|show|list|get|any|fetch|see|read)\s+(?:my\s+)?(?:unread|new|unseen)\s+(?:email|emails|mail|messages?)[\?\.!]?$|"
    r"^(?:unread|new|unseen)\s+(?:email|emails|mail|messages?)[\?\.!]?$|"
    r"^(?:do\s+i\s+have\s+(?:any\s+)?(?:new|unread)\s+(?:email|emails|mail))[\?\.!]?$",
    re.I,
)
_EMAIL_FROM_RE = re.compile(
    r"^(?:check|show|get|find|read|any|list)\s+(?:for\s+)?(?:my\s+)?(?:email|emails|mail)s?\s+(?:from|by)\s+(.+?)[\?\.!]?$|"
    r"^(?:mail|email|emails)\s+from\s+(.+?)[\?\.!]?$",
    re.I,
)
_EMAIL_SEARCH_RE = re.compile(
    r"^(?:search|find|look\s+for|check\s+for|search\s+email\s+for)\s+(?:email|emails|mail)s?\s+(?:about|for|re:?|regarding|with|mentioning)\s+(.+?)[\?\.!]?$|"
    r"^(?:search|find)\s+(?:email|emails|gmail)\s+for\s+(.+?)[\?\.!]?$|"
    r"^(?:search\s+email\s+for|check\s+email\s+for)\s+(.+?)[\?\.!]?$",
    re.I,
)
_EMAIL_LATEST_RE = re.compile(
    r"^(?:show|get|check|fetch|list)\s+(?:my\s+)?(?:latest|recent|last|newest)\s+(?:email|emails|mail|messages?)[\?\.!]?$",
    re.I,
)
# Category-specific inbox queries
_EMAIL_ALL_RE = re.compile(
    r"^(?:check|show|get|list)\s+all\s+(?:my\s+)?(?:email|emails|mail)[\?\.!]?$",
    re.I,
)
_EMAIL_CAT_RE = re.compile(
    r"^(?:check|show|get|open|read|view)\s+(?:my\s+)?(?:email\s+)?(?P<cat>promotions?|social|updates?|forums?)[\?\.!]?$",
    re.I,
)
# ── Productivity — Google Calendar (Phase 12G) ───────────────────────────────
_GCAL_TODAY_RE = re.compile(
    r"^(?:what(?:'s|\s+is)?\s+(?:on\s+)?(?:my\s+)?(?:google\s+)?(?:calendar|schedule|agenda)(?:\s+today)?|"
    r"(?:show|check|view)\s+(?:my\s+)?(?:google\s+)?(?:calendar|schedule|agenda)(?:\s+today)?)[\?\.!]?$",
    re.I,
)
_GCAL_WEEK_RE = re.compile(
    r"(?:my\s+)?(?:google\s+)?calendar.*?(?:this\s+week|next\s+7\s+days?|week)|"
    r"(?:events?|schedule|agenda).*?(?:this\s+week|next\s+7\s+days?)|"
    r"(?:this\s+week|next\s+7\s+days?).*?(?:calendar|events?|schedule|agenda)",
    re.I,
)
# ── Productivity status ───────────────────────────────────────────────────────
_PROD_STATUS_RE = re.compile(
    r"^(?:show\s+)?(?:productivity|google|gmail|calendar)\s+(?:status|connection|info|connected)[\?\.!]?$|"
    r"^(?:is\s+)?(?:google|gmail)\s+(?:connected|linked|authorized|active)[\?\.!]?$|"
    r"^productivity\s+status[\?\.!]?$",
    re.I,
)


def _cap(capability: str, node: str = "", args: dict | None = None) -> dict:
    return {"action": "call_tool", "name": "execute_capability",
            "args": {"capability": capability, "node": node, "args": args or {}}}


_OPT_NODE = r"(?:\s+on\s+([a-z0-9][a-z0-9_\-]*))?[\?\.!]?$"   # optional "on <node>" suffix

# ── Media capability regexes ──────────────────────────────────────────────────
_CAP_MEDIA_PLAY = re.compile(
    r"^(?:play|start\s+playing|play\s+(?:music|audio|track|song))" + _OPT_NODE, re.I)
_CAP_MEDIA_PAUSE = re.compile(
    r"^(?:pause(?:\s+(?:music|audio|track|song|playback))?)" + _OPT_NODE, re.I)
_CAP_MEDIA_STOP = re.compile(
    r"^(?:stop\s+(?:the\s+)?(?:music|audio|track|song|playback)|stop\s+playing)" + _OPT_NODE, re.I)
_CAP_MEDIA_NEXT = re.compile(
    r"^(?:(?:skip|next)\s+(?:track|song)|next\s+track|skip\s+song)" + _OPT_NODE, re.I)
_CAP_MEDIA_PREV = re.compile(
    r"^(?:(?:previous|prev|last|go\s+back)\s+(?:track|song)|previous\s+track)" + _OPT_NODE, re.I)
_CAP_MEDIA_VOL = re.compile(
    r"^set\s+volume\s+(?:to\s+)?(\d+)" + _OPT_NODE, re.I)

# ── Motion capability regexes ─────────────────────────────────────────────────
_CAP_MOTION_FWD  = re.compile(rf"^move\s+{_N}\s+forward[\?\.!]?$", re.I)
_CAP_MOTION_BWD  = re.compile(rf"^move\s+{_N}\s+backward[\?\.!]?$", re.I)
_CAP_MOTION_LEFT = re.compile(rf"^(?:turn|rotate)\s+{_N}\s+left[\?\.!]?$", re.I)
_CAP_MOTION_RIGHT = re.compile(rf"^(?:turn|rotate)\s+{_N}\s+right[\?\.!]?$", re.I)
_CAP_MOTION_STOP = re.compile(rf"^stop\s+{_N}[\?\.!]?$", re.I)

# ── Camera capability regexes ─────────────────────────────────────────────────
_CAP_CAMERA_CAPTURE = re.compile(
    r"^(?:take\s+(?:a\s+)?(?:photo|picture|image|snapshot)|capture\s+(?:image|photo))" + _OPT_NODE, re.I)
_CAP_CAMERA_STREAM = re.compile(
    r"^start\s+(?:camera\s+)?stream" + _OPT_NODE, re.I)
_CAP_CAMERA_STREAM_STOP = re.compile(
    r"^stop\s+(?:camera\s+)?stream" + _OPT_NODE, re.I)

# ── System service capability regexes ─────────────────────────────────────────
# "restart nginx on carrera" / "stop apache on nighthawk"
_SVC_NAME = r"([a-zA-Z0-9_.\-]{1,64})"
_ON_NODE   = rf"(?:\s+on\s+{_N})?[\?\.!]?$"
_CAP_SYS_RESTART = re.compile(rf"^restart\s+{_SVC_NAME}{_ON_NODE}", re.I)
_CAP_SYS_START   = re.compile(rf"^start\s+{_SVC_NAME}{_ON_NODE}", re.I)
_CAP_SYS_STOP    = re.compile(rf"^stop\s+{_SVC_NAME}{_ON_NODE}", re.I)
_CAP_SYS_STATUS  = re.compile(rf"^(?:status\s+of\s+)?{_SVC_NAME}\s+(?:service\s+)?status{_ON_NODE}", re.I)

# ── Battery / sensor capability regexes ───────────────────────────────────────
_CAP_BATTERY = re.compile(rf"^(?:battery\s+(?:status|level|info)|check\s+battery)\s+(?:of\s+|on\s+)?{_N}[\?\.!]?$", re.I)
_CAP_SENSOR  = re.compile(rf"^(?:read|get|check)\s+sensor\s+(?:on\s+)?{_N}[\?\.!]?$", re.I)

# ── Services listing regexes ──────────────────────────────────────────────────
_SVC_LIST_ON = re.compile(
    rf"^(?:show|list|get|display|what)\s+(?:all\s+)?services?\s+(?:on|for|from)\s+{_N}[\?\.!]?$", re.I)
_SVC_WHAT    = re.compile(
    rf"^what\s+(?:services?|capabilities?)\s+(?:does|do)\s+{_N}\s+(?:have|support|expose)[\?\.!]?$", re.I)
_SVC_LIST_ALL = re.compile(
    r"^(?:list|show|display|get)\s+all\s+services?[\?\.!]?$", re.I)
# "what can X do/run/execute" — Phase 13A capability discovery
_SVC_WHAT_CAN = re.compile(
    rf"^what\s+can\s+{_N}\s+(?:do|run|execute|perform)[\?\.!]?$", re.I)
# "show/list capabilities on X" — Phase 13A
_SVC_CAPS_ON  = re.compile(
    rf"^(?:show|list|get|display)\s+(?:all\s+)?capabilities?\s+(?:on|for|of|from)\s+{_N}[\?\.!]?$", re.I)

# ── Fleet management regexes (Phase 13B) ──────────────────────────────────────
_FLEET_STATUS_RE = re.compile(
    r"^(?:show|get|display|check)?\s*fleet\s+(?:status|health|overview|summary|dashboard)[\?\.!]?$|"
    r"^fleet\s+(?:status|health|overview|summary|dashboard)[\?\.!]?$|"
    r"^(?:show|get|display)\s+infrastructure\s+(?:status|health|overview|summary)[\?\.!]?$|"
    r"^(?:how\s+is|how\s+are)\s+(?:the\s+)?(?:fleet|nodes|infrastructure)[\?\.!]?$",
    re.I,
)
_FLEET_OFFLINE_RE = re.compile(
    r"^(?:show|list|get)\s+(?:all\s+)?offline\s+(?:nodes?|devices?|machines?)[\?\.!]?$|"
    r"^(?:show|list)\s+(?:all\s+)?(?:nodes?|devices?)\s+(?:that\s+(?:are\s+)?)?offline[\?\.!]?$|"
    r"^which\s+(?:nodes?|devices?|machines?)\s+(?:are\s+)?(?:down|offline|unreachable)[\?\.!]?$|"
    r"^what(?:'s|\s+is)\s+(?:currently\s+)?(?:down|offline)[\?\.!]?$",
    re.I,
)
_FLEET_UNHEALTHY_RE = re.compile(
    r"^(?:show|list|get)\s+(?:all\s+)?(?:unhealthy|degraded|problem|warning|critical)\s+(?:nodes?|devices?|machines?)[\?\.!]?$|"
    r"^(?:which|what)\s+(?:nodes?|devices?|machines?)\s+(?:are|have)\s+(?:issues?|problems?|warnings?|degraded|unhealthy)[\?\.!]?$|"
    r"^(?:show|list)\s+(?:nodes?\s+with\s+)?(?:issues?|problems?|warnings?|errors?)[\?\.!]?$|"
    r"^show\s+(?:problem|warning|critical)\s+nodes?[\?\.!]?$",
    re.I,
)
_FLEET_GROUPS_RE = re.compile(
    r"^(?:show|list|get|display)\s+(?:all\s+)?(?:node\s+)?groups?(?:\s+by\s+(?:type|tag|service))?[\?\.!]?$|"
    r"^(?:group|organize|categorize)\s+(?:my\s+)?nodes?(?:\s+by\s+(?:type|tag|service))?[\?\.!]?$|"
    r"^(?:how\s+(?:are|is))\s+(?:the\s+)?nodes?\s+(?:grouped|organized|categorized)[\?\.!]?$",
    re.I,
)
# "restart X on all Y" / "restart X everywhere" → fleet_action
_FLEET_ACT_ON_ALL = re.compile(
    r"^(?P<action>restart|start|stop)\s+(?P<service>[a-zA-Z0-9_.\-]{1,64})"
    r"\s+on\s+all\s+(?P<filter>.+?)[\?\.!]?$",
    re.I,
)
_FLEET_ACT_EVERYWHERE = re.compile(
    r"^(?P<action>restart|start|stop)\s+(?P<service>[a-zA-Z0-9_.\-]{1,64})"
    r"\s+(?:everywhere|on\s+(?:all\s+)?(?:nodes?|everything|machines?|devices?))[\?\.!]?$",
    re.I,
)

# ── Project Intelligence regexes (Phase 14A) ─────────────────────────────────
_PROJ_BRIEFING_RE = re.compile(
    r"^(?:project\s+briefing|brief(?:ing)?\s+(?:me\s+)?(?:on|about)|"
    r"what(?:'s|\s+is)\s+the\s+(?:update|status|progress|situation)\s+on|"
    r"how\s+is|status\s+of|what(?:'s|\s+is)\s+happening\s+with)\s+"
    r"(?P<project>[a-zA-Z0-9_\-][a-zA-Z0-9_\-\s]{0,40}?)[\?\.!]?$",
    re.I,
)
_PROJ_BLOCKERS_RE = re.compile(
    r"^project\s+blockers?\s+(?P<project>[a-zA-Z0-9_\-\s]{1,40}?)[\?\.!]?$|"
    r"^what(?:'s|\s+is)\s+blocking\s+(?P<project2>[a-zA-Z0-9_\-\s]{1,40}?)[\?\.!]?$",
    re.I,
)
_PROJ_READINESS_RE = re.compile(
    r"^(?:project\s+readiness|can\s+(?:i|we)\s+build)\s+"
    r"(?P<project>[a-zA-Z0-9_\-\s]{1,40}?)[\?\.!]?$",
    re.I,
)
_PROJ_DEPS_RE = re.compile(
    r"^project\s+dependencies\s+(?P<project>[a-zA-Z0-9_\-\s]{1,40}?)[\?\.!]?$|"
    r"^show\s+(?P<project2>[a-zA-Z0-9_\-\s]{1,40}?)\s+dependencies[\?\.!]?$",
    re.I,
)
_PROJ_USING_RE = re.compile(
    r"^(?:what|which)\s+projects?\s+(?:use|need|require|depend\s+on|contain)\s+"
    r"(?P<component>[a-zA-Z0-9_\-\s]{1,60}?)[\?\.!]?$",
    re.I,
)
_PROJ_BLOCKED_RE = re.compile(
    r"^(?:which|what)\s+projects?\s+(?:are\s+)?blocked[\?\.!]?$|"
    r"^show\s+blocked\s+projects?[\?\.!]?$",
    re.I,
)
_PROJ_STARTABLE_RE = re.compile(
    r"^(?:which|what)\s+projects?\s+can\s+(?:(?:i|we)\s+)?(?:start|begin)(?:\s+now)?[\?\.!]?$|"
    r"^(?:which|what)\s+projects?\s+(?:are\s+)?ready[\?\.!]?$|"
    r"^what\s+can\s+(?:i|we)\s+build\s+now[\?\.!]?$",
    re.I,
)

# ── Internal Board Router ────────────────────────────────────────────────────

# Board name fragment → (board_id, route)
_BOARD_ALIASES: list[tuple["re.Pattern[str]", str, str]] = [
    (re.compile(r"\bintel\b|\bintelligence\b|\bworld.?intel",         re.I), "intel",          "/intel"),
    (re.compile(r"\bhardware\b",                                       re.I), "hardware",        "/hardware"),
    (re.compile(r"\bknowledge\b|\bgraph\b|\bkg\b",                    re.I), "knowledge_graph",  "/knowledge"),
    (re.compile(r"\bmemory\s+board|\bproject\s+memory|\beng.*memory", re.I), "memory",          "/memory"),
    (re.compile(r"\bworkspace\b|\bdigital\s*twin\b|\btwin\b",         re.I), "workspace",        "/workspace"),
    (re.compile(r"\bplanner\b|\bengineering\s*planner\b|\bproject\s*planner\b", re.I), "planner", "/planner"),
    (re.compile(r"\bworkflows?\b|\bchange\s*management\b",             re.I), "workflows",        "/workflows"),
    (re.compile(r"\bbrain\s*63\b|\bb63\b|\bsteward\b",                 re.I), "brain63",          "/brain63"),
    (re.compile(r"\bvoice\b",                                          re.I), "voice",            "/voice"),
    (re.compile(r"\bfleet\b",                                          re.I), "fleet",            "/"),
    (re.compile(r"\bobservab|\bexecution.?log|\bledger",               re.I), "observability",    "/"),
    (re.compile(r"\bmission\b",                                        re.I), "mission",          "/"),
    (re.compile(r"\binfra",                                            re.I), "infrastructure",   "/"),
    (re.compile(r"\bfiles?\b|\bdesktop\b",                             re.I), "desktop",          "/"),
    (re.compile(r"\bcommand\b|\bhome\b",                               re.I), "command_center",   "/"),
]

_BOARD_LABELS: dict[str, str] = {
    "intel":          "Intel Board",
    "hardware":       "Hardware Board",
    "knowledge_graph": "Knowledge Graph",
    "memory":         "Project Memory",
    "workspace":      "Workspace Digital Twin",
    "planner":        "Engineering Planner",
    "workflows":      "Workflow Board",
    "brain63":        "Brain63 Steward",
    "voice":          "Voice Diagnostics",
    "fleet":          "Fleet Dashboard",
    "observability":  "Observability",
    "mission":        "Mission Control",
    "infrastructure": "Infrastructure",
    "desktop":        "Files & Apps",
    "command_center": "Command Center",
}

# Board name fragments that appear in commands like "open <board>" or "show <board> board"
_BOARD_NAME_FRAG = (
    r"intel(?:\s+board)?|intelligence(?:\s+board)?|world\s+intel(?:\s+board)?|"
    r"hardware(?:\s+(?:board|ops(?:\s+center)?))?|"
    r"knowledge(?:\s+graph)?(?:\s+board)?|knowledge\s+graph\s+board|graph\s+board|engineering\s+graph|"
    r"voice(?:\s+diagnostics?)?|"
    r"fleet(?:\s+dashboard)?|fleet\s+view|"
    r"observability(?:\s+(?:board|panel|dashboard))?|execution\s+log(?:\s+board)?|ledger|"
    r"mission(?:\s+control(?:\s+board)?)?|"
    r"infrastructure(?:\s+(?:panel|board))?|infra(?:\s+panel)?|"
    r"command(?:\s+center(?:\s+board)?)?|home|"
    r"files?(?:\s+(?:and|&)\s+apps?)?|desktop(?:\s+panel)?|"
    r"workflows?(?:\s+(?:board|review))?|change\s+management|"
    r"brain\s*63(?:\s+(?:board|steward|dashboard))?"
)

# "open/go to/navigate to/launch" + any board name
_BOARD_OPEN_RE = re.compile(
    r"^(?:open|go\s+to|navigate\s+to|launch|take\s+me\s+to|switch\s+to)\s+"
    r"(?:the\s+|a\s+)?"
    r"(?P<board>" + _BOARD_NAME_FRAG + r")[\?\.!]?$",
    re.I,
)

# "show (me) (the) <board> board/dashboard/diagnostics" — requires explicit board/dashboard suffix
# to avoid capturing "show fleet status", "show knowledge graph" (those have their own handlers)
_BOARD_SHOW_RE = re.compile(
    r"^show(?:\s+me)?\s+(?:the\s+)?"
    r"(?P<board>"
    r"intel(?:\s+board)|intelligence(?:\s+board)|world\s+intel(?:\s+board)|"
    r"hardware(?:\s+board)|"
    r"knowledge(?:\s+graph)?\s+board|"
    r"voice(?:\s+diagnostics?)|"
    r"fleet(?:\s+dashboard)|"
    r"observability(?:\s+(?:board|dashboard))?|"
    r"mission(?:\s+control)?(?:\s+board)|"
    r"infrastructure(?:\s+board)|"
    r"workflows?(?:\s+(?:board|review))|change\s+management|"
    r"brain\s*63(?:\s+(?:board|steward|dashboard))|"
    r"command\s+center"
    r")[\?\.!]?$",
    re.I,
)


def _resolve_board_alias(text: str) -> tuple[str, str]:
    """Return (board_id, route) for a board fragment."""
    for pattern, board_id, route in _BOARD_ALIASES:
        if pattern.search(text):
            return board_id, route
    return "command_center", "/"


def _regex_board(query: str) -> dict | None:
    """Match internal SILVIA board navigation — checked FIRST in _regex_fallback.

    Fires for "open X", "go to X", "show X board/dashboard/diagnostics".
    NEVER fires for "open VS Code", "open Downloads" (no board name match).
    """
    text = query.strip()

    m = _BOARD_OPEN_RE.match(text) or _BOARD_SHOW_RE.match(text)
    if not m:
        return None
    board_text = m.group("board").lower().strip()
    board_id, route = _resolve_board_alias(board_text)
    return {"action": "call_tool", "name": "open_board", "args": {"board": board_id, "route": route}}


# ── Knowledge Graph (Phase 14A) ───────────────────────────────────────────────
_KG_GENERAL_RE = re.compile(
    r"^(?:show|view|display)\s+(?:the\s+)?(?:knowledge\s+graph|engineering\s+graph|kg|project\s+graph)[\?\.!]?$|"
    r"^what'?s?\s+in\s+(?:the\s+)?(?:knowledge\s+graph|kg)[\?\.!]?$|"
    r"^(?:show|display)\s+(?:the\s+)?graph[\?\.!]?$",
    re.I,
)
_KG_PROJECT_RE = re.compile(
    r"^show\s+(?P<project>[a-zA-Z0-9_\-\s]{1,40}?)\s+(?:graph|in\s+(?:the\s+)?(?:knowledge\s+)?graph)[\?\.!]?$|"
    r"^(?:show|view)\s+(?P<project2>[a-zA-Z0-9_\-\s]{1,40}?)\s+knowledge\s+graph[\?\.!]?$",
    re.I,
)

# ── Engineering Memory regexes (Phase 14C) ───────────────────────────────────

# "record decision: ..." / "add lesson: ..." / "log milestone: ..."
_MEM_RECORD_RE = re.compile(
    r"^(?:record|add|log|note|save|capture)\s+"
    r"(?P<type>decision|lesson|milestone|failure|success|experiment|design\s*note|engineering\s*note|risk|assumption|retrospective)"
    r"(?:\s+for\s+(?P<proj1>[a-zA-Z0-9_\-\s]{1,30}?))?"
    r"\s*[:\-]\s*(?P<text>.+)$",
    re.I | re.S,
)

# "show decisions for cyberdeck" / "show lessons for dronehive" / "show project memory cyberdeck"
_MEM_SHOW_RE = re.compile(
    r"^(?:show|list|display|get|what(?:\s+are\s+the)?)\s+"
    r"(?:(?P<type>decisions?|lessons?(?:\s+learned)?|milestones?|failures?|successes?|risks?|assumptions?|retrospectives?|"
    r"engineering\s+notes?|design\s+notes?|experiments?)\s+)?"
    r"(?:for\s+|from\s+|on\s+|in\s+)?(?:the\s+)?"
    r"(?:project\s+memory\s+for\s+|project\s+memory\s+|memory\s+for\s+|engineering\s+memory\s+(?:for\s+)?)?"
    r"(?P<project>[a-zA-Z0-9_\-]{2,30})[\?\.!]?$",
    re.I,
)

# "show project memory cyberdeck" / "show all decisions" / "show all lessons"
_MEM_SHOW_ALL_RE = re.compile(
    r"^(?:show|list|display)\s+"
    r"(?:all\s+)?(?:project\s+)?(?:engineering\s+)?"
    r"(?P<type>decisions?|lessons?(?:\s+learned)?|milestones?|failures?|successes?|risks?|engineering\s+notes?)"
    r"[\?\.!]?$",
    re.I,
)

# "show project history cyberdeck" / "show timeline cyberdeck" / "show cyberdeck timeline"
_MEM_TIMELINE_RE = re.compile(
    r"^(?:show|display)\s+(?:project\s+)?(?:history|timeline)\s+(?:for\s+|of\s+)?(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^(?:show|display)\s+(?P<project2>[a-zA-Z0-9_\-]{2,30})\s+(?:history|timeline)[\?\.!]?$",
    re.I,
)

# "what failed on X" / "what went wrong with X" / "what broke on X" → get failures for project
_MEM_FAILURES_ON_RE = re.compile(
    r"^what\s+(?:failed|went\s+wrong|broke|happened)\s+(?:on|with|in|to)\s+(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)

# "why did we choose X" / "why did we switch to X" / "why did we use X"
_MEM_SEARCH_RE = re.compile(
    r"^(?:why\s+did\s+we\s+(?:choose|switch|use|adopt|pick|select|decide|move|go\s+with)|"
    r"why\s+(?:did\s+)?(?:we\s+)?(?:chose?|switched?|used?|adopted?)|"
    r"what\s+(?:did\s+we\s+)?(?:decide|learn|discover)\s+about\s+|"
    r"find\s+(?:decisions?|lessons?|memories?)\s+(?:about|for|on)\s+)"
    r"(?P<query>.+)$",
    re.I,
)

# "import memories from brain63" / "sync decisions from brain63"
_MEM_IMPORT_RE = re.compile(
    r"^(?:import|sync|load|pull)\s+(?:memories?|decisions?|lessons?|memory)\s+"
    r"(?:from\s+brain63?|from\s+vault|from\s+obsidian)?[\?\.!]?$|"
    r"^import\s+(?P<project>[a-zA-Z0-9_\-]{2,30})\s+(?:memories?|decisions?)(?:\s+from\s+brain63?)?[\?\.!]?$",
    re.I,
)

_MEM_TYPE_NORM = {
    "decision": "decision", "decisions": "decision",
    "lesson": "lesson", "lessons": "lesson", "lessons learned": "lesson",
    "milestone": "milestone", "milestones": "milestone",
    "failure": "failure", "failures": "failure",
    "success": "success", "successes": "success",
    "risk": "risk", "risks": "risk",
    "assumption": "assumption", "assumptions": "assumption",
    "retrospective": "retrospective", "retrospectives": "retrospective",
    "engineering note": "engineering_note", "engineering notes": "engineering_note",
    "design note": "design_note", "design notes": "design_note",
    "experiment": "experiment", "experiments": "experiment",
}


def _regex_memory(query: str) -> dict | None:
    """Match engineering memory commands."""
    text = query.strip()

    # Record command
    m = _MEM_RECORD_RE.match(text)
    if m:
        raw_type = m.group("type").lower().strip()
        mem_type = _MEM_TYPE_NORM.get(raw_type, raw_type.replace(" ", "_"))
        body = m.group("text").strip()
        proj = (m.group("proj1") or "").strip()
        return {
            "action": "call_tool",
            "name": "record_project_memory",
            "args": {"project": proj, "type": mem_type, "title": body, "summary": body, "reasoning": ""},
        }

    # Timeline
    m = _MEM_TIMELINE_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or "").strip()
        return {"action": "call_tool", "name": "get_project_timeline", "args": {"project": project}}

    # "what failed on X" → get_project_memory with type=failure
    m = _MEM_FAILURES_ON_RE.match(text)
    if m:
        project = m.group("project").strip()
        return {"action": "call_tool", "name": "get_project_memory", "args": {"project": project, "type": "failure", "query": ""}}

    # Search
    m = _MEM_SEARCH_RE.match(text)
    if m:
        q = m.group("query").strip()
        return {"action": "call_tool", "name": "search_project_memory", "args": {"query": q, "project": ""}}

    # Import from Brain63
    m = _MEM_IMPORT_RE.match(text)
    if m:
        proj = (m.group("project") if m.lastindex and m.group("project") else "")
        return {"action": "call_tool", "name": "import_brain63_memory", "args": {"project": proj or ""}}

    # Show all (no project)
    m = _MEM_SHOW_ALL_RE.match(text)
    if m:
        raw_type = m.group("type").lower().strip()
        mem_type = _MEM_TYPE_NORM.get(raw_type, raw_type.replace(" ", "_"))
        return {"action": "call_tool", "name": "get_project_memory", "args": {"project": "", "type": mem_type, "query": ""}}

    # Show for project
    m = _MEM_SHOW_RE.match(text)
    if m:
        project = (m.group("project") or "").strip()
        raw_type = (m.group("type") or "").lower().strip()
        mem_type = _MEM_TYPE_NORM.get(raw_type, raw_type.replace(" ", "_")) if raw_type else ""
        return {"action": "call_tool", "name": "get_project_memory", "args": {"project": project, "type": mem_type, "query": ""}}

    return None


# ── Workspace Digital Twin regexes (Phase 15A) ────────────────────────────────
_WS_STATUS_RE = re.compile(
    r"^(?:show\s+)?workspace(?:\s+status)?[\?\.!]?$|"
    r"^(?:show|display)\s+workspace\s+(?:status|overview|state|summary)[\?\.!]?$|"
    r"^how\s+is\s+(?:the\s+)?workspace[\?\.!]?$",
    re.I,
)
_WS_PRIORITIES_RE = re.compile(
    r"^(?:show\s+)?workspace\s+priorities[\?\.!]?$|"
    r"^(?:show|display)\s+(?:project\s+)?(?:priority\s+)?rankings?[\?\.!]?$|"
    r"^rank\s+(?:my\s+)?projects[\?\.!]?$",
    re.I,
)
_WS_DAILY_BRIEFING_RE = re.compile(
    r"^daily\s+(?:engineering\s+)?briefing[\?\.!]?$|"
    r"^engineering\s+briefing[\?\.!]?$|"
    r"^full\s+briefing[\?\.!]?$",
    re.I,
)
_WS_BLOCKED_RE = re.compile(
    r"^(?:show\s+)?blocked\s+projects[\?\.!]?$|"
    r"^what(?:\s+projects?)?\s+(?:is|are)\s+blocked[\?\.!]?$|"
    r"^which\s+projects?\s+(?:is|are)\s+blocked[\?\.!]?$",
    re.I,
)
_WS_READY_RE = re.compile(
    r"^(?:show\s+)?ready\s+projects[\?\.!]?$|"
    r"^what\s+(?:projects?\s+)?can\s+I\s+(?:continue|build|start|work\s+on)\s+(?:right\s+now|now|today)[\?\.!]?$|"
    r"^what\s+is\s+(?:available|ready)[\?\.!]?$",
    re.I,
)
_WS_WORK_ON_RE = re.compile(
    r"^what\s+should\s+I\s+(?:work\s+on|focus\s+on|do)(?:\s+(?:tonight|today|now|next))?[\?\.!]?$|"
    r"^(?:show\s+)?recommended\s+work[\?\.!]?$",
    re.I,
)
_WS_ORDER_RE = re.compile(
    r"^what\s+should\s+I\s+order(?:\s+next)?[\?\.!]?$|"
    r"^what\s+(?:do\s+I\s+)?need\s+to\s+order[\?\.!]?$|"
    r"^(?:show\s+)?order\s+needs[\?\.!]?$",
    re.I,
)
_WS_CLOSEST_RE = re.compile(
    r"^what\s+(?:project\s+)?is\s+(?:closest|nearest)\s+to\s+(?:completion|done|finished)[\?\.!]?$|"
    r"^which\s+project\s+is\s+(?:almost|nearly)\s+(?:done|finished|complete)[\?\.!]?$",
    re.I,
)
# "what should I order/buy next for X" / "what parts am I missing for X" / "what do I need for X"
_WS_PROJECT_ORDER_RE = re.compile(
    r"^what\s+(?:should\s+I\s+(?:order|buy)(?:\s+next)?|parts?\s+(?:am\s+I|are)\s+(?:still\s+)?missing|do\s+I\s+(?:still\s+)?need(?:\s+to\s+(?:buy|order))?)\s+for\s+(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^(?:order\s+(?:status|recommendations?)|what\s+(?:have\s+I\s+)?already\s+(?:bought|ordered|acquired))\s+for\s+(?P<project2>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^(?:show\s+)?(?:missing|needed)\s+parts?\s+for\s+(?P<project3>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^what\s+should\s+I\s+(?:buy|order)\s+(?:next\s+)?for\s+(?P<project4>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)
# "what can I work on for X" / "what should I do on X"
_WS_PROJECT_WORK_RE = re.compile(
    r"^what\s+(?:can|should)\s+I\s+(?:work|do)\s+(?:on\s+)?(?:for|on|next\s+for)\s+(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)
# "I already bought X for Y" / "mark X as acquired for Y" / "I received X for Y" / "I ordered X for Y"
_WS_MARK_ACQUIRED_RE = re.compile(
    r"^(?:I\s+(?:already\s+)?(?:bought|acquired|have|got|received|ordered)|"
    r"mark\s+(?P<item1>[a-zA-Z0-9_\-\s,]+?)\s+as\s+(?:acquired|owned|received|ordered))\s+"
    r"(?:for\s+)?(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)
_WS_MARK_ACQUIRED_V2_RE = re.compile(
    r"^I\s+(?:already\s+)?(?P<verb>bought|acquired|have|got|received|ordered)\s+"
    r"(?:the\s+)?(?P<items>.+?)\s+for\s+(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)

# ── Screen Awareness regexes (Phase 16A) ────────────────────────────────────

_SA_CONTEXT_RE = re.compile(
    r"^(?:what\s+am\s+I\s+(?:working\s+on|doing)|"
    r"(?:show|display|get)\s+(?:my\s+)?(?:current\s+)?(?:workspace\s+)?context|"
    r"what(?:'s|\s+is)\s+(?:on\s+)?my\s+screen|"
    r"show\s+(?:current\s+)?(?:workspace|screen)\s+(?:context|awareness|state))[\?\.!]?$",
    re.I,
)
_SA_ACTIVE_PROJECT_RE = re.compile(
    r"^(?:show\s+)?active\s+project[\?\.!]?$|"
    r"^what\s+project\s+am\s+I\s+(?:working\s+on|in|on)[\?\.!]?$|"
    r"^(?:show\s+)?current\s+project[\?\.!]?$",
    re.I,
)
_SA_ACTIVE_FILE_RE = re.compile(
    r"^(?:show\s+)?active\s+file[\?\.!]?$|"
    r"^what\s+file\s+am\s+I\s+(?:editing|working\s+on|in)[\?\.!]?$|"
    r"^(?:show\s+)?current\s+file[\?\.!]?$",
    re.I,
)
_SA_ACTIVE_APP_RE = re.compile(
    r"^(?:show\s+)?active\s+(?:application|app)[\?\.!]?$|"
    r"^what\s+(?:app|application)\s+am\s+I\s+(?:using|in|on)[\?\.!]?$|"
    r"^(?:show\s+)?current\s+(?:application|app)[\?\.!]?$|"
    r"^what\s+(?:application|app)\s+is\s+(?:open|active|running)[\?\.!]?$",
    re.I,
)

# ── Session Continuity regexes (Phase 16B) ──────────────────────────────────

_SC_RECENT_SESSIONS_RE = re.compile(
    r"^(?:show\s+)?(?:my\s+)?(?:recent\s+)?sessions[\?\.!]?$|"
    r"^(?:show|list|display)\s+(?:recent\s+)?(?:session\s+)?history[\?\.!]?$|"
    r"^show\s+(?:my\s+)?(?:recent\s+)?sessions[\?\.!]?$|"
    r"^(?:show|list)\s+project\s+sessions[\?\.!]?$",
    re.I,
)
_SC_LAST_SESSION_RE = re.compile(
    r"^(?:show\s+)?(?:my\s+)?last\s+session[\?\.!]?$|"
    r"^what\s+was\s+I\s+(?:doing|working\s+on)(?:\s+(?:last\s+night|yesterday|earlier|before))[\?\.!]?$|"
    r"^what\s+was\s+I\s+(?:doing|working\s+on)[\?\.!]?$",
    re.I,
)
_SC_CONTINUE_RE = re.compile(
    r"^(?:continue|resume)\s+(?P<project>[a-zA-Z0-9_\-\s]{2,40})(?:\s+work)?[\?\.!]?$|"
    r"^continue\s+(?:working\s+on\s+)?(?:project\s+)?(?P<project2>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)
_SC_RESTORE_RE = re.compile(
    r"^(?:open|restore|launch)\s+(?P<project>[a-zA-Z0-9_\-\s]{2,40})\s+workspace[\?\.!]?$|"
    r"^restore\s+(?:yesterday(?:'s)?|last)\s+(?:session|workspace)[\?\.!]?$",
    re.I,
)
_SC_ACCOMPLISHMENTS_RE = re.compile(
    r"^(?:show\s+)?what\s+(?:I|did\s+I)\s+(?:accomplish|do|work\s+on)\s*(?:ed)?\s*(?:today|this\s+week|yesterday|recently)[\?\.!]?$|"
    r"^what\s+did\s+I\s+(?:do|work\s+on|accomplish)\s+(?:today|this\s+week|yesterday|recently)[\?\.!]?$|"
    r"^show\s+(?:today(?:'s)?|recent)\s+(?:activity|accomplishments?|work)[\?\.!]?$",
    re.I,
)

# ── Engineering Planner regexes (Phase 15B) ─────────────────────────────────

_EP_PLAN_RE = re.compile(
    r"^(?:I\s+want\s+to\s+build|plan|design|create\s+a?\s*plan\s+for)\s+(?:a\s+)?(?P<desc>[a-zA-Z0-9_\-\s]{2,60})[\?\.!]?$",
    re.I,
)
_EP_BOM_RE = re.compile(
    r"^(?:generate|create|show|make|get)\s+(?:a\s+)?(?:bom|bill\s+of\s+materials)\s+(?:for\s+)?(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^(?:bom|bill\s+of\s+materials)\s+(?:for\s+)?(?P<project2>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)
_EP_ROADMAP_RE = re.compile(
    r"^(?:generate|create|make)\s+(?:a\s+)?roadmap\s+(?:for\s+)?(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^(?:build\s+plan|project\s+plan)\s+(?:for\s+)?(?P<project2>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)
_EP_GAP_RE = re.compile(
    r"^what\s+am\s+I\s+missing\s+for\s+(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^(?:gap\s+analysis|what\s+do\s+I\s+(?:still\s+)?need)\s+for\s+(?P<project2>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^(?:show\s+)?(?:project\s+)?gap\s+analysis\s+(?:for\s+)?(?P<project3>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)
_EP_CAN_BUILD_RE = re.compile(
    r"^can\s+I\s+build\s+(?:a\s+)?(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^do\s+I\s+have\s+(?:enough|what\s+I\s+need|everything)\s+(?:for|to\s+build)\s+(?:a\s+)?(?P<project2>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)
_EP_WHAT_BUILD_RE = re.compile(
    r"^what\s+can\s+I\s+build\s+(?:with\s+(?:my\s+)?(?:current\s+)?inventory|today|right\s+now)[\?\.!]?$|"
    r"^what\s+projects?\s+can\s+I\s+(?:make|build)\s+with\s+(?:what\s+I\s+have|my\s+(?:current\s+)?(?:parts?|inventory|components?))[\?\.!]?$|"
    r"^suggest\s+projects?\s+(?:from|based\s+on)\s+(?:my\s+)?(?:parts?|inventory)[\?\.!]?$",
    re.I,
)
_EP_ARCH_RE = re.compile(
    r"^(?:show\s+)?(?:project\s+)?architecture\s+(?:for\s+)?(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^(?:show|display|get)\s+(?:the\s+)?architecture\s+(?:for|of)\s+(?P<project2>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)
_EP_PROCURE_RE = re.compile(
    r"^(?:generate|create|show)\s+(?:a\s+)?(?:procurement\s+plan|purchasing\s+list|buy\s+list)\s+(?:for\s+)?(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^what\s+do\s+I\s+need\s+to\s+buy\s+for\s+(?P<project2>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)
_EP_CREATE_RE = re.compile(
    r"^create\s+(?:a\s+)?(?:new\s+)?project\s+(?P<name>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^create\s+(?P<name2>[a-zA-Z0-9_\-\s]{2,40})\s+project[\?\.!]?$",
    re.I,
)
_EP_TEMPLATES_RE = re.compile(
    r"^(?:list|show|display)\s+(?:project\s+)?templates[\?\.!]?$|"
    r"^(?:what|which)\s+templates?\s+(?:are\s+)?(?:available|exist)[\?\.!]?$",
    re.I,
)

# Board alias for planner
_PLANNER_BOARD_ALIAS = re.compile(
    r"\bplanner\b|\bengineering\s*planner\b|\bproject\s*planner\b",
    re.I,
)


def _regex_planner(query: str) -> dict | None:
    """Match engineering planner commands (Phase 15B)."""
    text = query.strip()

    if _EP_TEMPLATES_RE.match(text):
        return {"action": "call_tool", "name": "list_project_templates", "args": {}}

    if _EP_WHAT_BUILD_RE.match(text):
        return {"action": "call_tool", "name": "planner_what_can_i_build", "args": {}}

    m = _EP_CAN_BUILD_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or "").strip()
        return {"action": "call_tool", "name": "planner_can_i_build", "args": {"project": project}}

    m = _EP_BOM_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or "").strip()
        return {"action": "call_tool", "name": "generate_bom", "args": {"project": project}}

    m = _EP_ROADMAP_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or "").strip()
        return {"action": "call_tool", "name": "generate_roadmap_plan", "args": {"project": project}}

    m = _EP_GAP_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or m.group("project3") or "").strip()
        return {"action": "call_tool", "name": "planner_gap_analysis", "args": {"project": project}}

    m = _EP_ARCH_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or "").strip()
        return {"action": "call_tool", "name": "planner_architecture", "args": {"project": project}}

    m = _EP_PROCURE_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or "").strip()
        return {"action": "call_tool", "name": "planner_procurement", "args": {"project": project}}

    m = _EP_CREATE_RE.match(text)
    if m:
        name = (m.group("name") or m.group("name2") or "").strip()
        return {"action": "call_tool", "name": "planner_create_project", "args": {"name": name, "template_id": ""}}

    # "plan X" / "design X" / "I want to build X" — must be last (broadest)
    m = _EP_PLAN_RE.match(text)
    if m:
        desc = m.group("desc").strip()
        return {"action": "call_tool", "name": "plan_project", "args": {"description": desc}}

    return None


# ── Workflow regexes (Phase 17B) ────────────────────────────────────────────

_WF_SHOW_RE = re.compile(
    r"^(?:show|list|display|get)?\s*(?:all\s+)?workflows?[\?\.!]?$|"
    r"^(?:show|list)\s+(?:all\s+)?(?:change\s+)?(?:requests?|changes?)[\?\.!]?$",
    re.I,
)
_WF_PENDING_RE = re.compile(
    r"^(?:show|list|display)?\s*(?:pending|open|waiting)\s+(?:workflows?|approvals?|changes?)[\?\.!]?$|"
    r"^(?:show|list)\s+(?:pending|waiting)\s+(?:change\s+)?(?:requests?)[\?\.!]?$|"
    r"^(?:pending|waiting)\s+(?:workflows?|approvals?|changes?)[\?\.!]?$",
    re.I,
)
_WF_HISTORY_RE = re.compile(
    r"^(?:show|list|display)?\s*(?:workflow|change)\s+history[\?\.!]?$|"
    r"^(?:show|list)\s+(?:completed|past|resolved)\s+workflows?[\?\.!]?$",
    re.I,
)
_WF_APPROVE_RE = re.compile(
    r"^approve\s+(?:workflow\s+)?(?P<code>WF-\d+)[\s\.!]*$",
    re.I,
)
_WF_REJECT_RE = re.compile(
    r"^reject\s+(?:workflow\s+)?(?P<code>WF-\d+)[\s\.!]*$",
    re.I,
)
_WF_CANCEL_RE = re.compile(
    r"^cancel\s+(?:workflow\s+)?(?P<code>WF-\d+)[\s\.!]*$",
    re.I,
)
_WF_APPROVE_ALL_RE = re.compile(
    r"^approve\s+all\s+(?:pending\s+)?(?:workflows?|changes?)[\s\.!]*$|"
    r"^approve\s+all\s+(?:low\s+risk)[\s\.!]*$",
    re.I,
)
_WF_REJECT_ALL_RE = re.compile(
    r"^reject\s+all\s+(?:pending\s+)?(?:workflows?|changes?)[\s\.!]*$",
    re.I,
)
_WF_DETAIL_RE = re.compile(
    r"^(?:show|display|get)\s+(?:workflow\s+)?(?P<code>WF-\d+)[\s\.!]*$",
    re.I,
)


def _regex_workflow(query: str) -> dict | None:
    """Match workflow management commands (Phase 17B)."""
    text = query.strip()

    if _WF_SHOW_RE.match(text):
        return {"action": "call_tool", "name": "list_workflows", "args": {}}

    if _WF_PENDING_RE.match(text):
        return {"action": "call_tool", "name": "show_pending_workflows", "args": {}}

    if _WF_HISTORY_RE.match(text):
        return {"action": "call_tool", "name": "show_workflow_history", "args": {}}

    m = _WF_APPROVE_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "approve_workflow", "args": {"code": m.group("code")}}

    m = _WF_REJECT_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "reject_workflow", "args": {"code": m.group("code")}}

    m = _WF_CANCEL_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "cancel_workflow", "args": {"code": m.group("code")}}

    if _WF_APPROVE_ALL_RE.match(text):
        max_risk = ""
        if "low risk" in text.lower():
            max_risk = "low"
        return {"action": "call_tool", "name": "approve_all_workflows", "args": {"max_risk": max_risk}}

    if _WF_REJECT_ALL_RE.match(text):
        return {"action": "call_tool", "name": "reject_all_workflows", "args": {}}

    m = _WF_DETAIL_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "get_workflow", "args": {"code": m.group("code")}}

    return None


# ── Brain63 Steward regexes (Phase 18B) ────────────────────────────────────

_B63_HEALTH_RE = re.compile(
    r"^(?:show|display|get)?\s*(?:brain\s*63|b63|documentation)\s+health[\?\.!]?$|"
    r"^(?:show|get)\s+brain\s*63\s+health[\?\.!]?$|"
    r"^brain\s*63\s+health[\?\.!]?$",
    re.I,
)
_B63_COVERAGE_RE = re.compile(
    r"^(?:show|display|get)?\s*(?:project\s+)?(?:documentation|doc|brain\s*63)\s+coverage[\?\.!]?$|"
    r"^(?:show|display)\s+(?:project\s+)?documentation\s+coverage[\?\.!]?$|"
    r"^(?:show|display)\s+(?P<project>[a-zA-Z0-9_\-]{2,30})\s+(?:documentation|doc)\s+coverage[\?\.!]?$",
    re.I,
)
_B63_DRAFTS_RE = re.compile(
    r"^(?:show|list|display)?\s*(?:pending\s+)?(?:brain\s*63|b63|documentation)\s+(?:drafts?|updates?)[\?\.!]?$|"
    r"^(?:show|list)\s+pending\s+documentation\s+updates?[\?\.!]?$",
    re.I,
)
_B63_ROADMAP_UPDATE_RE = re.compile(
    r"^update\s+(?P<project>[a-zA-Z0-9_\-\s]{2,30})\s+roadmap[\?\.!]?$|"
    r"^update\s+roadmap\s+(?:for\s+)?(?P<project2>[a-zA-Z0-9_\-\s]{2,30})[\?\.!]?$|"
    r"^(?:move|add|change)\s+(?P<change>.+?)\s+(?:in|on|for)\s+(?P<project3>[a-zA-Z0-9_\-\s]{2,30})\s+roadmap[\?\.!]?$",
    re.I,
)
_B63_STATUS_UPDATE_RE = re.compile(
    r"^(?:mark|set)\s+(?P<change>.+?)\s+(?:complete|done|finished|in\s+progress|started)[\?\.!]?$",
    re.I,
)


def _regex_brain_steward(query: str) -> dict | None:
    """Match Brain63 steward commands (Phase 18B)."""
    text = query.strip()

    if _B63_HEALTH_RE.match(text):
        return {"action": "call_tool", "name": "show_brain63_health", "args": {}}

    m = _B63_COVERAGE_RE.match(text)
    if m:
        project = ""
        if m.groupdict().get("project"):
            project = m.group("project").strip()
        return {"action": "call_tool", "name": "show_brain63_coverage", "args": {"project": project}}

    if _B63_DRAFTS_RE.match(text):
        return {"action": "call_tool", "name": "show_brain63_drafts", "args": {}}

    m = _B63_ROADMAP_UPDATE_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or m.group("project3") or "").strip()
        change = ""
        if m.groupdict().get("change"):
            change = m.group("change").strip()
        return {"action": "call_tool", "name": "update_brain63_roadmap",
                "args": {"project": project, "change": change}}

    return None


# ── Memory Provider regexes (Phase 18A) ────────────────────────────────────

_MP_PROVIDERS_RE = re.compile(
    r"^(?:show|list|display)?\s*(?:memory\s+)?providers?[\?\.!]?$|"
    r"^(?:show|list)\s+memory\s+providers?[\?\.!]?$|"
    r"^memory\s+providers?[\?\.!]?$",
    re.I,
)
_MP_HEALTH_RE = re.compile(
    r"^(?:show|display|get)?\s*(?:memory\s+)?(?:provider\s+)?(?:health|status)[\?\.!]?$|"
    r"^(?:show|get)\s+memory\s+health[\?\.!]?$|"
    r"^memory\s+health[\?\.!]?$|"
    r"^(?:show|get)\s+provider\s+status[\?\.!]?$",
    re.I,
)
_MP_TIMELINE_RE = re.compile(
    r"^(?:show|display)?\s*(?:memory\s+)?timeline[\?\.!]?$|"
    r"^(?:show|display)\s+(?:memory\s+)?timeline\s+(?:for\s+)?(?P<project>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$|"
    r"^(?:show|display)\s+(?P<project2>[a-zA-Z0-9_\-]{2,30})\s+(?:memory\s+)?timeline[\?\.!]?$|"
    r"^(?:show|display)\s+engineering\s+history[\?\.!]?$",
    re.I,
)
_MP_RELATIONSHIPS_RE = re.compile(
    r"^(?:show|display)?\s*(?:memory\s+)?(?:related\s+memories|relationships?|memory\s+graph)[\?\.!]?$|"
    r"^(?:show|display)\s+related\s+(?:memories|decisions?|entries)[\?\.!]?$|"
    r"^(?:show|display)\s+(?:related\s+)?(?:memories|decisions?)\s+(?:for\s+)?(?P<entity>[a-zA-Z0-9_\-\s]{2,40})[\?\.!]?$",
    re.I,
)


def _regex_memory_provider(query: str) -> dict | None:
    """Match memory provider framework commands (Phase 18A)."""
    text = query.strip()

    if _MP_PROVIDERS_RE.match(text):
        return {"action": "call_tool", "name": "show_memory_providers", "args": {}}

    if _MP_HEALTH_RE.match(text):
        return {"action": "call_tool", "name": "show_memory_health", "args": {}}

    m = _MP_TIMELINE_RE.match(text)
    if m:
        project = ""
        if m.lastgroup and m.group(m.lastgroup):
            project = m.group(m.lastgroup).strip()
        elif m.groupdict().get("project"):
            project = m.group("project").strip()
        elif m.groupdict().get("project2"):
            project = m.group("project2").strip()
        return {"action": "call_tool", "name": "show_memory_timeline", "args": {"project": project}}

    m = _MP_RELATIONSHIPS_RE.match(text)
    if m:
        entity = ""
        if m.groupdict().get("entity"):
            entity = m.group("entity").strip()
        return {"action": "call_tool", "name": "show_memory_relationships", "args": {"entity": entity}}

    return None


def _regex_workspace(query: str) -> dict | None:
    """Match workspace digital twin commands."""
    text = query.strip()

    # Rich output intent — must be checked first (catches "detailed shopping list for X" etc.)
    from backend.app.services.rich_output_service import detect_rich_intent
    rich = detect_rich_intent(text)
    if rich:
        return {"action": "call_tool", "name": "rich_output",
                "args": {"project": rich.get("project") or "", "render_type": rich["render_type"]}}

    # Screen Awareness (Phase 16A)
    if _SA_CONTEXT_RE.match(text):
        return {"action": "call_tool", "name": "show_workspace_context", "args": {}}
    if _SA_ACTIVE_PROJECT_RE.match(text):
        return {"action": "call_tool", "name": "show_active_project", "args": {}}
    if _SA_ACTIVE_FILE_RE.match(text):
        return {"action": "call_tool", "name": "show_active_file", "args": {}}
    if _SA_ACTIVE_APP_RE.match(text):
        return {"action": "call_tool", "name": "show_active_application", "args": {}}

    # Session Continuity (Phase 16B)
    if _SC_RECENT_SESSIONS_RE.match(text):
        return {"action": "call_tool", "name": "show_recent_sessions", "args": {}}
    if _SC_LAST_SESSION_RE.match(text):
        return {"action": "call_tool", "name": "show_last_session", "args": {"project": ""}}
    if _SC_ACCOMPLISHMENTS_RE.match(text):
        return {"action": "call_tool", "name": "show_accomplishments", "args": {"hours": 24}}
    m = _SC_RESTORE_RE.match(text)
    if m:
        project = (m.group("project") or "").strip()
        if not project or project.lower() in ("yesterday", "last"):
            return {"action": "call_tool", "name": "restore_workspace", "args": {"project": ""}}
        return {"action": "call_tool", "name": "restore_workspace", "args": {"project": project}}
    m = _SC_CONTINUE_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or "").strip()
        return {"action": "call_tool", "name": "continue_project", "args": {"project": project}}

    if _WS_STATUS_RE.match(text):
        return {"action": "call_tool", "name": "workspace_status", "args": {}}

    if _WS_PRIORITIES_RE.match(text):
        return {"action": "call_tool", "name": "workspace_priorities", "args": {}}

    if _WS_DAILY_BRIEFING_RE.match(text):
        return {"action": "call_tool", "name": "daily_briefing", "args": {}}

    if _WS_BLOCKED_RE.match(text):
        return {"action": "call_tool", "name": "show_blocked_projects", "args": {}}

    if _WS_READY_RE.match(text):
        return {"action": "call_tool", "name": "show_ready_projects", "args": {}}

    if _WS_WORK_ON_RE.match(text):
        return {"action": "call_tool", "name": "what_should_i_work_on", "args": {}}

    if _WS_ORDER_RE.match(text):
        return {"action": "call_tool", "name": "what_to_order", "args": {}}

    if _WS_CLOSEST_RE.match(text):
        return {"action": "call_tool", "name": "closest_to_completion", "args": {}}

    # Per-project order reconciliation
    m = _WS_PROJECT_ORDER_RE.match(text)
    if m:
        project = next((g for g in [m.group("project"), m.group("project2"), m.group("project3"), m.group("project4")] if g), "").strip()
        return {"action": "call_tool", "name": "reconcile_project_orders", "args": {"project": project}}

    # "what can I work on for X"
    m = _WS_PROJECT_WORK_RE.match(text)
    if m:
        project = m.group("project").strip()
        return {"action": "call_tool", "name": "project_briefing", "args": {"project": project}}

    # "I already bought X for Y" / "mark X as acquired for Y"
    m = _WS_MARK_ACQUIRED_V2_RE.match(text)
    if m:
        verb = m.group("verb").lower()
        items_raw = m.group("items").strip()
        project = m.group("project").strip()
        state = {"bought": "owned", "acquired": "owned", "have": "owned", "got": "owned",
                 "received": "received", "ordered": "ordered"}.get(verb, "owned")
        return {"action": "call_tool", "name": "mark_item_acquired",
                "args": {"project": project, "items": items_raw, "state": state}}

    m = _WS_MARK_ACQUIRED_RE.match(text)
    if m:
        item1 = (m.group("item1") or "").strip()
        project = (m.group("project") or "").strip()
        if item1:
            return {"action": "call_tool", "name": "mark_item_acquired",
                    "args": {"project": project, "items": item1, "state": "owned"}}

    return None


# ── Observability regexes (Phase 13C) ────────────────────────────────────────
_OBS_RECENT_RE = re.compile(
    r"^(?:show|list|display|get)?\s*"
    r"(?:recent|last|latest|my|what(?:\s+did\s+(?:you|silvia)\s+do)?)"
    r"\s*(?:actions?|executions?|commands?|activity|history|things?(?:\s+you\s+did)?)?"
    r"[\?\.!]?$",
    re.I,
)
_OBS_ACTIONS_NODE_RE = re.compile(
    r"^(?:show|list|display)?\s*"
    r"(?:actions?|executions?|activity|history|commands?)"
    r"\s+(?:on|for|from|at)\s+(?P<node>\S+)[\?\.!]?$",
    re.I,
)
_OBS_FAILURES_RE = re.compile(
    r"^(?:show|list|display|get)?\s*"
    r"(?:failures?|errors?|failed\s+(?:actions?|commands?|executions?)|what\s+failed)[\?\.!]?$",
    re.I,
)
_OBS_PLANNER_RE = re.compile(
    r"^(?:show|list|display|get)?\s*"
    r"(?:planner|planning|router|routing)?\s*"
    r"(?:decisions?|trace|log|choices?|reasoning|why\s+did\s+(?:you|silvia))[\?\.!]?$",
    re.I,
)
_OBS_HEALTH_RE = re.compile(
    r"^(?:show|get|display|check)?\s*"
    r"(?:system|capability|service|silvia)?\s*"
    r"(?:health|reliability|success\s+rate|uptime|metrics|stats|statistics)[\?\.!]?$",
    re.I,
)
_OBS_WHY_RE = re.compile(
    r"^(?:why|what|explain|tell\s+me\s+about)"
    r"\s+(?:did\s+(?:you|silvia)\s+do\s+(?:that|it)|just\s+happened|was\s+that|happened)[\?\.!]?$",
    re.I,
)


# ── Desktop control regexes (Phase 11) ───────────────────────────────────────

# Known location names (aliases included for regex matching)
_KNOWN_LOCS_PAT = (
    r"(?:cmd[\s\-]?ctr|command\s+center|brain[\s\-]?63|drone[\s\-]?hive|koi|magi|"
    r"downloads?|documents?|desktop|github|projects?|repos?|university|internship|portfolio)"
)

# Known app names (and aliases)
_KNOWN_APPS_PAT = (
    r"(?:vs[\s\-]?code|visual\s+studio\s+code|vscode|fusion[\s\-]?360|fusion|"
    r"kicad|chrome|google\s+chrome|browser|spotify|blender|prusa[\s\-]?slicer|cura|"
    r"notepad|explorer|file\s+explorer)"
)

# Known file extensions for direct regex routing
_FILE_EXT_PAT = (
    r"(?:stl|obj|pcb|kicad|kicad[\s_]pro|kicad[\s_]pcb|sch|kicad[\s_]sch|pdf|py|python|ipynb|md|txt|json|"
    r"yaml|yml|cpp|hpp|h|ino|svg|dxf|step|stp|fcstd|f3d|zip|csv)"
)

# ── Phase 11F: URL / modifier / preference patterns ───────────────────────────
# Explicit URL or bare domain — always open in browser
_DESK_OPEN_URL = re.compile(
    r"^(?:open|go\s+to|visit|browse|navigate\s+to)\s+"
    r"(?P<url>(?:https?://|www\.)[^\s]+|[a-z0-9][-a-z0-9]*\.[a-z]{2,}(?:/[^\s]*)?)"
    r"\s*[\?\.!]?$",
    re.I,
)
# "open X web/site/browser" — explicit web modifier
_DESK_OPEN_WEB_MOD = re.compile(
    r"^(?:open|go\s+to|visit|launch)\s+(?P<target>[a-z0-9][a-z0-9\s\-_\.&+]*?)"
    r"\s+(?:web(?:site|page)?|site|browser|online)\s*[\?\.!]?$",
    re.I,
)
# "open X app/desktop" — explicit app modifier
_DESK_OPEN_APP_MOD = re.compile(
    r"^(?:open|launch|start)\s+(?P<target>[a-z0-9][a-z0-9\s\-_\.&+]*?)"
    r"\s+(?:desktop|app|application|program)\s*[\?\.!]?$",
    re.I,
)
# "open X folder/directory" — explicit folder modifier
_DESK_OPEN_FOLDER_MOD = re.compile(
    r"^(?:open|show|navigate\s+to|reveal)\s+(?:the\s+)?(?P<target>[a-z0-9][a-z0-9\s\-_\.&+]*?)"
    r"\s+(?:folder|directory|dir|repo|repository)\s*[\?\.!]?$",
    re.I,
)
# Set launch preference — "prefer github web"
_DESK_SET_PREF = re.compile(
    r"^(?:prefer|set\s+preference\s+(?:for|of)|default)\s+"
    r"(?P<target>[a-z0-9][a-z0-9\s\-_\.&+]*?)\s+(?:to\s+)?(?P<pref>web|app|desktop|folder)\s*[\?\.!]?$",
    re.I,
)
# Show target info — "show target github"
_DESK_SHOW_TARGET = re.compile(
    r"^show\s+(?:launch\s+)?target(?:s?)?\s+(?:for\s+)?(?P<target>[a-z0-9][a-z0-9\s\-_\.&+]*?)\s*[\?\.!]?$",
    re.I,
)
# List all preferences — "show launch preferences"
_DESK_LIST_PREFS = re.compile(
    r"^(?:show|list)\s+(?:launch\s+)?preferences?\s*[\?\.!]?$",
    re.I,
)

_DESK_OPEN_LOC = re.compile(
    rf"^(?:show|navigate\s+to|go\s+to|reveal|browse)\s+(?:the\s+)?(?P<name>{_KNOWN_LOCS_PAT})"
    rf"(?:\s+(?:folder|directory|project|repo|dir|repository))?\s*[\?\.!]?$",
    re.I,
)
_DESK_WHERE = re.compile(
    rf"^where\s+(?:is|are)\s+(?:the\s+)?(?P<name>{_KNOWN_LOCS_PAT})\s*[\?\.!]?$",
    re.I,
)
_DESK_LIST_LOCS = re.compile(
    r"^(?:list|show)\s+(?:(?:trusted\s+)?(?:locations?|folders?|directories?|places?))\s*[\?\.!]?$",
    re.I,
)
_DESK_OPEN_APP = re.compile(
    rf"^(?:open|launch|start|run)\s+(?:the\s+)?(?P<app>{_KNOWN_APPS_PAT})"
    rf"(?:\s+(?:app|application|program))?\s*[\?\.!]?$",
    re.I,
)
_DESK_OPEN_APP_GENERIC = re.compile(
    r"^(?:open|launch|start|run)\s+(?:the\s+)?(?P<app>[a-z0-9][a-z0-9\s\-_\.&+]{1,80}?)"
    r"(?:\s+(?:app|application|program))?\s*[\?\.!]?$",
    re.I,
)
_DESK_SCAN_APPS = re.compile(
    r"^(?:scan|rescan|discover|refresh)\s+(?:installed\s+)?(?:apps?|applications?|programs?)\s*[\?\.!]?$",
    re.I,
)
_DESK_SHOW_APP = re.compile(
    r"^(?:show|inspect|find|lookup)\s+(?:the\s+)?app\s+(?P<app>[a-z0-9][a-z0-9\s\-_\.&+]{1,80}?)\s*[\?\.!]?$",
    re.I,
)
_DESK_LIST_APPS = re.compile(
    r"^(?:list|show)\s+(?:(?:installed\s+|my\s+)?(?:apps?|applications?|programs?))"
    r"(?:\s+(?:i\s+have|available|registered))?\s*[\?\.!]?$",
    re.I,
)
_DESK_WHAT_LAUNCH = re.compile(
    r"^what\s+(?:apps?|applications?|programs?)\s+(?:can\s+you|do\s+you|are\s+you\s+able\s+to)\s+(?:open|launch|start)[\?\.!]?$",
    re.I,
)
_DESK_FIND_EXT = re.compile(
    rf"^(?:find|show|list|search\s+(?:for\s+)?)\s+(?:all\s+|latest\s+|newest\s+)?\.?(?P<ext>{_FILE_EXT_PAT})\s+"
    rf"(?:files?|scripts?|documents?|projects?|designs?)(?:\s+in\s+(?P<loc>[a-z0-9\s\-_]+?))?\s*[\?\.!]?$",
    re.I,
)
_DESK_FIND_QUERY = re.compile(
    r"^(?:find|search\s+(?:for\s+)?|locate)\s+(?:files?\s+)?(?:related\s+to|about|named|called|containing|with|for)\s+"
    r"(?P<query>[a-z0-9\s\-_\.]+?)(?:\s+(?:in|on|from)\s+(?P<loc>[a-z0-9\s\-_]+?))?\s*[\?\.!]?$",
    re.I,
)
_DESK_SEARCH_LOC = re.compile(
    rf"^(?:search|browse|list|show)\s+(?P<loc>{_KNOWN_LOCS_PAT})\s+"
    rf"(?:files?|folder|contents?|projects?)[\?\.!]?$",
    re.I,
)
_DESK_RECENT = re.compile(
    rf"^(?:show|list|find)\s+(?:the\s+)?(?:latest|newest|recent)\s+files?"
    rf"(?:\s+(?:in|from)\s+(?P<loc>[a-z0-9\s\-_]+?))?\s*[\?\.!]?$",
    re.I,
)
_DESK_OPEN_LATEST_KICAD_PROJECT = re.compile(
    r"^(?:open|launch|start)\s+(?:the\s+)?(?:latest|newest)\s+kicad\s+projects?\s*[\?\.!]?$",
    re.I,
)
_DESK_OPEN_KICAD_PROJECT_PREFIX = re.compile(
    r"^(?:open|launch|start)\s+kicad\s+projects?\s+(?P<query>[a-z0-9\s\-_\.]+?)\s*[\?\.!]?$",
    re.I,
)
_DESK_OPEN_KICAD_PROJECT_SUFFIX = re.compile(
    r"^(?:open|launch|start)\s+(?P<query>[a-z0-9\s\-_\.]+?)\s+kicad\s+projects?\s*[\?\.!]?$",
    re.I,
)
_DESK_OPEN_PROJECT = re.compile(
    r"^(?:open|launch|start)\s+(?P<query>[a-z0-9][a-z0-9\s\-_\.]*?)\s+projects?\s*[\?\.!]?$",
    re.I,
)

# ── Lifecycle regexes (Phase 11D) ─────────────────────────────────────────────
# close/quit/exit — "close Bambu Studio", "quit OBS", "exit Fusion"
_DESK_CLOSE_APP = re.compile(
    r"^(?:close|quit|exit)\s+(?:the\s+)?(?P<app>[a-z0-9][a-z0-9\s\-_\.&+]{1,80}?)"
    r"(?:\s+(?:app|application|program))?\s*[\?\.!]?$",
    re.I,
)
# app status — "is fusion running", "app status obs", "is kicad open"
_DESK_APP_STATUS = re.compile(
    r"^(?:"
    r"is\s+(?P<app1>[a-z0-9][a-z0-9\s\-_\.&+]{1,80}?)\s+(?:running|open|active|launched|on)"
    r"|(?:app(?:lication)?\s+)?status\s+(?:of\s+)?(?P<app2>[a-z0-9][a-z0-9\s\-_\.&+]{1,80}?)"
    r"|check\s+if\s+(?P<app3>[a-z0-9][a-z0-9\s\-_\.&+]{1,80}?)\s+is\s+(?:running|open|active)"
    r")\s*[\?\.!]?$",
    re.I,
)
# show_app_runtime — "show app runtime Spotify", "show runtime for OBS"
_DESK_APP_RUNTIME = re.compile(
    r"^(?:show|display|get)\s+(?:app(?:lication)?\s+)?runtime\s+(?:for\s+)?(?P<app>[a-z0-9][a-z0-9\s\-_\.&+]{1,80}?)[\?\.!]?$"
    r"|^(?:show|display|get)\s+(?P<app2>[a-z0-9][a-z0-9\s\-_\.&+]{1,80}?)\s+runtime[\?\.!]?$",
    re.I,
)
# list running — "show running apps", "what apps are running", "show launched apps"
_DESK_LIST_RUNNING = re.compile(
    r"^(?:"
    r"(?:show|list)\s+(?:(?:all|my)\s+)?(?:running|active|launched|open)\s+(?:apps?|applications?|programs?)"
    r"|what\s+(?:apps?|applications?|programs?)\s+(?:are\s+)?(?:running|active|open|launched)"
    r"|(?:show|list)\s+launched\s+(?:apps?|applications?)"
    r")[\?\.!]?$",
    re.I,
)


def _regex_desktop(query: str) -> dict | None:
    """Match desktop control patterns — Phase 11."""
    text = query.strip()

    if _DESK_OPEN_LATEST_KICAD_PROJECT.match(text):
        logger.info("INTENT: open_project ROUTE: file_open APPLICATION: KiCad Query=%r Latest=True", query)
        return {"action": "call_tool", "name": "open_kicad_project", "args": {"query": "", "latest": True}}

    m = _DESK_OPEN_KICAD_PROJECT_PREFIX.match(text)
    if m:
        project_query = m.group("query").strip()
        logger.info("INTENT: open_project ROUTE: file_open APPLICATION: KiCad Query=%r", project_query)
        return {"action": "call_tool", "name": "open_kicad_project", "args": {"query": project_query, "latest": False}}

    # ── Phase 11F: URL / modifier / preference — HIGHEST PRIORITY ─────────────
    m = _DESK_OPEN_URL.match(text)
    if m:
        url = m.group("url").strip()
        logger.info("INTENT: open_url ROUTE: explicit_url URL=%r", url)
        return {"action": "call_tool", "name": "open_url", "args": {"url": url}}

    m = _DESK_OPEN_WEB_MOD.match(text)
    if m:
        target = m.group("target").strip()
        logger.info("INTENT: open_target ROUTE: web_modifier Target=%r", target)
        return {"action": "call_tool", "name": "open_target", "args": {"target": target, "modifier": "web"}}

    m = _DESK_OPEN_APP_MOD.match(text)
    if m:
        target = m.group("target").strip()
        logger.info("INTENT: open_target ROUTE: app_modifier Target=%r", target)
        return {"action": "call_tool", "name": "open_target", "args": {"target": target, "modifier": "app"}}

    m = _DESK_OPEN_FOLDER_MOD.match(text)
    if m:
        target = m.group("target").strip()
        logger.info("INTENT: open_target ROUTE: folder_modifier Target=%r", target)
        return {"action": "call_tool", "name": "open_target", "args": {"target": target, "modifier": "folder"}}

    m = _DESK_SET_PREF.match(text)
    if m:
        target = m.group("target").strip()
        pref = m.group("pref").strip()
        logger.info("INTENT: set_launch_preference Target=%r Pref=%r", target, pref)
        return {"action": "call_tool", "name": "set_launch_preference", "args": {"target": target, "preferred": pref}}

    if _DESK_LIST_PREFS.match(text):
        return {"action": "call_tool", "name": "list_launch_preferences", "args": {}}

    m = _DESK_SHOW_TARGET.match(text)
    if m:
        target = m.group("target").strip()
        return {"action": "call_tool", "name": "show_launch_target", "args": {"target": target}}
    # ── End Phase 11F priority block ──────────────────────────────────────────

    # ── KiCad project patterns ────────────────────────────────────────────────
    m = _DESK_OPEN_KICAD_PROJECT_SUFFIX.match(text)
    if m:
        project_query = m.group("query").strip()
        logger.info("INTENT: open_project ROUTE: file_open APPLICATION: KiCad Query=%r", project_query)
        return {"action": "call_tool", "name": "open_kicad_project", "args": {"query": project_query, "latest": False}}

    m = _DESK_OPEN_PROJECT.match(text)
    if m:
        project_query = m.group("query").strip()
        logger.info("INTENT: open_project ROUTE: file_open APPLICATION: KiCad Query=%r", project_query)
        return {"action": "call_tool", "name": "open_kicad_project", "args": {"query": project_query, "latest": False}}

    # ── Unambiguous known apps — still use open_target for preference awareness ─
    m = _DESK_OPEN_APP.match(text)
    if m:
        app_name = m.group("app").strip()
        logger.info("INTENT: open_target ROUTE: known_app Target=%r", app_name)
        return {"action": "call_tool", "name": "open_target", "args": {"target": app_name, "modifier": ""}}

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    m = _DESK_APP_RUNTIME.match(text)
    if m:
        app_name = (m.group("app") or m.group("app2") or "").strip()
        logger.info("INTENT: show_app_runtime Application=%r", app_name)
        return {"action": "call_tool", "name": "show_app_runtime", "args": {"name": app_name}}

    if _DESK_LIST_RUNNING.match(text):
        return {"action": "call_tool", "name": "list_running_apps", "args": {}}

    m = _DESK_APP_STATUS.match(text)
    if m:
        app_name = (m.group("app1") or m.group("app2") or m.group("app3") or "").strip()
        logger.info("INTENT: app_status Application=%r", app_name)
        return {"action": "call_tool", "name": "app_status", "args": {"name": app_name}}

    m = _DESK_CLOSE_APP.match(text)
    if m:
        app_name = m.group("app").strip()
        logger.info("INTENT: close_app Application=%r", app_name)
        return {"action": "call_tool", "name": "close_app", "args": {"name": app_name}}

    # ── Registry queries ───────────────────────────────────────────────────────
    m = _DESK_APP_RUNTIME.match(text)
    if m:
        app_name = (m.group("app") or m.group("app2") or "").strip()
        return {"action": "call_tool", "name": "show_app_runtime", "args": {"name": app_name}}

    m = _DESK_SHOW_APP.match(text)
    if m:
        app_name = m.group("app").strip()
        return {"action": "call_tool", "name": "show_app", "args": {"name": app_name}}

    if _DESK_LIST_APPS.match(text) or _DESK_WHAT_LAUNCH.match(text):
        return {"action": "call_tool", "name": "list_apps", "args": {}}

    if _DESK_SCAN_APPS.match(text):
        return {"action": "call_tool", "name": "scan_apps", "args": {}}

    if _DESK_LIST_LOCS.match(text):
        return {"action": "call_tool", "name": "list_locations", "args": {}}

    # "where is X" and "show/navigate X" still route to location
    m = _DESK_OPEN_LOC.match(text) or _DESK_WHERE.match(text)
    if m:
        return {"action": "call_tool", "name": "open_location", "args": {"name": m.group("name").strip()}}

    # ── File search ────────────────────────────────────────────────────────────
    m = _DESK_RECENT.match(text)
    if m:
        return {"action": "call_tool", "name": "recent_files",
                "args": {"location": (m.group("loc") or "").strip()}}

    m = _DESK_FIND_EXT.match(text)
    if m:
        ext = m.group("ext").lower().replace(" ", "_").replace("-", "_")
        ext = {
            "python": "py",
            "kicad": "kicad_pro",
            "kicad_project": "kicad_pro",
            "kicad_projects": "kicad_pro",
        }.get(ext, ext)
        loc = (m.group("loc") or "").strip()
        return {"action": "call_tool", "name": "find_files",
                "args": {"query": "", "extension": ext, "location": loc}}

    m = _DESK_FIND_QUERY.match(text)
    if m:
        return {"action": "call_tool", "name": "find_files",
                "args": {"query": m.group("query").strip(),
                         "extension": "",
                         "location": (m.group("loc") or "").strip()}}

    m = _DESK_SEARCH_LOC.match(text)
    if m:
        return {"action": "call_tool", "name": "find_files",
                "args": {"query": "", "extension": "", "location": m.group("loc").strip()}}

    # ── Multi-app: "open X and Y", "open X, Y, and Z" ──────────────────────────
    m = re.match(r"^(?:open|launch|start)\s+(.+?)[\.\?!]*$", text, re.I)
    if m:
        from backend.app.services.command_router import parse_multi_targets
        targets = parse_multi_targets(m.group(1).strip())
        if targets:
            calls = [{"name": "open_target", "args": {"target": t, "modifier": ""}} for t in targets]
            logger.info("INTENT: open_multi ROUTE: multi_app Targets=%r", targets)
            return {"action": "call_tools", "calls": calls}

    # ── Generic "open X" — preference-aware resolver (catches everything else) ─
    m = _DESK_OPEN_APP_GENERIC.match(text)
    if m:
        target = m.group("app").strip()
        logger.info("INTENT: open_target ROUTE: generic_resolver Target=%r", target)
        return {"action": "call_tool", "name": "open_target", "args": {"target": target, "modifier": ""}}

    return None


# ── Service assignment regexes (Phase 10B) ────────────────────────────────────
_SN = r"([a-z0-9][a-z0-9_\-]*)"   # service name (lower-case first char)

# Presets
_PRESET_KW = r"(nas|media[\s\-]?player|robot|esp32|web[\s\-]?server|drone|rover|iot|uav|storage|music)"

_SVC_PRESET_AS = re.compile(
    rf"^(?:register|configure|setup|set\s+up|assign)\s+{_N}\s+(?:service\s+)?as\s+(?:a\s+)?{_PRESET_KW}[\?\.!]?$",
    re.I,
)
_SVC_PRESET_RUNS = re.compile(
    rf"^{_N}\s+(?:should\s+)?(?:run|be|act\s+as|function\s+as)\s+(?:a\s+)?{_PRESET_KW}[\?\.!]?$",
    re.I,
)
_SVC_PRESET_ASSIGN = re.compile(
    rf"^(?:assign|apply|use)\s+{_PRESET_KW}\s+(?:preset\s+)?(?:to|on|for)\s+{_N}[\?\.!]?$",
    re.I,
)

# Add single service
_SVC_ADD_TO = re.compile(
    rf"^(?:add|install|register|enable)\s+{_SN}\s+(?:service\s+)?(?:to|on|for)\s+{_N}[\?\.!]?$",
    re.I,
)
_SVC_RUNS = re.compile(
    rf"^{_N}\s+(?:runs?|has|hosts?|provides?|exposes?)\s+{_SN}(?:\s+service)?[\?\.!]?$",
    re.I,
)
_SVC_ASSIGN_TO = re.compile(
    rf"^(?:assign)\s+{_SN}\s+(?:service\s+)?to\s+{_N}[\?\.!]?$",
    re.I,
)

# Remove service
_SVC_REMOVE_FROM = re.compile(
    rf"^(?:remove|delete|unregister|disable)\s+{_SN}\s+(?:service\s+)?from\s+{_N}[\?\.!]?$",
    re.I,
)

# Rename service
_SVC_RENAME = re.compile(
    rf"^rename\s+(?:service\s+)?{_SN}\s+to\s+{_SN}(?:\s+on\s+{_N})?[\?\.!]?$",
    re.I,
)


def _regex_service_assignment(query: str) -> dict | None:
    """Match chat-based service assignment patterns."""
    text = query.strip()

    # Preset patterns
    m = _SVC_PRESET_AS.match(text)
    if m:
        return {"action": "call_tool", "name": "register_node_preset",
                "args": {"node": m.group(1).strip(), "preset": m.group(2).strip()}}

    m = _SVC_PRESET_RUNS.match(text)
    if m:
        return {"action": "call_tool", "name": "register_node_preset",
                "args": {"node": m.group(1).strip(), "preset": m.group(2).strip()}}

    m = _SVC_PRESET_ASSIGN.match(text)
    if m:
        return {"action": "call_tool", "name": "register_node_preset",
                "args": {"node": m.group(2).strip(), "preset": m.group(1).strip()}}

    # Add single service
    m = _SVC_ADD_TO.match(text)
    if m:
        return {"action": "call_tool", "name": "add_node_service",
                "args": {"node": m.group(2).strip(), "service": m.group(1).strip(),
                         "type": "", "description": ""}}

    m = _SVC_ASSIGN_TO.match(text)
    if m:
        return {"action": "call_tool", "name": "add_node_service",
                "args": {"node": m.group(2).strip(), "service": m.group(1).strip(),
                         "type": "", "description": ""}}

    m = _SVC_RUNS.match(text)
    if m:
        return {"action": "call_tool", "name": "add_node_service",
                "args": {"node": m.group(1).strip(), "service": m.group(2).strip(),
                         "type": "", "description": ""}}

    # Remove service
    m = _SVC_REMOVE_FROM.match(text)
    if m:
        return {"action": "call_tool", "name": "remove_node_service",
                "args": {"node": m.group(2).strip(), "service": m.group(1).strip()}}

    # Rename service
    m = _SVC_RENAME.match(text)
    if m:
        old = m.group(1).strip()
        new = m.group(2).strip()
        node = m.group(3).strip() if m.group(3) else ""
        return {"action": "call_tool", "name": "rename_node_service",
                "args": {"node": node, "old": old, "new": new}}

    return None


def _regex_project_intelligence(query: str) -> dict | None:
    """Match project intelligence patterns — Phase 14A."""
    text = query.strip()

    m = _PROJ_BLOCKED_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "blocked_projects", "args": {}}

    m = _PROJ_STARTABLE_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "startable_projects", "args": {}}

    m = _PROJ_USING_RE.match(text)
    if m:
        component = m.group("component").strip()
        return {"action": "call_tool", "name": "projects_using", "args": {"component": component}}

    m = _PROJ_BLOCKERS_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or "").strip()
        if project:
            return {"action": "call_tool", "name": "project_blockers", "args": {"project": project}}

    m = _PROJ_READINESS_RE.match(text)
    if m:
        project = m.group("project").strip()
        if project:
            return {"action": "call_tool", "name": "project_readiness", "args": {"project": project}}

    m = _PROJ_DEPS_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or "").strip()
        if project:
            return {"action": "call_tool", "name": "project_dependencies", "args": {"project": project}}

    m = _PROJ_BRIEFING_RE.match(text)
    if m:
        project = m.group("project").strip()
        if project:
            return {"action": "call_tool", "name": "project_briefing", "args": {"project": project}}

    return None


def _regex_knowledge_graph(query: str) -> dict | None:
    """Match knowledge graph patterns — Phase 14A."""
    text = query.strip()

    if _KG_GENERAL_RE.match(text):
        return {"action": "call_tool", "name": "show_knowledge_graph", "args": {}}

    m = _KG_PROJECT_RE.match(text)
    if m:
        project = (m.group("project") or m.group("project2") or "").strip()
        if project:
            return {"action": "call_tool", "name": "show_knowledge_graph", "args": {"project": project}}

    return None


def _regex_observability(query: str) -> dict | None:
    """Match observability/ledger patterns — Phase 13C."""
    text = query.strip()

    if _OBS_WHY_RE.match(text):
        return {"action": "call_tool", "name": "explain_last_action", "args": {}}

    m = _OBS_ACTIONS_NODE_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "show_recent_actions",
                "args": {"node": m.group("node"), "limit": 20}}

    if _OBS_FAILURES_RE.match(text):
        return {"action": "call_tool", "name": "show_failures", "args": {"limit": 20}}

    if _OBS_PLANNER_RE.match(text):
        return {"action": "call_tool", "name": "show_planner_trace", "args": {"limit": 10}}

    if _OBS_HEALTH_RE.match(text):
        return {"action": "call_tool", "name": "show_capability_health", "args": {}}

    if _OBS_RECENT_RE.match(text):
        return {"action": "call_tool", "name": "show_recent_actions", "args": {"limit": 20}}

    return None


def _regex_fleet(query: str) -> dict | None:
    """Match fleet management patterns — Phase 13B."""
    from backend.app.services.fleet_manager import normalize_fleet_filter
    text = query.strip()

    if _FLEET_STATUS_RE.match(text):
        return {"action": "call_tool", "name": "fleet_status", "args": {}}

    if _FLEET_OFFLINE_RE.match(text):
        return {"action": "call_tool", "name": "show_fleet_offline", "args": {}}

    if _FLEET_UNHEALTHY_RE.match(text):
        return {"action": "call_tool", "name": "show_fleet_unhealthy", "args": {}}

    if _FLEET_GROUPS_RE.match(text):
        return {"action": "call_tool", "name": "show_fleet_groups", "args": {}}

    m = _FLEET_ACT_ON_ALL.match(text)
    if m:
        action   = m.group("action").lower()
        service  = m.group("service")
        ftype, fval = normalize_fleet_filter(m.group("filter"))
        return {"action": "call_tool", "name": "fleet_action",
                "args": {"capability": f"system.{action}",
                         "filter_type": ftype, "filter_value": fval,
                         "service_name": service}}

    m = _FLEET_ACT_EVERYWHERE.match(text)
    if m:
        action  = m.group("action").lower()
        service = m.group("service")
        return {"action": "call_tool", "name": "fleet_action",
                "args": {"capability": f"system.{action}",
                         "filter_type": "all", "filter_value": "",
                         "service_name": service}}

    return None


def _regex_capability(query: str) -> dict | None:
    """Match capability NL patterns — checked before node/system patterns."""
    text = query.strip()

    # Services / capability listing
    m = _SVC_LIST_ON.match(text) or _SVC_WHAT.match(text) or _SVC_WHAT_CAN.match(text) or _SVC_CAPS_ON.match(text)
    if m:
        return {"action": "call_tool", "name": "list_services", "args": {"node": m.group(1).strip()}}
    if _SVC_LIST_ALL.match(text):
        return {"action": "call_tool", "name": "list_services", "args": {"node": ""}}

    # Media — play
    m = _CAP_MEDIA_PLAY.match(text)
    if m:
        return _cap("media.play", m.group(1).strip() if m.group(1) else "")

    # Media — pause (must come before stop to avoid "stop" matching "pause")
    m = _CAP_MEDIA_PAUSE.match(text)
    if m:
        return _cap("media.pause", m.group(1).strip() if m.group(1) else "")

    # Media — next
    m = _CAP_MEDIA_NEXT.match(text)
    if m:
        return _cap("media.next", m.group(1).strip() if m.group(1) else "")

    # Media — previous
    m = _CAP_MEDIA_PREV.match(text)
    if m:
        return _cap("media.previous", m.group(1).strip() if m.group(1) else "")

    # Media — volume ("set volume to 50 on nighthawk")
    m = _CAP_MEDIA_VOL.match(text)
    if m:
        vol = int(m.group(1))
        node = m.group(2).strip() if m.group(2) else ""
        return _cap("media.volume", node, {"volume": vol})

    # Media — stop (specific: "stop music / stop playing")
    m = _CAP_MEDIA_STOP.match(text)
    if m:
        return _cap("media.stop", m.group(1).strip() if m.group(1) else "")

    # Camera
    m = _CAP_CAMERA_CAPTURE.match(text)
    if m:
        return _cap("camera.capture", m.group(1).strip() if m.group(1) else "")
    m = _CAP_CAMERA_STREAM_STOP.match(text)
    if m:
        return _cap("camera.stream_stop", m.group(1).strip() if m.group(1) else "")
    m = _CAP_CAMERA_STREAM.match(text)
    if m:
        return _cap("camera.stream", m.group(1).strip() if m.group(1) else "")

    # Motion — node name explicit in phrase
    m = _CAP_MOTION_FWD.match(text)
    if m:
        return _cap("motion.forward", m.group(1))
    m = _CAP_MOTION_BWD.match(text)
    if m:
        return _cap("motion.backward", m.group(1))
    m = _CAP_MOTION_LEFT.match(text)
    if m:
        return _cap("motion.turn_left", m.group(1))
    m = _CAP_MOTION_RIGHT.match(text)
    if m:
        return _cap("motion.turn_right", m.group(1))
    m = _CAP_MOTION_STOP.match(text)
    if m:
        return _cap("motion.stop", m.group(1))

    # Battery
    m = _CAP_BATTERY.match(text)
    if m:
        return _cap("battery.status", m.group(1))

    # Sensor
    m = _CAP_SENSOR.match(text)
    if m:
        return _cap("sensor.read", m.group(1))

    # System service control — "restart nginx on carrera"
    m = _CAP_SYS_RESTART.match(text)
    if m:
        svc_name = m.group(1).strip()
        node = m.group(2).strip() if m.group(2) else ""
        # Guard: don't eat single-word "restart node-name" — handled by send_node_command
        if node or len(svc_name) > 1:
            return _cap("system.restart", node, {"service": svc_name})

    m = _CAP_SYS_START.match(text)
    if m:
        svc_name = m.group(1).strip()
        node = m.group(2).strip() if m.group(2) else ""
        if node or len(svc_name) > 1:
            return _cap("system.start", node, {"service": svc_name})

    m = _CAP_SYS_STOP.match(text)
    if m:
        svc_name = m.group(1).strip()
        node = m.group(2).strip() if m.group(2) else ""
        if node or len(svc_name) > 1:
            return _cap("system.stop", node, {"service": svc_name})

    return None


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

    m = _NODE_MERGE.match(text)
    if m:
        return {"action": "call_tool", "name": "merge_nodes",
                "args": {"source": m.group(1).strip(), "target": m.group(2).strip()}}

    if _NODE_DEDUP.match(text):
        return {"action": "call_tool", "name": "deduplicate_nodes", "args": {}}

    # SSH profile update — must come before the connect/ssh regex to avoid false match
    _USER_TOKEN = r"([a-zA-Z0-9_.\-]{1,64})"
    _KEY_TOKEN  = r"([~/a-zA-Z0-9_.\-]{1,256})"
    m = re.match(
        rf"^(?:set|update|configure|change)\s+(?:ssh\s+)?(?:username|user)\s+for\s+{_N}"
        rf"\s+(?:to|as)\s+{_USER_TOKEN}[\?\.!]?$",
        text, re.I,
    )
    if m:
        return {"action": "call_tool", "name": "update_ssh_profile",
                "args": {"node": m.group(1).strip(), "username": m.group(2).strip(), "key_path": ""}}

    m = re.match(
        rf"^(?:configure|set|update)\s+{_N}\s+ssh(?:\s+(?:profile|user(?:name)?))?\s+(?:as|to)\s+{_USER_TOKEN}[\?\.!]?$",
        text, re.I,
    )
    if m:
        return {"action": "call_tool", "name": "update_ssh_profile",
                "args": {"node": m.group(1).strip(), "username": m.group(2).strip(), "key_path": ""}}

    m = re.match(
        rf"^(?:set|update)\s+(?:ssh\s+)?key\s+for\s+{_N}\s+(?:to|as)\s+{_KEY_TOKEN}[\?\.!]?$",
        text, re.I,
    )
    if m:
        return {"action": "call_tool", "name": "update_ssh_profile",
                "args": {"node": m.group(1).strip(), "username": "", "key_path": m.group(2).strip()}}

    m = re.match(
        rf"^(?:set|update)\s+{_N}\s+(?:ssh\s+)?key\s+(?:to|as)\s+{_KEY_TOKEN}[\?\.!]?$",
        text, re.I,
    )
    if m:
        return {"action": "call_tool", "name": "update_ssh_profile",
                "args": {"node": m.group(1).strip(), "username": "", "key_path": m.group(2).strip()}}

    # SSH connect
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


def _regex_mission(query: str) -> dict | None:
    """Mission control fast-path regex dispatcher."""
    if _BRIEFING_RE.match(query):
        return {"action": "call_tool", "name": "morning_briefing", "args": {}}
    if _EVENING_RE.match(query):
        return {"action": "call_tool", "name": "evening_review", "args": {}}
    if _FOCUS_RE.match(query):
        return {"action": "call_tool", "name": "daily_focus", "args": {}}
    if _WEEKLY_RE.match(query):
        return {"action": "call_tool", "name": "weekly_review", "args": {}}
    if _STALE_PROJECTS_RE.match(query):
        return {"action": "call_tool", "name": "forgotten_items", "args": {}}
    if _FORGOTTEN_RE.match(query):
        return {"action": "call_tool", "name": "forgotten_items", "args": {}}
    if _PROJECT_HEALTH_RE.match(query):
        return {"action": "call_tool", "name": "project_health", "args": {}}
    if _LIST_PROJECTS_RE.match(query):
        return {"action": "call_tool", "name": "list_projects", "args": {"status": ""}}
    m = _CREATE_PROJECT_RE.match(query)
    if m:
        return {"action": "call_tool", "name": "create_project", "args": {
            "name": m.group(1).strip(), "status": "active", "priority": "normal",
            "brain63_key": "", "notes": "",
        }}
    m = _UPDATE_PROJECT_STATUS_RE.match(query)
    if m:
        return {"action": "call_tool", "name": "update_project_status", "args": {
            "name": m.group(1).strip(), "status": m.group(2).strip(),
        }}
    return None


# ── Hardware Operations (Phase 12A) ──────────────────────────────────────────

# Inventory patterns
_HW_ADD = re.compile(
    r"^(?:add|register|log|create)\s+"
    r"(?:component|part|chip|sensor|board|display|motor|battery|radio|module|pcb|sbc|mcu|ic|misc\s+)?"
    r"(?P<name>.+?)\s+"
    r"(?:category\s+(?P<cat>\w+)\s+)?"
    r"(?:(?:quantity|qty|x|count)\s*)(?P<qty>\d+)"
    r"(?:\s+category\s+(?P<cat2>\w+))?.*$",
    re.I,
)
_HW_ADD_SIMPLE = re.compile(
    r"^(?:add|register|log)\s+"
    r"(?:a\s+)?(?:component|part|chip|sensor|board|display|motor|battery|radio|module|pcb|sbc|mcu)?\s*"
    r"(?P<name>[A-Za-z0-9_.\-]+(?:\s+[A-Za-z0-9_.\-]+)?)"
    r"(?:\s+category\s+(?P<cat>\w+))?"
    r"\s*$",
    re.I,
)

_HW_LIST_ALL = re.compile(
    r"^(?:show|list|display|view)\s+(?:all\s+)?(?:hardware\s+)?(?:components?|parts?|inventory|hardware)[\?\.!]?$",
    re.I,
)
_HW_LIST_CAT = re.compile(
    r"^(?:show|list|display)\s+(?:all\s+)?(?:hardware\s+)?(?P<cat>sensors?|microcontrollers?|mcus?|displays?|batteries|battery|radios?|motors?|sbcs?|pcbs?|misc|power|modules?)\s*[\?\.!]?$",
    re.I,
)
_HW_SEARCH = re.compile(
    r"^(?:search|find|look\s*up|locate)\s+(?:component|hardware|part|chip|sensor)?\s+(?P<q>.+?)[\?\.!]?$",
    re.I,
)
_HW_HOW_MANY = re.compile(
    r"^how\s+many\s+(?P<q>.+?)\s+(?:do\s+i\s+(?:own|have)|are\s+(?:in\s+stock|available))[\?\.!]?$",
    re.I,
)
_HW_SUMMARY = re.compile(
    r"^(?:hardware\s+(?:summary|overview|status|inventory)|show\s+hardware(?:\s+summary)?|what\s+hardware\s+do\s+i\s+have)[\?\.!]?$",
    re.I,
)
_HW_GET_COMP = re.compile(
    r"^(?:show|get|details?\s+for|info\s+on|lookup)\s+(?:component|part|chip|sensor)?\s*(?P<name>.+?)[\?\.!]?$",
    re.I,
)
_HW_UPDATE_QTY = re.compile(
    r"^update\s+(?P<name>.+?)\s+quantity\s+(?P<qty>\d+)[\?\.!]?$",
    re.I,
)

# Project patterns
_HW_PROJ_CREATE = re.compile(
    r"^(?:create|add|new|start)\s+(?:a\s+)?(?:hardware|hw)\s+project\s+(?P<name>.+?)(?:\s+priority\s+(?P<pri>\w+))?[\?\.!]?$",
    re.I,
)
_HW_PROJ_LIST = re.compile(
    r"^(?:show|list|display)\s+(?:all\s+)?(?:hardware|hw)\s+projects?[\?\.!]?$",
    re.I,
)
_HW_PROJ_LIST_STATUS = re.compile(
    r"^(?:show|list)\s+(?P<status>active|paused|complete|abandoned)\s+(?:hardware|hw)\s+projects?[\?\.!]?$",
    re.I,
)
_HW_PROJ_SHOW = re.compile(
    r"^(?:show|get|view|inspect)\s+(?:hardware|hw)\s+project\s+(?P<name>.+?)[\?\.!]?$",
    re.I,
)
_HW_PROJ_STATUS_VALUES = (
    r"planned|researching|designing|ordering|waiting[\s_]for[\s_]parts|"
    r"building|testing|blocked|completed?|done|archived|active|paused?|abandoned"
)
_HW_PROJ_STATUS = re.compile(
    r"^(?:mark|set|update)\s+(?:hardware|hw\s+)?project\s+(?P<name>.+?)\s+(?:as\s+)?(?P<status>"
    + _HW_PROJ_STATUS_VALUES + r")[\?\.!]?$",
    re.I,
)
_HW_PROJ_STATUS2 = re.compile(
    r"^(?:mark|set)\s+(?P<name>.+?)\s+(?:hardware\s+)?(?:to\s+)?(?P<status>"
    + _HW_PROJ_STATUS_VALUES + r")[\?\.!]?$",
    re.I,
)

# Project-part linking
_HW_ASSIGN = re.compile(
    r"^assign\s+(?P<part>.+?)\s+to\s+(?:(?:hardware|hw)\s+project\s+)?(?P<project>.+?)"
    r"(?:\s+(?:quantity|qty|x)\s*(?P<qty>\d+))?[\?\.!]?$",
    re.I,
)
_HW_PROJ_PARTS = re.compile(
    r"^(?:show|list)\s+(?:components?|parts?)\s+(?:for|in|of|used\s+by)\s+(?P<project>.+?)[\?\.!]?$",
    re.I,
)
_HW_PART_PROJECTS = re.compile(
    r"^(?:show|list)\s+projects?\s+(?:using|that\s+use[s]?|with)\s+(?P<part>.+?)[\?\.!]?$",
    re.I,
)

# Orders
_HW_ORDER = re.compile(
    r"^(?:log\s+)?order\s+(?P<part>.+?)\s+"
    r"(?:(?:from|at|via)\s+(?P<vendor>[A-Za-z0-9\s]+?)\s+)?"
    r"(?:(?:quantity|qty|x)\s*)?(?P<qty>\d+)[\?\.!]?$",
    re.I,
)
_HW_ORDERS_LIST = re.compile(
    r"^(?:show|list|display)\s+(?:all\s+)?(?:(?P<status>pending|ordered|manufacturing|shipped|delivered|cancelled)\s+)?orders?[\?\.!]?$",
    re.I,
)
_HW_ORDER_UPDATE = re.compile(
    r"^mark\s+order\s+(?P<q>.+?)\s+(?:as\s+)?(?P<status>ordered|manufacturing|shipped|delivered|cancelled)[\?\.!]?$",
    re.I,
)

# Phase 12B intelligence patterns
_HW_BUILD_READY = re.compile(
    r"^(?:can\s+i\s+build|build\s+readiness\s+for|check\s+(?:build\s+readiness|readiness)\s+for)"
    r"\s+(?P<name>.+?)[\?\.!]?$",
    re.I,
)
_HW_BUILD_READY2 = re.compile(
    r"^is\s+(?P<name>.+?)\s+ready\s+to\s+build[\?\.!]?$",
    re.I,
)
_HW_MISSING = re.compile(
    r"^(?:show\s+)?(?:missing\s+(?:parts?|components?)|what\s+(?:am\s+i|parts?)\s+missing)"
    r"(?:\s+(?:for|from)\s+(?P<project>.+?))?[\?\.!]?$",
    re.I,
)
_HW_MISSING_FOR = re.compile(
    r"^(?:missing\s+parts?\s+for|what\s+do\s+i\s+(?:need|lack)\s+for)\s+(?P<project>.+?)[\?\.!]?$",
    re.I,
)
_HW_BLOCKED = re.compile(
    r"^(?:show|list|which)\s+(?:projects?\s+(?:are\s+)?blocked|blocked\s+projects?)[\?\.!]?$",
    re.I,
)
_HW_COMP_USAGE = re.compile(
    r"^(?:show\s+)?(?:component\s+usage(?:\s+stats?)?|shared\s+components?|"
    r"which\s+components?\s+are\s+used\s+most|most\s+used\s+components?)[\?\.!]?$",
    re.I,
)
_HW_PROJ_USES = re.compile(
    r"^how\s+many\s+projects\s+use\s+(?P<part>.+?)[\?\.!]?$",
    re.I,
)
_HW_RECOMMEND = re.compile(
    r"^(?:what\s+should\s+i\s+order|show\s+(?:order\s+)?recommendations?|"
    r"show\s+critical\s+shortages?|what\s+do\s+i\s+(?:need\s+to\s+buy|need\s+to\s+order)|"
    r"show\s+low\s+stock)[\?\.!]?$",
    re.I,
)
_HW_PRIORITY = re.compile(
    r"^(?:what\s+should\s+i\s+work\s+on|show\s+project\s+priorit(?:y|ies)|"
    r"which\s+project\s+is\s+closest\s+to\s+(?:completion|done)|what\s+can\s+i\s+build\s+now|"
    r"project\s+priority\s+ranking)[\?\.!]?$",
    re.I,
)
_HW_IMPORT_BOM = re.compile(
    r"^(?:import|ingest|load)\s+(?:kicad\s+)?bom\s+(?P<path>.+?)(?:\s+(?:for|as|project)\s+(?P<project>.+?))?[\?\.!]?$",
    re.I,
)
_HW_IMPORT_INVENTORY = re.compile(
    r"^(?:import|ingest|load)\s+inventory\s+(?P<path>.+?)[\?\.!]?$",
    re.I,
)
_HW_SCAN_PROJECT_BOM = re.compile(
    r"^scan\s+(?:(?P<project>.+?)\s+)?project\s+bom[\?\.!]?$",
    re.I,
)
_HW_IMPORTED_COMPONENTS = re.compile(
    r"^(?:show|list)\s+imported\s+(?:components?|parts?)(?:\s+(?P<import_id>[a-z0-9]{4,12}))?[\?\.!]?$",
    re.I,
)
_HW_IMPORTED_PROJECTS = re.compile(
    r"^(?:show|list)\s+imported\s+projects?[\?\.!]?$",
    re.I,
)
_HW_BOM_STATUS = re.compile(
    r"^(?:show\s+)?bom\s+status[\?\.!]?$",
    re.I,
)
_HW_PROJECT_READINESS = re.compile(
    r"^(?:show\s+)?(?:project\s+readiness|build\s+readiness)[\?\.!]?$",
    re.I,
)
_HW_INVENTORY_IMPACT = re.compile(
    r"^(?:show\s+)?(?:inventory\s+impact|what\s+parts\s+will\s+be\s+consumed|consumed\s+parts)(?:\s+(?:for|by)\s+(?P<project>.+?))?[\?\.!]?$",
    re.I,
)

# Category alias normalizer
_HW_CAT_MAP = {
    "sensor": "sensor", "sensors": "sensor",
    "microcontroller": "microcontroller", "microcontrollers": "microcontroller",
    "mcu": "microcontroller", "mcus": "microcontroller",
    "display": "display", "displays": "display",
    "battery": "battery", "batteries": "battery",
    "radio": "radio", "radios": "radio",
    "motor": "motor", "motors": "motor",
    "sbc": "sbc", "sbcs": "sbc",
    "pcb": "pcb", "pcbs": "pcb",
    "power": "power",
    "module": "module", "modules": "module",
    "misc": "misc",
}


def _regex_hardware(query: str) -> dict | None:
    text = query.strip()

    # Phase 12C imports must come before generic hardware search/get patterns.
    m = _HW_IMPORT_BOM.match(text)
    if m:
        return {"action": "call_tool", "name": "import_bom",
                "args": {"path": m.group("path").strip(),
                         "project": (m.group("project") or "").strip()}}

    m = _HW_IMPORT_INVENTORY.match(text)
    if m:
        return {"action": "call_tool", "name": "import_inventory",
                "args": {"path": m.group("path").strip()}}

    m = _HW_SCAN_PROJECT_BOM.match(text)
    if m:
        project = (m.group("project") or "").strip()
        return {"action": "call_tool", "name": "import_bom",
                "args": {"path": f"{project} bom".strip(), "project": project}}

    m = _HW_IMPORTED_COMPONENTS.match(text)
    if m:
        return {"action": "call_tool", "name": "show_imported_components",
                "args": {"import_id": (m.group("import_id") or "").strip()}}

    if _HW_IMPORTED_PROJECTS.match(text):
        return {"action": "call_tool", "name": "show_imported_projects", "args": {}}

    if _HW_BOM_STATUS.match(text):
        return {"action": "call_tool", "name": "list_imports", "args": {}}

    if _HW_PROJECT_READINESS.match(text):
        return {"action": "call_tool", "name": "show_project_readiness", "args": {}}

    m = _HW_INVENTORY_IMPACT.match(text)
    if m:
        return {"action": "call_tool", "name": "show_inventory_impact",
                "args": {"project": (m.group("project") or "").strip()}}

    # Summary
    if _HW_SUMMARY.match(text):
        return {"action": "call_tool", "name": "hw_inventory_summary", "args": {}}

    # List all inventory
    if _HW_LIST_ALL.match(text):
        return {"action": "call_tool", "name": "list_components", "args": {}}

    # List by category
    m = _HW_LIST_CAT.match(text)
    if m:
        cat_raw = m.group("cat").rstrip("s").lower()
        cat = _HW_CAT_MAP.get(cat_raw, _HW_CAT_MAP.get(m.group("cat").lower(), cat_raw))
        return {"action": "call_tool", "name": "list_components", "args": {"category": cat}}

    # Show / get a specific component (narrow form — must have MCU/sensor word trigger)
    # Done later to avoid false positives

    # Add component with explicit quantity
    m = _HW_ADD.match(text)
    if m:
        name = m.group("name").strip()
        qty = int(m.group("qty"))
        cat = (m.group("cat") or m.group("cat2") or "misc").lower()
        cat = _HW_CAT_MAP.get(cat, cat)
        return {"action": "call_tool", "name": "add_component",
                "args": {"name": name, "category": cat, "quantity": qty}}

    # Search / how many
    m = _HW_SEARCH.match(text)
    if m:
        return {"action": "call_tool", "name": "search_hardware", "args": {"query": m.group("q").strip()}}

    m = _HW_HOW_MANY.match(text)
    if m:
        return {"action": "call_tool", "name": "search_hardware", "args": {"query": m.group("q").strip()}}

    # Update quantity
    m = _HW_UPDATE_QTY.match(text)
    if m:
        return {"action": "call_tool", "name": "update_component",
                "args": {"name": m.group("name").strip(), "quantity": int(m.group("qty"))}}

    # Projects — create
    m = _HW_PROJ_CREATE.match(text)
    if m:
        priority = m.group("pri") or "normal"
        return {"action": "call_tool", "name": "create_hw_project",
                "args": {"name": m.group("name").strip(), "priority": priority}}

    # Projects — list with optional status filter
    m = _HW_PROJ_LIST_STATUS.match(text)
    if m:
        return {"action": "call_tool", "name": "list_hw_projects",
                "args": {"status": m.group("status").lower()}}

    if _HW_PROJ_LIST.match(text):
        return {"action": "call_tool", "name": "list_hw_projects", "args": {}}

    # Projects — show detail
    m = _HW_PROJ_SHOW.match(text)
    if m:
        return {"action": "call_tool", "name": "get_hw_project",
                "args": {"name": m.group("name").strip()}}

    # Project status update
    _STATUS_ALIASES = {"done": "completed", "paused": "paused", "complete": "completed"}
    m = _HW_PROJ_STATUS.match(text)
    if m:
        status = m.group("status").lower().replace(" ", "_")
        status = _STATUS_ALIASES.get(status, status)
        return {"action": "call_tool", "name": "update_hw_project_status",
                "args": {"name": m.group("name").strip(), "status": status}}

    m = _HW_PROJ_STATUS2.match(text)
    if m:
        status = m.group("status").lower().replace(" ", "_")
        status = _STATUS_ALIASES.get(status, status)
        return {"action": "call_tool", "name": "update_hw_project_status",
                "args": {"name": m.group("name").strip(), "status": status}}

    # Assign part to project
    m = _HW_ASSIGN.match(text)
    if m:
        qty = int(m.group("qty")) if m.group("qty") else 1
        return {"action": "call_tool", "name": "assign_part_to_project",
                "args": {"part": m.group("part").strip(),
                         "project": m.group("project").strip(),
                         "quantity_required": qty}}

    # List project parts
    m = _HW_PROJ_PARTS.match(text)
    if m:
        return {"action": "call_tool", "name": "list_project_parts",
                "args": {"project": m.group("project").strip()}}

    # List part projects
    m = _HW_PART_PROJECTS.match(text)
    if m:
        return {"action": "call_tool", "name": "list_part_projects",
                "args": {"part": m.group("part").strip()}}

    # Orders
    m = _HW_ORDER.match(text)
    if m:
        vendor = m.group("vendor").strip() if m.group("vendor") else ""
        return {"action": "call_tool", "name": "add_order",
                "args": {"part_name": m.group("part").strip(),
                         "vendor": vendor,
                         "quantity": int(m.group("qty"))}}

    m = _HW_ORDERS_LIST.match(text)
    if m:
        status_map = {"pending": "ordered"}
        raw_status = m.group("status") or ""
        status = status_map.get(raw_status.lower(), raw_status.lower())
        return {"action": "call_tool", "name": "list_orders", "args": {"status": status}}

    m = _HW_ORDER_UPDATE.match(text)
    if m:
        return {"action": "call_tool", "name": "update_order_status",
                "args": {"query": m.group("q").strip(), "status": m.group("status").lower()}}

    # Phase 12B intelligence patterns
    m = _HW_BUILD_READY.match(text) or _HW_BUILD_READY2.match(text)
    if m:
        return {"action": "call_tool", "name": "build_readiness_check",
                "args": {"project": m.group("name").strip()}}

    m = _HW_MISSING_FOR.match(text)
    if m:
        return {"action": "call_tool", "name": "show_missing_parts",
                "args": {"project": m.group("project").strip()}}

    m = _HW_MISSING.match(text)
    if m:
        project = (m.group("project") or "").strip()
        return {"action": "call_tool", "name": "show_missing_parts", "args": {"project": project}}

    if _HW_BLOCKED.match(text):
        return {"action": "call_tool", "name": "show_blocked_projects", "args": {}}

    m = _HW_PROJ_USES.match(text)
    if m:
        return {"action": "call_tool", "name": "component_usage_stats",
                "args": {"part": m.group("part").strip()}}

    if _HW_COMP_USAGE.match(text):
        return {"action": "call_tool", "name": "component_usage_stats", "args": {"part": ""}}

    if _HW_RECOMMEND.match(text):
        return {"action": "call_tool", "name": "recommend_orders", "args": {}}

    if _HW_PRIORITY.match(text):
        return {"action": "call_tool", "name": "what_should_i_work_on", "args": {}}

    return None


def _regex_fallback(query: str) -> dict:
    text = query.lower().strip()

    # ── Internal board router — FIRST, before all other patterns ─────────────
    # Catches "open intel board", "open knowledge graph", etc.
    # NEVER competes with desktop app/location search.
    board_result = _regex_board(query)
    if board_result:
        return board_result

    # Mission control — exact-match phrases, check first
    result = _regex_mission(query.strip())
    if result:
        return result

    # News and current events — always require live data; route straight to search_web.
    # These checks come first so short queries like "latest news" or "Premier League
    # standings" don't get absorbed by later patterns or fall through to "final".
    if _NEWS_RE.search(text):
        return {"action": "call_tool", "name": "search_web", "args": {"query": query.strip()}}
    if _CURRENT_EVENTS_RE.search(text):
        return {"action": "call_tool", "name": "search_web", "args": {"query": query.strip()}}

    if _DATE_RE.search(text):
        return {"action": "call_tool", "name": "get_time", "args": {}}

    m = _TIME_IN_RE.search(text)
    if m:
        return {"action": "call_tool", "name": "get_time_in", "args": {"place": m.group(1).strip()}}

    if re.search(r"\btime\b", text) and "in" not in text:
        return {"action": "call_tool", "name": "get_time", "args": {}}

    m = _WEATHER_RE.search(text) or _TEMP_RE.search(text) or _RAIN_RE.search(text) or _HOT_COLD_RE.search(text)
    if m:
        return {"action": "call_tool", "name": "get_weather", "args": {"place": m.group(1).strip()}}

    # Market comparison queries — need live search, not a specific ticker
    if _BEST_STOCK_RE.search(text):
        return {"action": "call_tool", "name": "search_web", "args": {"query": query.strip()}}

    m = _STOCK_RE.search(query)
    if m:
        raw = next((g for g in m.groups() if g), "").strip()
        if raw:
            return {"action": "call_tool", "name": "get_stock_price", "args": {"query": raw}}

    if _NODE_COUNT_RE.search(text):
        return {"action": "call_tool", "name": "list_nodes", "args": {}}

    if _WATCH_ALERTS_RE.match(text):
        return {"action": "call_tool", "name": "get_watch_alerts", "args": {}}

    # ── Semantic memory search ────────────────────────────────────────────────
    m = _SEMANTIC_SEARCH_RE.search(query)
    if m:
        q = next((g for g in m.groups() if g), "").strip()
        if q:
            return {"action": "call_tool", "name": "semantic_search", "args": {"query": q}}

    # ── Robotics — bulk commands (must come before single-node) ──────────────
    m = _BULK_LAND_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_bulk_command", "args": {"type": m.group(1).lower(), "command": "land"}}

    m = _BULK_DISARM_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_bulk_command", "args": {"type": m.group(1).lower(), "command": "disarm"}}

    m = _BULK_ARM_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_bulk_command", "args": {"type": m.group(1).lower(), "command": "arm"}}

    m = _BULK_ESTOP_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_bulk_command", "args": {"type": m.group(1).lower(), "command": "emergency_stop"}}

    m = _BULK_REBOOT_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_bulk_command", "args": {"type": m.group(1).lower(), "command": "reboot"}}

    m = _BULK_HOME_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_bulk_command", "args": {"type": m.group(1).lower(), "command": "home"}}

    # ── Robotics — single-node ────────────────────────────────────────────────
    m = _ROBOTICS_TYPE_RE.match(text)
    if m:
        rtype = m.group(1).lower().replace(" ", "-").replace("sensor-network", "sensor-network")
        return {"action": "call_tool", "name": "list_nodes_by_type", "args": {"type": rtype}}

    m = _CMD_ARM_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_node_command", "args": {"node": m.group(1), "command": "arm", "payload": {}}}

    m = _CMD_DISARM_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_node_command", "args": {"node": m.group(1), "command": "disarm", "payload": {}}}

    m = _CMD_LAND_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_node_command", "args": {"node": m.group(1), "command": "land", "payload": {}}}

    m = _CMD_HOME_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_node_command", "args": {"node": m.group(1), "command": "home", "payload": {}}}

    m = _CMD_ESTOP_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_node_command", "args": {"node": m.group(1), "command": "emergency_stop", "payload": {}}}

    m = _CMD_REBOOT_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "send_node_command", "args": {"node": m.group(1), "command": "reboot", "payload": {}}}

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

    # ── Scheduled tasks ───────────────────────────────────────────────────────
    if _SCHED_LIST_RE.match(text):
        return {"action": "call_tool", "name": "list_scheduled_tasks", "args": {}}

    m = _SCHED_DISABLE_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "disable_scheduled_task", "args": {"name": m.group(1).strip()}}

    m = _SCHED_DELETE_RE.match(text)
    if m:
        return {"action": "call_tool", "name": "delete_scheduled_task", "args": {"name": m.group(1).strip()}}

    m = _SCHED_CREATE_RE.match(query)
    if m:
        desc = m.group(1).strip()
        minutes = int(m.group(2))
        return {"action": "call_tool", "name": "schedule_task",
                "args": {"name": desc[:40], "prompt": desc, "interval_minutes": minutes}}

    # ── Productivity — Gmail / Calendar / Status (Phase 12G) ─────────────────
    # Must run BEFORE node/hardware patterns so "gmail status", "check email" etc.
    # are not absorbed by generic node-name matchers.
    if _PROD_STATUS_RE.match(text):
        return {"action": "call_tool", "name": "show_productivity_status", "args": {}}

    # Category-specific: check promotions / social / updates / all
    m = _EMAIL_CAT_RE.match(text)
    if m:
        cat = m.group("cat").rstrip("s").lower()  # normalise: "promotions" → "promotion"
        cat_map = {"promotion": "promotions", "social": "social",
                   "update": "updates", "forum": "forums"}
        label = cat_map.get(cat, cat)
        return {"action": "call_tool", "name": "list_emails",
                "args": {"folder": "inbox", "search": f"category:{label}", "limit": 10}}

    if _EMAIL_ALL_RE.match(text):
        return {"action": "call_tool", "name": "list_emails",
                "args": {"folder": "inbox", "search": "", "limit": 10}}

    if _EMAIL_UNREAD_RE.match(text):
        return {"action": "call_tool", "name": "list_emails",
                "args": {"folder": "inbox", "search": "category:primary is:unread", "limit": 10}}

    if _EMAIL_CHECK_RE.match(text) or _EMAIL_LATEST_RE.match(text):
        return {"action": "call_tool", "name": "list_emails",
                "args": {"folder": "inbox", "search": "category:primary", "limit": 10}}

    m = _EMAIL_FROM_RE.match(query)  # match original to preserve sender casing
    if m:
        sender = next((g for g in m.groups() if g), "").strip()
        return {"action": "call_tool", "name": "list_emails",
                "args": {"folder": "inbox", "search": f"from:{sender}", "limit": 10}}

    m = _EMAIL_SEARCH_RE.match(text)
    if m:
        q = next((g for g in m.groups() if g), "").strip()
        return {"action": "call_tool", "name": "search_emails", "args": {"query": q, "limit": 10}}

    if _GCAL_WEEK_RE.search(text):
        return {"action": "call_tool", "name": "list_gcal_events",
                "args": {"date": "today", "days": 7}}

    if _GCAL_TODAY_RE.match(text):
        return {"action": "call_tool", "name": "list_gcal_events",
                "args": {"date": "today", "days": 1}}

    # ── Engineering Memory (Phase 14C) ───────────────────────────────────────
    mem_result = _regex_memory(query)
    if mem_result:
        return mem_result

    # ── Workspace Digital Twin (Phase 15A) ────────────────────────────────────
    ws_result = _regex_workspace(query)
    if ws_result:
        return ws_result

    # ── Engineering Planner (Phase 15B) ──────────────────────────────────────
    ep_result = _regex_planner(query)
    if ep_result:
        return ep_result

    # ── Knowledge Graph (Phase 14A) — checked before node/telemetry patterns ──
    kg_result = _regex_knowledge_graph(query)
    if kg_result:
        return kg_result

    # ── Project Intelligence (Phase 14A) ─────────────────────────────────────
    pi_result = _regex_project_intelligence(query)
    if pi_result:
        return pi_result

    # ── Observability (Phase 13C) ─────────────────────────────────────────────
    obs_result = _regex_observability(query)
    if obs_result:
        return obs_result

    # ── Fleet management (Phase 13B) ─────────────────────────────────────────
    fleet_result = _regex_fleet(query)
    if fleet_result:
        return fleet_result

    # ── Hardware Operations (Phase 12A) ──────────────────────────────────────
    hw_result = _regex_hardware(query)
    if hw_result:
        return hw_result

    # ── Desktop control (Phase 11) ────────────────────────────────────────────
    desk_result = _regex_desktop(query)
    if desk_result:
        return desk_result

    # ── Service assignment (Phase 10B) ───────────────────────────────────────
    svc_assign_result = _regex_service_assignment(query)
    if svc_assign_result:
        return svc_assign_result

    # ── Service / capability (Phase 10) ──────────────────────────────────────
    cap_result = _regex_capability(query)
    if cap_result:
        return cap_result

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
