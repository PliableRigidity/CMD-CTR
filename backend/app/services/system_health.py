"""System Health — Phase 13C.

Computes reliability metrics from the Execution Ledger:
  - Overall success rate
  - Per-capability success rates
  - Most used / most failed capabilities
  - Node failure frequency
  - Planner routing accuracy
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional

_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "cmdctr.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _since(hours: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - hours * 3600))


def get_capability_health(hours: float = 24 * 7) -> list[dict]:
    """Per-capability success rate over the last N hours."""
    with _conn() as db:
        rows = db.execute("""
            SELECT capability,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS succeeded,
                   SUM(CASE WHEN status IN ('failure','error') THEN 1 ELSE 0 END) AS failed,
                   ROUND(AVG(duration_ms),0) AS avg_ms
            FROM execution_log
            WHERE capability IS NOT NULL AND timestamp >= ?
            GROUP BY capability
            ORDER BY total DESC
        """, (_since(hours),)).fetchall()
    result = []
    for r in rows:
        total = r["total"] or 0
        ok    = r["succeeded"] or 0
        result.append({
            "capability":   r["capability"],
            "total":        total,
            "succeeded":    ok,
            "failed":       r["failed"] or 0,
            "success_rate": round(ok / total * 100, 1) if total else 0.0,
            "avg_ms":       r["avg_ms"],
        })
    return result


def get_node_health(hours: float = 24 * 7) -> list[dict]:
    """Per-node execution success rate over the last N hours."""
    with _conn() as db:
        rows = db.execute("""
            SELECT node,
                   COUNT(*) AS total,
                   SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS succeeded,
                   SUM(CASE WHEN status IN ('failure','error') THEN 1 ELSE 0 END) AS failed
            FROM execution_log
            WHERE node IS NOT NULL AND timestamp >= ?
            GROUP BY node
            ORDER BY total DESC
        """, (_since(hours),)).fetchall()
    result = []
    for r in rows:
        total = r["total"] or 0
        ok    = r["succeeded"] or 0
        result.append({
            "node":         r["node"],
            "total":        total,
            "succeeded":    ok,
            "failed":       r["failed"] or 0,
            "success_rate": round(ok / total * 100, 1) if total else 0.0,
        })
    return result


def get_overall_health() -> dict:
    """Aggregate health snapshot."""
    from backend.app.services.execution_ledger import get_ledger
    stats = get_ledger().get_stats()
    cap_health = get_capability_health(hours=24)
    node_health = get_node_health(hours=24)

    most_failed = min(cap_health, key=lambda x: x["success_rate"], default=None) if cap_health else None
    most_used   = max(cap_health, key=lambda x: x["total"],        default=None) if cap_health else None

    return {
        **stats,
        "capability_health": cap_health,
        "node_health":       node_health,
        "most_failed_cap":   most_failed,
        "most_used_cap":     most_used,
    }
