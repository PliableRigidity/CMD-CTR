"""Provider-agnostic contract for email and calendar operations.

All concrete providers (Google, Microsoft, …) implement this interface so the
rest of the codebase never imports provider-specific code directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ProductivityProvider(ABC):
    """Abstract base for all productivity providers."""

    # ── Auth ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def get_auth_url(self) -> str:
        """Return the OAuth2 authorization URL the user should visit."""

    @abstractmethod
    def exchange_code(self, code: str) -> dict:
        """Exchange an authorization code for tokens. Returns stored token dict."""

    @abstractmethod
    def is_authenticated(self) -> bool:
        """True if valid (and auto-refreshable) credentials are stored."""

    @abstractmethod
    def whoami(self) -> str:
        """Return the authenticated account identifier (email address)."""

    @abstractmethod
    def revoke(self) -> None:
        """Revoke stored credentials and clear them from storage."""

    # ── Gmail ────────────────────────────────────────────────────────────────

    @abstractmethod
    def list_emails(
        self,
        folder: str = "inbox",
        search: str = "",
        limit: int = 10,
    ) -> list[dict]:
        """List emails. Each dict: {id, subject, sender, date, snippet, unread}."""

    @abstractmethod
    def get_email(self, message_id: str) -> dict:
        """Full email: {id, subject, sender, date, body_text, snippet}."""

    @abstractmethod
    def draft_email(self, to: str, subject: str, body: str) -> dict:
        """Create a Gmail draft. Returns {draft_id, to, subject, preview}."""

    @abstractmethod
    def send_email(self, to: str, subject: str, body: str) -> dict:
        """Send an email immediately. Call ONLY after user confirmation."""

    # ── Calendar ─────────────────────────────────────────────────────────────

    @abstractmethod
    def list_events(self, date: str | None = None, days: int = 1) -> list[dict]:
        """List calendar events. date='today' or 'YYYY-MM-DD'. Each dict:
        {id, title, start, end, location, description}."""

    @abstractmethod
    def create_event(
        self,
        title: str,
        start_iso: str,
        end_iso: str | None = None,
        description: str = "",
        location: str = "",
    ) -> dict:
        """Create a calendar event. Returns the created event dict."""

    @abstractmethod
    def delete_event(self, event_id: str) -> bool:
        """Delete a calendar event. Returns True on success."""

