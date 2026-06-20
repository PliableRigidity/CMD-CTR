"""Engineering Planner — Phase 15B.

Transforms SILVIA from a reactive project tracker into an engineering
co-engineer that can design projects, generate BOMs, suggest architectures,
estimate gaps, and create projects automatically.

All recommendations are inventory-aware: the planner checks what exists
in SILVIA's hardware registry, orders, knowledge graph, project memory,
digital twin, and Brain63 before suggesting anything.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional

logger = logging.getLogger("silvia.engineering_planner")

_DIFFICULTY = {"trivial": 1, "easy": 2, "moderate": 3, "hard": 4, "expert": 5}

# ── Project Templates ───────────────────────────────────────────────────────

TEMPLATES: dict[str, dict[str, Any]] = {
    "gps-tracker": {
        "name": "GPS Tracker",
        "description": "Portable GPS location tracker with wireless reporting.",
        "difficulty": "moderate",
        "tags": ["gps", "iot", "wireless"],
        "architecture": {
            "purpose": "Track location and transmit coordinates wirelessly.",
            "components": ["Microcontroller (ESP32)", "GPS Module (NEO-6M/NEO-M8N)", "LoRa Radio (RFM95W) or GSM Module", "LiPo Battery + Charger", "Antenna (GPS + LoRa)", "Enclosure"],
            "connections": "ESP32 → GPS (UART) → LoRa (SPI) → Battery (power)",
            "firmware": ["GPS NMEA parsing", "LoRa packet transmission", "Sleep mode for battery life", "Geofencing alerts"],
        },
        "phases": [
            {"name": "Electronics", "items": ["ESP32 dev board", "GPS module (NEO-6M)", "LoRa radio (RFM95W)", "LiPo battery 1000mAh", "LiPo charger module", "GPS antenna", "LoRa antenna", "Breadboard + jumper wires"]},
            {"name": "Firmware", "items": ["GPS NMEA parser", "LoRa transmit code", "Sleep/wake cycle", "LED status indicators"]},
            {"name": "Integration", "items": ["Receiver node or gateway", "Data logging", "Map visualization"]},
            {"name": "Enclosure", "items": ["3D-printed case", "Weatherproofing"]},
        ],
    },
    "rover": {
        "name": "Rover",
        "description": "Autonomous ground vehicle with obstacle avoidance and telemetry.",
        "difficulty": "hard",
        "tags": ["robotics", "autonomous", "rover"],
        "architecture": {
            "purpose": "Navigate terrain autonomously while streaming telemetry.",
            "components": ["Raspberry Pi 4/5 or Jetson Nano", "Motor driver (L298N/TB6612)", "DC motors + wheels (4WD chassis)", "LiDAR or ultrasonic sensors", "Camera module", "IMU (MPU6050/BNO055)", "LiPo battery pack", "Power distribution board", "Chassis/frame"],
            "connections": "Pi → Motor Driver → Motors | Pi → LiDAR/Ultrasonic → Obstacle map | Pi → Camera → CV pipeline | Pi → IMU → Orientation",
            "firmware": ["Motor control + PID", "Obstacle avoidance", "Path planning", "Telemetry streaming", "Remote control fallback"],
        },
        "phases": [
            {"name": "Chassis & Power", "items": ["4WD chassis kit", "DC motors (4x)", "Wheels (4x)", "LiPo battery 3S 5000mAh", "Power distribution board", "Voltage regulators"]},
            {"name": "Electronics", "items": ["Raspberry Pi 4/5", "Motor driver L298N", "IMU MPU6050", "Ultrasonic sensors (3x)", "Camera module", "Wiring harness"]},
            {"name": "Firmware", "items": ["Motor control library", "PID controller", "Sensor fusion", "Obstacle avoidance algorithm"]},
            {"name": "Autonomy", "items": ["Path planning", "SLAM or visual odometry", "Waypoint navigation"]},
            {"name": "Telemetry", "items": ["WiFi/LoRa link", "Dashboard", "Remote E-stop"]},
        ],
    },
    "sensor-node": {
        "name": "Sensor Node",
        "description": "Wireless environmental sensor with long-range radio.",
        "difficulty": "easy",
        "tags": ["iot", "sensor", "wireless"],
        "architecture": {
            "purpose": "Measure environmental data and transmit to a gateway.",
            "components": ["ESP32 or Arduino Pro Mini", "LoRa Radio (RFM95W)", "Temperature/Humidity sensor (BME280/DHT22)", "LiPo battery + solar panel (optional)", "Antenna"],
            "connections": "MCU → BME280 (I2C) → LoRa (SPI) → Battery",
            "firmware": ["Sensor read loop", "LoRa packet format", "Deep sleep", "Battery voltage monitoring"],
        },
        "phases": [
            {"name": "Electronics", "items": ["ESP32 dev board", "BME280 sensor", "LoRa radio RFM95W", "LoRa antenna", "LiPo battery 2000mAh", "Solar panel (optional)", "Charge controller (optional)"]},
            {"name": "Firmware", "items": ["BME280 I2C driver", "LoRa transmit", "Deep sleep cycle", "Battery monitor"]},
            {"name": "Gateway", "items": ["Gateway node (ESP32 + LoRa)", "MQTT bridge", "Data storage"]},
        ],
    },
    "lora-node": {
        "name": "LoRa Node",
        "description": "Long-range LoRa communication node for mesh networking.",
        "difficulty": "moderate",
        "tags": ["lora", "wireless", "mesh"],
        "architecture": {
            "purpose": "Long-range wireless communication for data relay or mesh.",
            "components": ["ESP32 or STM32", "LoRa Radio (RFM95W/SX1276)", "Antenna (868/915MHz)", "LiPo battery", "OLED display (optional)"],
            "connections": "MCU → LoRa (SPI) → Antenna | MCU → OLED (I2C)",
            "firmware": ["LoRa send/receive", "Packet routing", "Mesh protocol (optional)", "Display status"],
        },
        "phases": [
            {"name": "Electronics", "items": ["ESP32 dev board", "LoRa radio RFM95W", "LoRa antenna 868/915MHz", "LiPo battery", "OLED display SSD1306", "Breadboard + wires"]},
            {"name": "Firmware", "items": ["LoRa init + config", "Send/receive handlers", "Packet format", "Mesh routing (optional)"]},
            {"name": "Deployment", "items": ["Enclosure", "Mounting hardware", "Range testing"]},
        ],
    },
    "environmental-monitor": {
        "name": "Environmental Monitor",
        "description": "Multi-sensor environmental monitoring station.",
        "difficulty": "moderate",
        "tags": ["environment", "sensor", "monitoring"],
        "architecture": {
            "purpose": "Continuously monitor air quality, temperature, humidity, pressure, and light.",
            "components": ["ESP32 or Raspberry Pi", "BME280 (temp/humidity/pressure)", "PMS5003 (particulate matter)", "MQ-135 (air quality)", "BH1750 (light)", "OLED or e-ink display", "MicroSD card module", "Power supply"],
            "connections": "MCU → BME280 (I2C) → PMS5003 (UART) → MQ-135 (ADC) → BH1750 (I2C) → Display → SD card (SPI)",
            "firmware": ["Multi-sensor polling loop", "Data logging to SD", "WiFi upload", "Display dashboard", "Alert thresholds"],
        },
        "phases": [
            {"name": "Sensors", "items": ["BME280 sensor", "PMS5003 air quality sensor", "MQ-135 gas sensor", "BH1750 light sensor"]},
            {"name": "Electronics", "items": ["ESP32 dev board", "OLED display", "MicroSD module", "Power supply 5V", "PCB or breadboard"]},
            {"name": "Firmware", "items": ["Sensor drivers", "Data logging", "WiFi upload", "Display rendering"]},
            {"name": "Enclosure", "items": ["Weather-resistant case", "Ventilation for sensors", "Mounting bracket"]},
        ],
    },
    "ai-edge-device": {
        "name": "AI Edge Device",
        "description": "Edge computing device for on-device ML inference.",
        "difficulty": "hard",
        "tags": ["ai", "ml", "edge"],
        "architecture": {
            "purpose": "Run ML models locally for real-time inference (vision, audio, or sensor data).",
            "components": ["Jetson Nano/Orin or Raspberry Pi 5 + Coral TPU", "Camera module (for vision)", "Microphone (for audio)", "Display (HDMI or OLED)", "NVMe SSD or SD card", "Active cooling", "Power supply (5V 4A+)"],
            "connections": "SBC → Camera (CSI/USB) → ML framework → Display | SBC → Coral TPU (USB) → Inference",
            "firmware": ["Model deployment (TensorFlow Lite / ONNX)", "Camera pipeline", "Inference loop", "Results display/streaming"],
        },
        "phases": [
            {"name": "Hardware", "items": ["Jetson Nano or RPi 5", "Coral TPU (if RPi)", "Camera module", "Power supply 5V 4A", "Heat sink + fan", "Storage (NVMe/SD)"]},
            {"name": "Software", "items": ["OS image + drivers", "ML framework install", "Model conversion to TFLite/ONNX", "Camera pipeline"]},
            {"name": "Application", "items": ["Inference loop", "Post-processing", "Results display", "API endpoint"]},
        ],
    },
    "robotics-controller": {
        "name": "Robotics Controller",
        "description": "General-purpose robotics control board for servos, motors, and sensors.",
        "difficulty": "hard",
        "tags": ["robotics", "controller", "motors"],
        "architecture": {
            "purpose": "Central controller for a multi-actuator robot (arm, hexapod, etc).",
            "components": ["Raspberry Pi or STM32", "PCA9685 servo driver", "Motor drivers", "IMU", "Power distribution", "Battery pack", "RC receiver (optional)"],
            "connections": "SBC → PCA9685 (I2C) → Servos | SBC → Motor drivers → Motors | SBC → IMU (I2C) → Orientation",
            "firmware": ["Servo control", "Motor PID", "Sensor fusion", "Remote control input", "Autonomous routines"],
        },
        "phases": [
            {"name": "Electronics", "items": ["Raspberry Pi / STM32", "PCA9685 servo driver", "Motor driver modules", "IMU sensor", "Battery pack", "Power distribution board", "Wiring"]},
            {"name": "Firmware", "items": ["Servo sweep test", "Motor control", "PID tuning", "IMU integration"]},
            {"name": "Control", "items": ["RC input handler", "Autonomous routines", "Safety limits", "Telemetry output"]},
        ],
    },
    "cyberdeck": {
        "name": "Cyberdeck",
        "description": "Portable custom computer build with integrated display and input.",
        "difficulty": "expert",
        "tags": ["cyberdeck", "portable", "computer"],
        "architecture": {
            "purpose": "Self-contained portable computing platform.",
            "components": ["Raspberry Pi 4/5 or x86 SBC", "7-10 inch display", "Mechanical keyboard", "Battery system (18650 or LiPo)", "BMS + charging circuit", "USB hub", "WiFi/BT", "Speakers/amp (optional)", "Custom case"],
            "connections": "SBC → Display (HDMI/DSI) → Keyboard (USB) → Battery → BMS → USB-C charging",
            "firmware": ["OS configuration", "Power management", "Display setup", "Input mapping"],
        },
        "phases": [
            {"name": "Core", "items": ["SBC (RPi 5 / x86)", "Display 7-10 inch", "Mechanical keyboard", "USB hub"]},
            {"name": "Power", "items": ["Battery cells", "BMS module", "Charging circuit", "Voltage regulators", "Power switch"]},
            {"name": "Assembly", "items": ["Case/enclosure", "Hinges or mount", "Cable management", "Cooling"]},
            {"name": "Software", "items": ["OS install", "Power management scripts", "Boot screen", "Application stack"]},
        ],
    },
    "drone": {
        "name": "Drone",
        "description": "Custom quadcopter with flight controller and telemetry.",
        "difficulty": "expert",
        "tags": ["drone", "quadcopter", "flight"],
        "architecture": {
            "purpose": "Autonomous or semi-autonomous aerial platform.",
            "components": ["Flight controller (Pixhawk / Betaflight FC)", "Frame (250-450mm)", "Motors (4x brushless)", "ESCs (4x)", "Propellers", "LiPo battery 3S-4S", "RC receiver", "GPS module", "Telemetry radio", "Camera (optional)"],
            "connections": "FC → ESCs → Motors | FC → GPS → Navigation | FC → RC Rx → Manual control | FC → Telemetry → Ground station",
            "firmware": ["ArduPilot or Betaflight", "PID tuning", "GPS waypoints", "Failsafe modes"],
        },
        "phases": [
            {"name": "Frame & Motors", "items": ["Drone frame", "Brushless motors (4x)", "Propellers (4+ sets)", "ESCs (4x)"]},
            {"name": "Electronics", "items": ["Flight controller", "GPS module", "RC receiver", "Telemetry radio", "Power distribution board", "LiPo battery"]},
            {"name": "Assembly", "items": ["Motor mounting", "ESC wiring", "FC mounting", "GPS mast"]},
            {"name": "Software", "items": ["Firmware flash", "PID tuning", "Failsafe config", "GPS waypoint mission"]},
            {"name": "Testing", "items": ["Motor spin test", "Hover test", "GPS hold test", "Failsafe test"]},
        ],
    },
    "custom-pcb": {
        "name": "Custom Electronics Board",
        "description": "Custom PCB design for a specific electronics project.",
        "difficulty": "hard",
        "tags": ["pcb", "electronics", "custom"],
        "architecture": {
            "purpose": "Purpose-built circuit board replacing breadboard prototypes.",
            "components": ["MCU (ATmega/ESP32/STM32)", "Voltage regulator", "Connectors", "Passive components", "IC sockets", "PCB fabrication"],
            "connections": "Schematic → PCB layout → Fabrication → Assembly",
            "firmware": ["Schematic capture (KiCad)", "PCB layout + routing", "Design rule check", "Gerber export"],
        },
        "phases": [
            {"name": "Design", "items": ["Schematic capture in KiCad", "Component selection", "Footprint library"]},
            {"name": "Layout", "items": ["PCB layout", "Routing", "Design rule check", "Gerber generation"]},
            {"name": "Fabrication", "items": ["PCB order (JLCPCB/PCBWay)", "Component order", "Stencil (optional)"]},
            {"name": "Assembly", "items": ["Solder paste", "Component placement", "Reflow or hand soldering", "Inspection"]},
            {"name": "Testing", "items": ["Continuity check", "Power-on test", "Functional test", "Firmware flash"]},
        ],
    },
}


class EngineeringPlanner:
    """Inventory-aware engineering project planner."""

    # ── Inventory snapshot ───────────────────────────────────────────────────

    def _inventory_snapshot(self) -> dict[str, dict]:
        """Get all inventory items keyed by normalized name."""
        items: dict[str, dict] = {}
        try:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()
            all_parts = hs.list_parts()
            for p in all_parts:
                norm = _normalize(p.get("name", ""))
                items[norm] = {
                    "name": p.get("name", ""),
                    "quantity": int(p.get("quantity", 0) or 0),
                    "category": p.get("category", "misc"),
                    "id": p.get("id", ""),
                }
                for alias in _parse_aliases(p.get("aliases", "[]")):
                    items[_normalize(alias)] = items[norm]
        except Exception:
            pass
        return items

    def _inventory_categories(self) -> dict[str, list[dict]]:
        """Group inventory by category."""
        cats: dict[str, list[dict]] = {}
        try:
            from backend.app.services.hardware_service import HardwareService
            for p in HardwareService().list_parts():
                qty = int(p.get("quantity", 0) or 0)
                if qty <= 0:
                    continue
                cat = p.get("category", "misc")
                cats.setdefault(cat, []).append({
                    "name": p.get("name", ""),
                    "quantity": qty,
                })
        except Exception:
            pass
        return cats

    # ── Templates ────────────────────────────────────────────────────────────

    def list_templates(self) -> list[dict]:
        """Return all available project templates."""
        return [
            {
                "id": tid,
                "name": t["name"],
                "description": t["description"],
                "difficulty": t["difficulty"],
                "tags": t["tags"],
                "phase_count": len(t["phases"]),
                "total_items": sum(len(ph["items"]) for ph in t["phases"]),
            }
            for tid, t in TEMPLATES.items()
        ]

    def get_template(self, template_id: str) -> Optional[dict]:
        return TEMPLATES.get(template_id)

    # ── Project Ideas / What can I build ─────────────────────────────────────

    def what_can_i_build(self) -> dict[str, Any]:
        """Suggest projects based on current inventory."""
        inv = self._inventory_snapshot()
        if not inv:
            return {
                "ok": True,
                "suggestions": [],
                "summary": "No inventory data. Add parts to the Hardware Board first.",
            }

        suggestions = []
        for tid, tmpl in TEMPLATES.items():
            match = self._match_template_to_inventory(tmpl, inv)
            if match["match_pct"] > 0:
                suggestions.append({
                    "template_id": tid,
                    "name": tmpl["name"],
                    "description": tmpl["description"],
                    "difficulty": tmpl["difficulty"],
                    "match_pct": match["match_pct"],
                    "matched_items": match["matched"],
                    "missing_items": match["missing"],
                    "total_items": match["total"],
                })

        suggestions.sort(key=lambda s: (-s["match_pct"], _DIFFICULTY.get(s["difficulty"], 3)))

        # Also generate custom suggestions from inventory categories
        custom = self._suggest_from_inventory(inv)

        return {
            "ok": True,
            "suggestions": suggestions[:8],
            "custom_ideas": custom,
            "inventory_count": sum(1 for v in inv.values() if v.get("quantity", 0) > 0),
            "summary": f"{len(suggestions)} template(s) match your inventory. {len(custom)} custom idea(s) generated.",
        }

    def _match_template_to_inventory(self, tmpl: dict, inv: dict) -> dict:
        """Check how well a template matches current inventory."""
        all_items = []
        for phase in tmpl["phases"]:
            all_items.extend(phase["items"])

        matched = []
        missing = []
        for item in all_items:
            norm = _normalize(item)
            found = False
            for inv_norm, inv_item in inv.items():
                if inv_item.get("quantity", 0) <= 0:
                    continue
                if _fuzzy_match(norm, inv_norm):
                    matched.append({"template_item": item, "inventory_item": inv_item["name"], "qty": inv_item["quantity"]})
                    found = True
                    break
            if not found:
                missing.append(item)

        total = len(all_items)
        match_pct = round(len(matched) / total * 100) if total else 0
        return {"matched": matched, "missing": missing, "total": total, "match_pct": match_pct}

    def _suggest_from_inventory(self, inv: dict) -> list[dict]:
        """Generate custom project ideas based on what's in inventory."""
        ideas = []
        cats = self._inventory_categories()
        cat_names = set(cats.keys())

        has_mcu = any(k in cat_names for k in ("microcontroller", "sbc", "development-board", "computer"))
        has_radio = any(k in cat_names for k in ("radio", "wireless", "communication", "lora"))
        has_sensor = any(k in cat_names for k in ("sensor", "environmental", "temperature", "imu"))
        has_motor = any(k in cat_names for k in ("motor", "actuator", "servo", "driver"))
        has_display = any(k in cat_names for k in ("display", "screen", "oled", "lcd"))
        has_gps = any(k in cat_names for k in ("gps", "navigation", "gnss"))
        has_camera = any(k in cat_names for k in ("camera", "vision", "imaging"))
        has_battery = any(k in cat_names for k in ("battery", "power", "lipo"))

        # Also scan names
        for norm in inv:
            if not has_mcu and any(k in norm for k in ("esp32", "raspberry pi", "arduino", "stm32", "jetson", "teensy", "rp2040")):
                has_mcu = True
            if not has_radio and any(k in norm for k in ("lora", "rfm95", "nrf24", "sx1276", "wifi module", "bluetooth")):
                has_radio = True
            if not has_sensor and any(k in norm for k in ("bme280", "dht", "mpu6050", "bno055", "bh1750", "pms5003")):
                has_sensor = True
            if not has_motor and any(k in norm for k in ("motor", "servo", "stepper", "l298", "tb6612", "pca9685")):
                has_motor = True
            if not has_gps and any(k in norm for k in ("gps", "neo-6m", "neo-m8", "gnss", "ublox")):
                has_gps = True
            if not has_camera and any(k in norm for k in ("camera", "ov5647", "imx219", "webcam")):
                has_camera = True

        if has_mcu and has_radio and has_sensor:
            ideas.append({"name": "Wireless Sensor Network", "reason": "You have MCUs, radios, and sensors", "difficulty": "moderate"})
        if has_mcu and has_gps and has_radio:
            ideas.append({"name": "GPS Tracker", "reason": "You have MCUs, GPS, and radios", "difficulty": "moderate"})
        if has_mcu and has_motor:
            ideas.append({"name": "Mobile Robot / Rover", "reason": "You have MCUs and motors", "difficulty": "hard"})
        if has_mcu and has_camera:
            ideas.append({"name": "Computer Vision Station", "reason": "You have MCUs and cameras", "difficulty": "hard"})
        if has_mcu and has_display:
            ideas.append({"name": "Dashboard Display", "reason": "You have MCUs and displays", "difficulty": "easy"})
        if has_mcu and has_sensor and has_display:
            ideas.append({"name": "Environmental Monitor with Display", "reason": "You have MCUs, sensors, and displays", "difficulty": "moderate"})
        if has_mcu and has_radio:
            ideas.append({"name": "LoRa Gateway / Relay", "reason": "You have MCUs and radios", "difficulty": "moderate"})
        if has_mcu and has_battery:
            ideas.append({"name": "Portable Telemetry Console", "reason": "You have MCUs and batteries", "difficulty": "moderate"})

        return ideas[:6]

    # ── BOM Generator ────────────────────────────────────────────────────────

    def generate_bom(self, project_name: str) -> dict[str, Any]:
        """Generate a Bill of Materials for a project.

        First checks if the project exists (uses reconciler), then falls back
        to template matching.
        """
        inv = self._inventory_snapshot()

        # Try existing project
        existing = self._get_existing_project_bom(project_name, inv)
        if existing:
            return existing

        # Try template match
        tmpl = self._find_template(project_name)
        if tmpl:
            return self._bom_from_template(tmpl, inv)

        return {"ok": False, "error": f"No project or template found for '{project_name}'. Try 'list project templates' to see available templates."}

    def _get_existing_project_bom(self, name: str, inv: dict) -> Optional[dict]:
        """Generate BOM from an existing project's hardware parts."""
        try:
            from backend.app.services.project_reconciler import get_reconciler
            recon = get_reconciler().reconcile_project(name)
            if not recon.get("found"):
                return None

            rows = []
            for item in recon.get("buy_now", []) + recon.get("buy_soon", []):
                rows.append({
                    "component": item["name"],
                    "qty": item.get("required_qty", 1),
                    "available": False,
                    "in_inventory": False,
                    "status": "missing",
                    "source": item.get("source", ""),
                })
            for item in recon.get("already_ordered", []):
                rows.append({
                    "component": item["name"],
                    "qty": item.get("required_qty", 1),
                    "available": False,
                    "in_inventory": False,
                    "status": "ordered",
                    "source": item.get("source", ""),
                })
            for item in recon.get("already_owned", []):
                rows.append({
                    "component": item["name"],
                    "qty": item.get("required_qty", 1),
                    "available": True,
                    "in_inventory": True,
                    "status": "owned",
                    "source": item.get("source", ""),
                })

            total = len(rows)
            available = sum(1 for r in rows if r["available"])
            missing = total - available

            return {
                "ok": True,
                "project": recon["project"],
                "source": "existing_project",
                "bom": rows,
                "total": total,
                "available": available,
                "missing": missing,
                "readiness_pct": round(available / total * 100) if total else 0,
                "sources_used": recon.get("sources_used", []),
                "summary": f"BOM for {recon['project']}: {total} components, {available} available, {missing} missing.",
            }
        except Exception:
            return None

    def _bom_from_template(self, tmpl: dict, inv: dict) -> dict:
        """Generate BOM from a template, checking against inventory."""
        rows = []
        for phase in tmpl["phases"]:
            for item in phase["items"]:
                norm = _normalize(item)
                in_inv = False
                inv_qty = 0
                for inv_norm, inv_item in inv.items():
                    if inv_item.get("quantity", 0) > 0 and _fuzzy_match(norm, inv_norm):
                        in_inv = True
                        inv_qty = inv_item["quantity"]
                        break
                rows.append({
                    "component": item,
                    "qty": 1,
                    "available": in_inv,
                    "in_inventory": in_inv,
                    "inventory_qty": inv_qty,
                    "status": "owned" if in_inv else "missing",
                    "phase": phase["name"],
                })

        total = len(rows)
        available = sum(1 for r in rows if r["available"])
        missing = total - available

        return {
            "ok": True,
            "project": tmpl["name"],
            "source": "template",
            "bom": rows,
            "total": total,
            "available": available,
            "missing": missing,
            "readiness_pct": round(available / total * 100) if total else 0,
            "summary": f"BOM for {tmpl['name']}: {total} components, {available} available, {missing} to acquire.",
        }

    # ── Gap Analysis ─────────────────────────────────────────────────────────

    def gap_analysis(self, project_name: str) -> dict[str, Any]:
        """What's missing for a project? Cross-references all sources."""
        bom = self.generate_bom(project_name)
        if not bom.get("ok"):
            return bom

        missing = [r for r in bom["bom"] if not r["available"]]
        owned = [r for r in bom["bom"] if r["available"]]

        return {
            "ok": True,
            "project": bom["project"],
            "source": bom.get("source", ""),
            "owned": owned,
            "missing": missing,
            "owned_count": len(owned),
            "missing_count": len(missing),
            "total": bom["total"],
            "readiness_pct": bom["readiness_pct"],
            "summary": f"{bom['project']}: {len(owned)} owned, {len(missing)} missing ({bom['readiness_pct']}% ready).",
        }

    # ── Buildability Check ───────────────────────────────────────────────────

    def can_i_build(self, project_name: str) -> dict[str, Any]:
        """Can I build this project with what I have?"""
        gap = self.gap_analysis(project_name)
        if not gap.get("ok"):
            return gap

        can_build = gap["missing_count"] == 0
        near_buildable = gap["readiness_pct"] >= 80

        verdict = "Yes" if can_build else ("Almost" if near_buildable else "Not yet")
        detail = ""
        if can_build:
            detail = f"You have all {gap['total']} components needed."
        elif near_buildable:
            names = ", ".join(m["component"] for m in gap["missing"][:3])
            extra = f" (+{gap['missing_count'] - 3} more)" if gap["missing_count"] > 3 else ""
            detail = f"Missing only {gap['missing_count']} part(s): {names}{extra}."
        else:
            names = ", ".join(m["component"] for m in gap["missing"][:5])
            extra = f" (+{gap['missing_count'] - 5} more)" if gap["missing_count"] > 5 else ""
            detail = f"Missing {gap['missing_count']} of {gap['total']} parts: {names}{extra}."

        return {
            "ok": True,
            "project": gap["project"],
            "can_build": can_build,
            "verdict": verdict,
            "readiness_pct": gap["readiness_pct"],
            "missing_count": gap["missing_count"],
            "missing": gap["missing"][:10],
            "owned_count": gap["owned_count"],
            "total": gap["total"],
            "detail": detail,
            "summary": f"{verdict} — {gap['project']} is {gap['readiness_pct']}% ready. {detail}",
        }

    # ── Architecture Generator ───────────────────────────────────────────────

    def get_architecture(self, project_name: str) -> dict[str, Any]:
        """Generate or retrieve architecture for a project."""
        # Check existing project in KG/PI
        try:
            from backend.app.services.project_intelligence import ProjectIntelligence
            pi = ProjectIntelligence()
            meta = pi.find_project_meta(project_name)
            if meta:
                briefing = pi.get_briefing(project_name)
                arch = self._architecture_from_briefing(meta, briefing)
                if arch:
                    return arch
        except Exception:
            pass

        # Fall back to template
        tmpl = self._find_template(project_name)
        if tmpl and tmpl.get("architecture"):
            return {
                "ok": True,
                "project": tmpl["name"],
                "source": "template",
                "architecture": tmpl["architecture"],
                "difficulty": tmpl["difficulty"],
                "tags": tmpl["tags"],
                "summary": f"Architecture for {tmpl['name']}: {tmpl['architecture']['purpose']}",
            }

        return {"ok": False, "error": f"No architecture data for '{project_name}'. Try a known project or template name."}

    def _architecture_from_briefing(self, meta: dict, briefing: dict) -> Optional[dict]:
        """Build architecture summary from existing project data."""
        if not briefing.get("found"):
            return None

        parts = briefing.get("parts", {})
        all_parts = parts.get("all", [])
        deps = briefing.get("dependencies", [])
        related = briefing.get("related_nodes", [])
        b63 = briefing.get("brain63_context", "")
        notes = meta.get("notes", "")

        components = [p.get("name", "") for p in all_parts[:15]]
        dep_names = [d["name"] for d in deps]
        node_names = [n["name"] for n in related]

        return {
            "ok": True,
            "project": meta["name"],
            "source": "existing_project",
            "architecture": {
                "purpose": notes or f"{meta['name']} project.",
                "components": components if components else ["No hardware parts registered yet."],
                "dependencies": dep_names,
                "related_nodes": node_names,
                "brain63_context": b63[:300] if b63 else "",
            },
            "status": meta["status"],
            "priority": meta["priority"],
            "difficulty": "unknown",
            "summary": f"Architecture for {meta['name']}: {len(components)} components, {len(deps)} dependencies.",
        }

    # ── Roadmap Generator ────────────────────────────────────────────────────

    def generate_roadmap(self, project_name: str) -> dict[str, Any]:
        """Generate a phased roadmap for a project."""
        # Existing project — use Brain63 roadmap via rich_output
        try:
            from backend.app.services.rich_output_service import _get_project_phases
            phases = _get_project_phases(project_name)
            if phases:
                return {
                    "ok": True,
                    "project": project_name,
                    "source": "brain63_roadmap",
                    "phases": phases,
                    "total_phases": len(phases),
                    "total_items": sum(p.get("total", 0) for p in phases),
                    "completed_items": sum(p.get("done", 0) for p in phases),
                    "summary": f"Roadmap for {project_name}: {len(phases)} phases.",
                }
        except Exception:
            pass

        # Template roadmap
        tmpl = self._find_template(project_name)
        if tmpl:
            phases = []
            for phase in tmpl["phases"]:
                phases.append({
                    "name": phase["name"],
                    "items": [{"name": item, "checked": False} for item in phase["items"]],
                    "done": 0,
                    "total": len(phase["items"]),
                })
            return {
                "ok": True,
                "project": tmpl["name"],
                "source": "template",
                "phases": phases,
                "total_phases": len(phases),
                "total_items": sum(p["total"] for p in phases),
                "completed_items": 0,
                "summary": f"Roadmap for {tmpl['name']}: {len(phases)} phases, {sum(p['total'] for p in phases)} tasks.",
            }

        return {"ok": False, "error": f"No roadmap data for '{project_name}'."}

    # ── Procurement Plan ─────────────────────────────────────────────────────

    def procurement_plan(self, project_name: str) -> dict[str, Any]:
        """Generate a prioritized procurement plan."""
        gap = self.gap_analysis(project_name)
        if not gap.get("ok"):
            return gap

        missing = gap["missing"]
        if not missing:
            return {
                "ok": True,
                "project": gap["project"],
                "buy_now": [],
                "buy_soon": [],
                "optional": [],
                "total_missing": 0,
                "summary": f"No parts needed — {gap['project']} has everything.",
            }

        buy_now = []
        buy_soon = []
        optional = []

        for item in missing:
            phase = item.get("phase", "")
            phase_lower = phase.lower() if phase else ""
            if not phase or "electronics" in phase_lower or "core" in phase_lower or "hardware" in phase_lower or "frame" in phase_lower or "chassis" in phase_lower:
                buy_now.append(item)
            elif "firmware" in phase_lower or "software" in phase_lower or "testing" in phase_lower:
                optional.append(item)
            else:
                buy_soon.append(item)

        return {
            "ok": True,
            "project": gap["project"],
            "buy_now": buy_now,
            "buy_soon": buy_soon,
            "optional": optional,
            "total_missing": len(missing),
            "readiness_pct": gap["readiness_pct"],
            "summary": f"Procurement for {gap['project']}: {len(buy_now)} buy now, {len(buy_soon)} buy soon, {len(optional)} optional.",
        }

    # ── Project Design (Full Pipeline) ───────────────────────────────────────

    def design_project(self, description: str) -> dict[str, Any]:
        """Full project design pipeline from a description.

        1. Match to template or generate custom
        2. Check inventory
        3. Generate architecture, BOM, gap analysis, roadmap
        """
        inv = self._inventory_snapshot()
        tmpl = self._find_template(description)

        if tmpl:
            bom = self._bom_from_template(tmpl, inv)
            gap_missing = [r for r in bom["bom"] if not r["available"]]
            gap_owned = [r for r in bom["bom"] if r["available"]]

            return {
                "ok": True,
                "project_name": tmpl["name"],
                "source": "template",
                "description": tmpl["description"],
                "difficulty": tmpl["difficulty"],
                "tags": tmpl["tags"],
                "architecture": tmpl.get("architecture", {}),
                "bom": bom,
                "gap": {
                    "owned": gap_owned,
                    "missing": gap_missing,
                    "readiness_pct": bom["readiness_pct"],
                },
                "phases": tmpl["phases"],
                "summary": f"Designed {tmpl['name']}: {bom['total']} parts, {bom['available']} available, {bom['missing']} to acquire.",
            }

        # No template match — return a generic design frame
        return {
            "ok": True,
            "project_name": description.title(),
            "source": "custom",
            "description": f"Custom project: {description}",
            "difficulty": "unknown",
            "tags": [],
            "architecture": {
                "purpose": description,
                "components": ["Define components based on requirements"],
            },
            "bom": {"bom": [], "total": 0, "available": 0, "missing": 0, "readiness_pct": 0},
            "gap": {"owned": [], "missing": [], "readiness_pct": 0},
            "phases": [],
            "note": "No matching template found. Add hardware parts and a Brain63 roadmap to enable full planning.",
            "summary": f"Custom project '{description}' — no template match. Define components to begin.",
        }

    # ── Project Creator ──────────────────────────────────────────────────────

    def create_project(self, name: str, template_id: str | None = None) -> dict[str, Any]:
        """Create a new project from a template or from scratch.

        Creates entries in: project_service, hardware_service (hw_projects),
        knowledge_graph, and project_memory.
        """
        from backend.app.services.project_service import ProjectService
        from backend.app.models.project import ProjectCreate

        ps = ProjectService()

        existing = ps.find_by_name(name)
        if existing:
            return {"ok": False, "error": f"Project '{name}' already exists (id: {existing.id})."}

        tmpl = None
        if template_id:
            tmpl = TEMPLATES.get(template_id)
        else:
            tmpl = self._find_template(name)

        tags = tmpl["tags"] if tmpl else []
        notes = tmpl["description"] if tmpl else f"Custom project: {name}"

        project = ps.create_project(ProjectCreate(
            name=name,
            status="planned",
            priority="normal",
            tags=tags,
            notes=notes,
        ))

        # Create hw_project + link template parts
        hw_project_id = None
        parts_linked = 0
        if tmpl:
            hw_project_id, parts_linked = self._create_hw_project(project.id, name, tmpl)

        # Register in KG
        try:
            from backend.app.services.knowledge_graph import get_graph
            kg = get_graph()
            kg.upsert_entity("project", name, external_id=project.id)
        except Exception:
            pass

        # Record in project memory
        try:
            from backend.app.services.project_memory import get_memory
            get_memory().record(
                project=name,
                type="milestone",
                title=f"Project created",
                summary=f"Created from {'template: ' + tmpl['name'] if tmpl else 'scratch'}.",
                source="planner",
            )
        except Exception:
            pass

        return {
            "ok": True,
            "project": {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "priority": project.priority,
                "tags": project.tags,
            },
            "template": tmpl["name"] if tmpl else None,
            "hw_project_id": hw_project_id,
            "parts_linked": parts_linked,
            "summary": f"Created project '{name}'" + (f" from template '{tmpl['name']}' with {parts_linked} parts linked." if tmpl else "."),
        }

    def _create_hw_project(self, project_id: str, name: str, tmpl: dict) -> tuple[str | None, int]:
        """Create hardware project and link template parts to inventory."""
        try:
            from backend.app.services.hardware_service import HardwareService
            hs = HardwareService()

            hw_proj = hs.create_project(
                name=name,
                description=tmpl.get("description", ""),
                priority="normal",
                status="planned",
            )
            hw_id = hw_proj["id"]

            inv = self._inventory_snapshot()
            linked = 0

            for phase in tmpl["phases"]:
                for item_name in phase["items"]:
                    norm = _normalize(item_name)
                    inv_id = None
                    for inv_norm, inv_item in inv.items():
                        if _fuzzy_match(norm, inv_norm):
                            inv_id = inv_item.get("id")
                            break

                    if not inv_id:
                        part = hs.add_part(
                            name=item_name,
                            category=_guess_category(item_name),
                            quantity=0,
                            status="out-of-stock",
                        )
                        inv_id = part["id"]
                        inv[norm] = {"name": item_name, "quantity": 0, "id": inv_id}

                    try:
                        hs.assign_part_to_project(hw_id, inv_id, quantity_required=1, is_required=1)
                        linked += 1
                    except Exception:
                        pass

            return hw_id, linked
        except Exception as e:
            logger.warning("Failed to create hw_project: %s", e)
            return None, 0

    # ── Recommendations (inventory-aware) ────────────────────────────────────

    def get_recommendations(self) -> dict[str, Any]:
        """Top project recommendations based on inventory + existing projects."""
        build = self.what_can_i_build()
        suggestions = build.get("suggestions", [])
        custom = build.get("custom_ideas", [])

        # Also check existing projects readiness
        existing_ready = []
        try:
            from backend.app.services.digital_twin import get_twin
            ready = get_twin().ready_projects()
            existing_ready = [{"name": p["name"], "readiness_pct": p["readiness_pct"]} for p in ready]
        except Exception:
            pass

        return {
            "ok": True,
            "template_matches": suggestions[:5],
            "custom_ideas": custom[:5],
            "existing_ready": existing_ready[:5],
            "summary": f"{len(suggestions)} template matches, {len(custom)} ideas, {len(existing_ready)} ready projects.",
        }

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _find_template(self, name: str) -> Optional[dict]:
        """Find a template by name, ID, or fuzzy match."""
        name_lower = name.lower().strip()

        # Exact ID match
        if name_lower in TEMPLATES:
            return TEMPLATES[name_lower]

        # Name match
        for tid, tmpl in TEMPLATES.items():
            if tmpl["name"].lower() == name_lower:
                return tmpl

        # Fuzzy match on name or tags
        for tid, tmpl in TEMPLATES.items():
            if name_lower in tmpl["name"].lower() or tmpl["name"].lower() in name_lower:
                return tmpl
            if any(name_lower in tag or tag in name_lower for tag in tmpl["tags"]):
                return tmpl

        return None


# ── Utilities ────────────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    s = re.sub(r"[^a-z0-9\s]", "", name.lower())
    return re.sub(r"\s+", " ", s).strip()


def _parse_aliases(raw: str) -> list[str]:
    try:
        import json
        return json.loads(raw) if raw else []
    except Exception:
        return []


def _fuzzy_match(a: str, b: str) -> bool:
    """Check if two normalized names are close enough to be the same component."""
    if a == b:
        return True
    if a in b or b in a:
        return True
    a_words = set(a.split())
    b_words = set(b.split())
    if len(a_words) >= 2 and len(b_words) >= 2:
        overlap = a_words & b_words
        if len(overlap) >= min(2, min(len(a_words), len(b_words))):
            return True
    return False


def _guess_category(name: str) -> str:
    """Guess hardware category from item name."""
    n = name.lower()
    if any(k in n for k in ("esp32", "arduino", "raspberry pi", "stm32", "teensy", "jetson", "rp2040", "sbc")):
        return "microcontroller"
    if any(k in n for k in ("motor", "servo", "stepper", "actuator")):
        return "motor"
    if any(k in n for k in ("sensor", "bme280", "dht", "mpu6050", "bno055", "lidar", "ultrasonic")):
        return "sensor"
    if any(k in n for k in ("lora", "rfm95", "nrf24", "radio", "antenna", "sx1276")):
        return "radio"
    if any(k in n for k in ("battery", "lipo", "18650", "charger", "bms")):
        return "power"
    if any(k in n for k in ("display", "oled", "lcd", "screen", "e-ink")):
        return "display"
    if any(k in n for k in ("gps", "neo-6m", "gnss")):
        return "gps"
    if any(k in n for k in ("camera", "webcam", "imx")):
        return "camera"
    if any(k in n for k in ("driver", "l298", "tb6612", "pca9685", "esc")):
        return "driver"
    if any(k in n for k in ("pcb", "breadboard", "wire", "jumper", "connector")):
        return "prototyping"
    if any(k in n for k in ("case", "enclosure", "mount", "bracket", "frame", "chassis")):
        return "mechanical"
    return "misc"


# ── Singleton ────────────────────────────────────────────────────────────────

_instance: Optional[EngineeringPlanner] = None


def get_planner() -> EngineeringPlanner:
    global _instance
    if _instance is None:
        _instance = EngineeringPlanner()
    return _instance
