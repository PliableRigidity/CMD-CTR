"""Data models for the Node Service / Capability layer (Phase 10)."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

# Valid transport types
TRANSPORTS = ["http", "mqtt", "ssh", "websocket", "local", "custom"]

# Valid service status values
SERVICE_STATUSES = ["running", "stopped", "failed", "starting", "stopping", "unknown"]

# Valid risk levels
RISK_LEVELS = ["low", "medium", "high", "critical"]

# Capability namespace prefixes — new namespaces can be added here
CAPABILITY_NAMESPACES = [
    "media",
    "motion",
    "camera",
    "system",
    "sensor",
    "navigation",
    "battery",
    "gpio",
    "display",
    "network",
    "audio",
    "custom",
]


class ServiceCapability(BaseModel):
    """A single capability exposed by a service."""
    id: str
    service_id: str
    name: str                                           # e.g. "media.play"
    namespace: str                                      # e.g. "media"
    description: Optional[str] = None
    parameters_schema: Optional[dict] = None            # JSON Schema for args
    transport_config: Optional[dict] = None             # capability-level transport override
    confirmation_required: bool = False
    risk_level: str = "low"
    enabled: bool = True
    executor: Optional[str] = None                      # ssh | http | local | mqtt
    command: Optional[str] = None                       # e.g. "sudo systemctl restart {service}"


class ServiceCapabilityCreate(BaseModel):
    name: str                                           # e.g. "media.play"
    description: Optional[str] = None
    parameters_schema: Optional[dict] = None
    transport_config: Optional[dict] = None
    confirmation_required: bool = False
    risk_level: str = "low"
    enabled: bool = True
    executor: Optional[str] = None
    command: Optional[str] = None


class NodeServiceModel(BaseModel):
    """A service running on a node."""
    id: str
    node_id: str
    node_name: Optional[str] = None                     # joined from nodes for display
    name: str                                           # e.g. "mp3-player"
    type: str = "custom"                                # e.g. "media", "motion", "sensor"
    description: Optional[str] = None
    status: str = "unknown"
    transport: str = "http"
    endpoint: Optional[str] = None                      # URL / topic prefix / hostname
    config: dict = Field(default_factory=dict)          # additional transport config
    metadata: dict = Field(default_factory=dict)        # free-form metadata
    last_seen: Optional[str] = None
    capabilities: list[ServiceCapability] = Field(default_factory=list)


class NodeServiceCreate(BaseModel):
    name: str
    type: str = "custom"
    description: Optional[str] = None
    status: str = "unknown"
    transport: str = "http"
    endpoint: Optional[str] = None
    config: dict = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)


class NodeServiceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    transport: Optional[str] = None
    endpoint: Optional[str] = None
    config: Optional[dict] = None
    metadata: Optional[dict] = None


class ServiceManifest(BaseModel):
    """
    Device-reported manifest. Ingested from silvia-agent /manifest endpoint
    or from MQTT silvia/manifest/{node_id}. Used to upsert services + capabilities
    into the registry without manual registration.
    """
    services: list[ServiceManifestEntry]


class ServiceManifestEntry(BaseModel):
    name: str
    type: str = "custom"
    status: str = "running"
    transport: str = "http"
    endpoint: Optional[str] = None
    config: dict = Field(default_factory=dict)
    capabilities: list[ManifestCapability] = Field(default_factory=list)


class ManifestCapability(BaseModel):
    name: str
    description: Optional[str] = None
    parameters_schema: Optional[dict] = None
    transport_config: Optional[dict] = None
    confirmation_required: bool = False
    risk_level: str = "low"


class CapabilityMatch(BaseModel):
    """Result of a capability search — one service that has the requested capability."""
    capability_id: str
    capability_name: str
    capability_risk: str
    capability_confirmation: bool
    service_id: str
    service_name: str
    service_type: str
    service_status: str
    service_transport: str
    service_endpoint: Optional[str]
    service_config: dict
    node_id: str
    node_name: str


class CapabilityExecuteRequest(BaseModel):
    """Body for POST /api/capabilities/execute"""
    capability: str                                     # e.g. "media.play"
    service_id: Optional[str] = None                   # if user has already chosen a service
    node_name: Optional[str] = None                     # optional node hint for resolution
    args: dict = Field(default_factory=dict)


# Forward ref fix for ServiceManifest
ServiceManifest.model_rebuild()
