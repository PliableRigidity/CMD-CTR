from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from backend.app.models.actions import ActionDescriptor, ActionExecutionResponse


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


class ActionService:
    def __init__(self) -> None:
        repo_root = str(Path.cwd())
        self._actions = [
            ActionDescriptor(
                id="open_vscode",
                label="Open VS Code",
                kind="app",
                target="code",
                description="Launch Visual Studio Code.",
                aliases=["vscode", "code", "visual studio code"],
            ),
            ActionDescriptor(
                id="open_browser",
                label="Open Browser",
                kind="url",
                target="https://www.google.com",
                description="Open the default browser.",
                aliases=["browser", "web", "google"],
            ),
            ActionDescriptor(
                id="open_spotify",
                label="Open Spotify",
                kind="app",
                target="spotify",
                description="Launch Spotify if installed.",
                aliases=["spotify"],
            ),
            ActionDescriptor(
                id="assistant_repo",
                label="Assistant Workspace",
                kind="workspace",
                target=repo_root,
                description="Open this repository workspace.",
                aliases=["assistant repo", "current repo", "workspace"],
            ),
            ActionDescriptor(
                id="open_github",
                label="Open GitHub",
                kind="url",
                target="https://github.com",
                description="Open GitHub in the browser.",
                aliases=["github"],
            ),
            ActionDescriptor(
                id="open_terminal",
                label="Open Terminal",
                kind="app",
                target="powershell.exe",
                description="Launch a terminal window.",
                aliases=["terminal", "powershell", "shell"],
            ),
        ]
        self._site_aliases = {
            "youtube": "https://www.youtube.com",
            "gmail": "https://mail.google.com",
            "github": "https://github.com",
            "spotify": "https://open.spotify.com",
        }

    def list_actions(self) -> list[ActionDescriptor]:
        return self._actions

    def open_registered_app(self, action_id: str, args: list[str] | None = None) -> ActionExecutionResponse:
        action = next((item for item in self._actions if item.id == action_id), None)
        if action is None:
            return ActionExecutionResponse(success=False, action=action_id, message="Action not allowlisted.")
        return self.execute_action(action, args or [])

    def execute_alias(self, value: str) -> ActionExecutionResponse:
        normalized = value.strip().lower()
        if normalized in self._site_aliases:
            return self.open_url(self._site_aliases[normalized])
        for action in self._actions:
            if normalized == action.id or normalized in [alias.lower() for alias in action.aliases]:
                return self.execute_action(action, [])
        for alias, url in self._site_aliases.items():
            if alias in normalized:
                return self.open_url(url)
        for action in self._actions:
            if any(alias.lower() in normalized for alias in action.aliases):
                args = []
                if action.id == "open_vscode" and ("repo" in normalized or "workspace" in normalized):
                    args = [str(Path.cwd())]
                return self.execute_action(action, args)
        if _is_url(value):
            return self.open_url(value)
        return ActionExecutionResponse(success=False, action=value, message="Unknown action or alias.")

    def execute_action(self, action: ActionDescriptor, args: list[str]) -> ActionExecutionResponse:
        try:
            if action.kind == "url":
                return self.open_url(action.target)
            if action.kind == "workspace":
                os.startfile(action.target)
                return ActionExecutionResponse(
                    success=True,
                    action=action.id,
                    message=f"Opened workspace at {action.target}.",
                    opened_target=action.target,
                )
            if action.kind == "app":
                return self._launch_app(action.target, action.id, args)
        except Exception as exc:
            return ActionExecutionResponse(
                success=False,
                action=action.id,
                message=f"Failed to execute action: {exc}",
                opened_target=action.target,
            )
        return ActionExecutionResponse(
            success=True,
            action=action.id,
            message="Action executed.",
            opened_target=action.target,
        )

    def open_url(self, target: str) -> ActionExecutionResponse:
        if not _is_url(target):
            alias = self._site_aliases.get(target.strip().lower())
            if alias:
                target = alias
            elif "." in target and " " not in target:
                target = f"https://{target}"
            else:
                return ActionExecutionResponse(success=False, action="open_url", message="Invalid URL or alias.")
        webbrowser.open(target, new=2)
        return ActionExecutionResponse(
            success=True,
            action="open_url",
            message="Opened URL in the default browser.",
            opened_target=target,
        )

    def _launch_app(self, target: str, action_id: str, args: list[str]) -> ActionExecutionResponse:
        if target == "code":
            executable = shutil.which("code") or shutil.which("code.cmd")
            if executable:
                subprocess.Popen([executable, *args] if args else [executable])
                return ActionExecutionResponse(
                    success=True,
                    action=action_id,
                    message="Launched Visual Studio Code.",
                    opened_target=executable,
                )
            repo = args[0] if args else str(Path.cwd())
            os.startfile(repo)
            return ActionExecutionResponse(
                success=True,
                action=action_id,
                message="VS Code executable not found; opened the requested folder instead.",
                opened_target=repo,
            )

        launch_target = target
        if target == "spotify":
            launch_target = "spotify:"
        if Path(launch_target).exists():
            os.startfile(str(Path(launch_target)))
        else:
            executable = shutil.which(launch_target)
            if executable:
                subprocess.Popen([executable, *args] if args else [executable])
            else:
                os.startfile(launch_target)
        return ActionExecutionResponse(
            success=True,
            action=action_id,
            message=f"Launched {action_id}.",
            opened_target=launch_target,
            details={"args": args},
        )
