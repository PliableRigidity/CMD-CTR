"""Acceptance tests for chat-based service assignment (Phase 10B).

Tests exercise:
  1. register_node_preset — NAS preset on a node
  2. list_services after preset registration
  3. add_node_service — single service add
  4. remove_node_service — remove by name
  5. assign media-player service to a different node
  6. duplicate prevention — second add doesn't create duplicate record
  7. rename_node_service

Run with:
    pytest backend/tests/test_service_assignment.py -v
"""
from __future__ import annotations

import sqlite3
import importlib
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Each test gets its own SQLite database so they don't interfere."""
    db_file = tmp_path / "test_silvia.db"

    # Monkeypatch DB_PATH as a Path object (node_service._conn reads DB_PATH.parent)
    import backend.app.services.node_service as _ns_mod
    if not hasattr(_ns_mod, "NodeService"):
        sys.modules.pop("backend.app.services.node_service", None)
        _ns_mod = importlib.import_module("backend.app.services.node_service")
    monkeypatch.setattr(_ns_mod, "DB_PATH", db_file, raising=False)

    # Let NodeService() initialise the full schema (with seed nodes including storage-node)
    _ns_mod.NodeService()  # triggers _init_db() and seed inserts

    # Insert pi-zero as an extra test node (not in seed data)
    import uuid
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute(
        "INSERT OR IGNORE INTO nodes (id, name, type, hostname, status) VALUES (?,?,?,?,?)",
        (str(uuid.uuid4()), "pi-zero", "server", "192.168.1.20", "unknown"),
    )
    conn.commit()
    conn.close()

    yield db_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _service_count(db_file, node_id: str, service_name: str) -> int:
    conn = sqlite3.connect(str(db_file))
    try:
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM node_services WHERE node_id=? AND LOWER(name)=LOWER(?)",
                (node_id, service_name),
            ).fetchone()
            return row[0] if row else 0
        except sqlite3.OperationalError:
            return 0
    finally:
        conn.close()


def _all_service_names(db_file, node_id: str) -> list[str]:
    conn = sqlite3.connect(str(db_file))
    try:
        try:
            rows = conn.execute(
                "SELECT name FROM node_services WHERE node_id=? ORDER BY name",
                (node_id,),
            ).fetchall()
            return [r[0] for r in rows]
        except sqlite3.OperationalError:
            return []
    finally:
        conn.close()


def _get_node_id(db_file, name: str) -> str:
    """Look up the real node ID from the DB by display name (case-insensitive)."""
    conn = sqlite3.connect(str(db_file))
    try:
        row = conn.execute(
            "SELECT id FROM nodes WHERE LOWER(name)=LOWER(?)", (name,)
        ).fetchone()
        assert row, f"Node '{name}' not found in test DB"
        return row[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Test 1: Register NAS preset on storage-node
# ---------------------------------------------------------------------------

def test_register_nas_preset(isolated_db):
    from backend.app.tools.service_tool import register_node_preset

    result = register_node_preset("storage-node", "NAS")

    assert result["ok"], f"Expected ok=True, got: {result}"
    assert result["node_name"].lower() == "storage-node"
    assert result["preset"] == "nas"
    assert "samba" in result["services"]
    assert "ssh" in result["services"]
    assert "file-storage" in result["services"]
    assert "Done." in result["summary"]

    # Verify DB rows created — storage-node is a seed node with id="storage-node"
    from backend.app.services.node_service import NodeService
    ns = NodeService()
    night = next((n for n in ns.list_nodes() if n.name.lower() == "storage-node"), None)
    assert night is not None
    names = _all_service_names(isolated_db, night.id)
    assert "samba" in names
    assert "ssh" in names
    assert "file-storage" in names


# ---------------------------------------------------------------------------
# Test 2: Show services after preset registration
# ---------------------------------------------------------------------------

def test_list_services_after_preset(isolated_db):
    from backend.app.tools.service_tool import register_node_preset
    from backend.app.services.service_registry import ServiceRegistry

    register_node_preset("storage-node", "NAS")

    from backend.app.services.node_service import NodeService
    ns = NodeService()
    night = next((n for n in ns.list_nodes() if n.name.lower() == "storage-node"), None)
    assert night is not None

    registry = ServiceRegistry()
    services = registry.list_services(night.id)

    assert len(services) >= 3, f"Expected ≥3 services, got {len(services)}: {[s.name for s in services]}"
    names = {s.name for s in services}
    assert "samba" in names
    assert "ssh" in names


# ---------------------------------------------------------------------------
# Test 3: Add a single service
# ---------------------------------------------------------------------------

def test_add_single_service(isolated_db):
    from backend.app.tools.service_tool import add_node_service

    result = add_node_service("storage-node", "nfs")

    assert result["ok"], f"Expected ok=True, got: {result}"
    assert result["action"] == "added"
    assert result["service_name"] == "nfs"
    assert "Done." in result["summary"]

    node_id = _get_node_id(isolated_db, "storage-node")
    count = _service_count(isolated_db, node_id, "nfs")
    assert count == 1


# ---------------------------------------------------------------------------
# Test 4: Remove a service by name
# ---------------------------------------------------------------------------

def test_remove_service(isolated_db):
    from backend.app.tools.service_tool import add_node_service, remove_node_service

    node_id = _get_node_id(isolated_db, "storage-node")
    add_node_service("storage-node", "samba")
    assert _service_count(isolated_db, node_id, "samba") == 1

    result = remove_node_service("storage-node", "samba")

    assert result["ok"], f"Expected ok=True, got: {result}"
    assert result["service_name"] == "samba"
    assert "Done." in result["summary"]
    assert _service_count(isolated_db, node_id, "samba") == 0


# ---------------------------------------------------------------------------
# Test 5: Assign media-player service to pi-zero
# ---------------------------------------------------------------------------

def test_assign_media_player_to_pi_zero(isolated_db):
    from backend.app.tools.service_tool import add_node_service

    result = add_node_service("pi-zero", "media-player")

    assert result["ok"], f"Expected ok=True, got: {result}"
    assert result["node_name"].lower() == "pi-zero"
    assert result["service_name"] == "media-player"
    node_id = _get_node_id(isolated_db, "pi-zero")
    assert _service_count(isolated_db, node_id, "media-player") == 1


# ---------------------------------------------------------------------------
# Test 6: Duplicate prevention — second add updates, not duplicates
# ---------------------------------------------------------------------------

def test_duplicate_prevention(isolated_db):
    from backend.app.tools.service_tool import add_node_service

    r1 = add_node_service("storage-node", "samba")
    assert r1["ok"]
    assert r1["action"] == "added"

    r2 = add_node_service("storage-node", "samba")
    assert r2["ok"]
    assert r2["action"] == "updated"  # must update, not create second row

    node_id = _get_node_id(isolated_db, "storage-node")
    count = _service_count(isolated_db, node_id, "samba")
    assert count == 1, f"Expected exactly 1 row for 'samba', got {count}"


# ---------------------------------------------------------------------------
# Test 7: Rename a service
# ---------------------------------------------------------------------------

def test_rename_service(isolated_db):
    from backend.app.tools.service_tool import add_node_service, rename_node_service

    add_node_service("storage-node", "samba")

    result = rename_node_service("storage-node", "samba", "file-sharing")

    assert result["ok"], f"Expected ok=True, got: {result}"
    assert result["old_name"] == "samba"
    assert result["new_name"] == "file-sharing"
    assert "Done." in result["summary"]

    node_id = _get_node_id(isolated_db, "storage-node")
    assert _service_count(isolated_db, node_id, "samba") == 0
    assert _service_count(isolated_db, node_id, "file-sharing") == 1


# ---------------------------------------------------------------------------
# Test 8: Node not found returns structured error
# ---------------------------------------------------------------------------

def test_node_not_found(isolated_db):
    from backend.app.tools.service_tool import add_node_service

    result = add_node_service("does-not-exist", "samba")

    assert not result["ok"]
    assert result["error"] == "node_not_found"
    assert result["node_name"] == "does-not-exist"


# ---------------------------------------------------------------------------
# Test 9: Unknown preset returns structured error
# ---------------------------------------------------------------------------

def test_unknown_preset(isolated_db):
    from backend.app.tools.service_tool import register_node_preset

    result = register_node_preset("storage-node", "not-a-preset-xyz")

    assert not result["ok"]
    assert result["error"] == "preset_not_found"


# ---------------------------------------------------------------------------
# Test 10: remove non-existent service returns service_not_found
# ---------------------------------------------------------------------------

def test_remove_nonexistent_service(isolated_db):
    from backend.app.tools.service_tool import remove_node_service

    result = remove_node_service("storage-node", "ghost-service")

    assert not result["ok"]
    assert result["error"] == "service_not_found"


# ---------------------------------------------------------------------------
# Test 11: Planner regex — register preset
# ---------------------------------------------------------------------------

def test_planner_regex_register_preset():
    from backend.app.tools.planner import _regex_fallback

    result = _regex_fallback("register storage-node service as NAS")
    assert result["action"] == "call_tool"
    assert result["name"] == "register_node_preset"
    assert result["args"]["node"] == "storage-node"
    assert result["args"]["preset"].upper() == "NAS"


# ---------------------------------------------------------------------------
# Test 12: Planner regex — add single service
# ---------------------------------------------------------------------------

def test_planner_regex_add_service():
    from backend.app.tools.planner import _regex_fallback

    result = _regex_fallback("add samba service to storage-node")
    assert result["action"] == "call_tool"
    assert result["name"] == "add_node_service"
    assert result["args"]["node"] == "storage-node"
    assert result["args"]["service"] == "samba"


# ---------------------------------------------------------------------------
# Test 13: Planner regex — remove service
# ---------------------------------------------------------------------------

def test_planner_regex_remove_service():
    from backend.app.tools.planner import _regex_fallback

    result = _regex_fallback("remove samba service from storage-node")
    assert result["action"] == "call_tool"
    assert result["name"] == "remove_node_service"
    assert result["args"]["node"] == "storage-node"
    assert result["args"]["service"] == "samba"


# ---------------------------------------------------------------------------
# Test 14: Planner regex — rename service
# ---------------------------------------------------------------------------

def test_planner_regex_rename_service():
    from backend.app.tools.planner import _regex_fallback

    result = _regex_fallback("rename service samba to file-sharing on storage-node")
    assert result["action"] == "call_tool"
    assert result["name"] == "rename_node_service"
    assert result["args"]["old"] == "samba"
    assert result["args"]["new"] == "file-sharing"
    assert result["args"]["node"] == "storage-node"


# ---------------------------------------------------------------------------
# Test 15: Planner regex — "storage-node runs file-storage"
# ---------------------------------------------------------------------------

def test_planner_regex_node_runs_service():
    from backend.app.tools.planner import _regex_fallback

    result = _regex_fallback("storage-node runs file-storage")
    assert result["action"] == "call_tool"
    assert result["name"] == "add_node_service"
    assert result["args"]["node"] == "storage-node"
    assert result["args"]["service"] == "file-storage"
