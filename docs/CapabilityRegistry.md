# Capability Registry

Capabilities are named, executable actions that services expose. SILVIA can execute any registered capability on any node's service via natural language.

---

## Table of Contents

1. [Concepts](#concepts)
2. [Capability Namespaces](#capability-namespaces)
3. [Executing Capabilities](#executing-capabilities)
4. [Risk Levels](#risk-levels)
5. [Commands](#commands)
6. [API Reference](#api-reference)

---

## Concepts

The capability hierarchy is:

```
Node (storage-node)
  └── Service (plex)             ← ServiceRegistry
        └── Capability: media.play   ← CapabilityRegistry
        └── Capability: media.pause
        └── Capability: media.next
```

Capabilities use a dot-namespace: `<category>.<action>`. The category maps to a service type, and SILVIA automatically routes to the correct node+service.

**Node is optional.** If you say "play music" without naming a node, SILVIA searches all nodes for one with a `media.play` capability and routes to the first available one.

---

## Capability Namespaces

### `media` — Media Playback

| Capability | Description | Args |
|---|---|---|
| `media.play` | Start playback | — |
| `media.pause` | Pause playback | — |
| `media.stop` | Stop playback | — |
| `media.next` | Next track | — |
| `media.previous` | Previous track | — |
| `media.volume` | Set volume | `{"volume": 50}` (0–100) |

### `motion` — Physical Movement (robots, drones)

| Capability | Description | Args |
|---|---|---|
| `motion.forward` | Move forward | `{"speed": 0.5, "duration": 2}` |
| `motion.backward` | Move backward | — |
| `motion.stop` | Stop movement | — |
| `motion.turn_left` | Turn left | `{"degrees": 90}` |
| `motion.turn_right` | Turn right | `{"degrees": 90}` |
| `motion.hover` | Hold position (drones) | — |

### `camera` — Camera Control

| Capability | Description | Args |
|---|---|---|
| `camera.capture` | Take a still photo | — |
| `camera.stream` | Start video stream | `{"url": "rtsp://..."}` |
| `camera.stream_stop` | Stop video stream | — |

### `system` — System Management

| Capability | Description | Args |
|---|---|---|
| `system.start` | Start a service/process | `{"service": "nginx"}` |
| `system.stop` | Stop a service/process | `{"service": "nginx"}` |
| `system.restart` | Restart a service | `{"service": "nginx"}` |
| `system.status` | Check service status | `{"service": "nginx"}` |
| `system.reload` | Reload config | `{"service": "nginx"}` |

### `sensor` — Sensor Reading

| Capability | Description | Args |
|---|---|---|
| `sensor.read` | Read current sensor data | — |
| `sensor.calibrate` | Trigger sensor calibration | — |

### `battery` — Power

| Capability | Description | Args |
|---|---|---|
| `battery.status` | Get battery percentage | — |

### `gpio` — General Purpose I/O

| Capability | Description | Args |
|---|---|---|
| `gpio.set` | Set a GPIO pin | `{"pin": 4, "value": 1}` |
| `gpio.get` | Read a GPIO pin | `{"pin": 4}` |

### `navigation` — Autonomous Navigation

| Capability | Description | Args |
|---|---|---|
| `navigation.goto` | Navigate to coordinates | `{"lat": 28.6, "lon": 77.2}` |
| `navigation.home` | Return to home/base | — |
| `navigation.waypoint` | Set next waypoint | `{"id": "wp1"}` |

### `audio` — Audio Playback

| Capability | Description | Args |
|---|---|---|
| `audio.play` | Play audio file | `{"file": "alarm.mp3"}` |
| `audio.stop` | Stop audio | — |
| `audio.volume` | Set volume | `{"volume": 70}` |

---

## Executing Capabilities

### Via Chat

```
play music on storage-node
pause music
skip track on storage-node
stop the music
set volume to 50 on storage-node
move drone-01 forward
stop rover
take a photo on pi5
start camera stream on pi5
restart nginx on remote-server
start mysql on storage-node
read sensor on esp32-01
battery status on drone-01
```

### Node is Optional

```
pause music             # SILVIA finds the node with media.pause
restart nginx           # SILVIA finds the node running nginx
read sensor             # SILVIA finds the first node with sensor.read
```

### Via API

```bash
curl -X POST http://localhost:8000/api/capabilities/execute \
  -H "Content-Type: application/json" \
  -d '{
    "capability": "media.play",
    "node": "storage-node",
    "args": {}
  }'
```

---

## Risk Levels

Capabilities have a risk level. High and critical capabilities require explicit confirmation:

| Risk Level | Confirmation Required | Examples |
|---|---|---|
| `low` | No | media.play, sensor.read, camera.capture |
| `medium` | No | system.status, battery.status |
| `high` | Yes | system.restart, motion.forward |
| `critical` | Yes | motion.stop (emergency), system.stop |

When confirmation is required, SILVIA will ask:
```
About to execute [system.restart] on [remote-server]. Confirm?
```

---

## Commands

```
# Execute capabilities
play music on storage-node
pause music
skip track on storage-node
stop the music
set volume to 50 on storage-node
move drone-01 forward
move backward
stop rover
take a photo on pi5
start camera stream on pi5
stop stream on pi5
restart nginx on remote-server
start mysql on storage-node
stop mysql on storage-node
check nginx status on remote-server
read sensor on esp32-01
calibrate sensor on esp32-01
battery status on drone-01
set gpio pin 4 high on esp32-01
read gpio pin 4 on esp32-01
navigate drone-01 home
go to waypoint 1
audio volume 70 on storage-node
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/nodes/{id}/services/{svc}/capabilities` | GET | List capabilities |
| `POST /api/nodes/{id}/services/{svc}/capabilities` | POST | Register capability |
| `DELETE /api/nodes/{id}/services/{svc}/capabilities/{name}` | DELETE | Remove capability |
| `POST /api/capabilities/execute` | POST | Execute a capability |

---

## Related Documentation

- [ServiceRegistry.md](ServiceRegistry.md) — Services that host capabilities
- [NodeRegistry.md](NodeRegistry.md) — Nodes that run services
- [Infrastructure.md](Infrastructure.md) — Infrastructure overview
