# SILVIA Hardware Board — Complete Guide

The Hardware Board is a dedicated full-page UI for managing all hardware-related operations: component inventory, hardware build projects, procurement orders, BOM imports, build readiness analysis, and vision-assisted inventory detection.

## Table of Contents

1. [Overview](#overview)
2. [Database Tables](#database-tables)
3. [Inventory Management](#inventory-management)
4. [Project Management](#project-management)
5. [Build Readiness System](#build-readiness-system)
6. [Procurement Engine](#procurement-engine)
7. [BOM Import Pipeline](#bom-import-pipeline)
8. [Hardware Assistant](#hardware-assistant)
9. [Vision Analysis (Phase 12F)](#vision-analysis-phase-12f)
10. [API Reference](#api-reference)
11. [Example Workflows](#example-workflows)

---

## Overview

Access the Hardware Board at `/hardware` in the frontend (click "Hardware" in the navigation).

The page is divided into:
- **Top panel (3-column grid):** Inventory | Projects | (Assistant + Imports + Orders)
- **Intelligence Section:** Build readiness, missing parts, order recommendations, project priorities
- **Procurement Section:** Active orders, deliveries, low stock, after-delivery forecast
- **Vision Analysis Section:** Image upload, component detection, inventory update

All data lives in `data/cmdctr.db`. All mutations go through the Hardware Assistant's preview→confirm flow.

---

## Database Tables

### `hw_inventory` — Component Inventory

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | 8-char UUID |
| `name` | TEXT | Component name (e.g. "ESP32-S3") |
| `normalized_name` | TEXT | Lowercased, punctuation-stripped for matching |
| `category` | TEXT | microcontroller, sensor, sbc, display, radio, motor, power, audio, storage, pcb, module, gps_gnss, misc |
| `subcategory` | TEXT | Optional sub-classification |
| `quantity` | INT | Units in stock |
| `status` | TEXT | in-stock, low-stock, out-of-stock, on-order |
| `location` | TEXT | Physical storage location (e.g. "Drawer 3") |
| `manufacturer` | TEXT | e.g. "Espressif" |
| `part_number` | TEXT | Manufacturer part number |
| `notes` | TEXT | Free-form notes |
| `datasheet_url` | TEXT | Link to datasheet |
| `reorder_threshold` | INT | Alert when quantity ≤ this value (0 = disabled) |
| `aliases` | TEXT | JSON array of alternative names |
| `created_at` | TEXT | ISO timestamp |
| `updated_at` | TEXT | ISO timestamp |

**Status auto-assignment:**
- quantity = 0 → `out-of-stock`
- quantity 1–4 → `low-stock`
- quantity ≥ 5 → `in-stock`

### `hw_projects` — Hardware Build Projects

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | 8-char UUID |
| `name` | TEXT | Project name |
| `status` | TEXT | See status model below |
| `priority` | TEXT | planned, low, normal, high, critical |
| `description` | TEXT | Project description |
| `notes` | TEXT | Free-form notes |
| `created_at` | TEXT | ISO timestamp |
| `updated_at` | TEXT | ISO timestamp |

**Project status model (10 states):**

| Status | Meaning |
|---|---|
| `planned` | Idea stage |
| `researching` | Researching components and design |
| `designing` | Active PCB/CAD/firmware design |
| `ordering` | Ordering parts |
| `waiting_for_parts` | Parts ordered, waiting on delivery |
| `building` | Assembly in progress |
| `testing` | Testing and debugging |
| `blocked` | Blocked by missing parts or other issue |
| `completed` | Build complete |
| `archived` | Retired/archived |

### `hw_project_parts` — Bill of Materials Links

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | 8-char UUID |
| `project_id` | TEXT FK | References `hw_projects.id` |
| `part_id` | TEXT FK | References `hw_inventory.id` |
| `quantity_required` | INT | Units required for one build |
| `is_required` | INT | 1 = required, 0 = optional |
| `acceptable_substitutes` | TEXT | JSON array of part names |
| `notes` | TEXT | Notes on this requirement |
| `source` | TEXT | How this requirement was added (e.g. "BOM import") |

### `hw_orders` — Procurement Orders

| Column | Type | Description |
|---|---|---|
| `id` | TEXT PK | 8-char UUID |
| `part_name` | TEXT | Component being ordered |
| `vendor` | TEXT | Supplier name (e.g. "Mouser", "AliExpress") |
| `quantity` | INT | Units ordered |
| `status` | TEXT | ordered, manufacturing, shipped, in_transit, delivered, cancelled |
| `notes` | TEXT | Order reference, notes |
| `expected_delivery` | TEXT | Expected delivery date |
| `date_received` | TEXT | Actual receipt date (set when received) |
| `created_at` | TEXT | ISO timestamp |

---

## Inventory Management

### Adding Components

Via Hardware Assistant:
```
I bought: 5 ESP32-S3

I bought:
5 ESP32-S3
3 MPU6050
2 VL53L0X

I received: 10 NEMA17 motors
```

Via the UI: Click the `+` button in the Inventory panel → fill in the Add Part form.

Via API:
```http
POST /api/hardware/inventory
Content-Type: application/json
{
  "name": "ESP32-S3",
  "category": "microcontroller",
  "quantity": 5,
  "manufacturer": "Espressif",
  "location": "Drawer 1"
}
```

### Removing / Consuming Components

```
remove 2 ESP32-S3
consume:
5 MPU6050
2 VL53L0X
```

### Viewing Inventory

```
show inventory
show all inventory
show microcontrollers
show sensors
show displays
```

### Auto-Classification

When a new part is added without a category (or with `misc`), the classifier runs:
- Pattern matching against known component names (ESP32, MPU6050, Raspberry Pi, etc.)
- Assigns category + subcategory with a confidence score
- Only applied when confidence ≥ 0.65

To bulk-reclassify all `misc` items:
```
recategorize inventory
```

### Reorder Thresholds

```
set reorder threshold for ESP32-S3 to 5
```

When `quantity ≤ reorder_threshold`, the part appears in Low Stock alerts.

---

## Project Management

### Creating a Project

Via Hardware Assistant:
```
create project Rover
```

Via UI: Click `+` in the Projects panel.

### Setting Bill of Materials

```
Rover requires:
3 ESP32-S3
2 MPU6050
1 NEO-M8N GPS

add ESP32-S3 as required part for Rover quantity 3 substitutes ESP32-C3
```

### Viewing Project Details

```
show project Rover
show Rover requirements
hardware requirements for Rover
what parts does Rover need
```

### Assigning Parts

```
assign MPU6050 to DroneHive
assign ESP32-S3 to Rover quantity 3
```

---

## Build Readiness System

### How It Works

`get_build_readiness(project_id)` compares each required part's `quantity_required` against the current inventory `quantity`:

1. For each part link: `available = inventory.quantity`
2. If `available ≥ quantity_required`: part is covered
3. If part is missing but an acceptable substitute is in stock: covered by substitute
4. `readiness_pct = (covered_parts / total_required_parts) * 100`
5. Status: `ready` (100%), `partial` (1–99%), `blocked` (0%), `no_required_parts`

### Commands

```
can I build Rover
can I make Rover
build readiness for Rover
ready to build Rover

what can I build right now
what projects can I build
which projects are blocked

what parts am I missing for Rover
show missing parts for DroneHive
missing parts

what inventory will be consumed for Rover
```

### Intelligence Section (UI)

The Intelligence Section shows four panels:
1. **Build Readiness** — all projects with readiness bars
2. **Missing Parts** — parts needed across all blocked projects
3. **Order Recommendations** — what to buy, ranked by urgency
4. **Project Priorities** — projects ranked by readiness + priority

---

## Procurement Engine

### Order Lifecycle

```
ordered → manufacturing → shipped → in_transit → delivered
                                                ↓
                                       cancelled (any stage)
```

### Creating Orders

```
order 5 ESP32-S3 from Mouser
order ESP32-S3 x10 from AliExpress

log order:
5 ESP32-S3
10 MPU6050
vendor: Mouser
```

### Receiving Deliveries

```
mark order delivered
mark order [ID] as delivered
mark order ESP32-S3 delivered
```

When an order is received:
1. Order status → `delivered`, `date_received` set
2. Inventory quantity increased by order quantity
3. Part status auto-updated

### Low Stock Monitoring

```
show low stock
stock alerts
what am I running out of
```

Only parts with `reorder_threshold > 0` appear here.

### After-Delivery Forecast

Simulates adding all active order quantities to inventory, then re-runs readiness for all projects:

```
what will be buildable after delivery
project completion forecast
```

Returns per-project: `becomes_buildable: true/false`, which parts are still missing.

### Procurement Section (UI)

- **Active Orders** — orders not yet delivered, with one-click ✓ receive button
- **Deliveries** — history of received orders
- **Low Stock** — items below reorder threshold
- **After-Delivery** — forecast after all pending orders arrive

---

## BOM Import Pipeline

### Supported Formats

| Format | Detection |
|---|---|
| KiCad BOM CSV | Columns: Reference, Value, Quantity |
| Generic inventory CSV | Columns: name/part, quantity/qty |
| Auto | `source_type=auto` detects format from headers |

### Importing

Via Hardware Assistant:
```
import BOM /path/to/Widget_BOM.csv
import inventory /path/to/stock.csv
```

Via UI: Click "Import" in the Imports panel → enter file path.

Via API:
```http
POST /api/hardware/imports
{
  "path": "C:/Users/IshaanV/Documents/DroneHive_BOM.csv",
  "source_type": "bom",
  "project": "DroneHive"
}
```

### What Happens on Import

1. File parsed according to detected format
2. Each part fuzzy-matched against existing inventory
3. Matched: quantity updated (or link created for BOM)
4. Unmatched: new inventory part created
5. If `project` specified: parts linked to that project
6. Import logged to `hw_imports` table

### Viewing Import History

```
show BOMs
show imported BOMs
show BOM status
```

---

## Hardware Assistant

The Hardware Assistant is a restricted chat interface on the Hardware Board. It handles **only hardware operations** — it cannot access nodes, calendar, projects, or any other SILVIA system.

### Routing Architecture

All routing is regex-based (no LLM). Commands are matched in priority order:

1. Confirm/cancel pending action
2. Blocked/buildable projects
3. Missing parts
4. Build readiness
5. Project requirements
6. Inventory impact
7. Delivery/order queries
8. Active orders
9. Project listing
10. BOM listing
11. Procurement queries
12. Inventory queries
13. Mutations (add/remove/order/import)
14. Help message

### Preview → Confirm Flow

All mutations show a preview:
```
User: I bought: 5 ESP32-S3
SILVIA: Preview:
  - ESP32-S3: 3 → 8 (category: microcontroller 95%)
  Reply `confirm` to apply, or `cancel`.

User: confirm
SILVIA: Inventory updated:
  - ESP32-S3: 3 → 8 [microcontroller]
```

This prevents accidental modifications. There is no way to skip the preview.

---

## Vision Analysis (Phase 12F)

### Setup

**Option A: Anthropic Vision (better accuracy)**
```bash
pip install anthropic>=0.50.0
# Add to .env:
ANTHROPIC_API_KEY=sk-ant-...
VISION_MODEL_ANTHROPIC=claude-haiku-4-5-20251001  # optional, default
```

**Option B: Ollama Vision (fully local)**
```bash
ollama pull llava
# No config needed — llava is the default ollama model
```

**Check status:**
```
vision status
```

### Workflow

1. Open Hardware Board → scroll to **Vision Analysis** section
2. Drag-and-drop or click to upload an image (JPEG, PNG, WebP, max 20 MB)
3. Click **Analyze Image**
4. Review detected components:
   - Green badge: HIGH confidence (≥ 85%)
   - Orange badge: MED confidence (65–85%)
   - Red badge: LOW confidence (< 65%)
   - Each row shows: `current qty → new total after adding`
5. Uncheck any items you don't want to add
6. Click **Confirm [N] items**
7. Inventory updates immediately

### Confidence Model

| Range | Badge | Pre-approved | Recommendation |
|---|---|---|---|
| ≥ 0.85 | HIGH | ✓ Yes | Accept unless visually wrong |
| 0.65–0.84 | MED | ✓ Yes | Review before confirming |
| < 0.65 | LOW | ✗ No | Manually review, treat as hint only |

Low-confidence items are **never auto-approved**. You must manually check them before confirming.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `VISION_PROVIDER` | `auto` | `auto` \| `anthropic` \| `ollama` |
| `ANTHROPIC_API_KEY` | — | Required for Anthropic provider |
| `VISION_MODEL_ANTHROPIC` | `claude-haiku-4-5-20251001` | Claude model for vision |
| `VISION_MODEL_OLLAMA` | `llava` | Ollama vision model |
| `VISION_CONFIDENCE_THRESHOLD` | `0.65` | Items below this are LOW confidence |

---

## API Reference

### Inventory

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/hardware/inventory` | List all parts (filter: category, search) |
| POST | `/api/hardware/inventory` | Create a part |
| GET | `/api/hardware/inventory/{id}` | Get part by ID |
| PUT | `/api/hardware/inventory/{id}` | Update part |
| DELETE | `/api/hardware/inventory/{id}` | Delete part |
| GET | `/api/hardware/categories` | Category summary |
| PATCH | `/api/hardware/inventory/{id}/threshold` | Set reorder threshold |

### Projects

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/hardware/projects` | List projects (filter: status) |
| POST | `/api/hardware/projects` | Create project |
| GET | `/api/hardware/projects/{id}` | Get project with parts |
| PUT | `/api/hardware/projects/{id}` | Update project |
| DELETE | `/api/hardware/projects/{id}` | Delete project |
| GET | `/api/hardware/projects/{id}/parts` | List project parts |
| POST | `/api/hardware/projects/{id}/parts` | Assign part to project |
| DELETE | `/api/hardware/projects/{id}/parts/{part_id}` | Unassign part |
| GET | `/api/hardware/inventory/{id}/projects` | Projects using a part |
| GET | `/api/hardware/projects/{id}/impact` | Inventory impact analysis |

### Orders

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/hardware/orders` | List orders (filter: status) |
| POST | `/api/hardware/orders` | Create order |
| GET | `/api/hardware/orders/{id}` | Get order |
| PATCH | `/api/hardware/orders/{id}/status` | Update order status |
| DELETE | `/api/hardware/orders/{id}` | Delete order |
| POST | `/api/hardware/orders/{id}/receive` | Receive order (update inventory) |

### Intelligence

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/hardware/intelligence/readiness` | Build readiness for all projects |
| GET | `/api/hardware/intelligence/readiness/{id}` | Build readiness for one project |
| GET | `/api/hardware/intelligence/missing` | Missing parts across all projects |
| GET | `/api/hardware/intelligence/blocked` | Blocked projects |
| GET | `/api/hardware/intelligence/recommendations` | Order recommendations |
| GET | `/api/hardware/intelligence/priority` | Project priority ranking |
| GET | `/api/hardware/intelligence/low-stock` | Low stock alerts |
| GET | `/api/hardware/intelligence/after-delivery` | After-delivery readiness forecast |

### Imports

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/hardware/imports` | List import history |
| POST | `/api/hardware/imports` | Import BOM or inventory file |
| GET | `/api/hardware/imports/{id}/items` | List items from an import |

### Assistant & Vision

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/hardware/assistant` | Hardware Assistant chat |
| GET | `/api/hardware/vision/status` | Vision provider status |
| POST | `/api/hardware/vision/analyze` | Analyze image (multipart/form-data) |
| POST | `/api/hardware/vision/apply` | Apply approved detections to inventory |

---

## Example Workflows

### Workflow 1: New Project from BOM

```
1. Create project
   → Hardware Assistant: create project DroneHive

2. Import BOM
   → Hardware Assistant: import BOM C:\Documents\DroneHive_BOM.csv

3. Check what's missing
   → Hardware Assistant: what parts am I missing for DroneHive

4. Order missing parts
   → Hardware Assistant: order 5 ESP32-S3 from Mouser
   → confirm
   → Hardware Assistant: order 3 MPU6050 from AliExpress
   → confirm

5. Wait for delivery, then receive
   → Hardware Assistant: mark order ESP32-S3 delivered
   → confirm

6. Check build readiness
   → Hardware Assistant: can I build DroneHive
```

### Workflow 2: Inventory from Workbench Photo

```
1. Open Hardware Board → Vision Analysis section
2. Drag image of components onto the drop zone
3. Click "Analyze Image"
4. Review detections:
   - ESP32-S3 x3 — HIGH 94% — checked ✓
   - MPU6050 x2 — MED 71% — checked ✓
   - Unknown board — LOW 42% — unchecked ✗
5. Click "Confirm 2 items"
6. Inventory updated: ESP32-S3 +3, MPU6050 +2
```

### Workflow 3: Procurement Planning Session

```
1. What should I order?
   → Hardware Assistant: what should I order
   → Returns ranked list with urgency and affected projects

2. Check if anything is low stock
   → Hardware Assistant: show low stock

3. Forecast what becomes buildable
   → Hardware Assistant: what will be buildable after delivery

4. Set threshold to prevent future stockouts
   → Hardware Assistant: set reorder threshold for ESP32-S3 to 5
   → confirm
```
