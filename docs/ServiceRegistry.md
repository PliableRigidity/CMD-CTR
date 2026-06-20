# Service Registry

The Service Registry maps named services to nodes. A service represents a capability a node provides — file storage, media playback, a web server, a sensor feed, a robot controller.

---

## Table of Contents

1. [Concepts](#concepts)
2. [Service Schema](#service-schema)
3. [Service Presets](#service-presets)
4. [Adding Services](#adding-services)
5. [Service Types](#service-types)
6. [Commands](#commands)
7. [API Endpoints](#api-endpoints)

---

## Concepts

Services sit between nodes and capabilities:

```
Node (nighthawk) 
  └── Service (samba)         ← Service Registry
        └── Capability (file-storage.read)  ← Capability Registry
```

A node can have multiple services. Each service has a type, description, and a set of capabilities.

Services are stored in `node_services` in `nodes.db`.

---

## Service Schema

```python
class NodeService:
    id: str          # UUID short hash
    node_id: str     # Parent node ID
    node_name: str   # Denormalized node name
    name: str        # Service name: "samba", "plex", "nginx"
    type: str        # Service type category
    description: str # Human-readable description
    created_at: str  # ISO timestamp
```

---

## Service Presets

Presets register a standard bundle of services on a node with one command.

| Preset | Services Registered |
|---|---|
| `nas` | samba (file-storage), rsync (backup), smb (network) |
| `media-player` | plex (streaming), kodi (media), vlc (playback) |
| `robot` | motor-controller, navigation, camera, sensor |
| `esp32` | sensor, gpio, telemetry |
| `web-server` | nginx (http), ssl, monitoring |
| `drone` | flight-controller, telemetry, camera, navigation |

### Register a Preset

```
register nighthawk as NAS
configure nighthawk as a NAS
register pi-zero as media-player
set up drone-01 as drone
```

---

## Adding Services

### Via Chat

```
# Add with preset
register nighthawk as NAS

# Add a single service
add samba service to nighthawk
nighthawk runs file-storage
assign media-player to pi-zero
add ssh service to carrera
pi5 has a sensor service
add nginx to carrera type web-server
```

### Via API

```bash
# Add a single service
curl -X POST http://localhost:8000/api/nodes/{node_id}/services \
  -H "Content-Type: application/json" \
  -d '{"name": "samba", "type": "file-storage", "description": "Samba file sharing"}'

# Register a preset
curl -X POST http://localhost:8000/api/nodes/{node_id}/services/preset \
  -H "Content-Type: application/json" \
  -d '{"preset": "nas"}'
```

---

## Service Types

Common service type values (free text — no enforced enum):

| Type | Description |
|---|---|
| `file-storage` | NAS, SMB, NFS |
| `media-player` | Plex, Kodi, VLC |
| `web-server` | nginx, Apache, Caddy |
| `database` | MySQL, PostgreSQL, Redis |
| `backup` | rsync, restic |
| `monitoring` | Prometheus, Grafana |
| `camera` | IP camera, capture device |
| `sensor` | Temperature, humidity, IMU |
| `flight-controller` | ArduPilot, PX4 |
| `motor-controller` | Robot drive system |
| `navigation` | Path planning |
| `gpio` | General purpose I/O |
| `ssh` | Remote shell access |
| `vpn` | WireGuard, OpenVPN |

---

## Commands

```
# List services
show services on nighthawk
what services does pi5 have
list all services

# Add services
add samba service to nighthawk
nighthawk runs file-storage
assign media-player to pi-zero
add ssh service to carrera

# Register preset
register nighthawk as NAS
register pi-zero as media-player
set up drone-01 as drone

# Remove services
remove samba service from nighthawk
remove ssh from carrera
delete media-player from pi-zero
unregister samba from nighthawk

# Rename services
rename service samba to file-sharing on nighthawk
rename ssh to remote-access on carrera
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/nodes/{id}/services` | GET | List services on a node |
| `POST /api/nodes/{id}/services` | POST | Add a service (upsert) |
| `POST /api/nodes/{id}/services/preset` | POST | Register a service preset |
| `DELETE /api/nodes/{id}/services/{name}` | DELETE | Remove a service |
| `PATCH /api/nodes/{id}/services/{name}` | PATCH | Rename or update a service |
| `GET /api/services` | GET | List all services across all nodes |

---

## Related Documentation

- [NodeRegistry.md](NodeRegistry.md) — Parent node management
- [CapabilityRegistry.md](CapabilityRegistry.md) — Capabilities on services
- [Infrastructure.md](Infrastructure.md) — Overview
