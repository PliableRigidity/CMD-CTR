"""SQLite-backed Service Registry — CRUD for node services and capabilities."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.app.models.services import (
    CapabilityMatch,
    ManifestCapability,
    NodeServiceModel,
    NodeServiceCreate,
    NodeServiceUpdate,
    ServiceCapability,
    ServiceCapabilityCreate,
    ServiceManifest,
    ServiceManifestEntry,
)
from backend.app.services.node_service import DB_PATH, _conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init_service_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS node_services (
            id          TEXT PRIMARY KEY,
            node_id     TEXT NOT NULL,
            name        TEXT NOT NULL,
            type        TEXT NOT NULL DEFAULT 'custom',
            status      TEXT NOT NULL DEFAULT 'unknown',
            transport   TEXT NOT NULL DEFAULT 'http',
            endpoint    TEXT,
            config      TEXT NOT NULL DEFAULT '{}',
            metadata    TEXT NOT NULL DEFAULT '{}',
            last_seen   TEXT,
            UNIQUE(node_id, name)
        );""")
    # Idempotent migration: add description column if absent
    try:
        conn.execute("ALTER TABLE node_services ADD COLUMN description TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.executescript("""

        CREATE TABLE IF NOT EXISTS service_capabilities (
            id                   TEXT PRIMARY KEY,
            service_id           TEXT NOT NULL,
            name                 TEXT NOT NULL,
            namespace            TEXT NOT NULL,
            description          TEXT,
            parameters_schema    TEXT,
            transport_config     TEXT,
            confirmation_required INTEGER NOT NULL DEFAULT 0,
            risk_level           TEXT NOT NULL DEFAULT 'low',
            enabled              INTEGER NOT NULL DEFAULT 1,
            UNIQUE(service_id, name),
            FOREIGN KEY(service_id) REFERENCES node_services(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_node_services_node
            ON node_services(node_id);
        CREATE INDEX IF NOT EXISTS idx_service_capabilities_service
            ON service_capabilities(service_id);
        CREATE INDEX IF NOT EXISTS idx_service_capabilities_name
            ON service_capabilities(name);
        CREATE INDEX IF NOT EXISTS idx_service_capabilities_namespace
            ON service_capabilities(namespace);
    """)
    # Idempotent migrations for Phase 13A
    for _col, _coltype in [("executor", "TEXT"), ("command", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE service_capabilities ADD COLUMN {_col} {_coltype}")
            conn.commit()
        except sqlite3.OperationalError:
            pass


class ServiceRegistry:
    def __init__(self) -> None:
        conn = _conn()
        try:
            _init_service_tables(conn)
            conn.commit()
        finally:
            conn.close()

    # ── Service CRUD ─────────────────────────────────────────────────────────

    def list_services(self, node_id: Optional[str] = None) -> list[NodeServiceModel]:
        conn = _conn()
        try:
            if node_id:
                rows = conn.execute(
                    """SELECT ns.*, n.name AS node_name FROM node_services ns
                       LEFT JOIN nodes n ON n.id = ns.node_id
                       WHERE ns.node_id = ? ORDER BY ns.name""",
                    (node_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT ns.*, n.name AS node_name FROM node_services ns
                       LEFT JOIN nodes n ON n.id = ns.node_id
                       ORDER BY n.name, ns.name"""
                ).fetchall()
            services = []
            for row in rows:
                svc = self._row_to_service(row, conn)
                services.append(svc)
            return services
        finally:
            conn.close()

    def get_service(self, service_id: str) -> Optional[NodeServiceModel]:
        conn = _conn()
        try:
            row = conn.execute(
                """SELECT ns.*, n.name AS node_name FROM node_services ns
                   LEFT JOIN nodes n ON n.id = ns.node_id
                   WHERE ns.id = ?""",
                (service_id,),
            ).fetchone()
            if not row:
                return None
            return self._row_to_service(row, conn)
        finally:
            conn.close()

    def create_service(self, node_id: str, data: NodeServiceCreate) -> NodeServiceModel:
        service_id = str(uuid.uuid4())
        conn = _conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO node_services
                   (id, node_id, name, type, description, status, transport, endpoint, config, metadata, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    service_id, node_id, data.name, data.type, data.description, data.status,
                    data.transport, data.endpoint,
                    json.dumps(data.config), json.dumps(data.metadata),
                    _utc_now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_service(service_id)

    def update_service(self, service_id: str, data: NodeServiceUpdate) -> Optional[NodeServiceModel]:
        updates = data.model_dump(exclude_unset=True)
        if not updates:
            return self.get_service(service_id)
        if "config" in updates and updates["config"] is not None:
            updates["config"] = json.dumps(updates["config"])
        if "metadata" in updates and updates["metadata"] is not None:
            updates["metadata"] = json.dumps(updates["metadata"])
        updates["last_seen"] = _utc_now()
        cols = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [service_id]
        conn = _conn()
        try:
            conn.execute(f"UPDATE node_services SET {cols} WHERE id = ?", vals)
            conn.commit()
        finally:
            conn.close()
        return self.get_service(service_id)

    def delete_service(self, service_id: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM node_services WHERE id = ?", (service_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def update_service_status(self, service_id: str, status: str) -> None:
        conn = _conn()
        try:
            conn.execute(
                "UPDATE node_services SET status = ?, last_seen = ? WHERE id = ?",
                (status, _utc_now(), service_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Capability CRUD ───────────────────────────────────────────────────────

    def list_capabilities(self, service_id: str) -> list[ServiceCapability]:
        conn = _conn()
        try:
            rows = conn.execute(
                "SELECT * FROM service_capabilities WHERE service_id = ? ORDER BY name",
                (service_id,),
            ).fetchall()
            return [self._row_to_capability(r) for r in rows]
        finally:
            conn.close()

    def add_capability(self, service_id: str, data: ServiceCapabilityCreate) -> ServiceCapability:
        cap_id = str(uuid.uuid4())
        namespace = data.name.split(".")[0] if "." in data.name else "custom"
        conn = _conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO service_capabilities
                   (id, service_id, name, namespace, description, parameters_schema,
                    transport_config, confirmation_required, risk_level, enabled,
                    executor, command)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cap_id, service_id, data.name, namespace, data.description,
                    json.dumps(data.parameters_schema) if data.parameters_schema else None,
                    json.dumps(data.transport_config) if data.transport_config else None,
                    int(data.confirmation_required), data.risk_level, int(data.enabled),
                    data.executor, data.command,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        conn2 = _conn()
        try:
            row = conn2.execute("SELECT * FROM service_capabilities WHERE id = ?", (cap_id,)).fetchone()
            return self._row_to_capability(row)
        finally:
            conn2.close()

    def delete_capability(self, capability_id: str) -> bool:
        conn = _conn()
        try:
            cur = conn.execute("DELETE FROM service_capabilities WHERE id = ?", (capability_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    # ── Search ────────────────────────────────────────────────────────────────

    def find_capability(
        self,
        capability_name: str,
        node_name: Optional[str] = None,
        running_only: bool = False,
    ) -> list[CapabilityMatch]:
        """Find all services that expose a given capability name.

        Args:
            capability_name: Exact capability name (e.g. "media.play") or namespace prefix (e.g. "media").
            node_name: If given, restrict to that node.
            running_only: If True, only return services with status='running'.
        """
        conn = _conn()
        try:
            params: list = []
            # Match exact name OR namespace prefix
            name_clause = "(sc.name = ? OR sc.namespace = ?)"
            params += [capability_name, capability_name]

            node_clause = ""
            if node_name:
                node_clause = "AND LOWER(n.name) = LOWER(?)"
                params.append(node_name)

            status_clause = ""
            if running_only:
                status_clause = "AND ns.status = 'running'"

            rows = conn.execute(
                f"""SELECT sc.id, sc.name, sc.risk_level, sc.confirmation_required,
                           ns.id, ns.name, ns.type, ns.status, ns.transport, ns.endpoint, ns.config,
                           n.id, n.name
                    FROM service_capabilities sc
                    JOIN node_services ns ON ns.id = sc.service_id
                    JOIN nodes n ON n.id = ns.node_id
                    WHERE {name_clause} AND sc.enabled = 1
                    {node_clause}
                    {status_clause}
                    ORDER BY ns.status DESC, n.name, ns.name""",
                params,
            ).fetchall()
            return [
                CapabilityMatch(
                    capability_id=r[0],
                    capability_name=r[1],
                    capability_risk=r[2],
                    capability_confirmation=bool(r[3]),
                    service_id=r[4],
                    service_name=r[5],
                    service_type=r[6],
                    service_status=r[7],
                    service_transport=r[8],
                    service_endpoint=r[9],
                    service_config=json.loads(r[10] or "{}"),
                    node_id=r[11],
                    node_name=r[12],
                )
                for r in rows
            ]
        finally:
            conn.close()

    # ── Manifest ingest ───────────────────────────────────────────────────────

    def ingest_manifest(self, node_id: str, manifest: ServiceManifest) -> dict:
        """Upsert services + capabilities from a device-reported manifest.

        Existing services that are not in the manifest are set to 'stopped'.
        Existing capabilities that are not in the manifest are deleted.
        Returns {"upserted": N, "stopped": M}.
        """
        conn = _conn()
        try:
            manifest_names = {e.name for e in manifest.services}
            existing = conn.execute(
                "SELECT id, name FROM node_services WHERE node_id = ?", (node_id,)
            ).fetchall()
            existing_by_name = {r[1]: r[0] for r in existing}

            upserted = 0
            for entry in manifest.services:
                if entry.name in existing_by_name:
                    sid = existing_by_name[entry.name]
                    conn.execute(
                        """UPDATE node_services SET type=?, status=?, transport=?, endpoint=?,
                           config=?, metadata='{}', last_seen=? WHERE id=?""",
                        (entry.type, entry.status, entry.transport, entry.endpoint,
                         json.dumps(entry.config), _utc_now(), sid),
                    )
                else:
                    sid = str(uuid.uuid4())
                    conn.execute(
                        """INSERT INTO node_services
                           (id, node_id, name, type, status, transport, endpoint, config, metadata, last_seen)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', ?)""",
                        (sid, node_id, entry.name, entry.type, entry.status,
                         entry.transport, entry.endpoint, json.dumps(entry.config), _utc_now()),
                    )
                    existing_by_name[entry.name] = sid

                # Replace capabilities for this service
                conn.execute("DELETE FROM service_capabilities WHERE service_id = ?", (sid,))
                for cap in entry.capabilities:
                    namespace = cap.name.split(".")[0] if "." in cap.name else "custom"
                    conn.execute(
                        """INSERT INTO service_capabilities
                           (id, service_id, name, namespace, description, parameters_schema,
                            transport_config, confirmation_required, risk_level, enabled)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                        (
                            str(uuid.uuid4()), sid, cap.name, namespace, cap.description,
                            json.dumps(cap.parameters_schema) if cap.parameters_schema else None,
                            json.dumps(cap.transport_config) if cap.transport_config else None,
                            int(cap.confirmation_required), cap.risk_level,
                        ),
                    )
                upserted += 1

            # Mark services absent from manifest as stopped
            stopped = 0
            for name, sid in existing_by_name.items():
                if name not in manifest_names:
                    conn.execute(
                        "UPDATE node_services SET status='stopped', last_seen=? WHERE id=?",
                        (_utc_now(), sid),
                    )
                    stopped += 1

            conn.commit()
            return {"upserted": upserted, "stopped": stopped}
        finally:
            conn.close()

    # ── Helpers ───────────────────────────────────────────────────────────────

    # ── Name-based helpers (for chat-driven service assignment) ───────────────

    def get_service_by_name(self, node_id: str, service_name: str) -> Optional[NodeServiceModel]:
        """Look up a service by node_id + name (case-insensitive)."""
        conn = _conn()
        try:
            row = conn.execute(
                """SELECT ns.*, n.name AS node_name FROM node_services ns
                   LEFT JOIN nodes n ON n.id = ns.node_id
                   WHERE ns.node_id = ? AND LOWER(ns.name) = LOWER(?)""",
                (node_id, service_name),
            ).fetchone()
            if not row:
                return None
            return self._row_to_service(row, conn)
        finally:
            conn.close()

    def remove_service_by_name(self, node_id: str, service_name: str) -> bool:
        """Delete a service by node_id + name (case-insensitive). Returns True if deleted."""
        conn = _conn()
        try:
            cur = conn.execute(
                "DELETE FROM node_services WHERE node_id = ? AND LOWER(name) = LOWER(?)",
                (node_id, service_name),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def rename_service(self, node_id: str, old_name: str, new_name: str) -> Optional[NodeServiceModel]:
        """Rename a service on a node. Returns the updated service, or None if not found."""
        conn = _conn()
        try:
            row = conn.execute(
                "SELECT id FROM node_services WHERE node_id = ? AND LOWER(name) = LOWER(?)",
                (node_id, old_name),
            ).fetchone()
            if not row:
                return None
            svc_id = row["id"]
            conn.execute(
                "UPDATE node_services SET name = ?, last_seen = ? WHERE id = ?",
                (new_name, _utc_now(), svc_id),
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_service(svc_id)

    def _row_to_service(self, row, conn: sqlite3.Connection) -> NodeServiceModel:
        d = dict(row)
        caps = conn.execute(
            "SELECT * FROM service_capabilities WHERE service_id = ? ORDER BY name",
            (d["id"],),
        ).fetchall()
        return NodeServiceModel(
            id=d["id"],
            node_id=d["node_id"],
            node_name=d.get("node_name"),
            name=d["name"],
            type=d.get("type", "custom"),
            description=d.get("description"),
            status=d.get("status", "unknown"),
            transport=d.get("transport", "http"),
            endpoint=d.get("endpoint"),
            config=json.loads(d.get("config") or "{}"),
            metadata=json.loads(d.get("metadata") or "{}"),
            last_seen=d.get("last_seen"),
            capabilities=[self._row_to_capability(c) for c in caps],
        )

    @staticmethod
    def _row_to_capability(row) -> ServiceCapability:
        d = dict(row)
        return ServiceCapability(
            id=d["id"],
            service_id=d["service_id"],
            name=d["name"],
            namespace=d["namespace"],
            description=d.get("description"),
            parameters_schema=json.loads(d["parameters_schema"]) if d.get("parameters_schema") else None,
            transport_config=json.loads(d["transport_config"]) if d.get("transport_config") else None,
            confirmation_required=bool(d.get("confirmation_required", 0)),
            risk_level=d.get("risk_level", "low"),
            enabled=bool(d.get("enabled", 1)),
            executor=d.get("executor"),
            command=d.get("command"),
        )
