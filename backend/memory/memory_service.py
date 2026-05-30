"""High-level memory service — wraps the SQLite layer."""

from __future__ import annotations

from typing import Any

from backend.memory import database as db


class MemoryService:
    """Provides conversation history and persistent fact storage."""

    def __init__(self) -> None:
        db.init_db()

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    def save_turn(self, session_id: str, user_query: str, assistant_reply: str, mode: str = "conversation") -> None:
        db.save_message(session_id, "user", user_query, mode)
        db.save_message(session_id, "assistant", assistant_reply, mode)

    def get_history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return last `limit` messages (oldest first) for use as Ollama context."""
        return db.get_messages(session_id, limit)

    def get_ollama_messages(self, session_id: str, limit: int = 10) -> list[dict[str, str]]:
        """
        Return conversation history formatted as Ollama chat messages.
        Excludes the current turn (caller adds that themselves).
        """
        history = self.get_history(session_id, limit * 2)
        return [{"role": msg["role"], "content": msg["content"]} for msg in history]

    def clear_session(self, session_id: str) -> int:
        return db.clear_session(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        return db.list_sessions()

    # ------------------------------------------------------------------
    # Facts / preferences
    # ------------------------------------------------------------------

    def remember(self, key: str, value: str) -> None:
        db.set_fact(key, value)

    def recall(self, key: str) -> str | None:
        return db.get_fact(key)

    def all_facts(self) -> dict[str, str]:
        return db.get_all_facts()
