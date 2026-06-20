# Inventory Registry

The hardware inventory registry tracks every component, module, and part in your possession. It is the source of truth for build readiness, procurement, and order tracking.

---

## Table of Contents

1. [Part Schema](#part-schema)
2. [Categories](#categories)
3. [Auto-Classification](#auto-classification)
4. [Fuzzy Matching](#fuzzy-matching)
5. [Status Tracking](#status-tracking)
6. [Reorder Thresholds](#reorder-thresholds)
7. [Inventory Commands](#inventory-commands)
8. [API Reference](#api-reference)

---

## Part Schema

```python
class Part:
    id: str              # UUID short hash ("8c535e9d")
    name: str            # "ESP32-S3", "MPU6050", "NEO-M8N GPS"
    normalized_name: str # "esp32s3" — for fuzzy matching
    aliases: str         # JSON array of alternate names
    category: str        # See Categories below
    subcategory: str     # Sub-classification (e.g. "IMU" for sensor)
    quantity: int        # Current stock count
    status: str          # in-stock | low-stock | out-of-stock | on-order
    reorder_threshold: int  # Alert when quantity ≤ this value (0 = disabled)
    location: str        # Physical location ("drawer 3", "shelf B")
    manufacturer: str    # "Espressif", "InvenSense"
    part_number: str     # Manufacturer part number
    notes: str           # Free text
    datasheet_url: str   # Link to datasheet
    created_at: str      # ISO timestamp
    updated_at: str      # ISO timestamp
```

---

## Categories

| Category | Description | Examples |
|---|---|---|
| `microcontroller` | MCUs and development boards | ESP32-S3, Arduino Nano, STM32 |
| `sbc` | Single-board computers | Raspberry Pi 4B, Jetson Nano |
| `sensor` | Sensors (all types) | MPU6050, BMP280, VL53L0X |
| `display` | Display modules | SSD1306 OLED, ILI9341 TFT |
| `radio` | Wireless modules | NRF24L01, SX1276 LoRa, HC-05 BLE |
| `motor` | Motor drivers, servos, ESCs | L298N, BLHeli ESC, MG996R |
| `power` | Power management | LiPo 3S, BEC, AMS1117-3.3 |
| `gps_gnss` | GPS and GNSS modules | NEO-M8N, NEO-9M, BN-880 |
| `audio` | Audio hardware | MAX98357A, PAM8403 |
| `storage` | Storage devices | SD card module, W25Q128 flash |
| `pcb` | Custom PCBs | Hive-FC v1.2, custom breakout |
| `module` | Generic modules | DS3231 RTC, MCP2515 CAN |
| `misc` | Unclassified | Anything not matched above |

### Subcategories (for `sensor`)

| Subcategory | Examples |
|---|---|
| `IMU` | MPU6050, ICM-42688, LSM6DS3 |
| `barometer` | BMP280, BMP388, MS5611 |
| `distance` | VL53L0X, HC-SR04, LIDAR-Lite |
| `temperature` | DHT22, DS18B20, SHT31 |
| `GPS/GNSS` | NEO-M8N, BN-220, u-blox M10 |
| `current` | INA219, ACS712 |
| `color` | TCS34725 |
| `humidity` | DHT22, SHT31 |

---

## Auto-Classification

When a new part is added, SILVIA automatically classifies it using the `hardware_category_classifier` — a rule-based system with no LLM involved.

### How It Works

1. Part name is normalized (lowercase, no spaces/punctuation)
2. Matched against keyword patterns:
   - `esp32`, `esp8266`, `arduino`, `stm32` → `microcontroller`
   - `raspberry pi`, `jetson`, `orange pi` → `sbc`
   - `mpu6050`, `bmp280`, `vl53`, `dht` → `sensor`
   - `ssd1306`, `ili9341`, `oled`, `tft` → `display`
   - `nrf24`, `sx1276`, `lora`, `hc-05`, `hc-06` → `radio`
   - `neo-m8`, `neo-9m`, `gps`, `gnss` → `gps_gnss`
   - etc.
3. Confidence score calculated (0.0–1.0)
4. If confidence ≥ 0.65: category applied automatically
5. If confidence < 0.65: category stays `misc`

### Classification Preview

On inventory add, SILVIA shows the proposed category:

```
Inventory add preview:
- ESP32-S3: 0 → 5 (category: microcontroller 95%)
- MPU6050: 0 → 3 (category: sensor / IMU 92%)
- mystery_board: 0 → 1 (category unclear: misc unless confirmed)
```

### Bulk Recategorization

Fix all `misc` items at once:

```
recategorize inventory
clean up categories
categorize inventory
```

Shows preview of all confident reclassifications, then asks for confirmation.

---

## Fuzzy Matching

SILVIA uses fuzzy matching to find parts by name. This handles:
- Abbreviations: `ESP32` matches `ESP32-S3`, `ESP32-C3`
- Spaces/dashes: `ESP32 S3` matches `ESP32-S3`
- Case insensitivity: `esp32-s3` matches `ESP32-S3`
- Partial matches: `MPU` matches `MPU6050`

**`find_part_smart(query)`** is used everywhere:
- Inventory lookups
- Project requirement checks
- Order-to-inventory matching (receive order → credit quantity)
- Vision analysis enrichment

Priority order: exact name match → normalized name match → alias match → partial token match.

---

## Status Tracking

Status is automatically computed from quantity:

| Quantity | Status |
|---|---|
| 0 | `out-of-stock` |
| 1–3 | `low-stock` |
| 4+ | `in-stock` |

Status is recalculated on every quantity update (add, remove, receive order).

Special case: `on-order` — set manually when a purchase order is placed (future: auto-set when order is active).

---

## Reorder Thresholds

Each part can have a reorder threshold: a minimum quantity below which a low-stock alert is raised.

### Setting Thresholds

```
set reorder threshold for ESP32-S3 to 5
set threshold for MPU6050 to 3
```

This sets `reorder_threshold = 5` on ESP32-S3. When quantity ≤ 5, the part appears in low-stock alerts.

### Viewing Low Stock

```
show low stock
what am I running out of
stock alerts
```

Shows: part name, current quantity, threshold, shortfall.

### API

```bash
PATCH /api/hardware/inventory/{part_id}/threshold
{ "threshold": 5 }
```

---

## Inventory Commands

### Adding Parts

```
# Single format
I bought: 5 ESP32-S3
I received: 3 MPU6050
add: 2 VL53L0X
add 5 ESP32-S3

# Multi-item format
I bought:
5 ESP32-S3
3 MPU6050
1 NEO-M8N GPS module

# With vendor context
I received: 10 resistors 100ohm from AliExpress
```

### Removing / Consuming Parts

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
show motors
show power components
show SBCs
how many ESP32-S3 do I have
how many sensors do I own
```

### Searching

Via main SILVIA assistant:
```
show components
search hardware gps
find IMU sensors
search component nrf
how many esp32 do I own
hardware summary
show hardware inventory
```

### Categories

```
show microcontrollers
show sensors
show GPS
show radios
show displays
show motors
show power
```

### Recategorize

```
recategorize inventory
categorize inventory
clean up categories
reclassify inventory
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/hardware/inventory` | GET | List all parts (filter: `?category=`, `?search=`) |
| `POST /api/hardware/inventory` | POST | Create a new part |
| `GET /api/hardware/inventory/{id}` | GET | Get a specific part |
| `PUT /api/hardware/inventory/{id}` | PUT | Update part fields |
| `DELETE /api/hardware/inventory/{id}` | DELETE | Delete a part |
| `GET /api/hardware/categories` | GET | Count per category |
| `PATCH /api/hardware/inventory/{id}/threshold` | PATCH | Set reorder threshold |
| `GET /api/hardware/intelligence/low-stock` | GET | Parts below threshold |
| `GET /api/hardware/summary` | GET | Overall inventory summary |

---

## Vision-Assisted Inventory (Phase 12F)

Upload an image to automatically detect components:

```
POST /api/hardware/vision/analyze  (multipart image)
→ { detections: [...], high_confidence: [...], low_confidence: [...] }

POST /api/hardware/vision/apply
body: { detections: [{ name, quantity, category, ... }] }
→ [ { action: "updated"|"created", name, previous_qty, new_qty } ]
```

The Vision Panel in the Hardware Board UI provides a drag-and-drop interface with preview, confidence indicators, and per-item approval toggles.

Providers:
- **Anthropic Claude Vision** (`ANTHROPIC_API_KEY` set + `pip install anthropic`)
- **Ollama llava** (`ollama pull llava`, no API key needed)

---

## Related Documentation

- [HardwareBoard.md](HARDWARE_BOARD.md) — Full Hardware Board guide
- [HardwareAssistant.md](HardwareAssistant.md) — Chat commands
- [ProjectRegistry.md](ProjectRegistry.md) — Projects that use inventory
