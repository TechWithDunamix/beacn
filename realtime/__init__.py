"""Realtime delivery layer.

One `Realtime` per process, reachable through `get_realtime()`. It owns:

* the **event bus** (`bus.EventBus`) — cross-instance fanout;
* a **`sillo_wire.Hub`** — local, non-blocking fanout to this process's sockets,
  with a bounded queue and a writer task per connection;
* the **session registry** — the live `RealtimeSession` objects, so the control
  plane can list connections and ask for one to be terminated.

Ingestion calls `Realtime.publish(...)`. Everything downstream — this process's
sockets and every other instance's — is the bus's and the hub's job.
"""

from __future__ import annotations

import os
import socket as _socket
import time
from typing import TYPE_CHECKING

from sillo_wire import Hub

from app.config import config

from .bus import EventBus, build_bus

if TYPE_CHECKING:
    from .session import RealtimeSession

_INSTANCE_ID = f"{_socket.gethostname()}:{os.getpid()}"


class Realtime:
    def __init__(self, bus: EventBus) -> None:
        self.bus = bus
        self.hub = Hub()
        self.instance_id = _INSTANCE_ID
        self.sessions: dict[str, RealtimeSession] = {}
        self.started_at = time.time()
        # cheap process counters exported at /metrics
        self.events_delivered = 0
        self.events_dropped = 0
        self.frames_sent = 0
        bus.on_local_delivery(self._deliver_local)

    async def _deliver_local(self, topic: str, wire: dict) -> None:
        # Wrap the bare event dict as an `event` frame for consumers. Idempotent
        # if it is already framed (bus round-trip from another instance).
        frame = wire if wire.get("type") == "event" else {"type": "event", **wire}
        report = await self.hub.broadcast(topic, frame, retain=False)
        self.events_delivered += report.delivered
        self.events_dropped += report.dropped
        self.frames_sent += report.delivered
        # fan the delivery outcome back to the originating session bookkeeping
        for session in list(self.sessions.values()):
            if topic in session.topics:
                session.note_delivery(report)

    async def publish(self, environment: str, topic: str, wire: dict) -> None:
        await self.bus.publish(environment, topic, wire)

    # -- registry -------------------------------------------------------

    def register(self, session: RealtimeSession) -> None:
        self.sessions[session.connection_id] = session

    def unregister(self, connection_id: str) -> None:
        self.sessions.pop(connection_id, None)

    def local_connection_count(self) -> int:
        return len(self.sessions)

    def local_subscription_count(self) -> int:
        return sum(len(s.topics) for s in self.sessions.values())

    async def start(self) -> None:
        await self.bus.start()

    async def stop(self) -> None:
        for session in list(self.sessions.values()):
            await session.shutdown(1001, "server shutting down")
        await self.hub.close()
        await self.bus.stop()

    async def health(self) -> dict:
        return await self.bus.health()


_realtime: Realtime | None = None


def get_realtime() -> Realtime:
    global _realtime
    if _realtime is None:
        _realtime = Realtime(
            build_bus(
                config.bus_backend,
                redis_url=config.redis_url,
                namespace=config.redis_namespace,
            )
        )
    return _realtime


def reset_realtime() -> None:
    """Test hook: drop the process singleton so the next `get_realtime()` is fresh."""
    global _realtime
    _realtime = None


def setup(app) -> Realtime:
    rt = get_realtime()
    app.state["realtime"] = rt
    app.on_startup(rt.start)
    app.on_shutdown(rt.stop)
    return rt
