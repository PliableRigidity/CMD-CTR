# Node Registry

The Node Registry is SILVIA's database of every machine you want to monitor or control — from Raspberry Pis and NAS boxes to drones, robots, and cloud VPS instances.

---

## Table of Contents

1. [Concepts](#concepts)
2. [Node Schema](#node-schema)
3. [Node Types](#node-types)
4. [Adding Nodes](#adding-nodes)
5. [Agent Nodes vs Passive Nodes](#agent-nodes-vs-passive-nodes)
6. [Verification](#verification)
7. [SSH Profiles](#ssh-profiles)
8. [Telemetry](#telemetry)
9. [Commands](#commands)
10. [API Endpoints](#api-endpoints)

---

## Concepts

A **node** is any networked device SILVIA knows about. Nodes are stored in `backend/nodes.db` (SQLite).

**Node lifecycle:**
```
Register → Probe → Verify → Monitor → Command
```

- **Register**: Add the node by name and hostname/IP
- **Probe**: SILVIA attempts to contact it (ping, HTTP)
- **Verify**: Full verification chain (agent → Tailscale → DNS → ping)
- **Monitor**: Background polling if agent is installed
- **Command**: Send commands via silvia-agent

---

## Node Schema

```python
class Node:
    id: str                  # UUID short hash (e.g. "abc123de")
    name: str                # Friendly name: "storage-node", "pi5", "drone-01"
    hostname: str            # IP address or DNS hostname
    type: str                # See Node Types below
    status: str              # "online" | "offline" | "unknown"
    agent_url: str           # e.g. "http://192.168.1.10:7700"
    last_seen: datetime      # Last successful contact
    last_verified: datetime  # Last full verification run
    verification_source: str # "agent" | "tailscale" | "dns" | "ping"
    aliases: str             # Comma-separated alternate names
    notes: str               # Free text

    # SSH profile
    ssh_username: str        # Default SSH user
    ssh_key_path: str        # Path to private key

    # Latest telemetry (null if not available)
    cpu: float               # CPU usage %
    ram: float               # RAM usage %
    disk: float              # Disk usage %
    temperature: float       # Core temp °C
    battery_pct: float       # Battery % (drones/mobile)
    altitude: float          # Altitude m (drones)
    mission_state: str       # Mission state string (drones/robots)
```

---

## Node Types

| Type | Description | Typical Hardware |
|---|---|---|
| `server` | Headless Linux server | Dell PowerEdge, mini-PC |
| `workstation` | Desktop or laptop | Main development machine |
| `sbc` | Single-board computer | Raspberry Pi 4/5, Jetson Nano, Orange Pi |
| `drone` | Aerial vehicle | DJI, custom ArduPilot build |
| `robot` | Ground robot or arm | ROS-based mobile robot |
| `esp32` | Microcontroller node | ESP32-S3, ESP32-C3 |
| `sensor-network` | Sensor array | Environmental monitoring |
| `vps` | Cloud VPS | DigitalOcean, Linode, Hetzner |

---

## Adding Nodes

### Via Chat

```
add storage-node
register storage-node at 192.168.1.50
add server1 at 100.64.1.5
```

If you omit the hostname, SILVIA will ask for it.

### Via Infrastructure Panel

1. Open the Infrastructure Panel in the frontend
2. Click **+ Add Node**
3. Fill in name, hostname, type
4. Optionally set `agent_url` if silvia-agent is installed

### Via API

```bash
curl -X POST http://localhost:8000/api/nodes \
  -H "Content-Type: application/json" \
  -d '{
    "name": "storage-node",
    "hostname": "192.168.1.50",
    "type": "server",
    "agent_url": "http://192.168.1.50:7700"
  }'
```

---

## Agent Nodes vs Passive Nodes

### Passive Nodes

Only connectivity probing is available:
- Ping (ICMP)
- DNS resolution
- TCP port check

No telemetry. No command execution. Good for simple reachability tracking.

### Agent Nodes

Nodes with `silvia-agent` installed support:
- **Real-time telemetry** (CPU, RAM, disk, temperature, battery)
- **Remote command execution** (arm, disarm, land, reboot)
- **Service/capability execution** (media.play, system.restart)
- **Active verification** (agent heartbeat)

Set up by configuring `agent_url` on the node record. SILVIA will attempt the agent URL first in all operations.

#### silvia-agent API Contract

SILVIA expects these endpoints on the agent:

```
GET  /health          → {"ok": true, "name": "storage-node", "version": "1.0"}
GET  /metrics         → {"cpu": 34.2, "ram": 67.1, "disk": 45.0, "temp": 52.3}
POST /command         → body: {"command": "land", "payload": {}}
                     ← {"ok": true, "result": "..."}
```

---

## Verification

SILVIA uses a 4-step verification chain to confirm a node is reachable:

```
1. silvia-agent   GET {agent_url}/health    → verification_source = "agent"
        ↓ fail
2. Tailscale      tailscale status lookup   → verification_source = "tailscale"
        ↓ fail
3. DNS            resolve hostname           → verification_source = "dns"
        ↓ fail
4. Ping           ICMP ping                 → verification_source = "ping"
        ↓ fail
   status = "offline"
```

**Trigger verification:**
```
verify storage-node          # verify one node
verify all nodes          # verify all
refresh nodes             # same as verify all
```

The `last_verified` timestamp and `verification_source` are updated on each run.

---

## SSH Profiles

SSH profile is stored per node in the registry.

### Setting a Profile

```
set ssh username for remote-server to user
configure storage-node ssh as pi
set remote-server ssh key to ~/.ssh/id_ed25519
set remote-server ssh key to default
```

### Using SSH

```
connect remote-server
ssh into storage-node
connect to server1
ssh storage-node as admin
open terminal on pi5
```

SILVIA opens a new Windows Terminal tab running:
```
ssh user@192.168.1.50
```
or with a key:
```
ssh -i ~/.ssh/id_ed25519 user@192.168.1.50
```

**Requirements:** Windows Terminal (`wt.exe`) must be installed.

---

## Telemetry

Telemetry is received from silvia-agent and stored on the node record. The most recent values are available immediately:

```
show storage-node telemetry
storage-node cpu
show all node telemetry
infrastructure status
```

### Historical Telemetry

SILVIA stores the last 7 days of readings in `node_telemetry_history`. Query via API:

```
GET /api/nodes/{node_id}/telemetry/history?hours=24
```

Returns chronological array:
```json
[
  {"timestamp": "2026-06-15T10:00:00Z", "cpu": 34.2, "ram": 67.1, "disk": 45.0},
  {"timestamp": "2026-06-15T10:00:30Z", "cpu": 38.0, "ram": 67.5, "disk": 45.0}
]
```

---

## Commands

### Registration and Management

```
add laptop
register storage-node at 192.168.1.50
update storage-node IP to 192.168.1.51
delete storage-node
merge VPS into remote-server
deduplicate nodes
```

### Status and Verification

```
what nodes are online
list my devices
status of storage-node
storage-node info
ping storage-node
is storage-node online
what's the IP of storage-node
verify storage-node
verify all nodes
refresh nodes
```

### Telemetry

```
show storage-node telemetry
workstation cpu
show all node telemetry
show hottest node
node health
infrastructure status
drone-01 battery
drone-01 mission state
```

### SSH

```
connect remote-server
ssh into storage-node
connect to server1
ssh storage-node as admin
open terminal on storage-node
set ssh username for remote-server to user
configure storage-node ssh as pi
set remote-server ssh key to ~/.ssh/id_ed25519
```

### Commands (requires silvia-agent)

```
arm drone-01
disarm drone-01
land drone-01
send drone-01 home
emergency stop drone-01
reboot pi5
restart_service pi5
list drones
show all robots
what esp32 nodes do I have
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/nodes` | GET | List all registered nodes |
| `GET /api/nodes/types` | GET | Available node type enum values |
| `POST /api/nodes` | POST | Create a new node |
| `PUT /api/nodes/{id}` | PUT | Update node fields |
| `DELETE /api/nodes/{id}` | DELETE | Remove a node |
| `PUT /api/nodes/{id}/metrics` | PUT | Push telemetry update (from agent) |
| `POST /api/nodes/{id}/probe` | POST | Probe connectivity |
| `POST /api/nodes/{id}/verify` | POST | Full verification chain |
| `GET /api/nodes/{id}/telemetry/history` | GET | Historical readings (`?hours=24`) |

---

## Related Documentation

- [Infrastructure.md](Infrastructure.md) — Telemetry, Watch Officer overview
- [ServiceRegistry.md](ServiceRegistry.md) — Services on nodes
- [CapabilityRegistry.md](CapabilityRegistry.md) — Capabilities on services
