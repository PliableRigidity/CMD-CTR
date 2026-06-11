"""SQLite-backed Node Registry — tracks SILVIA infrastructure nodes."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import socket
import subprocess
import time
import uuid
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from typing import Optional

try:
    import psutil as _psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

from backend.app.models.nodes import Node, NodeCreate, NodeMetricsUpdate, NodeUpdate

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db() -> None:
    conn = _conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id              TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                type            TEXT NOT NULL DEFAULT 'custom',
                hostname        TEXT NOT NULL DEFAULT '',
                tailscale_ip    TEXT,
                tailscale_name  TEXT,
                status          TEXT NOT NULL DEFAULT 'unknown',
                cpu             REAL,
                ram             REAL,
                disk            REAL,
                temperature     REAL,
                uptime          INTEGER,
                last_seen       TEXT,
                last_probe_at   TEXT,
                latency_ms      REAL,
                resolved_ip     TEXT,
                hostname_valid  INTEGER,
                tailscale_reachable INTEGER,
                probe_error     TEXT,
                tags            TEXT NOT NULL DEFAULT '[]',
                notes           TEXT
            );
        """)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}
        for column_name, column_type in [
            ("last_probe_at", "TEXT"),
            ("latency_ms", "REAL"),
            ("resolved_ip", "TEXT"),
            ("hostname_valid", "INTEGER"),
            ("tailscale_reachable", "INTEGER"),
            ("probe_error", "TEXT"),
        ]:
            if column_name not in existing:
                conn.execute(f"ALTER TABLE nodes ADD COLUMN {column_name} {column_type}")
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        if count == 0:
            conn.execute(
                """INSERT INTO nodes (id, name, type, hostname, status, tags, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    "workstation",
                    "Workstation",
                    "workstation",
                    "local",
                    "unknown",
                    '["core"]',
                    "Primary local node — SILVIA host machine",
                ),
            )
            conn.commit()
    finally:
        conn.close()


def _row_to_node(row) -> Node:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    if d.get("hostname_valid") is not None:
        d["hostname_valid"] = bool(d["hostname_valid"])
    if d.get("tailscale_reachable") is not None:
        d["tailscale_reachable"] = bool(d["tailscale_reachable"])
    return Node(**d)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NodeService:
    def __init__(self) -> None:
        _init_db()

    def list_nodes(self) -> list[Node]:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM nodes ORDER BY name ASC"
            ).fetchall()
            return [_row_to_node(r) for r in rows]
        finally:
            conn.close()

    def get_node(self, node_id: str) -> Optional[Node]:
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT * FROM nodes WHERE id = ?", (node_id,)
            ).fetchone()
            return _row_to_node(row) if row else None
        finally:
            conn.close()

    def create_node(self, data: NodeCreate) -> Node:
        node_id = str(uuid.uuid4())[:8]
        conn = _conn()
        try:
            conn.execute(
                """INSERT INTO nodes
                       (id, name, type, hostname, tailscale_ip, tailscale_name, status, tags, notes)
                   VALUES (?, ?, ?, ?, ?, ?, 'unknown', ?, ?)""",
                (
                    node_id,
                    data.name,
                    data.type,
                    data.hostname or "",
                    data.tailscale_ip,
                    data.tailscale_name,
                    json.dumps(data.tags),
                    data.notes,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        self.probe_node(node_id)
        return self.get_node(node_id)

    def update_metrics(self, node_id: str, metrics: NodeMetricsUpdate) -> Optional[Node]:
        updates = {k: v for k, v in metrics.model_dump().items() if v is not None}
        if not updates:
            return self.get_node(node_id)
        updates["last_seen"] = datetime.now(timezone.utc).isoformat()
        cols = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [node_id]
        conn = _conn()
        try:
            conn.execute(f"UPDATE nodes SET {cols} WHERE id = ?", vals)
            conn.commit()
            return self.get_node(node_id)
        finally:
            conn.close()

    def update_node(self, node_id: str, data: NodeUpdate) -> Optional[Node]:
        updates = data.model_dump(exclude_unset=True)
        if "tags" in updates and updates["tags"] is not None:
            updates["tags"] = json.dumps(updates["tags"])
        if not updates:
            return self.get_node(node_id)
        cols = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [node_id]
        conn = _conn()
        try:
            conn.execute(f"UPDATE nodes SET {cols} WHERE id = ?", vals)
            conn.commit()
            return self.get_node(node_id)
        finally:
            conn.close()

    def probe_node(self, node_id: str) -> Optional[Node]:
        node = self.get_node(node_id)
        if not node:
            return None

        if node.hostname == "local" or node.type == "workstation":
            return self._probe_local(node_id)

        probe = self._probe_targets(node)
        conn = _conn()
        try:
            conn.execute(
                """
                UPDATE nodes
                SET status = ?, last_probe_at = ?, latency_ms = ?, resolved_ip = ?,
                    hostname_valid = ?, tailscale_reachable = ?, probe_error = ?, last_seen = COALESCE(?, last_seen)
                WHERE id = ?
                """,
                (
                    probe["status"],
                    probe["checked_at"],
                    probe["latency_ms"],
                    probe["resolved_ip"],
                    None if probe["hostname_valid"] is None else int(probe["hostname_valid"]),
                    None if probe["tailscale_reachable"] is None else int(probe["tailscale_reachable"]),
                    probe["probe_error"],
                    probe["checked_at"] if probe["status"] == "online" else None,
                    node_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_node(node_id)

    def probe_all_nodes(self) -> list[Node]:
        nodes = self.list_nodes()
        results = []
        for node in nodes:
            result = self.probe_node(node.id)
            if result:
                results.append(result)
        return results

    def _probe_local(self, node_id: str) -> Optional[Node]:
        checked_at = _utc_now()
        cpu = ram = disk = None
        if _HAS_PSUTIL:
            try:
                cpu = _psutil.cpu_percent(interval=0.1)
                ram = _psutil.virtual_memory().percent
                drive = os.path.splitdrive(os.getcwd())[0] or "C:"
                disk = _psutil.disk_usage(drive + "\\").percent
            except Exception:
                pass
        conn = _conn()
        try:
            conn.execute(
                """UPDATE nodes SET status='online', last_probe_at=?, last_seen=?,
                   latency_ms=0.1, resolved_ip='127.0.0.1', hostname_valid=1,
                   tailscale_reachable=NULL, probe_error=NULL, cpu=?, ram=?, disk=?
                   WHERE id=?""",
                (checked_at, checked_at, cpu, ram, disk, node_id),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_node(node_id)

    def delete_node(self, node_id: str) -> bool:
        if node_id == "workstation":
            return False
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def _probe_targets(self, node: Node) -> dict:
        checked_at = _utc_now()
        hostname = (node.hostname or "").strip()
        tailscale_target = (node.tailscale_ip or node.tailscale_name or "").strip()
        hostname_valid = self._is_valid_host(hostname) if hostname else None
        resolved_ip = self._resolve_hostname(hostname) if hostname_valid else None

        primary_target = hostname or tailscale_target
        primary_result = self._ping_target(primary_target) if primary_target else None
        tailscale_result = self._ping_target(tailscale_target) if tailscale_target else None

        reachable = bool((primary_result and primary_result["reachable"]) or (tailscale_result and tailscale_result["reachable"]))
        latency_candidates = [
            result["latency_ms"]
            for result in (primary_result, tailscale_result)
            if result and result["latency_ms"] is not None
        ]
        probe_error = None
        if not primary_target:
            probe_error = "No hostname or Tailscale target configured"
        elif primary_result and primary_result["error"]:
            probe_error = primary_result["error"]
        elif tailscale_result and tailscale_result["error"]:
            probe_error = tailscale_result["error"]

        return {
            "checked_at": checked_at,
            "status": "online" if reachable else "offline",
            "latency_ms": round(min(latency_candidates), 1) if latency_candidates else None,
            "resolved_ip": resolved_ip or node.tailscale_ip,
            "hostname_valid": hostname_valid,
            "tailscale_reachable": tailscale_result["reachable"] if tailscale_result else None,
            "probe_error": probe_error,
        }

    def _resolve_hostname(self, hostname: str) -> str | None:
        try:
            return socket.gethostbyname(hostname)
        except OSError:
            return None

    def _is_valid_host(self, hostname: str) -> bool:
        if not hostname:
            return False
        try:
            ip_address(hostname)
            return True
        except ValueError:
            pass
        return bool(re.fullmatch(r"[A-Za-z0-9.-]+", hostname))

    def _ping_target(self, target: str) -> dict:
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                ["ping", "-n", "1", "-w", "1200", target],
                capture_output=True,
                text=True,
                timeout=4,
                check=False,
            )
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            return {
                "reachable": completed.returncode == 0,
                "latency_ms": latency_ms if completed.returncode == 0 else None,
                "error": None if completed.returncode == 0 else completed.stdout.strip() or completed.stderr.strip() or "Ping failed",
            }
        except Exception as exc:
            return {
                "reachable": False,
                "latency_ms": None,
                "error": str(exc),
            }
