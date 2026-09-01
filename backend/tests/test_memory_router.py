"""Unit tests for the MemoryManager router modes + hybrid dedup/conflict.

Verifies MEMORY_MODE priority construction (auto/brain63/kosine/hybrid) and the
deterministic cross-provider dedup that marks — never merges — conflicts.

Run: pytest backend/tests/test_memory_router.py -v
"""
from __future__ import annotations

import pytest

from backend import config
from backend.app.memory.provider import MemoryEntry, MemoryProvider, ProviderHealth
from backend.app.services.memory_manager import MemoryManager


class FakeProvider(MemoryProvider):
    def __init__(self, pid: str, entries=None):
        self._pid = pid
        self._entries = entries or []

    @property
    def name(self) -> str:
        return self._pid.title()

    @property
    def provider_id(self) -> str:
        return self._pid

    def search(self, query: str, project: str = "", limit: int = 10):
        return list(self._entries)[:limit]

    def get(self, entry_id):
        return None

    def timeline(self, project: str = "", limit: int = 50):
        return []

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, True, len(self._entries))


def entry(pid, title, content, score=1.0, type="project"):
    return MemoryEntry(id=f"{pid}-{title}", provider=pid, type=type,
                       title=title, content=content, score=score)


def make_manager(providers, monkeypatch, mode="", primary=False):
    monkeypatch.setattr(config, "MEMORY_MODE", mode)
    monkeypatch.setattr(config, "KOSINE_PRIMARY", primary)
    mm = MemoryManager.__new__(MemoryManager)
    mm._providers = {p.provider_id: p for p in providers}
    mm._priority = mm._build_priority()
    return mm


# ── priority / mode ───────────────────────────────────────────────────────

def test_auto_mode_kosine_primary(monkeypatch):
    mm = make_manager(
        [FakeProvider("brain63"), FakeProvider("kosine"), FakeProvider("sqlite")],
        monkeypatch, mode="", primary=True)
    assert mm._priority[0] == "kosine"
    assert mm._priority[-1] == "brain63"  # demoted to fallback


def test_auto_mode_default_brain63_first(monkeypatch):
    mm = make_manager(
        [FakeProvider("brain63"), FakeProvider("kosine")],
        monkeypatch, mode="", primary=False)
    assert mm._priority[0] == "brain63"
    assert "kosine" in mm._priority  # appended, not primary


def test_brain63_mode_excludes_kosine(monkeypatch):
    mm = make_manager(
        [FakeProvider("brain63"), FakeProvider("kosine"), FakeProvider("sqlite")],
        monkeypatch, mode="brain63")
    assert "kosine" not in mm._priority
    assert mm._priority[0] == "brain63"


def test_kosine_mode_kosine_first_brain63_fallback(monkeypatch):
    mm = make_manager(
        [FakeProvider("brain63"), FakeProvider("kosine"), FakeProvider("sqlite")],
        monkeypatch, mode="kosine")
    assert mm._priority[0] == "kosine"
    assert mm._priority[-1] == "brain63"


def test_hybrid_mode_includes_both(monkeypatch):
    mm = make_manager(
        [FakeProvider("brain63"), FakeProvider("kosine")],
        monkeypatch, mode="hybrid")
    assert "kosine" in mm._priority and "brain63" in mm._priority


def test_mode_accessor(monkeypatch):
    monkeypatch.setattr(config, "MEMORY_MODE", "")
    mm = make_manager([FakeProvider("brain63")], monkeypatch, mode="")
    assert mm.mode() == "auto"


# ── dedup + conflict marking ────────────────────────────────────────────────

def test_dedup_same_content_no_conflict():
    e = [entry("kosine", "Silvia", "an ai os", 0.9),
         entry("brain63", "Silvia", "an ai os", 0.7)]
    out = MemoryManager._dedup_and_mark_conflicts(e)
    assert len(out) == 1
    assert out[0].provider == "kosine"  # higher score kept
    assert out[0].metadata["conflict"] is False
    assert set(out[0].metadata["providers"]) == {"kosine", "brain63"}


def test_dedup_conflicting_content_marked():
    e = [entry("kosine", "Nebula", "status active", 0.9),
         entry("brain63", "Nebula", "status archived", 0.6)]
    out = MemoryManager._dedup_and_mark_conflicts(e)
    assert len(out) == 1
    assert out[0].metadata["conflict"] is True
    versions = out[0].metadata["conflicting_versions"]
    assert any(v["provider"] == "brain63" for v in versions)


def test_dedup_keeps_distinct_titles():
    e = [entry("kosine", "A", "x"), entry("kosine", "B", "y")]
    out = MemoryManager._dedup_and_mark_conflicts(e)
    assert len(out) == 2


def test_hybrid_search_dedupes(monkeypatch):
    shared = [entry("_", "Silvia", "same", 1.0)]
    k = FakeProvider("kosine", [entry("kosine", "Silvia", "same", 0.9)])
    b = FakeProvider("brain63", [entry("brain63", "Silvia", "same", 0.8)])
    mm = make_manager([b, k], monkeypatch, mode="hybrid")
    results = mm.search("silvia", limit=10)
    titles = [r.title for r in results]
    assert titles.count("Silvia") == 1  # deduped across providers


def test_non_hybrid_search_does_not_dedupe(monkeypatch):
    k = FakeProvider("kosine", [entry("kosine", "Silvia", "same", 0.9)])
    b = FakeProvider("brain63", [entry("brain63", "Silvia", "same", 0.8)])
    mm = make_manager([b, k], monkeypatch, mode="", primary=True)
    results = mm.search("silvia", limit=10)
    assert len([r for r in results if r.title == "Silvia"]) == 2  # both kept
