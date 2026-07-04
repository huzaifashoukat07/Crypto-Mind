import asyncio
import logging

from fastapi import WebSocket

from .schemas import WsEvent

logger = logging.getLogger("ws_manager")


class WsManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._connections.discard(ws)

    def broadcast(self, event: WsEvent):
        asyncio.create_task(self._broadcast(event))

    async def _broadcast(self, event: WsEvent):
        payload = event.model_dump_json()
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_text(payload)
            except Exception:  # noqa: BLE001
                await self.disconnect(ws)


ws_manager = WsManager()
