"""SILVIA-owned HTTP client for KOSINE's public REST contract.

Talks to a standalone, unmodified KOSINE service over HTTP only:
- ``POST /agent/tool/{name}``  — universal dispatch to any of KOSINE's tools
- ``GET  /agent/tools``        — capability discovery (tool list + schemas)
- ``GET  /health``             — liveness + object count

Stdlib ``urllib`` only (no third-party HTTP dep, matching SILVIA's convention),
and — deliberately — **no ``import kos``**. KOSINE is a replaceable external
brain reached purely through its published network interface; another AI system
could implement an equivalent client against the same endpoints.

The client is communication + translation only. It contains no SILVIA reasoning
policy (that lives in the provider/router/cognition layers). It exposes the same
method surface the rest of SILVIA already used from the KOSINE SDK, so it is a
drop-in transport replacement:
``call``, ``search_memory``, ``show_object``, ``get_timeline``, ``get_related``,
``list_objects``, ``create_memory``, ``update_memory``, ``create_relationship``,
``add_event``, ``health``, ``list_tools``, ``capabilities``, ``close``.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Optional

from backend.app.integrations.kosine.errors import (
    KosineProtocolError,
    KosineToolError,
    KosineUnavailable,
    KosineWriteBlocked,
)

logger = logging.getLogger("silvia.integrations.kosine")

# KOSINE keeps destructive tools in a separate, opt-in registry that is never
# served over the default surface. We refuse to even send them unless explicitly
# permitted — defense in depth on top of KOSINE's own gating.
_DESTRUCTIVE_TOOLS = frozenset({
    "clear_all", "clear_type", "clear_demo", "clear_inbox", "delete_object",
})


class KosineHTTPClient:
    """HTTP transport for KOSINE's universal-tool REST surface."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 15.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.4,
        allow_destructive: bool = False,
        api_token: str = "",
    ) -> None:
        if not base_url:
            raise ValueError("KosineHTTPClient requires a base_url")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.backoff_seconds = backoff_seconds
        self.allow_destructive = allow_destructive
        self.api_token = api_token
        self._capabilities: Optional[set[str]] = None

    # ── low-level HTTP ────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: Optional[dict],
                 correlation_id: str) -> tuple[int, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/json")
        req.add_header("X-Correlation-ID", correlation_id)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if self.api_token:
            req.add_header("Authorization", f"Bearer {self.api_token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return resp.status, self._parse_json(raw)
        except urllib.error.HTTPError as e:
            # Server responded with a non-2xx. 4xx are meaningful (e.g. 404
            # unknown tool); 5xx are retryable transport-ish failures.
            raw = e.read() if hasattr(e, "read") else b""
            return e.code, self._parse_json(raw, soft=True)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            raise KosineUnavailable(
                f"KOSINE unreachable at {url} [cid={correlation_id}]: {e}"
            ) from e

    @staticmethod
    def _parse_json(raw: bytes, soft: bool = False) -> Any:
        if not raw:
            return None if soft else {}
        try:
            return json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            if soft:
                return {"_raw": raw[:500].decode("utf-8", "replace")}
            raise KosineProtocolError(
                "KOSINE returned a non-JSON response",
                body=raw[:500].decode("utf-8", "replace"),
            )

    # ── envelope dispatch ─────────────────────────────────────────────────

    def call(self, tool_name: str, **params: Any) -> dict:
        """Invoke any KOSINE tool; return the full response envelope.

        The envelope shape is KOSINE's contract:
        ``{status, tool, data, objects_changed, events_created,
        confirmation_required, error}``.

        Raises:
            KosineWriteBlocked: destructive tool requested without permission.
            KosineUnavailable: transport failure after retries (service down).
            KosineProtocolError: response wasn't a valid envelope.

        A tool that ran but returned ``status='error'`` is NOT raised here — the
        envelope is returned so callers (e.g. the audit layer) can inspect
        ``status``/``error`` themselves, matching prior SDK behaviour.
        """
        if tool_name in _DESTRUCTIVE_TOOLS and not self.allow_destructive:
            raise KosineWriteBlocked(
                f"Refusing destructive KOSINE tool '{tool_name}' "
                "(allow_destructive is off)"
            )
        cid = uuid.uuid4().hex[:12]
        attempt = 0
        last_exc: Optional[Exception] = None
        while attempt <= self.max_retries:
            try:
                status, env = self._request(
                    "POST", f"/agent/tool/{tool_name}", dict(params), cid)
                if status >= 500:
                    # retryable server-side failure
                    last_exc = KosineUnavailable(
                        f"KOSINE {status} on '{tool_name}' [cid={cid}]")
                    raise last_exc
                if status == 404:
                    raise KosineToolError(
                        tool_name, "unknown tool (404)", correlation_id=cid)
                if not isinstance(env, dict) or "status" not in env:
                    raise KosineProtocolError(
                        f"KOSINE '{tool_name}' returned an unexpected shape "
                        f"[cid={cid}]",
                        body=str(env)[:500],
                    )
                return env
            except KosineUnavailable as e:
                last_exc = e
                if attempt >= self.max_retries:
                    break
                time.sleep(self.backoff_seconds * (2 ** attempt))
                attempt += 1
                logger.debug("KOSINE retry %d for '%s' [cid=%s]",
                             attempt, tool_name, cid)
        assert last_exc is not None
        raise last_exc

    def _data(self, tool_name: str, **params: Any) -> Any:
        """Call a READ tool and return its ``data`` payload.

        Transport failures propagate (KosineUnavailable) so the provider can
        degrade. A tool-level ``status='error'`` returns ``None`` (reads degrade
        gracefully) rather than raising.
        """
        env = self.call(tool_name, **{k: v for k, v in params.items()
                                      if v is not None})
        if env.get("status") != "ok":
            logger.debug("KOSINE read '%s' status=%s: %s",
                         tool_name, env.get("status"), env.get("error"))
            return None
        return env.get("data")

    # ── read convenience (drop-in for the prior SDK surface) ──────────────

    def search_memory(self, query: str, limit: int = 10) -> Any:
        return self._data("search_memory", query=query, limit=limit)

    def show_object(self, target: str) -> Any:
        return self._data("show_object", target=target)

    def get_timeline(self, target: Optional[str] = None, limit: int = 20) -> Any:
        return self._data("get_timeline", target=target, limit=limit)

    def get_related(self, target: str) -> Any:
        return self._data("get_related", target=target)

    def list_objects(self, type: Optional[str] = None,  # noqa: A002 (KOSINE param)
                     status: Optional[str] = None, limit: int = 100) -> Any:
        return self._data("list_objects", type=type, status=status, limit=limit)

    def get_graph_data(self, target: Optional[str] = None,
                       graph_type: str = "knowledge", depth: int = 1,
                       limit: int = 50) -> Any:
        return self._data("get_graph_data", target=target,
                          graph_type=graph_type, depth=depth, limit=limit)

    # ── write convenience (envelopes flow through the audit layer) ────────

    def create_memory(self, type: str, title: str, **fields: Any) -> dict:  # noqa: A002
        return self.call("create_memory", type=type, title=title, **fields)

    def update_memory(self, target: str, **fields: Any) -> dict:
        return self.call("update_memory", target=target, **fields)

    def create_relationship(self, from_: str, relation: str, to: str) -> dict:
        return self.call("create_relationship", **{"from": from_,
                                                   "relation": relation, "to": to})

    def add_event(self, target: str, description: str,
                  event_type: str = "note") -> dict:
        return self.call("add_event", target=target, description=description,
                         event_type=event_type)

    # ── health & capabilities ─────────────────────────────────────────────

    def health(self) -> dict:
        """GET /health → {'status': 'ok', 'objects': N}. Raises if unreachable."""
        cid = uuid.uuid4().hex[:12]
        status, body = self._request("GET", "/health", None, cid)
        if status != 200 or not isinstance(body, dict):
            raise KosineUnavailable(
                f"KOSINE /health returned {status} [cid={cid}]")
        return body

    def list_tools(self, include_destructive: bool = False) -> list[dict]:
        """GET /agent/tools → tool descriptors (name + JSON schema)."""
        cid = uuid.uuid4().hex[:12]
        suffix = "?include_destructive=true" if include_destructive else ""
        status, body = self._request("GET", f"/agent/tools{suffix}", None, cid)
        if status != 200:
            raise KosineUnavailable(
                f"KOSINE /agent/tools returned {status} [cid={cid}]")
        if isinstance(body, dict):
            tools = body.get("tools", body.get("data", []))
        else:
            tools = body or []
        return tools if isinstance(tools, list) else []

    def capabilities(self, refresh: bool = False) -> set[str]:
        """Return the set of available tool names (cached).

        Degrades to an empty set if KOSINE is unreachable — callers should treat
        an empty capability set as "unknown / degraded", not "no capabilities".
        """
        if self._capabilities is not None and not refresh:
            return self._capabilities
        try:
            tools = self.list_tools()
            names = {t.get("name", "") for t in tools if isinstance(t, dict)}
            names.discard("")
            self._capabilities = names
            return names
        except (KosineUnavailable, KosineProtocolError) as e:
            logger.debug("KOSINE capability discovery failed: %s", e)
            return set()

    def close(self) -> None:
        """No persistent connection to close (urllib); present for API parity."""
        self._capabilities = None
