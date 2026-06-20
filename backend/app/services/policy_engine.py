"""Policy Engine — Phase 17A.

Permission profiles that control which risk levels are allowed
without approval, which require approval, and which are blocked.

Profiles:
  - readonly:      Only READ allowed, everything else blocked
  - developer:     READ + LOW + MODERATE allowed, HIGH/CRITICAL need approval
  - operator:      READ + LOW + MODERATE + HIGH allowed, CRITICAL needs approval
  - administrator: Everything allowed, CRITICAL still needs approval
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from backend.app.services.safety_engine import READ, LOW, MODERATE, HIGH, CRITICAL

logger = logging.getLogger("silvia.policy")

DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"

PROFILES: dict[str, dict[str, Any]] = {
    "readonly": {
        "name": "Read Only",
        "description": "View-only access. Cannot modify, execute, or delete anything.",
        "allowed_levels": {READ},
        "approval_levels": set(),
        "blocked_levels": {LOW, MODERATE, HIGH, CRITICAL},
    },
    "developer": {
        "name": "Developer",
        "description": "Can edit projects, manage inventory, create plans. Cannot delete infrastructure or shutdown nodes without approval.",
        "allowed_levels": {READ, LOW, MODERATE},
        "approval_levels": {HIGH, CRITICAL},
        "blocked_levels": set(),
    },
    "operator": {
        "name": "Operator",
        "description": "Full operational access. Can manage infrastructure. Critical actions still require approval.",
        "allowed_levels": {READ, LOW, MODERATE, HIGH},
        "approval_levels": {CRITICAL},
        "blocked_levels": set(),
    },
    "administrator": {
        "name": "Administrator",
        "description": "Full access. Critical actions still require approval for safety.",
        "allowed_levels": {READ, LOW, MODERATE, HIGH},
        "approval_levels": {CRITICAL},
        "blocked_levels": set(),
    },
}

DEFAULT_PROFILE = "administrator"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


class PolicyEngine:
    """Evaluates permissions based on the active policy profile."""

    def __init__(self) -> None:
        self._init_tables()
        self._profile: str | None = None

    def _init_tables(self) -> None:
        with _conn() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS safety_policy (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

    def get_active_profile(self) -> str:
        """Get the currently active policy profile name."""
        if self._profile:
            return self._profile
        with _conn() as db:
            row = db.execute(
                "SELECT value FROM safety_policy WHERE key='active_profile'"
            ).fetchone()
        self._profile = row["value"] if row else DEFAULT_PROFILE
        return self._profile

    def set_profile(self, profile_name: str) -> dict[str, Any]:
        """Set the active policy profile."""
        if profile_name not in PROFILES:
            return {"ok": False, "error": f"Unknown profile '{profile_name}'. Available: {', '.join(PROFILES.keys())}"}

        with _conn() as db:
            db.execute(
                "INSERT OR REPLACE INTO safety_policy (key, value) VALUES ('active_profile', ?)",
                (profile_name,),
            )
        self._profile = profile_name
        return {"ok": True, "profile": profile_name, "description": PROFILES[profile_name]["description"]}

    def check(self, tool_name: str, risk_level: int) -> dict[str, Any]:
        """Check if a tool action is allowed under the current policy.

        Returns:
            {
                "allowed": bool,
                "needs_approval": bool,
                "reason": str,
                "profile": str,
            }
        """
        profile_name = self.get_active_profile()
        profile = PROFILES.get(profile_name, PROFILES[DEFAULT_PROFILE])

        if risk_level in profile["blocked_levels"]:
            return {
                "allowed": False,
                "needs_approval": False,
                "reason": f"Blocked by '{profile['name']}' policy. Risk level too high.",
                "profile": profile_name,
            }

        if risk_level in profile["approval_levels"]:
            return {
                "allowed": True,
                "needs_approval": True,
                "reason": f"Requires approval under '{profile['name']}' policy.",
                "profile": profile_name,
            }

        if risk_level in profile["allowed_levels"]:
            return {
                "allowed": True,
                "needs_approval": False,
                "reason": "Allowed.",
                "profile": profile_name,
            }

        # Default: require approval for unknown levels
        return {
            "allowed": True,
            "needs_approval": True,
            "reason": f"Unknown risk level — defaulting to approval required.",
            "profile": profile_name,
        }

    def list_profiles(self) -> list[dict[str, Any]]:
        """List all available policy profiles."""
        active = self.get_active_profile()
        return [
            {
                "id": pid,
                "name": p["name"],
                "description": p["description"],
                "active": pid == active,
            }
            for pid, p in PROFILES.items()
        ]

    def get_profile_detail(self, profile_name: str) -> Optional[dict]:
        """Get detailed info about a profile."""
        p = PROFILES.get(profile_name)
        if not p:
            return None
        from backend.app.services.safety_engine import _LEVEL_NAMES
        return {
            "id": profile_name,
            "name": p["name"],
            "description": p["description"],
            "allowed": [_LEVEL_NAMES[l] for l in sorted(p["allowed_levels"])],
            "requires_approval": [_LEVEL_NAMES[l] for l in sorted(p["approval_levels"])],
            "blocked": [_LEVEL_NAMES[l] for l in sorted(p["blocked_levels"])],
        }


_instance: Optional[PolicyEngine] = None


def get_policy_engine() -> PolicyEngine:
    global _instance
    if _instance is None:
        _instance = PolicyEngine()
    return _instance
