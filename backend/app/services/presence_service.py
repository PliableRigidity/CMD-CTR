"""Presence Manager — conversational context and work session tracking.

Maintains the active project/task/topic so follow-up commands like
"what's next?" or "open Fusion" are scoped to the current context
without the user repeating themselves.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("silvia.presence")


@dataclass
class WorkSession:
    project: str
    started_at: str
    tasks_completed: list[str] = field(default_factory=list)
    decisions_made: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    actions_performed: list[str] = field(default_factory=list)


class PresenceManager:
    def __init__(self) -> None:
        self.active_project: str | None = None
        self.active_task: str | None = None
        self.active_node: str | None = None
        self.active_topic: str | None = None
        self.focus_mode: bool = False
        self.work_session: WorkSession | None = None
        self._last_interaction: float = 0.0
        self._voice_state: str = "idle"
        logger.info("PresenceManager initialized")

    def set_project(self, project: str) -> dict:
        prev = self.active_project
        self.active_project = project
        self._last_interaction = time.time()
        logger.info("Active project: %s -> %s", prev, project)
        return {"project": project, "previous": prev}

    def set_task(self, task: str) -> None:
        self.active_task = task
        self._last_interaction = time.time()

    def set_node(self, node: str) -> None:
        self.active_node = node
        self._last_interaction = time.time()

    def set_topic(self, topic: str) -> None:
        self.active_topic = topic
        self._last_interaction = time.time()

    def set_voice_state(self, state: str) -> None:
        self._voice_state = state

    def toggle_focus(self, enabled: bool | None = None) -> bool:
        if enabled is not None:
            self.focus_mode = enabled
        else:
            self.focus_mode = not self.focus_mode
        logger.info("Focus mode: %s", self.focus_mode)
        return self.focus_mode

    def start_work_session(self, project: str | None = None) -> dict:
        proj = project or self.active_project
        if proj:
            self.active_project = proj
        self.work_session = WorkSession(
            project=proj or "General",
            started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        logger.info("Work session started: %s", self.work_session.project)
        return {
            "started": True,
            "project": self.work_session.project,
            "started_at": self.work_session.started_at,
        }

    def end_work_session(self) -> dict:
        if not self.work_session:
            return {"ended": False, "reason": "No active work session"}
        summary = {
            "ended": True,
            "project": self.work_session.project,
            "started_at": self.work_session.started_at,
            "ended_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tasks_completed": self.work_session.tasks_completed,
            "decisions_made": self.work_session.decisions_made,
            "actions_performed": self.work_session.actions_performed,
            "notes": self.work_session.notes,
        }
        logger.info("Work session ended: %s (%d tasks, %d actions)",
                     self.work_session.project,
                     len(self.work_session.tasks_completed),
                     len(self.work_session.actions_performed))
        self.work_session = None
        return summary

    def record_action(self, action: str) -> None:
        if self.work_session:
            self.work_session.actions_performed.append(action)
        self._last_interaction = time.time()

    def record_task_completed(self, task: str) -> None:
        if self.work_session:
            self.work_session.tasks_completed.append(task)

    def record_decision(self, decision: str) -> None:
        if self.work_session:
            self.work_session.decisions_made.append(decision)

    def reset(self) -> dict:
        self.active_project = None
        self.active_task = None
        self.active_node = None
        self.active_topic = None
        self.work_session = None
        logger.info("Presence context reset")
        return {"reset": True}

    def get_status(self) -> dict:
        return {
            "active_project": self.active_project,
            "active_task": self.active_task,
            "active_node": self.active_node,
            "active_topic": self.active_topic,
            "focus_mode": self.focus_mode,
            "voice_state": self._voice_state,
            "work_session": {
                "active": self.work_session is not None,
                "project": self.work_session.project if self.work_session else None,
                "started_at": self.work_session.started_at if self.work_session else None,
                "tasks_completed": len(self.work_session.tasks_completed) if self.work_session else 0,
                "actions_performed": len(self.work_session.actions_performed) if self.work_session else 0,
            },
            "follow_up_active": self.in_followup_window(),
            "last_interaction": self._last_interaction,
        }

    def get_context(self) -> dict:
        return {
            "active_project": self.active_project,
            "active_task": self.active_task,
            "active_node": self.active_node,
            "active_topic": self.active_topic,
        }

    def in_followup_window(self) -> bool:
        from backend.config import VOICE_FOLLOWUP_WINDOW
        if not self._last_interaction:
            return False
        return (time.time() - self._last_interaction) < VOICE_FOLLOWUP_WINDOW

    def build_context_block(self) -> str:
        """Build a context string to inject into LLM prompts."""
        parts: list[str] = []
        if self.active_project:
            parts.append(f"The user is currently working on project: {self.active_project}")
        if self.active_task:
            parts.append(f"Current task: {self.active_task}")
        if self.active_node:
            parts.append(f"Active node/device: {self.active_node}")
        if self.active_topic:
            parts.append(f"Discussion topic: {self.active_topic}")
        if self.work_session:
            parts.append(f"Work session active since {self.work_session.started_at} on {self.work_session.project}")
        if not parts:
            return ""
        return (
            "[PRESENCE CONTEXT — scope follow-up questions to this context]\n"
            + "\n".join(parts)
        )


_singleton: PresenceManager | None = None


def get_presence() -> PresenceManager:
    global _singleton
    if _singleton is None:
        _singleton = PresenceManager()
    return _singleton
