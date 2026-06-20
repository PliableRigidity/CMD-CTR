"""Acceptance tests for Phase 11 — Desktop Control & Local File Awareness.

Run with:
    pytest backend/tests/test_desktop.py -v
"""
from __future__ import annotations

import os
import sqlite3
import importlib
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# DB isolation fixture
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_silvia.db"
    import backend.app.services.node_service as _ns
    if not hasattr(_ns, "NodeService"):
        sys.modules.pop("backend.app.services.node_service", None)
        _ns = importlib.import_module("backend.app.services.node_service")
    monkeypatch.setattr(_ns, "DB_PATH", db_file, raising=False)
    # Init node schema first (desktop_service uses same _conn)
    _ns.NodeService()
    yield db_file


# ---------------------------------------------------------------------------
# Test 1: List trusted locations — seed data present
# ---------------------------------------------------------------------------

def test_list_locations_seeded(isolated_db):
    from backend.app.tools.desktop_tool import list_locations
    result = list_locations()
    assert result["ok"]
    assert result["count"] >= 8  # seed has CMD-CTR, Brain63, DroneHive, etc.
    names = {l["name"] for l in result["locations"]}
    assert "CMD-CTR" in names
    assert "Brain63" in names
    assert "DroneHive" in names
    assert "Downloads" in names


# ---------------------------------------------------------------------------
# Test 2: Find location by name
# ---------------------------------------------------------------------------

def test_find_location_by_name(isolated_db):
    from backend.app.services.desktop_service import DesktopService
    svc = DesktopService()
    loc = svc.find_location("CMD-CTR")
    assert loc is not None
    assert loc["name"] == "CMD-CTR"


# ---------------------------------------------------------------------------
# Test 3: Find location by alias
# ---------------------------------------------------------------------------

def test_find_location_by_alias(isolated_db):
    from backend.app.services.desktop_service import DesktopService
    svc = DesktopService()
    # "brain" is an alias for Brain63
    loc = svc.find_location("brain")
    assert loc is not None
    assert loc["name"] == "Brain63"


# ---------------------------------------------------------------------------
# Test 4: Open CMD-CTR folder — path exists on this machine
# ---------------------------------------------------------------------------

def test_open_cmdctr_folder(isolated_db, monkeypatch):
    opened = []
    monkeypatch.setattr("os.startfile", lambda p: opened.append(p))
    from backend.app.tools.desktop_tool import open_location
    result = open_location("CMD-CTR")
    assert result["ok"], result.get("summary")
    assert len(opened) == 1
    assert "CMD-CTR" in opened[0]


# ---------------------------------------------------------------------------
# Test 5: Open Brain63 folder
# ---------------------------------------------------------------------------

def test_open_brain63_folder(isolated_db, monkeypatch):
    opened = []
    monkeypatch.setattr("os.startfile", lambda p: opened.append(p))
    from backend.app.tools.desktop_tool import open_location
    result = open_location("Brain63")
    assert result["ok"], result.get("summary")
    assert "Brain63" in opened[0]


# ---------------------------------------------------------------------------
# Test 6: Unknown location → structured error
# ---------------------------------------------------------------------------

def test_open_unknown_location(isolated_db):
    from backend.app.tools.desktop_tool import open_location
    result = open_location("xyzzy-does-not-exist")
    assert not result["ok"]
    assert result["error"] == "location_not_found"


# ---------------------------------------------------------------------------
# Test 7: List apps — seed data present
# ---------------------------------------------------------------------------

def test_list_apps_seeded(isolated_db):
    from backend.app.tools.desktop_tool import list_apps
    result = list_apps()
    assert result["ok"]
    assert result["count"] >= 4
    names = {a["name"] for a in result["apps"]}
    assert "VS Code" in names
    assert "KiCad" in names
    assert "Chrome" in names


# ---------------------------------------------------------------------------
# Test 8: Find app by alias
# ---------------------------------------------------------------------------

def test_find_app_by_alias(isolated_db):
    from backend.app.services.desktop_service import DesktopService
    svc = DesktopService()
    app = svc.find_app("fusion")
    assert app is not None
    assert app["name"] == "Fusion 360"


# ---------------------------------------------------------------------------
# Test 9: Find app by alias — "browser" → Chrome
# ---------------------------------------------------------------------------

def test_find_app_browser_alias(isolated_db):
    from backend.app.services.desktop_service import DesktopService
    svc = DesktopService()
    app = svc.find_app("browser")
    assert app is not None
    assert app["name"] == "Chrome"


# ---------------------------------------------------------------------------
# Test 10: Unknown app → structured error
# ---------------------------------------------------------------------------

def test_open_unknown_app(isolated_db):
    from backend.app.tools.desktop_tool import open_app
    result = open_app("nonexistent-app-xyz")
    assert not result["ok"]
    assert result["error"] == "app_not_found"


# ---------------------------------------------------------------------------
# Test 11: Add custom location
# ---------------------------------------------------------------------------

def test_add_custom_location(isolated_db, tmp_path):
    custom_dir = tmp_path / "MyProject"
    custom_dir.mkdir()
    from backend.app.tools.desktop_tool import add_location, list_locations
    result = add_location("MyProject", str(custom_dir), "my project, project x", "code")
    assert result["ok"], result.get("summary")
    locs = list_locations()
    names = {l["name"] for l in locs["locations"]}
    assert "MyProject" in names


# ---------------------------------------------------------------------------
# Test 12: Add custom app
# ---------------------------------------------------------------------------

def test_add_custom_app(isolated_db):
    from backend.app.tools.desktop_tool import add_app, list_apps
    result = add_app("Notepad++", "notepad++", "npp,notepadpp", "development")
    assert result["ok"], result.get("summary")
    apps = list_apps()
    names = {a["name"] for a in apps["apps"]}
    assert "Notepad++" in names


# ---------------------------------------------------------------------------
# Test 13: find_files returns results (search inside CMD-CTR for .py files)
# ---------------------------------------------------------------------------

def test_find_python_files_in_cmdctr(isolated_db):
    from backend.app.tools.desktop_tool import find_files
    result = find_files(extension="py", location="CMD-CTR")
    assert result["ok"]
    # CMD-CTR exists and has Python files
    assert result["count"] > 0
    assert all(r["name"].endswith(".py") for r in result["results"])


# ---------------------------------------------------------------------------
# Test 14: find_files with query
# ---------------------------------------------------------------------------

def test_find_files_by_query(isolated_db):
    from backend.app.tools.desktop_tool import find_files
    result = find_files(query="planner", location="CMD-CTR")
    assert result["ok"]
    # planner.py should be found in CMD-CTR
    assert result["count"] >= 1
    assert any("planner" in r["name"].lower() for r in result["results"])


# ---------------------------------------------------------------------------
# Test 15: find_files unknown location → error
# ---------------------------------------------------------------------------

def test_find_files_unknown_location(isolated_db):
    from backend.app.tools.desktop_tool import find_files
    result = find_files(extension="stl", location="nonexistent-location-xyz")
    assert not result["ok"]
    assert result["error"] == "location_not_found"


# ---------------------------------------------------------------------------
# Test 16: Planner regex — open location
# ---------------------------------------------------------------------------

def test_planner_regex_open_cmdctr():
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback("open CMD-CTR folder")
    assert result["action"] == "call_tool"
    assert result["name"] in {"open_location", "open_target"}
    assert "cmd" in (result["args"].get("name") or result["args"].get("target", "")).lower()


# ---------------------------------------------------------------------------
# Test 17: Planner regex — where is Brain63
# ---------------------------------------------------------------------------

def test_planner_regex_where_is():
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback("where is Brain63")
    assert result["action"] == "call_tool"
    assert result["name"] in {"open_location", "open_target"}


# ---------------------------------------------------------------------------
# Test 18: Planner regex — find STL files
# ---------------------------------------------------------------------------

def test_planner_regex_find_stl():
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback("find STL files")
    assert result["action"] == "call_tool"
    assert result["name"] == "find_files"
    assert result["args"]["extension"].lower() == "stl"


# ---------------------------------------------------------------------------
# Test 19: Planner regex — open VS Code
# ---------------------------------------------------------------------------

def test_planner_regex_open_vscode():
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback("open VS Code")
    assert result["action"] == "call_tool"
    assert result["name"] in {"open_app", "open_target"}
    assert "code" in (result["args"].get("name") or result["args"].get("target", "")).lower()


# ---------------------------------------------------------------------------
# Test 20: Planner regex — show installed apps
# ---------------------------------------------------------------------------

def test_planner_regex_list_apps():
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback("show installed apps")
    assert result["action"] == "call_tool"
    assert result["name"] == "list_apps"


# ---------------------------------------------------------------------------
# Test 21: Planner regex — find PCB files
# ---------------------------------------------------------------------------

def test_planner_regex_find_pcb():
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback("find PCB files")
    assert result["action"] == "call_tool"
    assert result["name"] == "find_files"
    assert "pcb" in result["args"]["extension"].lower()


# ---------------------------------------------------------------------------
# Test 22: Planner regex — find files related to nighthawk
# ---------------------------------------------------------------------------

def test_planner_regex_find_query():
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback("find files related to nighthawk")
    assert result["action"] == "call_tool"
    assert result["name"] == "find_files"
    assert "nighthawk" in result["args"]["query"].lower()


# ---------------------------------------------------------------------------
# Test 23: recent_files returns indexed results
# ---------------------------------------------------------------------------

def test_recent_files_in_cmdctr(isolated_db):
    from backend.app.tools.desktop_tool import recent_files
    result = recent_files(location="CMD-CTR")
    assert result["ok"]
    assert result["count"] > 0
    assert all(r["location"] == "CMD-CTR" for r in result["results"])


# ---------------------------------------------------------------------------
# Test 24: Planner regex - show recent files
# ---------------------------------------------------------------------------

def test_planner_regex_recent_files():
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback("show recent files")
    assert result["action"] == "call_tool"
    assert result["name"] == "recent_files"
    assert result["args"]["location"] == ""


# ---------------------------------------------------------------------------
# Test 25: Planner regex - find python files
# ---------------------------------------------------------------------------

def test_planner_regex_find_python_files():
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback("find python files")
    assert result["action"] == "call_tool"
    assert result["name"] == "find_files"
    assert result["args"]["extension"] == "py"


# ---------------------------------------------------------------------------
# Test 26: Planner regex - show KiCad projects
# ---------------------------------------------------------------------------

def test_planner_regex_show_kicad_projects():
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback("show all KiCad projects")
    assert result["action"] == "call_tool"
    assert result["name"] == "find_files"
    assert result["args"]["extension"] == "kicad_pro"


# ---------------------------------------------------------------------------
# Test 27: Legacy action path delegates to app registry
# ---------------------------------------------------------------------------

def test_action_alias_uses_desktop_app_registry(isolated_db, monkeypatch):
    calls = []

    def fake_open_app(name):
        calls.append(name)
        return {
            "ok": True,
            "name": "KiCad",
            "executable": r"C:\Program Files\KiCad\9.0\bin\kicad.exe",
            "summary": "Done. Launched KiCad using C:\\Program Files\\KiCad\\9.0\\bin\\kicad.exe.",
        }

    monkeypatch.setattr("backend.app.tools.desktop_tool.open_app", fake_open_app)
    from backend.app.services.action_service import ActionService
    result = ActionService().execute_alias("open KiCad")
    assert result.success
    assert result.action == "desktop:KiCad"
    assert calls == ["kicad"]


# ---------------------------------------------------------------------------
# Test 28: Planner regex - open named KiCad project variants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command,query,latest", [
    ("open Hive-FC project", "Hive-FC", False),
    ("open HiveFC KiCad project", "HiveFC", False),
    ("open KiCad project Hive-FC", "Hive-FC", False),
    ("open latest KiCad project", "", True),
])
def test_planner_regex_open_kicad_project_variants(command, query, latest):
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback(command)
    assert result["action"] == "call_tool"
    assert result["name"] == "open_kicad_project"
    assert result["args"]["query"] == query
    assert result["args"]["latest"] is latest


# ---------------------------------------------------------------------------
# Test 29: open_kicad_project launches KiCad with resolved file path
# ---------------------------------------------------------------------------

def test_open_kicad_project_passes_project_path(isolated_db, tmp_path, monkeypatch):
    project_dir = tmp_path / "KiCadProjects"
    project_dir.mkdir()
    project_file = project_dir / "UnitTestHiveFC.kicad_pro"
    project_file.write_text("(kicad_pro)", encoding="utf-8")

    from backend.app.tools.desktop_tool import add_location, open_kicad_project
    from backend.app.services.desktop_service import DesktopService

    add_location("KiCadTest", str(project_dir), "kicad test", "electronics")
    monkeypatch.setattr(DesktopService, "resolve_app_executable", lambda self, app: "kicad.exe")

    launched = []
    monkeypatch.setattr(
        "backend.app.tools.desktop_tool.subprocess.Popen",
        lambda args, **kwargs: launched.append(args),
    )

    result = open_kicad_project("UnitTestHiveFC")
    assert result["ok"], result.get("summary")
    assert launched == [["kicad.exe", str(project_file)]]
    assert result["project"]["path"] == str(project_file)


# ---------------------------------------------------------------------------
# Test 30: Dynamic app aliases include common workstation names
# ---------------------------------------------------------------------------

def test_generate_app_aliases_dynamic_examples():
    from backend.app.services.desktop_service import generate_app_aliases

    assert "obs" in generate_app_aliases("OBS Studio")
    assert "unity" in generate_app_aliases("Unity Hub")
    assert "fusion360" in generate_app_aliases("Autodesk Fusion 360")
    assert "vs code" in generate_app_aliases("Visual Studio Code")


# ---------------------------------------------------------------------------
# Test 31: Discovered apps persist into app registry
# ---------------------------------------------------------------------------

def test_discovered_app_persists_and_matches_alias(isolated_db, tmp_path):
    from backend.app.services.desktop_service import DesktopService

    exe = tmp_path / "obs64.exe"
    exe.write_text("", encoding="utf-8")
    svc = DesktopService()
    conn = __import__("backend.app.services.node_service", fromlist=["_conn"])._conn()
    try:
        svc._upsert_discovered_app(conn, {
            "name": "OBS Studio",
            "executable_path": str(exe),
            "shortcut_path": "",
            "launch_command": str(exe),
            "source": "Unit Test",
            "launch_type": "desktop",
            "confidence": 0.9,
        })
        conn.commit()
    finally:
        conn.close()

    app = svc.find_app("obs")
    assert app is not None
    assert app["name"] == "OBS Studio"
    assert app["executable_path"] == str(exe)
    assert "obs" in app["aliases"]


# ---------------------------------------------------------------------------
# Test 32: open_app launches shortcut before executable
# ---------------------------------------------------------------------------

def test_open_app_uses_shortcut_first(isolated_db, tmp_path, monkeypatch):
    from backend.app.services.desktop_service import DesktopService
    from backend.app.tools.desktop_tool import open_app

    shortcut = tmp_path / "Unity Hub.lnk"
    exe = tmp_path / "Unity Hub.exe"
    shortcut.write_text("", encoding="utf-8")
    exe.write_text("", encoding="utf-8")

    svc = DesktopService()
    conn = __import__("backend.app.services.node_service", fromlist=["_conn"])._conn()
    try:
        svc._upsert_discovered_app(conn, {
            "name": "Unity Hub",
            "executable_path": str(exe),
            "shortcut_path": str(shortcut),
            "launch_command": str(shortcut),
            "source": "Unit Test",
            "launch_type": "shortcut",
            "confidence": 0.95,
        })
        conn.commit()
    finally:
        conn.close()

    launched = []
    monkeypatch.setattr("backend.app.tools.desktop_tool.os.startfile", lambda target: launched.append(target), raising=False)

    result = open_app("unity")
    assert result["ok"], result.get("summary")
    assert launched == [str(shortcut)]
    assert result["launch_type"] == "shortcut"


# ---------------------------------------------------------------------------
# Test 33: Planner routes generic app opens and scan/show commands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("command,tool,args", [
    ("open obs", "open_app", {"name": "obs"}),
    ("open unity hub", "open_app", {"name": "unity hub"}),
    ("rescan apps", "scan_apps", {}),
    ("show app blender", "show_app", {"name": "blender"}),
])
def test_planner_regex_dynamic_app_commands(command, tool, args):
    from backend.app.tools.planner import _regex_fallback
    result = _regex_fallback(command)
    assert result["action"] == "call_tool"
    if tool == "open_app":
        assert result["name"] in {"open_app", "open_target"}
    else:
        assert result["name"] == tool
    for key, value in args.items():
        actual = result["args"].get(key) or result["args"].get("target")
        assert actual == value
