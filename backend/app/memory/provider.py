"""Memory Provider Interface — Phase 18A.

Abstract base class for all SILVIA memory providers.
Each provider wraps a specific memory backend (Brain63, ProjectMemory,
KnowledgeGraph, SQLite, Workflows, Sessions) behind a unified interface.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MemoryEntry:
    """Unified memory entry returned by all providers."""
    id: str
    provider: str
    type: str
    title: str
    content: str
    project: str = ""
    date: str = ""
    source: str = ""
    score: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ProviderHealth:
    """Health status of a memory provider."""
    name: str
    available: bool
    entry_count: int = 0
    details: str = ""


@dataclass
class MemoryWriteProposal:
    """A proposed, not-yet-applied write to a memory provider.

    Providers translate this into their own approval/audit machinery. Nothing
    here writes directly — a proposal becomes a durable change only after review
    (see the WorkflowEngine approval lifecycle).
    """
    operation: str                      # create | update | relate | event
    object_type: str = ""               # provider object type (e.g. 'Decision')
    content: dict = field(default_factory=dict)   # proposed fields
    source_event: str = ""              # what produced this (event id / reason)
    confidence: float = 0.5
    requires_review: bool = True        # default: nothing auto-applies
    idempotency_key: str = ""           # dedup guard for repeated proposals
    provenance: dict = field(default_factory=dict)


class MemoryProvider(ABC):
    """Abstract base for memory providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Short identifier (e.g. 'brain63', 'project_memory')."""

    @abstractmethod
    def search(self, query: str, project: str = "", limit: int = 10) -> list[MemoryEntry]:
        """Search this provider's memory store."""

    @abstractmethod
    def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve a specific entry by ID."""

    @abstractmethod
    def timeline(self, project: str = "", limit: int = 50) -> list[MemoryEntry]:
        """Return entries ordered chronologically."""

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Return health/availability status."""

    def store(self, entry: dict) -> Optional[str]:
        """Store a new entry. Returns ID or None if read-only."""
        return None

    def update(self, entry_id: str, updates: dict) -> bool:
        """Update an existing entry. Returns success."""
        return False

    def delete(self, entry_id: str) -> bool:
        """Delete an entry. Returns success."""
        return False

    def relationships(self, entity: str = "", limit: int = 20) -> list[dict]:
        """Return relationships/connections (for graph-capable providers)."""
        return []

    def propose_write(self, proposal: "MemoryWriteProposal") -> Optional[str]:
        """Register a review-gated write proposal. Returns a proposal/workflow
        id, or None if the provider does not support writes. Never writes
        directly — approval happens elsewhere."""
        return None

    def capabilities(self) -> dict:
        """Describe what this provider supports, for the router/cognition layer.

        Default assumes a read-only, search-only provider. Providers override to
        advertise writes, relationship traversal, provenance, or a live
        network boundary. Keys are stable; add new ones additively.
        """
        return {
            "provider_id": self.provider_id,
            "searchable": True,
            "timeline": True,
            "relationships": False,
            "provenance": False,
            "writable": False,
            "remote": False,
        }
