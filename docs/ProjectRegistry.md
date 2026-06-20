# Project Registry

SILVIA maintains two separate project registries:

1. **Personal Projects** (`missions.db`) — software/research/maker projects tracked through the main assistant
2. **Hardware Projects** (`hardware.db`) — physical build projects with part requirements and build readiness

This document covers both, with clear distinction.

---

## Table of Contents

1. [Personal Projects](#personal-projects)
2. [Hardware Projects](#hardware-projects)
3. [Project Intelligence](#project-intelligence)
4. [Project Commands](#project-commands)

---

## Personal Projects

Personal projects track your current work at a high level: status, priority, notes, Brain63 link.

### Schema

```python
class Project:
    id: str            # UUID
    name: str          # "DroneHive", "Brain63", "CMD-CTR"
    status: str        # active | paused | complete | blocked
    priority: str      # critical | high | normal | low
    brain63_key: str   # Corresponding Obsidian note key (optional)
    notes: str         # Free text
    created_at: str    # ISO timestamp
    updated_at: str    # ISO timestamp
```

### Statuses

| Status | Meaning |
|---|---|
| `active` | Currently working on it |
| `paused` | Temporarily suspended |
| `blocked` | Waiting on external dependency |
| `complete` | Done |

### Brain63 Integration

If `brain63_key` is set, SILVIA can cross-reference the project with your Obsidian vault when answering questions about it. This is read-only — SILVIA cannot create or modify Brain63 notes.

### Creating Projects

```
create project DroneHive
add project Cyberdeck
new project MP3 Player priority high
start project DroneHive status active priority critical
```

### Viewing Projects

```
list projects
show projects
my projects
active projects
what projects are active
what projects do I have
show blocked projects
project health
how are my projects
```

### Updating Status

```
mark project DroneHive as complete
set project Cyberdeck to paused
project DroneHive is blocked
complete project DroneHive
```

### Project Health Reports

SILVIA generates a per-project health report using the `project_health` tool:

- Status and priority
- Open tasks linked to this project
- Active reminders for this project
- Related Watch Officer alerts
- Hardware readiness (if a matching hardware project exists)

```
project health
show project health
project status
health report
project overview
```

### Proactive Intelligence

SILVIA runs proactive daily scans and reports:

- **Morning briefing**: mentions active projects with open tasks
- **Weekly review**: projects touched vs. untouched this week
- **Forgotten items**: projects with no activity for 2+ weeks
- **Daily focus**: highest-priority project with most-due tasks

---

## Hardware Projects

Hardware projects extend the personal project concept with:
- A bill of materials (BOM) — required parts and quantities
- Real-time build readiness calculation against inventory
- Missing parts analysis
- Inventory impact simulation

### Schema

```python
class HardwareProject:
    id: str           # UUID short hash
    name: str         # "DroneHive", "Cyberdeck", "Rover"
    description: str
    status: str       # 10-state model (see below)
    priority: str     # low | normal | high | critical
    notes: str
    created_at: str
    updated_at: str

    # Derived fields (not stored, computed)
    part_count: int        # Total required part types
    readiness_pct: int     # 0-100 build readiness
    missing_count: int     # Part types with zero stock
```

### 10-State Status Model

Hardware projects have a richer status model reflecting physical build phases:

| Status | Phase |
|---|---|
| `planned` | Idea stage, no action taken |
| `researching` | Choosing components, reading datasheets |
| `designing` | Schematic/PCB layout, 3D modeling |
| `ordering` | Parts ordered, waiting |
| `waiting_for_parts` | Some parts arrived, waiting for rest |
| `building` | Actively assembling |
| `testing` | Hardware assembled, testing/debugging |
| `blocked` | Stuck on a problem |
| `completed` | Finished and working |
| `archived` | Retired or abandoned |

### Project-Part Links

Hardware projects maintain a bill of materials: a list of parts from inventory with required quantities.

```
project: DroneHive
├── ESP32-S3        × 3   (have: 5 ✓)
├── MPU6050         × 2   (have: 3 ✓)
├── NEO-M8N         × 1   (have: 0 ✗)  ← missing
└── VL53L0X         × 4   (have: 2 ✗)  ← short by 2
```

### Build Readiness

```
readiness_pct = parts_fully_covered / total_required_parts × 100
```

States:
- `ready` — 100% of required parts are in stock
- `missing_parts` — one or more required parts have insufficient stock
- `no_required_parts` — project has no BOM defined yet

---

## Project Intelligence

### Build Readiness Check

```
can I build DroneHive?
can I make Rover?
what can I build right now?
which projects can I build?
which projects are blocked?
build readiness for Cyberdeck
```

### Missing Parts Analysis

```
show missing parts
what am I missing for DroneHive?
missing parts for Rover
what parts does Cyberdeck need?
```

### Inventory Impact Simulation

What happens to your inventory if you build a project:

```
what inventory will be consumed by DroneHive?
if I build DroneHive what inventory remains?
what parts would DroneHive use?
```

### Order Recommendations

Based on all active projects' shortfalls:

```
what should I order?
order recommendations
show procurement list
```

### Project Priority Ranking

Rank projects by build readiness and priority:

```
what should I work on?
which project is closest to completion?
show project priorities
what can I build now?
```

---

## Project Commands

### Personal Projects

```
# Create
create project DroneHive
add project Cyberdeck priority high
new project MP3 Player

# View
list projects
show projects
active projects
project health
show project health
weekly review
morning briefing
forgotten items
daily focus

# Update
mark project DroneHive as complete
set project Cyberdeck to paused
project DroneHive is blocked

# Search semantic memory
what did I say about DroneHive?
find conversations about Brain63
did we discuss the rover build?
```

### Hardware Projects (via Hardware Assistant)

```
# Create
create project Rover
create project: DroneHive

# View
show projects
list all projects
show project DroneHive
show active projects

# Requirements
DroneHive requires:
3 ESP32-S3
2 MPU6050

# Build readiness
can I build DroneHive?
what can I build right now?
which projects are blocked?
show missing parts for DroneHive
what should I order?

# Update
update hardware project DroneHive to status building
```

---

## Related Documentation

- [HardwareBoard.md](HARDWARE_BOARD.md) — Hardware Board overview
- [InventoryRegistry.md](InventoryRegistry.md) — Inventory that backs build readiness
- [HardwareAssistant.md](HardwareAssistant.md) — Chat commands for hardware projects
