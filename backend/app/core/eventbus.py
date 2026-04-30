"""Process-local async event bus for real-time SSE streaming.

Producers call `publish(bot_id, event_type, data)`.
SSE consumers call `subscribe(bot_id)` to get an async generator of events.

All data stays in-memory; nothing is persisted here.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator

log = logging.getLogger("eventbus")


@dataclass
class _Event:
    bot_id: str
    event_type: str  # "order", "fill", "position", "state", "alert"
    data: dict


class EventBus:
    def __init__(self) -> None:
        # bot_id -> list of subscriber queues
        self._subscribers: dict[str, list[asyncio.Queue[_Event]]] = {}

    def publish(self, bot_id: str, event_type: str, data: dict) -> None:
        """Fire-and-forget publish. Non-blocking."""
        event = _Event(bot_id=bot_id, event_type=event_type, data=data)
        queues = self._subscribers.get(bot_id, [])
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest to prevent memory buildup on slow consumers
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:  # noqa: BLE001
                    pass
        # Also publish to wildcard subscribers (listening to all bots)
        for q in self._subscribers.get("*", []):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:  # noqa: BLE001
                    pass

    async def subscribe(self, bot_id: str) -> AsyncGenerator[tuple[str, dict], None]:
        """Yields (event_type, data) tuples as they arrive."""
        q: asyncio.Queue[_Event] = asyncio.Queue(maxsize=256)
        subs = self._subscribers.setdefault(bot_id, [])
        subs.append(q)
        try:
            while True:
                event = await q.get()
                yield event.event_type, event.data
        finally:
            subs.remove(q)
            if not subs:
                self._subscribers.pop(bot_id, None)


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
