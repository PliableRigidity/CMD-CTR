from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone

from fastapi import WebSocket

from backend.app.models.assistant import CommandLogEntry


class EventService:
    def __init__(self) -> None:
        self._history: deque[CommandLogEntry] = deque(maxlen=200)
        self._connections: set[WebSocket] = set()

    def history(self) -> list[CommandLogEntry]:
        return list(self._history)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.add(websocket)
        for item in self._history:
            await websocket.send_json(item.model_dump())

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def emit(self, title: str, detail: str, level: str = "info") -> CommandLogEntry:
        entry = CommandLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            title=title,
            detail=detail,
            level=level,
        )
        self._history.append(entry)
        stale: list[WebSocket] = []
        for connection in list(self._connections):
            try:
                await connection.send_json(entry.model_dump())
            except Exception:
                stale.append(connection)
        for connection in stale:
            self._connections.discard(connection)
        return entry

    def emit_nowait(self, title: str, detail: str, level: str = "info") -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.emit(title=title, detail=detail, level=level))
