"""Execution Ledger — Phase 13C.

Persistent audit trail for every action SILVIA performs.

Three tables in the existing cmdctr.db:
  execution_log  — capability / fleet / tool executions with outcome + duration
  planner_log    — planner decisions (query → tool selected)
  failure_log    — exceptions, stack traces, retry context

All writes are synchronous (SQLite is fast enough for a personal AI OS).
The module exposes a singleton via get_ledger().
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "cmdctr.db"
_lock    = threading.Lock()


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


class ExecutionLedger:
    def __init__(self) -> None:
        self._init_tables()

    def _init_tables(self) -> None:
        with _lock, _conn() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS execution_log (
                    id           TEXT PRIMARY KEY,
                    timestamp    TEXT NOT NULL,
                    intent       TEXT,
                    source       TEXT DEFAULT 'chat',
                    node         TEXT,
                    service      TEXT,
                    capability   TEXT,
                    tool         TEXT,
                    executor     TEXT,
                    status       TEXT NOT NULL,
                    duration_ms  INTEGER,
                    message      TEXT,
                    metadata     TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_elog_ts     ON execution_log(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_elog_node   ON execution_log(node);
                CREATE INDEX IF NOT EXISTS idx_elog_cap    ON execution_log(capability);
                CREATE INDEX IF NOT EXISTS idx_elog_status ON execution_log(status);

                CREATE TABLE IF NOT EXISTS planner_log (
                    id           TEXT PRIMARY KEY,
                    timestamp    TEXT NOT NULL,
                    query        TEXT NOT NULL,
                    tool         TEXT,
                    args         TEXT,
                    route        TEXT,
                    duration_ms  INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_plog_ts ON planner_log(timestamp DESC);

                CREATE TABLE IF NOT EXISTS failure_log (
                    id           TEXT PRIMARY KEY,
                    timestamp    TEXT NOT NULL,
                    context      TEXT,
                    node         TEXT,
                    capability   TEXT,
                    tool         TEXT,
                    exception    TEXT,
                    traceback    TEXT,
                    metadata     TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_flog_ts ON failure_log(timestamp DESC);
            """)

    # ── Writers ────────────────────────────────────────────────────────────────

    def log_execution(
        self,
        *,
        intent:      str = "",
        source:      str = "chat",
        node:        Optional[str] = None,
        service:     Optional[str] = None,
        capability:  Optional[str] = None,
        tool:        Optional[str] = None,
        executor:    Optional[str] = None,
        status:      str,              # "success" | "failure" | "simulated" | "dry_run" | "partial"
        duration_ms: Optional[int] = None,
        message:     str = "",
        metadata:    Optional[dict] = None,
    ) -> str:
        eid = f"evt_{uuid.uuid4().hex[:12]}"
        ts  = _now()
        with _lock, _conn() as db:
            db.execute(
                """INSERT INTO execution_log
                   (id,timestamp,intent,source,node,service,capability,tool,executor,
                    status,duration_ms,message,metadata)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (eid, ts, intent or "", source, node, service, capability, tool, executor,
                 status, duration_ms, message or "",
                 json.dumps(metadata) if metadata else None),
            )
        return eid

    def log_planner(
        self,
        *,
        query:       str,
        tool:        Optional[str] = None,
        args:        Optional[dict] = None,
        route:       str = "regex",
        duration_ms: Optional[int] = None,
    ) -> str:
        pid = f"pln_{uuid.uuid4().hex[:12]}"
        with _lock, _conn() as db:
            db.execute(
                "INSERT INTO planner_log (id,timestamp,query,tool,args,route,duration_ms) VALUES (?,?,?,?,?,?,?)",
                (pid, _now(), query, tool, json.dumps(args) if args else None, route, duration_ms),
            )
        return pid

    def log_failure(
        self,
        *,
        context:    str = "",
        node:       Optional[str] = None,
        capability: Optional[str] = None,
        tool:       Optional[str] = None,
        exc:        Optional[Exception] = None,
        metadata:   Optional[dict] = None,
    ) -> str:
        fid = f"fail_{uuid.uuid4().hex[:12]}"
        tb  = traceback.format_exc() if exc else None
        with _lock, _conn() as db:
            db.execute(
                """INSERT INTO failure_log
                   (id,timestamp,context,node,capability,tool,exception,traceback,metadata)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (fid, _now(), context, node, capability, tool,
                 str(exc) if exc else None, tb,
                 json.dumps(metadata) if metadata else None),
            )
        return fid

    # ── Readers ────────────────────────────────────────────────────────────────

    def get_recent(
        self,
        limit:      int = 20,
        node:       Optional[str] = None,
        capability: Optional[str] = None,
        status:     Optional[str] = None,
        since_hours: Optional[float] = None,
    ) -> list[dict]:
        wheres, params = [], []
        if node:
            wheres.append("node = ?"); params.append(node)
        if capability:
            wheres.append("capability LIKE ?"); params.append(f"%{capability}%")
        if status:
            wheres.append("status = ?"); params.append(status)
        if since_hours is not None:
            ts_cutoff = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(time.time() - since_hours * 3600),
            )
            wheres.append("timestamp >= ?"); params.append(ts_cutoff)
        where = f"WHERE {' AND '.join(wheres)}" if wheres else ""
        params.append(limit)
        with _conn() as db:
            rows = db.execute(
                f"SELECT * FROM execution_log {where} ORDER BY timestamp DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_failures(self, limit: int = 20) -> list[dict]:
        with _conn() as db:
            rows = db.execute(
                "SELECT * FROM failure_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_planner_trace(self, limit: int = 20) -> list[dict]:
        with _conn() as db:
            rows = db.execute(
                "SELECT * FROM planner_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_last_action(self) -> Optional[dict]:
        rows = self.get_recent(limit=1)
        return rows[0] if rows else None

    def get_stats(self) -> dict:
        with _conn() as db:
            total   = db.execute("SELECT COUNT(*) FROM execution_log").fetchone()[0]
            success = db.execute(
                "SELECT COUNT(*) FROM execution_log WHERE status='success'"
            ).fetchone()[0]
            failures = db.execute("SELECT COUNT(*) FROM failure_log").fetchone()[0]
            cap_rows = db.execute("""
                SELECT capability,
                       COUNT(*) AS cnt,
                       SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS ok
                FROM execution_log WHERE capability IS NOT NULL
                GROUP BY capability ORDER BY cnt DESC LIMIT 10
            """).fetchall()
            avg_ms = db.execute(
                "SELECT AVG(duration_ms) FROM execution_log WHERE duration_ms IS NOT NULL"
            ).fetchone()[0]
            failures_24h = db.execute(
                "SELECT COUNT(*) FROM failure_log WHERE timestamp >= ?",
                (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 86400)),),
            ).fetchone()[0]
        return {
            "total_executions": total,
            "success_count":    success,
            "failure_count":    failures,
            "failures_24h":     failures_24h,
            "success_rate":     round(success / total * 100, 1) if total else 0.0,
            "avg_duration_ms":  round(avg_ms, 0) if avg_ms else None,
            "top_capabilities": [dict(r) for r in cap_rows],
        }


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# Module-level singleton
_instance: Optional[ExecutionLedger] = None


def get_ledger() -> ExecutionLedger:
    global _instance
    if _instance is None:
        _instance = ExecutionLedger()
    return _instance
