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


# ---------------------------------------------------------------------------
# Built-in site shortcuts  (name → URL)
# ---------------------------------------------------------------------------
SITE_ALIASES: dict[str, str] = {
    # Search & productivity
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "google drive": "https://drive.google.com",
    "google docs": "https://docs.google.com",
    "google sheets": "https://sheets.google.com",
    "google calendar": "https://calendar.google.com",
    "google meet": "https://meet.google.com",
    # Dev tools
    "github": "https://github.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "mdn": "https://developer.mozilla.org",
    "npm": "https://www.npmjs.com",
    "pypi": "https://pypi.org",
    "docker hub": "https://hub.docker.com",
    # AI tools
    "claude": "https://claude.ai",
    "chatgpt": "https://chat.openai.com",
    "perplexity": "https://www.perplexity.ai",
    "gemini": "https://gemini.google.com",
    # Media & social
    "spotify": "https://open.spotify.com",
    "twitter": "https://twitter.com",
    "reddit": "https://www.reddit.com",
    "linkedin": "https://www.linkedin.com",
    "twitch": "https://www.twitch.tv",
    "netflix": "https://www.netflix.com",
    # News
    "bbc": "https://www.bbc.com/news",
    "hackernews": "https://news.ycombinator.com",
    "hacker news": "https://news.ycombinator.com",
    # Tools
    "notion": "https://www.notion.so",
    "figma": "https://www.figma.com",
    "canva": "https://www.canva.com",
    "excalidraw": "https://excalidraw.com",
    "linear": "https://linear.app",
    "trello": "https://trello.com",
}

# Spoken display names for aliases whose .title() form is wrong.
_DISPLAY_OVERRIDES: dict[str, str] = {
    "github": "GitHub", "youtube": "YouTube", "gmail": "Gmail",
    "chatgpt": "ChatGPT", "mdn": "MDN", "npm": "npm", "pypi": "PyPI",
    "stackoverflow": "Stack Overflow", "stack overflow": "Stack Overflow",
    "hackernews": "Hacker News", "hacker news": "Hacker News",
    "linkedin": "LinkedIn", "bbc": "BBC News", "docker hub": "Docker Hub",
}

# URL → spoken name, so responses say "Spotify is open" instead of the URL.
_URL_DISPLAY_NAMES: dict[str, str] = {}
for _alias, _url in SITE_ALIASES.items():
    _URL_DISPLAY_NAMES.setdefault(_url, _DISPLAY_OVERRIDES.get(_alias, _alias.title()))


def _spoken_name_for_url(url: str) -> str | None:
    if url in _URL_DISPLAY_NAMES:
        return _URL_DISPLAY_NAMES[url]
    stripped = url.rstrip("/")
    return _URL_DISPLAY_NAMES.get(stripped) or _URL_DISPLAY_NAMES.get(stripped + "/")


def _strip_desktop_action_prefix(value: str) -> str:
    for prefix in ("open ", "launch ", "start ", "run "):
        if value.startswith(prefix):
            return value[len(prefix):].strip()
    return value


def _try_desktop_app(value: str) -> ActionExecutionResponse | None:
    if not value:
        return None
    try:
        from backend.app.services.desktop_service import DesktopService
        from backend.app.tools.desktop_tool import open_app
        svc = DesktopService()
        app = svc.find_app(value)
        if app is None:
            return None
        result = open_app(value)
        return ActionExecutionResponse(
            success=bool(result.get("ok")),
            action=f"desktop:{app['name']}",
            message=result.get("summary", ""),
            opened_target=result.get("executable") or app.get("executable"),
            details={
                "registry": "app_registry",
                "app": app,
                "tool_result": result,
            },
        )
    except Exception as exc:
        return ActionExecutionResponse(
            success=False,
            action=f"desktop:{value}",
            message=f"Desktop application registry lookup failed for '{value}': {exc}",
        )

# ---------------------------------------------------------------------------
# Default actions
# ---------------------------------------------------------------------------
_DEFAULT_ACTIONS: list[dict] = [
    # Editors & IDEs
    {
        "id": "open_vscode",
        "label": "VS Code",
        "kind": "app",
        "target": "code",
        "description": "Launch Visual Studio Code.",
        "aliases": ["vscode", "code", "visual studio code", "vs code"],
    },
    {
        "id": "open_cursor",
        "label": "Cursor",
        "kind": "app",
        "target": "cursor",
        "description": "Launch Cursor AI editor.",
        "aliases": ["cursor"],
    },
    # Terminals
    {
        "id": "open_terminal",
        "label": "Terminal",
        "kind": "app",
        "target": "powershell.exe",
        "description": "Launch a PowerShell terminal.",
        "aliases": ["terminal", "powershell", "shell", "cmd"],
    },
    {
        "id": "open_wt",
        "label": "Windows Terminal",
        "kind": "app",
        "target": "wt.exe",
        "description": "Launch Windows Terminal.",
        "aliases": ["windows terminal", "wt"],
    },
    # Browsers
    {
        "id": "open_browser",
        "label": "Browser",
        "kind": "url",
        "target": "https://www.google.com",
        "description": "Open the default browser.",
        "aliases": ["browser", "web", "google chrome", "chrome", "firefox", "edge"],
    },
    # Music & media
    {
        "id": "open_spotify",
        "label": "Spotify",
        "kind": "app",
        "target": "spotify:",
        "description": "Launch Spotify.",
        "aliases": ["spotify", "music"],
    },
    # File management
    {
        "id": "open_explorer",
        "label": "File Explorer",
        "kind": "app",
        "target": "explorer.exe",
        "description": "Open Windows File Explorer.",
        "aliases": ["explorer", "file explorer", "files", "finder"],
    },
    # Dev sites
    {
        "id": "open_github",
        "label": "GitHub",
        "kind": "url",
        "target": "https://github.com",
        "description": "Open GitHub.",
        "aliases": ["github"],
    },
    {
        "id": "open_claude",
        "label": "Claude.ai",
        "kind": "url",
        "target": "https://claude.ai",
        "description": "Open Claude.ai in the browser.",
        "aliases": ["claude", "claude ai", "claude.ai", "anthropic"],
    },
    # Productivity
    {
        "id": "open_notion",
        "label": "Notion",
        "kind": "url",
        "target": "https://www.notion.so",
        "description": "Open Notion.",
        "aliases": ["notion"],
    },
    {
        "id": "open_calendar",
        "label": "Google Calendar",
        "kind": "url",
        "target": "https://calendar.google.com",
        "description": "Open Google Calendar.",
        "aliases": ["calendar", "google calendar"],
    },
    # Communications
    {
        "id": "open_gmail",
        "label": "Gmail",
        "kind": "url",
        "target": "https://mail.google.com",
        "description": "Open Gmail.",
        "aliases": ["gmail", "email", "mail"],
    },
    # Workspace
    {
        "id": "assistant_workspace",
        "label": "CMD-CTR Workspace",
        "kind": "workspace",
        "target": str(Path(__file__).resolve().parent.parent.parent.parent),
        "description": "Open this project's root folder.",
        "aliases": ["workspace", "assistant repo", "cmd-ctr", "project"],
    },
    # System utilities
    {
        "id": "open_task_manager",
        "label": "Task Manager",
        "kind": "app",
        "target": "taskmgr.exe",
        "description": "Open Windows Task Manager.",
        "aliases": ["task manager", "taskmgr", "processes"],
    },
    {
        "id": "open_settings",
        "label": "Windows Settings",
        "kind": "app",
        "target": "ms-settings:",
        "description": "Open Windows Settings.",
        "aliases": ["settings", "windows settings", "control panel"],
    },
    {
        "id": "open_calculator",
        "label": "Calculator",
        "kind": "app",
        "target": "calc.exe",
        "description": "Open the Windows Calculator.",
        "aliases": ["calculator", "calc"],
    },
    {
        "id": "open_snipping",
        "label": "Snipping Tool",
        "kind": "app",
        "target": "SnippingTool.exe",
        "description": "Open the Windows Snipping Tool for screenshots.",
        "aliases": ["snipping tool", "screenshot", "snip", "snipscreen"],
    },
]


class ActionService:
    def __init__(self) -> None:
        self._actions: list[ActionDescriptor] = [
            ActionDescriptor(**a) for a in _DEFAULT_ACTIONS
        ]
        self._site_aliases: dict[str, str] = dict(SITE_ALIASES)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_action(self, action: ActionDescriptor) -> None:
        """Dynamically add or replace an action at runtime."""
        self._actions = [a for a in self._actions if a.id != action.id]
        self._actions.append(action)

    def register_site(self, name: str, url: str) -> None:
        self._site_aliases[name.lower()] = url

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_actions(self) -> list[ActionDescriptor]:
        return self._actions

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def open_registered_app(self, action_id: str, args: list[str] | None = None) -> ActionExecutionResponse:
        action = next((a for a in self._actions if a.id == action_id), None)
        if action is None:
            return ActionExecutionResponse(success=False, action=action_id, message="Action not found.")
        return self.execute_action(action, args or [])

    def execute_alias(self, value: str) -> ActionExecutionResponse:
        normalized = value.strip().lower()
        desktop_target = _strip_desktop_action_prefix(normalized)

        desktop_app = _try_desktop_app(desktop_target or normalized)
        if desktop_app is not None:
            return desktop_app

        # Exact site alias match
        if normalized in self._site_aliases:
            return self.open_url(self._site_aliases[normalized])

        # Exact action id / alias match
        for action in self._actions:
            aliases_lower = [a.lower() for a in action.aliases]
            if normalized == action.id or normalized in aliases_lower:
                return self.execute_action(action, [])

        # Partial site alias match (e.g. "youtube" in "open youtube music")
        for alias, url in self._site_aliases.items():
            if alias in normalized:
                return self.open_url(url)

        # Partial action alias match
        for action in self._actions:
            if any(alias.lower() in normalized for alias in action.aliases):
                args = []
                if action.id == "open_vscode" and ("repo" in normalized or "workspace" in normalized):
                    args = [str(Path.cwd())]
                return self.execute_action(action, args)

        # Raw URL
        if _is_url(value):
            return self.open_url(value)

        # Domain shorthand (e.g. "github.com")
        if "." in value and " " not in value:
            return self.open_url(f"https://{value}")

        return ActionExecutionResponse(
            success=False,
            action=value,
            message=(
                f"Unknown action or alias: '{value}'. Checked registered desktop apps, "
                "built-in actions, site aliases, URL syntax, and domain shorthand."
            ),
        )

    def execute_action(self, action: ActionDescriptor, args: list[str]) -> ActionExecutionResponse:
        try:
            if action.kind == "url":
                return self.open_url(action.target)
            if action.kind == "workspace":
                os.startfile(action.target)
                return ActionExecutionResponse(
                    success=True, action=action.id,
                    message=f"{action.label} is open.",
                    opened_target=action.target,
                )
            if action.kind == "app":
                return self._launch_app(action.target, action.id, args, label=action.label)
        except Exception as exc:
            return ActionExecutionResponse(
                success=False, action=action.id,
                message=f"Failed to execute: {exc}",
                opened_target=action.target,
            )
        return ActionExecutionResponse(success=True, action=action.id, message="Action executed.", opened_target=action.target)

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
        spoken = _spoken_name_for_url(target)
        if spoken:
            message = f"{spoken} is open."
        else:
            domain = urlparse(target).netloc or target
            message = f"{domain} is open in the browser."
        return ActionExecutionResponse(
            success=True, action="open_url",
            message=message,
            opened_target=target,
        )

    def _launch_app(self, target: str, action_id: str, args: list[str], label: str | None = None) -> ActionExecutionResponse:
        spoken = label or action_id.removeprefix("open_").replace("_", " ").title()
        # VS Code special case
        if target == "code":
            executable = shutil.which("code") or shutil.which("code.cmd")
            if executable:
                subprocess.Popen([executable, *args] if args else [executable])
                return ActionExecutionResponse(
                    success=True, action=action_id,
                    message="VS Code is up.",
                    opened_target=executable,
                )
            repo = args[0] if args else str(Path.cwd())
            os.startfile(repo)
            return ActionExecutionResponse(
                success=True, action=action_id,
                message="VS Code not found on PATH; opened the folder instead.",
                opened_target=repo,
            )

        # URI schemes (ms-settings:, spotify:, etc.)
        if ":" in target and not target.startswith("/"):
            try:
                os.startfile(target)
                return ActionExecutionResponse(
                    success=True, action=action_id,
                    message=f"{spoken} is up.", opened_target=target,
                )
            except Exception as exc:
                return ActionExecutionResponse(
                    success=False, action=action_id,
                    message=f"Failed to launch {target}: {exc}",
                )

        # Path / executable
        if Path(target).exists():
            os.startfile(str(target))
        else:
            executable = shutil.which(target)
            if executable:
                subprocess.Popen([executable, *args] if args else [executable])
            else:
                try:
                    os.startfile(target)
                except Exception as exc:
                    return ActionExecutionResponse(
                        success=False, action=action_id,
                        message=f"Could not launch '{target}': {exc}",
                    )
        return ActionExecutionResponse(
            success=True, action=action_id,
            message=f"{spoken} is up.",
            opened_target=target,
            details={"args": args},
        )
