"""Semantic Memory — sqlite-vec storage + search over conversation history."""
from __future__ import annotations

import logging
import sqlite3
import struct
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sqlite_vec

from backend.app.services.embedding_service import get_embedding

logger = logging.getLogger(__name__)

_DB_PATH  = Path(__file__).resolve().parent.parent.parent.parent / "data" / "cmdctr.db"
_EMBED_DIM = 768


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _normalize(vec: list[float]) -> list[float]:
    """Normalize to unit length so L2 distance ≈ angular distance."""
    import math
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class SemanticMemoryService:
    def __init__(self) -> None:
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        conn = _connect()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_entries (
                    id          TEXT PRIMARY KEY,
                    session_id  TEXT NOT NULL,
                    user_msg    TEXT NOT NULL,
                    assistant_reply TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                )
            """)
            conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS semantic_vectors
                USING vec0(embedding float[{_EMBED_DIM}])
            """)
            conn.commit()
        except Exception as exc:
            logger.warning("semantic_memory table init failed: %s", exc)
        finally:
            conn.close()

    async def embed_and_store(
        self, session_id: str, user_msg: str, assistant_reply: str
    ) -> bool:
        """Embed a conversation turn and store it. Non-blocking fire-and-forget."""
        combined = f"User: {user_msg}\nAssistant: {assistant_reply}"
        vec = await get_embedding(combined)
        if not vec:
            return False
        vec = _normalize(vec)
        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO semantic_entries (id, session_id, user_msg, assistant_reply, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (entry_id, session_id, user_msg, assistant_reply, now),
            )
            # rowid in vec0 table links to semantic_entries by rowid
            row = conn.execute(
                "SELECT rowid FROM semantic_entries WHERE id = ?", (entry_id,)
            ).fetchone()
            if row:
                conn.execute(
                    "INSERT INTO semantic_vectors(rowid, embedding) VALUES (?, ?)",
                    (row["rowid"], _pack(vec)),
                )
            conn.commit()
            return True
        except Exception as exc:
            logger.warning("embed_and_store failed: %s", exc)
            return False
        finally:
            conn.close()

    async def search(
        self, query: str, top_k: int = 5, min_similarity: float = 0.55
    ) -> list[dict]:
        """
        Search conversation memory by semantic similarity.
        Returns list of {user_msg, assistant_reply, created_at, distance}.
        """
        vec = await get_embedding(query)
        if not vec:
            return []
        vec = _normalize(vec)
        conn = _connect()
        try:
            rows = conn.execute(
                f"""
                SELECT e.user_msg, e.assistant_reply, e.created_at, v.distance
                FROM semantic_vectors v
                JOIN semantic_entries e ON e.rowid = v.rowid
                WHERE v.embedding MATCH ?
                  AND k = ?
                ORDER BY v.distance
                """,
                (_pack(vec), top_k),
            ).fetchall()
            # With unit-normalized vectors: L2_dist^2 = 2 - 2*cos_sim
            # So cos_sim = 1 - L2_dist^2/2, and max_dist = sqrt(2*(1-min_sim))
            import math
            max_dist = math.sqrt(2.0 * (1.0 - min_similarity))
            results = []
            for row in rows:
                if row["distance"] <= max_dist:
                    # cos_sim = 1 - L2_dist^2 / 2  (for unit vectors)
                    cos_sim = max(0.0, 1.0 - (row["distance"] ** 2) / 2.0)
                    results.append({
                        "user_msg":        row["user_msg"],
                        "assistant_reply": row["assistant_reply"],
                        "created_at":      row["created_at"],
                        "distance":        round(row["distance"], 4),
                        "similarity":      round(cos_sim, 4),
                    })
            return results
        except Exception as exc:
            logger.warning("semantic search failed: %s", exc)
            return []
        finally:
            conn.close()

    async def index_existing(self, limit: int = 200) -> int:
        """Retroactively index recent messages from the messages table."""
        conn = _connect()
        indexed = 0
        try:
            # Get messages not yet in semantic_entries
            rows = conn.execute(
                """
                SELECT m.session_id, m.user_message, m.assistant_response, m.created_at
                FROM messages m
                WHERE m.user_message IS NOT NULL
                  AND m.assistant_response IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM semantic_entries se
                      WHERE se.user_msg = m.user_message
                        AND se.session_id = m.session_id
                  )
                ORDER BY m.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        except Exception:
            rows = []
        finally:
            conn.close()

        for row in rows:
            ok = await self.embed_and_store(
                row["session_id"] or "default",
                row["user_message"],
                row["assistant_response"],
            )
            if ok:
                indexed += 1
        logger.info("Retroactive index: embedded %d/%d turns", indexed, len(rows))
        return indexed
