"""HTTP adapter for a locally running SILVIA backend.

This is the ONLY place the QA harness talks to SILVIA. It uses the real
FastAPI surface (POST /api/chat, /api/voice/*) over localhost — no mocks,
no faked answers. If the backend is not running, every call raises
SilviaUnreachable and the test runner records an honest error result.

Stdlib only (urllib) so the harness has zero extra dependencies.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://localhost:8000"
QA_SESSION_ID = "qa-agent"


class SilviaUnreachable(Exception):
    """Raised when the SILVIA backend cannot be reached at all."""


class SilviaClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 90.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ── low-level ────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: dict | None = None,
                 timeout: float | None = None) -> tuple[int, bytes, str]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return resp.status, resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            # Server responded with an error status — still a real response.
            return e.code, e.read(), e.headers.get("Content-Type", "") if e.headers else ""
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            raise SilviaUnreachable(f"{method} {url} failed: {e}") from e

    # ── health ───────────────────────────────────────────────────────────

    def is_alive(self) -> bool:
        try:
            status, _, _ = self._request("GET", "/health", timeout=5.0)
            return status == 200
        except SilviaUnreachable:
            return False

    # ── chat ─────────────────────────────────────────────────────────────

    def chat(self, question: str, session_id: str = QA_SESSION_ID) -> dict:
        """Send a chat query and return a normalized record.

        Returns a dict with: answer, sources, tool_calls, payload_keys,
        text_latency_seconds, server_processing_ms, http_status, error.
        Never fakes success: any transport/parse problem lands in "error".
        """
        payload = {
            "query": question,
            "mode": "auto",
            "session_id": session_id,
            "metadata": {"source": "qa_agent"},
        }
        started = time.monotonic()
        status, raw, _ = self._request("POST", "/api/chat", payload)
        elapsed = time.monotonic() - started

        record: dict = {
            "http_status": status,
            "text_latency_seconds": round(elapsed, 3),
            "answer": "",
            "sources": [],
            "tool_calls": [],
            "payload_keys": [],
            "server_processing_ms": None,
            "error": None,
        }
        if status != 200:
            record["error"] = f"HTTP {status}: {raw[:500].decode('utf-8', 'replace')}"
            return record
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as e:
            record["error"] = f"Non-JSON response: {e}"
            return record

        record["answer"] = body.get("answer", "") or ""
        record["server_processing_ms"] = body.get("processing_time_ms")
        record["payload_keys"] = sorted((body.get("payload") or {}).keys())
        for src in body.get("sources") or []:
            record["sources"].append({
                "title": src.get("title", ""),
                "source": src.get("source", ""),
                "url": src.get("url", ""),
            })
        # Tool executions are emitted into the response log as "[TOOL] <name>".
        for entry in body.get("logs") or []:
            title = entry.get("title", "")
            if title.startswith("[TOOL]"):
                record["tool_calls"].append({
                    "tool": title.replace("[TOOL]", "").strip(),
                    "detail": entry.get("detail", ""),
                })
        return record

    # ── voice ────────────────────────────────────────────────────────────

    def synthesize(self, text: str) -> dict:
        """POST /api/voice/synthesize and measure wall-clock TTS latency."""
        started = time.monotonic()
        status, raw, content_type = self._request(
            "POST", "/api/voice/synthesize", {"text": text}
        )
        elapsed = time.monotonic() - started
        ok = status == 200 and len(raw) > 0 and "audio" in content_type
        return {
            "http_status": status,
            "tts_latency_seconds": round(elapsed, 3),
            "audio_bytes": len(raw) if ok else 0,
            "ok": ok,
            "error": None if ok else f"HTTP {status}: {raw[:300].decode('utf-8', 'replace')}",
        }

    def voice_status(self) -> dict:
        status, raw, _ = self._request("GET", "/api/voice/status", timeout=10.0)
        out = {"http_status": status, "ok": False, "body": None, "error": None}
        if status == 200:
            try:
                out["body"] = json.loads(raw)
                out["ok"] = True
            except json.JSONDecodeError as e:
                out["error"] = f"Non-JSON /voice/status response: {e}"
        else:
            out["error"] = f"HTTP {status}"
        return out

    def voice_latency_metrics(self) -> dict:
        status, raw, _ = self._request("GET", "/api/voice/latency", timeout=10.0)
        out = {"http_status": status, "ok": False, "body": None, "error": None}
        if status == 200:
            try:
                out["body"] = json.loads(raw)
                out["ok"] = True
            except json.JSONDecodeError as e:
                out["error"] = f"Non-JSON /voice/latency response: {e}"
        else:
            out["error"] = f"HTTP {status}"
        return out
