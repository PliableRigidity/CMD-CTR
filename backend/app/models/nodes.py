from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

NODE_TYPES = [
    "workstation",
    "server",
    "raspberry-pi",
    "vps",
    "nas",
    "router",
    "vm",
    "container",
    "cyberdeck",
    "edge-device",
    "drone",
    "robot",
    "esp32",
    "sensor-network",
    "custom",
]


class NodeCreate(BaseModel):
    name: str
    type: str = "custom"
    hostname: str = ""
    tailscale_ip: Optional[str] = None
    tailscale_name: Optional[str] = None
    agent_url: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    hostname: Optional[str] = None
    tailscale_ip: Optional[str] = None
    tailscale_name: Optional[str] = None
    agent_url: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[list[str]] = None
    notes: Optional[str] = None


class NodeMetricsUpdate(BaseModel):
    status: Optional[str] = None
    cpu: Optional[float] = None
    ram: Optional[float] = None
    disk: Optional[float] = None
    temperature: Optional[float] = None
    uptime: Optional[int] = None
    services: Optional[list[str]] = None
    capabilities: Optional[list[str]] = None
    last_verified: Optional[str] = None
    verification_source: Optional[str] = None
    latency_ms: Optional[float] = None


class Node(BaseModel):
    id: str
    name: str
    type: str = "custom"
    hostname: str = ""
    tailscale_ip: Optional[str] = None
    tailscale_name: Optional[str] = None
    agent_url: Optional[str] = None
    status: str = "unknown"
    cpu: Optional[float] = None
    ram: Optional[float] = None
    disk: Optional[float] = None
    temperature: Optional[float] = None
    uptime: Optional[int] = None
    services: Optional[list[str]] = None
    capabilities: Optional[list[str]] = None
    last_seen: Optional[str] = None
    last_probe_at: Optional[str] = None
    last_verified: Optional[str] = None
    verification_source: Optional[str] = None
    latency_ms: Optional[float] = None
    resolved_ip: Optional[str] = None
    hostname_valid: Optional[bool] = None
    tailscale_reachable: Optional[bool] = None
    probe_error: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
