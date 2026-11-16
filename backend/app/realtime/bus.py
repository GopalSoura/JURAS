import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from fastapi import WebSocket

from app.realtime.events import make_event

logger = logging.getLogger("juras.realtime")

EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class RealtimeBus:
    def __init__(self) -> None:
        self.live_connections: set[WebSocket] = set()
        self._adapter_handler: EventHandler | None = None
        self._lock = asyncio.Lock()

    def set_adapter_handler(self, handler: EventHandler) -> None:
        self._adapter_handler = handler

    async def connect(self, ws: WebSocket, group: str) -> None:
        await ws.accept()
        async with self._lock:
            self.live_connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.live_connections.discard(ws)

    def has_listeners(self) -> bool:
        return len(self.live_connections) > 0

    async def broadcast_event(self, name: str, data: dict[str, Any], simulation: bool = True) -> None:
        payload = make_event(name, data, simulation)
        dead: list[WebSocket] = []
        for ws in list(self.live_connections):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
        if self._adapter_handler is not None:
            try:
                await self._adapter_handler(name, data)
            except Exception:
                logger.exception("adapter handler failed for event %s", name)

    async def send_raw(self, ws: WebSocket, payload: dict[str, Any]) -> None:
        await ws.send_json(payload)


bus = RealtimeBus()
