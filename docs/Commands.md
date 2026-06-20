# SILVIA — Master Command Reference

All commands documented here are natural language — SILVIA understands variations. Exact phrasing shown is the canonical form; alternatives are noted.

## Table of Contents

1. [Proactive Intelligence](#1-proactive-intelligence)
2. [Time & Weather](#2-time--weather)
3. [Web Search & Markets](#3-web-search--markets)
4. [Tasks](#4-tasks)
5. [Reminders](#5-reminders)
6. [Calendar](#6-calendar)
7. [Projects — Mission Control](#7-projects--mission-control)
8. [Node Registry](#8-node-registry)
9. [Node Telemetry](#9-node-telemetry)
10. [Node Commands (silvia-agent)](#10-node-commands-silvia-agent)
11. [SSH](#11-ssh)
12. [Node Services](#12-node-services)
13. [Capability Execution](#13-capability-execution)
14. [Watch Officer](#14-watch-officer)
15. [Desktop Awareness — Apps](#15-desktop-awareness--apps)
16. [Desktop Awareness — Files & Locations](#16-desktop-awareness--files--locations)
17. [System Info](#17-system-info)
18. [Semantic Memory](#18-semantic-memory)
19. [Scheduled Tasks](#19-scheduled-tasks)
20. [Hardware Assistant — Inventory](#20-hardware-assistant--inventory)
21. [Hardware Assistant — Projects](#21-hardware-assistant--projects)
22. [Hardware Assistant — Build Readiness](#22-hardware-assistant--build-readiness)
23. [Hardware Assistant — Orders](#23-hardware-assistant--orders)
24. [Hardware Assistant — Procurement](#24-hardware-assistant--procurement)
25. [Hardware Assistant — BOM Import](#25-hardware-assistant--bom-import)
26. [Hardware Assistant — Vision](#26-hardware-assistant--vision)
27. [Voice](#27-voice)

> **Hardware Assistant commands** (sections 20–26) are typed into the **Hardware Assistant panel** on the Hardware Board page, not the main chat.

---

## 1. Proactive Intelligence

### morning briefing
**Purpose:** Full operational picture — projects, tasks, reminders, calendar, alerts, offline nodes.

**Syntax:** `morning briefing`

**Alternatives:** `good morning`, `daily briefing`, `briefing`, `status report`, `what's happening today`

**Expected behavior:** Aggregates all system data (no LLM invention) and presents a structured overview of your day.

---

### daily focus
**Purpose:** Priority-ranked list of what to work on today.

**Syntax:** `what should I focus on today`

**Alternatives:** `what should I work on`, `daily focus`, `what's my priority today`, `what should I do today`, `what's most important today`

**Expected behavior:** Ranks tasks, reminders, and project work by urgency and importance.

---

### evening review
**Purpose:** End-of-day summary — what was accomplished, what's outstanding.

**Syntax:** `evening review`

**Alternatives:** `end of day`, `day review`, `what did I accomplish today`, `how did today go`, `EOD`, `wrap up`

---

### weekly review
**Purpose:** 7-day retrospective and upcoming-week preview.

**Syntax:** `weekly review`

**Alternatives:** `week review`, `weekly summary`, `how was my week`, `week in review`

---

### forgotten items
**Purpose:** Find stale projects, overdue reminders, long-pending tasks, and old unresolved alerts.

**Syntax:** `what am I forgetting`

**Alternatives:** `forgotten items`, `what's overdue`, `overdue items`, `what's stale`

---

### project health
**Purpose:** Per-project health report with status, task count, idle duration, and alerts.

**Syntax:** `project health`

**Alternatives:** `show project health`, `project status`, `health report`, `project overview`, `how are my projects`

---

## 2. Time & Weather

### get time
**Purpose:** Show current local time.

**Syntax:** `what time is it`

**Alternatives:** `current time`, `what's the time`

---

### get time in city
**Purpose:** Show current time in any city or country.

**Syntax:** `what time is it in [place]`

**Examples:**
```
time in tokyo
what time is it in Singapore
what's the time in New York
current time in Dubai
```

---

### get weather
**Purpose:** Current weather conditions for any location.

**Syntax:** `weather in [place]`

**Examples:**
```
weather in London
what's the weather in Tokyo
is it raining in Paris
temperature in Berlin
```

**Notes:** Requires `OPENWEATHER_API_KEY` in `.env`.

---

### combined time + weather
**Purpose:** Get both at once for the same place.

**Syntax:** `what's the time and weather in [place]`

**Expected behavior:** Both tools execute in parallel, response includes both.

---

## 3. Web Search & Markets

### web search
**Purpose:** Search the web for factual information, news, people, definitions.

**Syntax:** `search for [query]`

**Examples:**
```
who is Elon Musk
latest news on Nvidia
what is quantum computing
how does a jet engine work
search for Raspberry Pi 5 review
```

**Notes:** Uses SearxNG if `SEARXNG_URL` configured, otherwise DuckDuckGo.

---

### stock price
**Purpose:** Get current stock price for any company or ticker.

**Syntax:** `price of [company]` or `[TICKER] stock price`

**Examples:**
```
what's the price of Apple
AAPL stock price
how much is Tesla stock
NVDA quote
what is Microsoft trading at
SPY stock
```

**Notes:** Always uses `get_stock_price` tool, never web search for stock prices.

---

## 4. Tasks

### add task
**Purpose:** Create a new task, optionally linked to a project.

**Syntax:** `add task: [title]`

**Examples:**
```
add task: finish DroneHive PCB
add task review motor controller code
add task review code for project DroneHive
```

---

### list tasks
**Purpose:** Show pending, completed, or all tasks.

**Syntax:** `show my tasks`

**Alternatives:** `list pending tasks`, `show completed tasks`, `show all tasks`

**Filter values:** `pending` (default), `done`, `all`

---

### complete task
**Purpose:** Mark a task as done by partial title match.

**Syntax:** `complete task [partial title]`

**Examples:**
```
complete task DroneHive PCB
mark done finish PCB
```

---

### delete task
**Purpose:** Delete a task by partial title match.

**Syntax:** `delete task [partial title]`

---

## 5. Reminders

### set reminder
**Purpose:** Create a one-time or recurring reminder.

**Syntax:** `remind me [time/recurrence] to [message]`

**Examples:**
```
remind me in 10 minutes to check the pi5
remind me tomorrow at 9am to review the logs
remind me every Friday to backup Brain63
remind me to call mom tomorrow at 3pm
remind me in 2 hours to check the build
```

**Recurrence patterns:** every day, every Monday, every Friday, every week, daily, weekly

---

### list reminders
**Purpose:** Show all active reminders.

**Syntax:** `show reminders`

**Alternatives:** `list my reminders`, `what reminders do I have`

---

### complete reminder
**Purpose:** Mark a reminder as done by partial message match.

**Syntax:** `complete reminder [partial message]`

---

### delete reminder
**Purpose:** Delete a reminder by partial message match.

**Syntax:** `delete reminder [partial message]`

---

## 6. Calendar

### today's calendar
**Purpose:** Show today's events.

**Syntax:** `what's on my calendar today`

**Alternatives:** `today's schedule`, `any events today`

---

### upcoming events
**Purpose:** Show events in the next N days.

**Syntax:** `upcoming events`

**Alternatives:** `what's coming up this week`, `next 7 days schedule`

---

### create event
**Purpose:** Add a calendar event by natural language description.

**Syntax:** `create an event [description]`

**Examples:**
```
create an event Robotics Meeting tomorrow at 3pm
schedule team sync Monday at 10am
```

---

### delete event
**Purpose:** Delete a calendar event by partial title.

**Syntax:** `delete event [partial title]`

---

## 7. Projects — Mission Control

### list projects
**Purpose:** Show registered Mission Control projects.

**Syntax:** `show projects`

**Alternatives:** `list projects`, `my projects`, `active projects`, `what projects are active`

**Filter examples:** `show active projects`, `show blocked projects`

---

### create project
**Purpose:** Register a new project.

**Syntax:** `create project [name] [priority?]`

**Examples:**
```
create project DroneHive
create project DroneHive priority high
new project Cyberdeck priority critical
```

---

### update project status
**Purpose:** Change a project's status.

**Syntax:** `mark project [name] as [status]`

**Examples:**
```
mark project DroneHive as complete
set project Cyberdeck to paused
project DroneHive is blocked
```

**Status values:** active, paused, blocked, complete

---

## 8. Node Registry

### list nodes
**Purpose:** Show all registered nodes with their status.

**Syntax:** `what nodes are online`

**Alternatives:** `list my devices`, `what machines do I have`

---

### list nodes by type
**Purpose:** Show nodes of a specific type.

**Syntax:** `list [type]s`

**Examples:**
```
list drones
show all robots
what drones do I have
list esp32 nodes
show all sensor nodes
show all servers
```

---

### add node
**Purpose:** Register a new node.

**Syntax:** `add [name]` or `register [name] at [hostname/IP]`

**Examples:**
```
add laptop
register server1 at 192.168.1.10
add nighthawk at 100.64.1.5
```

---

### get node info
**Purpose:** Show network details, connectivity, and probe results for a node.

**Syntax:** `status of [node]`

**Alternatives:** `[node] info`, `what's the status of [node]`

---

### get node IP
**Purpose:** Show the IP address for a node.

**Syntax:** `what's the IP of [node]`

**Alternatives:** `[node] IP address`, `address of [node]`

---

### ping node
**Purpose:** Check if a node is reachable.

**Syntax:** `ping [node]`

**Alternatives:** `is [node] online`, `check [node] connectivity`

---

### verify node
**Purpose:** Run the full verification chain (silvia-agent → Tailscale → DNS → ping).

**Syntax:** `verify [node]`

**Alternatives:** `confirm [node] is online`, `check [node] connectivity`

---

### verify all nodes
**Purpose:** Verify all registered nodes.

**Syntax:** `verify all nodes`

**Alternatives:** `refresh nodes`, `check all nodes`, `run verification`

---

### update node IP
**Purpose:** Change a node's registered IP or hostname.

**Syntax:** `update [node] IP to [address]`

---

### delete node
**Purpose:** Remove a node from the registry.

**Syntax:** `delete [node]`

**Alternatives:** `remove [node] from the registry`

---

### merge nodes
**Purpose:** Merge two nodes — source deleted, its name becomes an alias on target.

**Syntax:** `merge [source] into [target]`

**Examples:**
```
merge VPS into carrera
consolidate nighthawk and nas
```

---

### deduplicate nodes
**Purpose:** Find and list duplicate nodes in the registry.

**Syntax:** `deduplicate nodes`

**Alternatives:** `clean up the registry`, `find duplicate nodes`

---

## 9. Node Telemetry

### get telemetry for node
**Purpose:** Show live metrics for a specific node.

**Syntax:** `show [node] telemetry`

**Alternatives:** `[node] cpu`, `[node] ram`, `[node] status`, `[node] metrics`, `[node] health`

**Examples:**
```
show workstation telemetry
workstation cpu
workstation ram
pi5 telemetry
show nighthawk metrics
show drone-01 battery
show robot-01 mission state
```

---

### get all telemetry
**Purpose:** Show live metrics for all nodes.

**Syntax:** `show all node telemetry`

**Alternatives:** `show hottest node`, `node health`, `infrastructure status`

---

## 10. Node Commands (silvia-agent)

These commands are sent to nodes via their `agent_url`. **Destructive commands require confirmation.**

### arm
```
arm drone-01
```

### disarm
```
disarm drone-01
```

### land
```
land drone-01
```

### home
```
send drone-01 home
```

### emergency stop
```
emergency stop drone-01
```

### reboot
```
reboot pi5
```

### restart service
```
restart service nginx on carrera
```

### bulk command (all nodes of type)
```
land all drones
disarm all robots
emergency stop all drones
reboot all vps
```

**Note:** Bulk destructive commands also require confirmation before executing.

---

## 11. SSH

### connect to node
**Purpose:** Open an SSH terminal to a node in Windows Terminal (new tab).

**Syntax:** `connect [node]`

**Alternatives:** `ssh into [node]`, `ssh [node]`, `connect to [node]`, `open terminal on [node]`

**Examples:**
```
connect carrera
ssh into nighthawk
connect to server1
open terminal on pi5
```

---

### ssh with username
**Purpose:** Connect with a specific username.

**Syntax:** `ssh [node] as [username]`

**Examples:**
```
ssh nighthawk as admin
ssh pi5 as pi
```

---

### set SSH profile
**Purpose:** Store SSH username and/or key path for a node so future connections don't prompt.

**Syntax:** `set ssh username for [node] to [username]`

**Examples:**
```
set ssh username for carrera to ishaan
configure nighthawk ssh as pi
update pi_ai ssh to use key ~/.ssh/id_ed25519
set carrera ssh key to default
```

---

## 12. Node Services

### list services
**Purpose:** Show services on a node (or all services).

**Syntax:** `show services on [node]`

**Alternatives:** `what services does [node] have`, `list all services`

---

### register preset
**Purpose:** Apply a named service bundle to a node.

**Syntax:** `register [node] as [preset]`

**Examples:**
```
register nighthawk as NAS
register pi-zero as media-player
set up drone-01 as drone
configure nighthawk as a NAS
```

**Presets:** nas, media-player, robot, esp32, web-server, drone

---

### add service
**Purpose:** Add a single named service to a node.

**Syntax:** `add [service] service to [node]`

**Examples:**
```
add samba service to nighthawk
nighthawk runs file-storage
add ssh service to carrera
```

---

### remove service
**Purpose:** Remove a service from a node.

**Syntax:** `remove [service] service from [node]`

---

### rename service
**Purpose:** Rename a service on a node.

**Syntax:** `rename service [old] to [new] on [node]`

---

## 13. Capability Execution

### execute capability
**Purpose:** Run a named capability on a node's service.

**Syntax:** `[action] on [node]`

**Examples:**
```
play music on nighthawk
pause music
stop the music
skip track on nighthawk
set volume to 50 on nighthawk
move drone-01 forward
stop rover
take a photo on pi5
start camera stream on pi5
stop camera stream on pi5
restart nginx on carrera
start mysql on nighthawk
read sensor on esp32-01
battery status on drone-01
```

**Capability namespaces:**

| Namespace | Capabilities |
|---|---|
| media | play, pause, stop, next, previous, volume |
| motion | forward, backward, stop, turn_left, turn_right, hover |
| camera | capture, stream, stream_stop |
| system | start, stop, restart, status, reload |
| sensor | read, calibrate |
| battery | status |
| gpio | set, get |
| navigation | goto, home, waypoint |
| audio | play, stop, volume |

**Risk levels:** `low` = execute immediately; `high`/`critical` = confirmation required.

---

## 14. Watch Officer

### show alerts
**Purpose:** Show all active Watch Officer alerts.

**Syntax:** `show alerts`

**Alternatives:** `active alerts`, `watch officer status`, `what alerts are active`, `show watch alerts`, `any alerts`

---

## 15. Desktop Awareness — Apps

### open app
**Purpose:** Launch any registered application.

**Syntax:** `open [app name]`

**Examples:**
```
open VS Code
launch KiCad
start Fusion 360
open Chrome
open obs
open unity hub
```

---

### open target (preference-aware)
**Purpose:** Open something — checks your saved preference first.

**Syntax:** `open [target]`

**Alternatives with modifier:**
```
open spotify         # uses your preference (web/app/folder)
open spotify web     # force web
open spotify app     # force app
open spotify folder  # force folder
open github          # opens github.com (web preference)
open CMD-CTR         # opens folder (folder preference)
```

---

### close app
**Purpose:** Gracefully close a running application.

**Syntax:** `close [app name]`

**Examples:**
```
close Bambu Studio
close Fusion 360
quit OBS
exit KiCad
```

---

### app status
**Purpose:** Check if an application is currently running.

**Syntax:** `is [app name] running`

**Examples:**
```
is Fusion running
app status OBS
is KiCad open
check if Chrome is running
```

---

### list running apps
**Purpose:** Show all registered apps that are currently running.

**Syntax:** `show running apps`

**Alternatives:** `what apps are running`, `list active applications`

---

### show app runtime
**Purpose:** Detailed runtime info for a specific app (PID, window title, launch time).

**Syntax:** `show app runtime [app]`

---

### scan apps
**Purpose:** Rescan Windows for installed applications.

**Syntax:** `scan installed apps`

**Alternatives:** `rescan apps`, `discover programs`

---

### show app
**Purpose:** Show registry metadata and launch candidates for a discovered app.

**Syntax:** `show app [name]`

**Examples:** `show app obs`, `show app unity`, `lookup app blender`

---

### list apps
**Purpose:** List all registered applications.

**Syntax:** `show installed apps`

**Alternatives:** `list my apps`, `what apps can you open`

---

### add app
**Purpose:** Manually register an application.

**Syntax:** `add [name] app at [executable path]`

**Example:** `add Blender app at C:\Program Files\Blender Foundation\Blender 4.2\blender.exe`

---

### set launch preference
**Purpose:** Set preferred open method for a target.

**Syntax:** `prefer [target] [web/desktop/folder]`

**Examples:**
```
prefer github web
prefer spotify desktop
default obs to app
```

---

### show launch target
**Purpose:** Show all configured targets and current preference for something.

**Syntax:** `show target [target]`

---

### list preferences
**Purpose:** Show all configured launch preferences.

**Syntax:** `show launch preferences`

---

### open URL
**Purpose:** Open an explicit URL or bare domain in the browser.

**Syntax:** `open [url]`

**Examples:**
```
open github.com
open https://youtube.com
visit stackoverflow.com
```

---

## 16. Desktop Awareness — Files & Locations

### find files
**Purpose:** Search trusted locations for files by name, extension, or description.

**Syntax:** `find [description] files`

**Examples:**
```
find STL files
find PCB files
find python files in CMD-CTR
find latest PDF
find files related to nighthawk
show all KiCad projects
find STL in DroneHive
```

---

### recent files
**Purpose:** Show newest files from trusted locations.

**Syntax:** `show recent files`

**Alternatives:** `latest files in [location]`, `recent [location] files`

---

### open location
**Purpose:** Open a trusted folder in Windows File Explorer.

**Syntax:** `open [location name] folder`

**Examples:**
```
open CMD-CTR folder
show Downloads
open DroneHive
where is Brain63
navigate to GitHub
open Desktop
```

---

### open KiCad project
**Purpose:** Resolve and launch a KiCad `.kicad_pro` project file.

**Syntax:** `open [project] project`

**Examples:**
```
open Hive-FC project
open MP3-Player project
open latest KiCad project
```

---

### add location
**Purpose:** Register a new trusted folder.

**Syntax:** `add [name] folder at [absolute path]`

**Example:** `add Cyberdeck folder at C:\Users\IshaanV\Documents\GitHub\Cyberdeck`

---

### list locations
**Purpose:** List all trusted locations.

**Syntax:** `list locations`

**Alternatives:** `show my folders`, `show trusted locations`, `what folders do you know`

---

## 17. System Info

### system specs
**Purpose:** Show your local machine's hardware specs.

**Syntax:** `what are my system specs`

**Alternatives:** `system configuration`, `cpu info`, `how much RAM`, `what GPU do I have`

---

### network info
**Purpose:** Show local network interfaces and IP addresses (your machine, not nodes).

**Syntax:** `what are my network interfaces`

**Alternatives:** `show my IP address`, `local IP`, `network adapters`

---

### running processes
**Purpose:** Show processes running on the local machine.

**Syntax:** `show running processes`

**Alternatives:** `what's running`, `list processes`, `top processes`

---

### run command
**Purpose:** Execute a shell command and return its output.

**Syntax:** `run [command]`

**Examples:**
```
run ipconfig
execute netstat -an
terminal systeminfo
run tasklist
run Get-Service
```

---

## 18. Semantic Memory

### semantic search
**Purpose:** Search past conversation history by meaning.

**Syntax:** `what did I say about [topic]`

**Examples:**
```
what did I say about DroneHive
find conversations about the pi5
did we discuss networking
previous discussions about the rover project
```

---

## 19. Scheduled Tasks

### schedule task
**Purpose:** Create a recurring Hermes autonomous task.

**Syntax:** `schedule task: [description] every [N] minutes`

**Examples:**
```
schedule task: check node health every 60 minutes
schedule a task to list all nodes every 30 minutes
schedule task: morning briefing every 1440 minutes
```

---

### list scheduled tasks
**Syntax:** `show scheduled tasks`

**Alternatives:** `list scheduled tasks`, `what scheduled tasks do I have`

---

### disable scheduled task
**Syntax:** `disable scheduled task [name]`

**Alternatives:** `pause task [name]`

---

### delete scheduled task
**Syntax:** `delete scheduled task [name]`

**Alternatives:** `remove task [name]`

---

## 20. Hardware Assistant — Inventory

> Type these in the **Hardware Assistant** panel on the Hardware Board page.

### add inventory (bought)
**Purpose:** Add components you purchased to inventory with preview.

**Syntax:** `I bought: [qty] [part name]` (multiple lines)

**Examples:**
```
I bought: 5 ESP32-S3

I bought:
5 ESP32-S3
3 MPU6050
2 VL53L0X
```

**Note:** Shows preview first. Type `confirm` to commit.

---

### add inventory (received)
```
I received:
10 NEMA17 motors
2 BMP280
```

---

### remove inventory
**Purpose:** Consume or remove components from inventory.

**Syntax:** `remove [qty] [part name]`

**Examples:**
```
remove 2 ESP32-S3
remove:
5 MPU6050
2 VL53L0X
```

---

### show inventory
```
show inventory
show all inventory
```

---

### show by category
```
show microcontrollers
show sensors
show displays
show motors
show radios
show batteries
show SBCs
show single board computers
```

---

### search inventory
```
how many ESP32 do I have
how many MPU6050 do I own
show ESP32
```

---

### recategorize inventory
**Purpose:** Auto-classify all `misc` category parts using the keyword classifier.

**Syntax:** `recategorize inventory`

**Alternatives:** `categorize inventory`, `clean inventory categories`

---

## 21. Hardware Assistant — Projects

### show all projects
```
show projects
list projects
list hardware projects
```

---

### show project detail
```
show project Rover
show project details for DroneHive
```

---

### create project
```
create project Rover
```

---

### show project requirements
```
hardware requirements for Rover
show Rover requirements
what parts does Rover need
what parts do I need for Rover
```

---

### set project requirements
```
Rover requires:
3 ESP32-S3
2 MPU6050
1 NEO-M8N GPS
```

---

### add part to project
```
add ESP32-S3 as required part for Rover
add ESP32-S3 as required part for Rover quantity 3
add MPU6050 as required part for Rover quantity 2 substitutes BMI270
```

---

### assign part to project
```
assign MPU6050 to DroneHive
```

---

### show parts for project
```
show components for Rover
show parts for DroneHive
```

---

## 22. Hardware Assistant — Build Readiness

### check build readiness
```
can I build Rover
can I make Rover
ready to build Rover
build readiness for Rover
```

### show buildable projects
```
what can I build right now
what projects can I build
which projects are ready to build
```

### show blocked projects
```
which projects are blocked
show blocked projects
```

### show missing parts
```
what parts am I missing for Rover
show missing parts for DroneHive
missing parts
```

### show inventory impact
```
what inventory will be consumed for Rover
what parts would Rover use
if I build Rover what inventory remains
```

---

## 23. Hardware Assistant — Orders

### create order (chat)
```
order 5 ESP32-S3
order 5 ESP32-S3 from Mouser
order ESP32-S3 x5 from AliExpress
order ESP32-S3 x10
```

### log order (multi-item)
```
log order:
5 ESP32-S3
10 MPU6050
vendor: Mouser
```

### show orders
```
show orders
show all orders
show active orders
what's on order
what is on order
show pending orders
show shipped orders
show recent deliveries
show delivered
```

### mark order delivered
```
mark order delivered
mark order [ID] as delivered
mark order ESP32-S3 delivered
```

---

## 24. Hardware Assistant — Procurement

### show order recommendations
```
what should I order
show order recommendations
recommended orders
generate order list
procurement list
```

### show low stock
```
show low stock
what am I running out of
stock alerts
low stock
```

### set reorder threshold
```
set reorder threshold for ESP32-S3 to 5
set threshold for MPU6050 to 3
```

### after-delivery forecast
```
what will be buildable after delivery
what becomes buildable after delivery
what can I build after orders arrive
project completion forecast
what projects become buildable
```

---

## 25. Hardware Assistant — BOM Import

### import BOM
```
import BOM /path/to/Widget_BOM.csv
import bom C:\Users\IshaanV\Documents\DroneHive_BOM.csv
```

### import inventory file
```
import inventory /path/to/stock.csv
load inventory C:\Users\IshaanV\Documents\stock.csv
```

### show imports
```
show BOMs
list BOMs
show imported BOMs
show BOM status
what components were imported
```

---

## 26. Hardware Assistant — Vision

### vision status
**Purpose:** Check which vision provider is configured and whether it's ready.

```
vision status
vision setup
vision provider
can you analyze images
can SILVIA analyze images
image analysis status
```

### analyze image
**Purpose:** Redirects to the Vision Analysis panel (upload must be done via the UI).

```
analyze this image
scan this image
detect components
```

---

## 27. Voice

### wake word
**Purpose:** Activate hands-free mode.

```
Hey SILVIA
```

**Notes:** Requires microphone access. Works when voice mode is enabled in the UI.

---

### voice diagnostics
Open the `/voice` page in the frontend to see:
- STT provider status (Speaches vs local Whisper)
- TTS provider status (Speaches/Kokoro vs local Piper)
- VAD (Silero) status
- Wake word detector status
- Test transcription
