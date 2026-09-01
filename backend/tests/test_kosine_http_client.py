"""Unit tests for the SILVIA-owned KOSINE HTTP client (Phase 19 boundary).

No network and no `import kos`: urllib is monkeypatched. Verifies envelope
dispatch, read-data extraction, error translation (unavailable/tool/protocol),
the destructive guard, bounded retries, and capability discovery.

Run: pytest backend/tests/test_kosine_http_client.py -v
"""
from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

import pytest

from backend.app.integrations.kosine.client import KosineHTTPClient
from backend.app.integrations.kosine.errors import (
    KosineProtocolError,
    KosineToolError,
    KosineUnavailable,
    KosineWriteBlocked,
)


class FakeResp:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def envelope(status="ok", data=None, error=None, **extra) -> bytes:
    return json.dumps({
        "status": status, "tool": "t", "data": data,
        "objects_changed": extra.get("objects_changed", []),
        "events_created": extra.get("events_created", []),
        "confirmation_required": None, "error": error,
    }).encode("utf-8")


def http_error(code: int, body: bytes = b"{}") -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", code, "err", None, io.BytesIO(body))


@pytest.fixture
def patch_urlopen(monkeypatch):
    state = {"n": 0, "reqs": []}

    def install(handler):
        def fake_urlopen(req, timeout=None):
            state["n"] += 1
            state["reqs"].append(req)
            result = handler(req, state["n"])
            if isinstance(result, Exception):
                raise result
            return result
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
        return state
    return install


def client(**kw) -> KosineHTTPClient:
    kw.setdefault("backoff_seconds", 0.0)  # keep retries instant in tests
    return KosineHTTPClient("http://kosine.test", **kw)


def test_call_returns_full_envelope(patch_urlopen):
    patch_urlopen(lambda req, n: FakeResp(200, envelope(data={"hits": 1})))
    env = client().call("search_memory", query="x")
    assert env["status"] == "ok"
    assert env["data"] == {"hits": 1}


def test_search_memory_returns_data(patch_urlopen):
    patch_urlopen(lambda req, n: FakeResp(200, envelope(data=[{"id": "1"}])))
    assert client().search_memory("x") == [{"id": "1"}]


def test_read_status_error_returns_none(patch_urlopen):
    # A tool-level error on a read degrades to None (provider maps to []).
    patch_urlopen(lambda req, n: FakeResp(200, envelope(status="error",
                                                        error="boom")))
    assert client().search_memory("x") is None


def test_unavailable_raises_and_retries(patch_urlopen):
    state = patch_urlopen(lambda req, n: urllib.error.URLError("refused"))
    with pytest.raises(KosineUnavailable):
        client(max_retries=2).call("search_memory", query="x")
    assert state["n"] == 3  # 1 initial + 2 retries


def test_retry_then_success(patch_urlopen):
    def handler(req, n):
        return urllib.error.URLError("refused") if n == 1 \
            else FakeResp(200, envelope(data="ok"))
    state = patch_urlopen(handler)
    env = client(max_retries=2).call("search_memory", query="x")
    assert env["data"] == "ok"
    assert state["n"] == 2


def test_500_is_unavailable(patch_urlopen):
    state = patch_urlopen(lambda req, n: http_error(500, b"server boom"))
    with pytest.raises(KosineUnavailable):
        client(max_retries=1).call("list_objects")
    assert state["n"] == 2  # retried once


def test_404_is_tool_error(patch_urlopen):
    patch_urlopen(lambda req, n: http_error(404, b"no tool"))
    with pytest.raises(KosineToolError):
        client().call("nonexistent_tool")


def test_destructive_tool_blocked_without_permission(patch_urlopen):
    state = patch_urlopen(lambda req, n: FakeResp(200, envelope()))
    with pytest.raises(KosineWriteBlocked):
        client().call("clear_all")
    assert state["n"] == 0  # never hit the network


def test_destructive_allowed_when_opted_in(patch_urlopen):
    patch_urlopen(lambda req, n: FakeResp(200, envelope(data="cleared")))
    env = client(allow_destructive=True).call("clear_all")
    assert env["data"] == "cleared"


def test_protocol_error_on_unexpected_shape(patch_urlopen):
    patch_urlopen(lambda req, n: FakeResp(200, json.dumps({"foo": 1}).encode()))
    with pytest.raises(KosineProtocolError):
        client().call("search_memory", query="x")


def test_health(patch_urlopen):
    patch_urlopen(lambda req, n: FakeResp(
        200, json.dumps({"status": "ok", "objects": 7}).encode()))
    assert client().health()["objects"] == 7


def test_capabilities_discovery(patch_urlopen):
    tools = {"tools": [{"name": "search_memory"}, {"name": "get_related"}]}
    patch_urlopen(lambda req, n: FakeResp(200, json.dumps(tools).encode()))
    caps = client().capabilities()
    assert "search_memory" in caps and "get_related" in caps


def test_capabilities_empty_when_unreachable(patch_urlopen):
    patch_urlopen(lambda req, n: urllib.error.URLError("down"))
    assert client().capabilities() == set()


def test_correlation_id_header_present(patch_urlopen):
    state = patch_urlopen(lambda req, n: FakeResp(200, envelope(data=1)))
    client().call("search_memory", query="x")
    assert state["reqs"][0].get_header("X-correlation-id")  # urllib title-cases


def test_bearer_token_header(patch_urlopen):
    state = patch_urlopen(lambda req, n: FakeResp(200, envelope(data=1)))
    client(api_token="secret").call("search_memory", query="x")
    assert state["reqs"][0].get_header("Authorization") == "Bearer secret"
