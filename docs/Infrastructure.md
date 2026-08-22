# Infrastructure — Nodes, Telemetry, Watch Officer, SSH

This document covers SILVIA's infrastructure layer: the Node Registry, real-time telemetry, the Watch Officer alert engine, and SSH terminal integration.

---

## Table of Contents

1. [Overview](#overview)
2. [Node Registry](#node-registry)
3. [Telemetry System](#telemetry-system)
4. [Watch Officer](#watch-officer)
5. [SSH Terminal Launch](#ssh-terminal-launch)
6. [Agent Node Protocol](#agent-node-protocol)
7. [Chat Commands](#chat-commands)
8. [API Reference](#api-reference)

---

## Overview

SILVIA treats every machine on your network — servers, Raspberry Pis, drones, robots, workstations — as a **node** in a unified registry. Nodes can be:

- **Passive** — known by IP/hostname, reachable via ping/probe
- **Agent nodes** — running `silvia-agent` for bidirectional telemetry and command execution

```
┌─────────────┐          ┌─────────────────────────┐
│   SILVIA    │ ────────▶│  Node: storage-node (NAS)  │
│  Backend    │◀──────── │  silvia-agent :7700      │
└─────────────┘  REST    │  CPU: 12%  RAM: 4.2GB   │
                         └─────────────────────────┘

┌─────────────┐   ping   ┌─────────────────────────┐
│   SILVIA    │ ────────▶│  Node: pi-zero (passive) │
│  Backend    │          │  IP: 192.168.1.42        │
└─────────────┘          └─────────────────────────┘
```

---

## Node Registry

### Node Schema

| Field | Type | Description |
|---|---|---|
| `id` | string | UUID short hash |
| `name` | string | Friendly name (e.g. "storage-node") |
| `hostname` | string | IP address or hostname |
| `type` | string | drone, robot, server, workstation, sbc, esp32, sensor-network, vps |
| `status` | string | online, offline, unknown |
| `agent_url` | string | URL of silvia-agent (if installed) |
| `last_seen` | datetime | Last successful contact |
| `last_verified` | datetime | Last full verification run |
| `verification_source` | string | How it was verified (agent, ping, dns) |
| `aliases` | string | Comma-separated alternate names |
| `ssh_username` | string | Stored SSH username |
| `ssh_key_path` | string | Path to SSH key file |
| `notes` | string | Free-text notes |
| `cpu` | float | Last CPU % reading |
| `ram` | float | Last RAM % reading |
| `disk` | float | Last disk % reading |
| `temperature` | float | Last temperature reading (°C) |
| `battery_pct` | float | Last battery % (drones, mobile nodes) |
| `altitude` | float | Last altitude reading (m) |

### Node Types

| Type | Typical Use |
|---|---|
| `server` | Headless Linux server, VPS |
| `workstation` | Desktop/laptop with a UI |
| `sbc` | Raspberry Pi, Orange Pi, Jetson |
| `drone` | Flying vehicle with flight controller |
| `robot` | Ground robot or arm |
| `esp32` | ESP32/ESP8266 microcontroller node |
| `sensor-network` | Environmental sensor array |
| `vps` | Cloud VPS |

### Verification Chain

When SILVIA verifies a node it tries in order:

1. **silvia-agent** — HTTP GET to `agent_url/health`. If responds: verified, sets `verification_source=agent`.
2. **Tailscale** — looks up node name in Tailscale network. If found: updates IP, sets `verification_source=tailscale`.
3. **DNS** — resolves hostname. If resolves: sets `verification_source=dns`.
4. **Ping** — ICMP ping. If responds: sets `verification_source=ping`.
5. If all fail: status = `offline`.

---

## Telemetry System

### How Telemetry Works

For agent nodes, SILVIA polls `agent_url/metrics` every 30 seconds (configurable) in a background task. The response is stored on the node record and broadcast to all connected WebSocket clients.

For passive nodes, SILVIA can only probe connectivity — no CPU/RAM data is available.

### Telemetry Fields

| Field | Unit | Notes |
|---|---|---|
| `cpu` | % | 0–100 |
| `ram` | % | 0–100 |
| `disk` | % | 0–100 |
| `temperature` | °C | Core temperature |
| `battery_pct` | % | 0–100, drones/mobile only |
| `altitude` | meters | Drone altitude above takeoff |

### WebSocket Events

SILVIA broadcasts telemetry updates as WebSocket events:

```json
{
  "type": "node_telemetry",
  "node_id": "abc123",
  "node_name": "storage-node",
  "cpu": 34.2,
  "ram": 67.1,
  "disk": 45.0,
  "temperature": 52.3
}
```

The Infrastructure Panel in the frontend renders these in real time.

### Telemetry History

SILVIA stores up to 7 days of telemetry history in `node_telemetry_history`. Query it:

```
GET /api/nodes/{node_id}/telemetry/history?hours=24
```

Returns an array of timestamped readings (oldest first).

---

## Watch Officer

The Watch Officer monitors telemetry in real time and raises alerts when thresholds are crossed.

### Alert Severity Levels

| Level | Color | Meaning |
|---|---|---|
| `info` | Blue | Informational — no action required |
| `warning` | Orange | Worth checking |
| `critical` | Red | Needs immediate attention |

### Built-in Watch Rules

SILVIA evaluates these rules on every telemetry update:

| Rule | Trigger |
|---|---|
| Node offline | Node was online, now not reachable |
| High CPU | CPU > 90% for 2+ consecutive readings |
| High RAM | RAM > 85% |
| High disk | Disk > 90% |
| High temperature | Temperature > 80°C |
| Low battery | Battery < 15% (drones/mobile) |

### Alert Lifecycle

```
Telemetry update arrives
        │
        ▼
Rule evaluation (all rules checked)
        │
   Threshold exceeded?
        │
    YES ▼
Alert raised → stored in DB → broadcast via WebSocket
        │
   Already active?
   (de-duplicate — same rule + node)
        │
    NO  ▼
Show in UI alert banner + alert log
        │
   NOTIFICATION_WEBHOOK_URL set?
        │
    YES ▼
POST to Discord/Slack webhook
```

### Viewing Alerts

- **UI**: Alert banner appears at the top of the Command Center when critical alerts are active
- **Chat**: `show alerts` or `watch officer status`
- **API**: `GET /api/watch/alerts`

### Notification Webhooks

Configure in `.env`:

```env
NOTIFICATION_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN
NOTIFICATION_WEBHOOK_FORMAT=discord    # discord | slack | json
NOTIFICATION_MIN_SEVERITY=critical     # warning | critical
```

Debounce: the same rule + node will not notify more than once per 30 minutes, preventing alert storms.

---

## SSH Terminal Launch

SILVIA can open a Windows Terminal tab connected to any registered node via SSH.

### How It Works

1. You say `connect remote-server` or type it in chat
2. SILVIA looks up `remote-server` in the node registry → finds hostname and stored SSH profile
3. SILVIA runs: `wt.exe new-tab --title "SILVIA: remote-server" ssh user@192.168.1.50`
4. A new Windows Terminal tab opens with the SSH session

### SSH Profiles

Store username and key per node:

```
set ssh username for remote-server to user
configure storage-node ssh as pi
set remote-server ssh key to ~/.ssh/id_ed25519
```

Profiles are stored in the node record (`ssh_username`, `ssh_key_path`). If no profile is stored, SILVIA will ask for a username on first connect.

### Requirements

- Windows Terminal (`wt.exe`) must be installed
- SSH must be configured on the target node
- The node must have a hostname/IP in the registry

---

## Agent Node Protocol

Nodes running `silvia-agent` support bidirectional communication.

### silvia-agent Endpoints

SILVIA expects the following endpoints on agent nodes:

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness check |
| `/metrics` | GET | Return CPU, RAM, disk, temperature, battery, altitude |
| `/command` | POST | Execute a command (arm, disarm, land, reboot...) |

### Command Protocol

```json
POST /command
{
  "command": "land",
  "payload": {}
}
```

Response:
```json
{
  "ok": true,
  "command": "land",
  "result": "Landing initiated"
}
```

### Destructive Commands

The following commands require explicit user confirmation before SILVIA executes them:

- `arm` — arm motors/actuators
- `disarm` — disarm
- `reboot` — reboot the node
- `emergency_stop` — immediate full stop

SILVIA will always show a confirmation prompt: "Are you sure you want to [command] [node]?" before sending these.

---

## Chat Commands

### Node Discovery and Status

| Command | Action |
|---|---|
| `what nodes are online` | List all registered nodes with status |
| `list my devices` | Same as above |
| `status of storage-node` | Detailed info for a specific node |
| `storage-node info` | Same as above |
| `ping storage-node` | Check if storage-node is reachable |
| `is storage-node online` | Same as ping |
| `what's the IP of storage-node` | Return stored IP/hostname |

### Node Telemetry

| Command | Action |
|---|---|
| `show storage-node telemetry` | CPU, RAM, disk, temperature for storage-node |
| `storage-node cpu` | Telemetry for storage-node (any metric keyword) |
| `show all node telemetry` | Telemetry for every registered node |
| `infrastructure status` | Same — overview of all nodes |
| `show hottest node` | All nodes sorted by temperature |
| `drone-01 battery` | Battery % and altitude for drone |

### Node Management

| Command | Action |
|---|---|
| `add laptop` | Register a new node named "laptop" |
| `register server1 at 192.168.1.10` | Register with specific hostname |
| `update storage-node IP to 192.168.1.50` | Update stored hostname |
| `delete storage-node` | Remove from registry |
| `merge VPS into remote-server` | Merge duplicate nodes (source deleted) |
| `deduplicate nodes` | Find and report duplicate entries |
| `verify storage-node` | Run full verification chain |
| `verify all nodes` | Verify every node |
| `refresh nodes` | Same as verify all |

### SSH and Remote Access

| Command | Action |
|---|---|
| `connect remote-server` | Open SSH terminal tab to remote-server |
| `ssh into storage-node` | Open SSH terminal tab |
| `connect storage-node as admin` | SSH with explicit username |
| `set ssh username for remote-server to user` | Save SSH username |
| `configure storage-node ssh as pi` | Save SSH username |
| `set remote-server ssh key to ~/.ssh/id_ed25519` | Save SSH key path |

### Node Commands (requires silvia-agent)

| Command | Action |
|---|---|
| `arm drone-01` | Arm motors (requires confirmation) |
| `disarm drone-01` | Disarm (requires confirmation) |
| `land drone-01` | Initiate landing |
| `send drone-01 home` | Return to home |
| `emergency stop drone-01` | Full stop (requires confirmation) |
| `reboot pi5` | Reboot node (requires confirmation) |
| `list drones` | List all drone-type nodes |
| `show all robots` | List all robot-type nodes |
| `what drones do I have` | Same as list drones |

### Watch Officer

| Command | Action |
|---|---|
| `show alerts` | All active Watch Officer alerts |
| `active alerts` | Same |
| `watch officer status` | Same |
| `any alerts` | Same |

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/nodes` | GET | List all nodes |
| `GET /api/nodes/types` | GET | Available node types |
| `POST /api/nodes` | POST | Create node |
| `PUT /api/nodes/{id}` | PUT | Update node |
| `DELETE /api/nodes/{id}` | DELETE | Delete node |
| `PUT /api/nodes/{id}/metrics` | PUT | Update telemetry |
| `POST /api/nodes/{id}/probe` | POST | Probe connectivity |
| `POST /api/nodes/{id}/verify` | POST | Full verification chain |
| `GET /api/nodes/{id}/telemetry/history` | GET | Historical telemetry (hours param) |
| `GET /api/watch/alerts` | GET | Active Watch Officer alerts |
| `POST /api/watch/alerts/{id}/dismiss` | POST | Dismiss an alert |
| `GET /api/nodes/{id}/services` | GET | Services on a node |
| `POST /api/nodes/{id}/services` | POST | Add service to node |

---

## Related Documentation

- [NodeRegistry.md](NodeRegistry.md) — Node schema details and agent protocol
- [ServiceRegistry.md](ServiceRegistry.md) — Services mapped to nodes
- [CapabilityRegistry.md](CapabilityRegistry.md) — Executable capabilities
- [Commands.md](Commands.md) — Full command reference
