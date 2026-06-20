# Hardware Assistant

The Hardware Assistant is a domain-restricted chat interface embedded in the Hardware Board. It understands natural language for inventory, project, order, and procurement management — and nothing else.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Routing Logic](#routing-logic)
3. [Mutation Preview → Confirm Flow](#mutation-preview--confirm-flow)
4. [Inventory Commands](#inventory-commands)
5. [Project Commands](#project-commands)
6. [Build Readiness Commands](#build-readiness-commands)
7. [Order Commands](#order-commands)
8. [Procurement Commands](#procurement-commands)
9. [BOM Import Commands](#bom-import-commands)
10. [Vision Commands](#vision-commands)
11. [Error Cases](#error-cases)
12. [Extending the Assistant](#extending-the-assistant)

---

## Architecture

The Hardware Assistant is a **separate service** from SILVIA's main assistant. It runs at `POST /api/hardware/assistant` and is handled by `HardwareAssistantService`.

```
User types in HW Assistant chat box
          │
          ▼
POST /api/hardware/assistant
    { message, pending_action }
          │
          ▼
HardwareAssistantService.handle()
          │
    ┌─────▼──────────────────────────┐
    │         Route matching         │
    │   (priority-ordered regex)     │
    └──────────────┬─────────────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
    Query routes        Mutation routes
    (read-only)         (plan_mutation)
          │                 │
          ▼                 ▼
    _info() response   _preview_response()
                       (pending_action set)
                            │
                    User types "confirm"
                            │
                            ▼
                    execute(pending_action)
                            │
                            ▼
                    _done() response
```

**Key design constraint:** The Hardware Assistant never calls an LLM. All routing is pure regex + deterministic logic. This makes it fast, reliable, and impossible to hallucinate.

---

## Routing Logic

Routes are matched in priority order. More specific patterns must appear before generic catch-alls:

1. `which projects are blocked` → `_blocked_projects()`
2. `what can I build right now` → `_buildable_projects()`
3. `missing parts for X` → `_missing_parts()`
4. `can I build/make X` → `_build_readiness()`
5. `requirements for X` / `what parts does X need` → `_show_project()`
6. `show imported BOMs` → `_show_imports()`
7. `inventory will be consumed` → `_inventory_impact()`
8. `show recent deliveries` → `_show_orders("delivered")`
9. `show active orders` → `_show_active_orders()`
10. `show orders` → `_show_orders("")`
11. `show project <name>` → `_show_project()`
12. `show projects` (generic) → `_show_projects()`
13. `show BOMs` → `_show_imports()`
14. `what should I order` → `_show_recommendations()`
15. `show low stock` → `_show_low_stock()`
16. `what will be buildable after delivery` → `_after_delivery_readiness()`
17. `show inventory` → `_show_all_inventory()`
18. `show <query>` (catch-all) → `_show_inventory()`
19. `how many X do I have` → `_show_inventory()`
20. Mutation patterns (add, remove, order, create, assign...) → `plan_mutation()`
21. Fallback → help message

---

## Mutation Preview → Confirm Flow

Any command that changes data goes through a two-step preview/confirm cycle.

### Step 1: Preview

SILVIA shows what will change without committing:

```
User: I bought: 3 ESP32-S3, 5 MPU6050

SILVIA: Inventory add preview:
- ESP32-S3: 1 → 4 (category: microcontroller 95%)
- MPU6050: 0 → 5 (category: sensor 92%)

Reply `confirm` to apply, or `cancel`.
```

### Step 2: Confirm or Cancel

```
User: confirm

SILVIA: Inventory updated:
- ESP32-S3: 1 → 4 [microcontroller]
- MPU6050: 0 → 5 [sensor]
```

Or:
```
User: cancel

SILVIA: Cancelled. No hardware registry changes were made.
```

### Pending Action State

The `pending_action` object is passed back to the frontend and re-sent on the next message:

```json
{
  "ok": true,
  "reply": "Inventory add preview:\n- ESP32-S3: 1 → 4...",
  "pending_action": {
    "type": "bulk_add_inventory",
    "items": [{"name": "ESP32-S3", "quantity": 3}]
  },
  "committed": false
}
```

---

## Inventory Commands

### Adding Parts

```
I bought: 5 ESP32-S3, 3 MPU6050
I received: 2 VL53L0X
received: 10 resistors 100ohm
add: 3 BMP280 sensors
add 5 ESP32-S3
```

Multi-item format:
```
I bought:
5 ESP32-S3
3 MPU6050
2 BMP280
```

### Removing Parts

```
remove 2 ESP32-S3
consume 3 MPU6050
used 1 VL53L0X
remove: 2 resistors
```

### Viewing Inventory

```
show inventory
show all inventory
show microcontrollers
show sensors
show GPS modules
show displays
show radios
how many ESP32-S3 do I have
how many sensors do I own
show all microcontrollers
```

### Auto-categorization

When adding a new part, the Hardware Assistant automatically classifies it using the `hardware_category_classifier` (rule-based, no LLM):

```
ESP32-S3 → microcontroller (95%)
MPU6050  → sensor / IMU (92%)
NEO-M8N  → GPS/GNSS (98%)
SSD1306  → display (87%)
```

Categories:
- `microcontroller` — ESP32, Arduino, STM32, ATmega
- `sbc` — Raspberry Pi, Jetson, Orange Pi
- `sensor` — IMU, GPS/GNSS, pressure, distance, temperature
- `display` — OLED, TFT, e-paper
- `radio` — LoRa, NRF24, BLE, CC2500
- `motor` — servo, stepper, ESC
- `power` — LiPo, BEC, voltage regulator
- `pcb` — custom boards
- `misc` — unclassified

### Recategorize Inventory

Fix all `misc` items in one shot:
```
recategorize inventory
categorize inventory
clean up categories
```

Shows a preview of confident category assignments, then ask for confirmation.

---

## Project Commands

### Creating Projects

```
create project Rover
create project DroneHive
create project: Cyberdeck
```

### Viewing Projects

```
show projects
list all projects
show active projects
show projects with status building
list hardware projects
show project Rover
show project DroneHive
show components for DroneHive
show parts for Rover
hardware requirements for DroneHive
show DroneHive requirements
what parts does Rover need
what does DroneHive require
```

### Adding Requirements

```
# Add requirements using project: syntax
DroneHive requires:
3 ESP32-S3
2 MPU6050
1 NEO-M8N

# Add single required part
add ESP32-S3 as required part for DroneHive quantity 2
add ESP32-S3 as required part for DroneHive quantity 2 substitutes ESP32-C3, ESP32
```

### Assigning Parts

```
assign MPU6050 to DroneHive
assign ESP32-C3 to Cyberdeck
assign MPU6050 to DroneHive quantity 3
```

---

## Build Readiness Commands

```
can I build Rover
can I make DroneHive
can I build Cyberdeck?
ready to build Rover?
build readiness for DroneHive
what can I build right now
which projects can I build
which projects are blocked
what projects can I make now
```

**Output example:**
```
No. DroneHive is 66% ready (missing_parts).
Missing:
- NEO-M8N ×1 (need:1 available:0)
Available:
- ESP32-S3 need:3 available:5
- MPU6050 need:2 available:3
```

---

## Order Commands

### Creating Orders

```
order 5 ESP32-S3
order 10 MPU6050 from AliExpress
order 3 VL53L0X from Mouser
order ESP32-S3 x5 from Digikey
```

### Viewing Orders

```
show orders
show all orders
show active orders
show pending orders
show recent deliveries
what's on order
what is on order
```

### Logging Orders (multi-item)

```
log order:
vendor: AliExpress
5 ESP32-S3
3 MPU6050
2 BMP280
```

### Marking Delivered

```
mark order delivered
mark order ESP32-S3 delivered
mark order ABC123 delivered
mark order as delivered
```

---

## Procurement Commands

### Order Recommendations

```
what should I order
order recommendations
recommended orders
generate order list
create procurement list
show procurement list
```

Shows parts to order ranked by urgency (CRITICAL → HIGH → normal), based on shortfalls across all active projects.

### Low Stock Alerts

```
show low stock
what am I running out of
low stock alert
stock alerts
```

Shows parts below their reorder threshold.

### Setting Reorder Thresholds

```
set reorder threshold for ESP32-S3 to 5
set threshold for MPU6050 to 3
```

Threshold = minimum quantity before a low-stock alert fires.

### After-Delivery Readiness Forecast

```
what will be buildable after delivery
what projects become buildable after delivery
project completion forecast
what can I build after orders land
```

Simulates inventory after all active orders arrive and reports which projects would become build-ready.

---

## BOM Import Commands

### Import a BOM

```
import BOM /path/to/bom.csv
import BOM C:\Projects\DroneHive\bom.csv
```

### View Imports

```
show BOMs
show imports
list imports
show imported BOMs
show BOM status
what components were imported
```

Supported formats: CSV (KiCad and generic), with columns: `Ref`, `Quantity`, `Part`, `Manufacturer Part Number`, etc.

---

## Vision Commands

Vision requires either Anthropic API key or Ollama `llava` model.

```
vision status              # Check vision provider configuration
analyze this image         # Redirect to Vision Panel in UI
can you analyze images     # Check vision availability
image analysis status      # Same as vision status
```

For actual image analysis, use the Vision Analysis panel in the Hardware Board UI — drag and drop an image to start.

---

## Error Cases

| Situation | Response |
|---|---|
| Project not found | "No hardware project found matching `X`." |
| Part not found for order | "No part found matching `X`." |
| No requirements set | "I do not have requirements recorded for X yet. Add requirements manually or import a BOM." |
| No missing parts | "No missing parts for X." |
| No inventory items | "No inventory parts found matching `X`." |
| Already have a pending action | "I have a pending preview. Reply `confirm` to apply it, or `cancel`." |
| Unrecognized command | "I can manage hardware inventory, projects, orders, and BOMs only. Try `I bought:`, `remove 2 ESP32-S3`..." |

---

## Extending the Assistant

To add a new read-only route:

1. Add a pattern check in `handle()` in `hardware_assistant_service.py`, **before** the catch-all `^show\s+`
2. Add the corresponding `_method_name()` that returns `_info(reply, data)`

To add a new mutation:

1. Add pattern to `plan_mutation()` → returns a dict with `type: "my_action"`, plus args
2. Add preview case to `preview()` → returns `_preview_response()`
3. Add execute case to `execute()` → calls `self.hardware.*` and returns `_done()`

**Critical rule:** Always insert specific patterns before catch-all patterns. The `^show\s+` catch-all must always be last in the read-only dispatch block.

---

## Related Documentation

- [HardwareBoard.md](HARDWARE_BOARD.md) — Full Hardware Board guide
- [InventoryRegistry.md](InventoryRegistry.md) — Inventory system details
- [ProjectRegistry.md](ProjectRegistry.md) — Project system details
