"""Workspace Restore — Phase 16B.

Restores engineering workspaces by launching applications, opening
project folders, and navigating to SILVIA boards. Uses workspace
profiles from session_manager and project data from the registry.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("silvia.workspace_restore")

_SILVIA_HOST = os.getenv("SILVIA_HOST", "localhost")
_SILVIA_PORT = os.getenv("SILVIA_PORT", "8001")
_FRONTEND_PORT = os.getenv("FRONTEND_PORT", "5173")


class WorkspaceRestore:
    """Restores engineering workspaces from profiles and session data."""

    def restore(self, project: str) -> dict[str, Any]:
        """Restore a workspace for a project.

        1. Get workspace profile (stored or auto-generated)
        2. Open VS Code with project folder
        3. Open relevant SILVIA boards
        4. Open URLs if configured
        """
        from backend.app.services.session_manager import get_session_manager
        sm = get_session_manager()
        profile = sm.get_profile(project)

        if not profile:
            return {"ok": False, "error": f"No workspace profile found for '{project}'."}

        results = {
            "ok": True,
            "project": profile["project"],
            "opened": [],
            "failed": [],
            "profile": profile,
        }

        # 1. Open VS Code with project folder
        folders = profile.get("folders", [])
        if folders:
            for folder in folders[:1]:
                r = self._open_vscode(folder)
                if r["ok"]:
                    results["opened"].append(f"VS Code: {folder}")
                else:
                    results["failed"].append(f"VS Code: {r.get('error', 'failed')}")
        elif "VS Code" in profile.get("apps", []):
            r = self._open_vscode(None)
            if r["ok"]:
                results["opened"].append("VS Code")

        # 2. Open SILVIA boards
        boards = profile.get("boards", [])
        for board in boards:
            r = self._open_board(board)
            if r["ok"]:
                results["opened"].append(f"Board: {board}")

        # 3. Open URLs
        urls = profile.get("urls", [])
        for url in urls[:3]:
            try:
                webbrowser.open(url, new=2)
                results["opened"].append(f"URL: {url}")
            except Exception as e:
                results["failed"].append(f"URL {url}: {e}")

        # 4. Open project folder in Explorer (if not already opened via VS Code)
        if not folders:
            folder = self._find_project_folder(profile["project"])
            if folder:
                results["project_folder"] = str(folder)

        results["summary"] = self._build_summary(results)
        return results

    def restore_last_session(self) -> dict[str, Any]:
        """Restore the most recent session's workspace."""
        from backend.app.services.session_manager import get_session_manager
        last = get_session_manager().get_last_session()
        if not last:
            return {"ok": False, "error": "No previous session found."}
        return self.restore(last["project"])

    def get_restore_plan(self, project: str) -> dict[str, Any]:
        """Preview what would be restored without actually opening anything."""
        from backend.app.services.session_manager import get_session_manager
        sm = get_session_manager()
        profile = sm.get_profile(project)

        if not profile:
            return {"ok": False, "error": f"No workspace profile for '{project}'."}

        steps = []
        folders = profile.get("folders", [])
        if folders:
            steps.append(f"Open VS Code with {folders[0]}")
        elif "VS Code" in profile.get("apps", []):
            steps.append("Open VS Code")

        for board in profile.get("boards", []):
            steps.append(f"Open SILVIA board: {board}")

        for url in profile.get("urls", [])[:3]:
            steps.append(f"Open URL: {url}")

        # Also find project folder
        folder = self._find_project_folder(profile["project"])
        if folder and str(folder) not in (folders or []):
            steps.append(f"Project folder: {folder}")

        return {
            "ok": True,
            "project": profile["project"],
            "steps": steps,
            "profile": profile,
            "auto_generated": profile.get("auto_generated", False),
        }

    # ── App launchers ───────────────────────────────────────────────────────

    def _open_vscode(self, folder: Optional[str]) -> dict:
        """Open VS Code, optionally with a project folder."""
        try:
            code = shutil.which("code") or shutil.which("code.cmd")
            if code:
                args = [code]
                if folder and Path(folder).exists():
                    args.append(folder)
                subprocess.Popen(args)
                return {"ok": True}
            elif folder and Path(folder).exists():
                os.startfile(folder)
                return {"ok": True}
            return {"ok": False, "error": "VS Code not found on PATH"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _open_board(self, route: str) -> dict:
        """Open a SILVIA board in the browser."""
        try:
            url = f"http://{_SILVIA_HOST}:{_FRONTEND_PORT}{route}"
            webbrowser.open(url, new=2)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _find_project_folder(self, project_name: str) -> Optional[Path]:
        """Find a project folder on disk."""
        gh_root = Path.home() / "Documents" / "GitHub"
        candidates = [
            gh_root / project_name,
            gh_root / project_name.lower(),
            gh_root / project_name.replace(" ", "-"),
            gh_root / project_name.upper(),
        ]
        for c in candidates:
            if c.exists():
                return c
        # Search all subdirectories of GitHub folder
        if gh_root.exists():
            for d in gh_root.iterdir():
                if d.is_dir() and d.name.lower() == project_name.lower():
                    return d
        return None

    def _build_summary(self, results: dict) -> str:
        opened = results.get("opened", [])
        failed = results.get("failed", [])
        proj = results.get("project", "")
        if opened and not failed:
            return f"Restored {proj} workspace: opened {len(opened)} item(s)."
        elif opened:
            return f"Partially restored {proj}: {len(opened)} opened, {len(failed)} failed."
        else:
            return f"Could not restore {proj} workspace."


_instance: Optional[WorkspaceRestore] = None


def get_restore() -> WorkspaceRestore:
    global _instance
    if _instance is None:
        _instance = WorkspaceRestore()
    return _instance
