"""Integration tests: KosineProvider ↔ a mocked KOSINE REST service (Phase 7).

Exercises the full SILVIA-side read path over the compliant HTTP boundary
(KosineProvider → kosine_client → KosineHTTPClient → mocked urllib), plus the
degraded-operation and malformed-response cases. No real KOSINE, no `import kos`.

Run: pytest backend/tests/test_kosine_provider_integration.py -v
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest


class FakeResp:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def env(data, status="ok"):
    return json.dumps({"status": status, "tool": "t", "data": data,
                       "objects_changed": [], "events_created": [],
                       "confirmation_required": None, "error": None}).encode()


@pytest.fixture
def rest_kosine(monkeypatch):
    """KOSINE enabled over the compliant REST transport, urllib mocked."""
    from backend import config
    from backend.app.memory import kosine_client

    monkeypatch.setattr(config, "KOSINE_ENABLED", True)
    monkeypatch.setattr(config, "KOSINE_TRANSPORT", "rest")
    monkeypatch.setattr(config, "KOSINE_BASE_URL", "http://kosine.test")
    monkeypatch.setattr(config, "KOSINE_MAX_RETRIES", 0)
    kosine_client.reset()

    state = {"handler": None}

    def fake_urlopen(req, timeout=None):
        result = state["handler"](req)
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    yield state
    kosine_client.reset()


def test_provider_search_maps_kosine_objects(rest_kosine):
    from backend.app.memory.kosine_provider import KosineProvider
    objs = [{"id": "01ABC", "type": "Project", "title": "Silvia",
             "description": "an ai os", "source_path": "vault/Silvia.md",
             "updated_at": "2026-01-01T00:00:00Z", "confidence": 0.9,
             "status": "active", "tags": ["ai"]}]
    rest_kosine["handler"] = lambda req: FakeResp(200, env(objs))

    results = KosineProvider().search("silvia", limit=5)
    assert len(results) == 1
    e = results[0]
    assert e.provider == "kosine" and e.title == "Silvia"
    assert e.source == "vault/Silvia.md"          # provenance preserved
    assert e.content == "an ai os"
    assert e.metadata["confidence"] == 0.9


def test_provider_health_counts_objects(rest_kosine):
    from backend.app.memory.kosine_provider import KosineProvider
    rest_kosine["handler"] = lambda req: FakeResp(200, env([{"id": "1"}, {"id": "2"}]))
    h = KosineProvider().health()
    assert h.available is True and h.entry_count == 2


def test_provider_degrades_when_kosine_unavailable(rest_kosine):
    from backend.app.memory.kosine_provider import KosineProvider
    rest_kosine["handler"] = lambda req: urllib.error.URLError("connection refused")
    prov = KosineProvider()
    assert prov.search("x") == []            # no fabricated results
    assert prov.health().available is False   # surfaced as unavailable


def test_provider_handles_malformed_response(rest_kosine):
    from backend.app.memory.kosine_provider import KosineProvider
    rest_kosine["handler"] = lambda req: FakeResp(200, b"not json at all")
    # malformed → provider swallows to empty rather than crashing the caller
    assert KosineProvider().search("x") == []


def test_provider_relationships_over_rest(rest_kosine):
    from backend.app.memory.kosine_provider import KosineProvider
    rels = [{"relation": "depends_on", "object_id": "T1", "title": "Target"}]
    rest_kosine["handler"] = lambda req: FakeResp(200, env(rels))
    out = KosineProvider().relationships(entity="Silvia", limit=5)
    assert out and out[0]["relation"] == "depends_on"


def test_client_is_http_not_sdk(rest_kosine):
    """The active client is the SILVIA-owned HTTP client — never the kos SDK."""
    import sys
    from backend.app.memory import kosine_client
    from backend.app.integrations.kosine import KosineHTTPClient
    rest_kosine["handler"] = lambda req: FakeResp(200, env([]))
    client = kosine_client.get_client()
    assert isinstance(client, KosineHTTPClient)
    assert "kos" not in sys.modules  # compliant boundary: no KOSINE internals
