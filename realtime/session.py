"""A single realtime connection.

`RealtimeSession` wraps a `WebSocketContext`, owns one `sillo_wire.Peer` (bounded
queue + writer task), runs the protocol loop, and guarantees the peer leaves
every topic and the `Connection` row is closed when the socket ends — including
when a handler raises.

Authorization is enforced here on every `subscribe` and `replay` against the
connection's `Grant` (`domain.topics.authorize_subscription`). The client's
opinion is never consulted.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime

from sillo_wire import Overflow, Peer
from sillo_wire.envelope import DeliveryReport

from app.config import config
from domain.ids import CONNECTION, new_id
from domain.topics import Grant, TopicSpec, authorize_subscription

from . import protocol as P

logger = logging.getLogger("beacn.realtime")

_OVERFLOW = {
    "drop_oldest": Overflow.DROP_OLDEST,
    "drop_newest": Overflow.DROP_NEWEST,
    "close": Overflow.CLOSE,
}


class RealtimeSession:
    def __init__(self, socket, grant: Grant, *, transport: str = "ws", client: str | None = None, ip: str | None = None):
        self.socket = socket
        self.grant = grant
        self.transport = transport
        self.client = client
        self.ip = ip
        self.connection_id = new_id(CONNECTION)
        self.topics: set[str] = set()
        self.peer = Peer(
            socket,
            identity=grant.user_id or self.connection_id,
            capacity=config.per_connection_queue,
            overflow=_OVERFLOW.get("drop_oldest", Overflow.DROP_OLDEST),
        )
        self.events_sent = 0
        self.events_dropped = 0
        self.opened_at = time.monotonic()
        self._row = None
        self._closing = False

    # -- lifecycle ----------------------------------------------------

    async def run(self) -> None:
        from realtime import get_realtime

        rt = get_realtime()
        await self.socket.accept()
        self.peer.start()
        rt.register(self)
        await self._open_row(rt.instance_id)
        await self.socket.send_json(P.welcome(self.connection_id, config.heartbeat_ms))

        deadline = time.monotonic() + config.connection_max_seconds
        try:
            while True:
                if time.monotonic() > deadline:
                    await self.socket.send_json(
                        P.error_frame("expired", "connection lifetime reached")
                    )
                    break
                try:
                    raw = await asyncio.wait_for(
                        self.socket.receive_json(), timeout=config.heartbeat_ms / 1000 * 3
                    )
                except TimeoutError:
                    # No client traffic for 3 heartbeats — assume it is gone.
                    break
                await self._handle(raw)
        except Exception as exc:  # noqa: BLE001 — disconnect arrives as an exception
            if "disconnect" not in exc.__class__.__name__.lower():
                logger.debug("session %s ended: %s", self.connection_id, exc)
        finally:
            await self.shutdown(1000, "closed")

    async def shutdown(self, code: int, reason: str) -> None:
        if self._closing:
            return
        self._closing = True
        from realtime import get_realtime

        rt = get_realtime()
        for topic in list(self.topics):
            with contextlib.suppress(Exception):
                await rt.hub.leave(self.peer, topic)
        self.topics.clear()
        with contextlib.suppress(Exception):
            await self.peer.close()
        rt.unregister(self.connection_id)
        await self._close_row(code, reason)

    # -- frame handling ---------------------------------------------

    async def _handle(self, raw) -> None:
        from realtime import get_realtime

        rt = get_realtime()
        try:
            frame = P.ClientFrame.parse(raw)
        except P.ProtocolError as exc:
            await self.socket.send_json(P.error_frame(exc.code, exc.message))
            return

        if frame.type == "ping":
            await self.socket.send_json(P.pong())
            return

        if frame.type == "subscribe":
            if not await self._authorize(frame.topic):
                await self.socket.send_json(
                    P.error_frame("forbidden", f"not allowed on topic {frame.topic}",
                                  topic=frame.topic, ref=frame.ref)
                )
                return
            await rt.hub.join(self.peer, frame.topic)
            self.topics.add(frame.topic)
            await self.socket.send_json(P.subscribed(frame.topic, frame.ref))
            await self._save_subs()
            return

        if frame.type == "unsubscribe":
            await rt.hub.leave(self.peer, frame.topic)
            self.topics.discard(frame.topic)
            await self.socket.send_json(P.unsubscribed(frame.topic))
            await self._save_subs()
            return

        if frame.type == "replay":
            await self._do_replay(frame)
            return

        if frame.type == "ack":
            await self._record_ack(frame.id)
            return

    async def _do_replay(self, frame: P.ClientFrame) -> None:
        from app.services import replay as replay_service

        if not await self._authorize(frame.topic):
            await self.socket.send_json(
                P.error_frame("forbidden", f"not allowed on topic {frame.topic}", topic=frame.topic)
            )
            return
        result = await replay_service.replay(
            environment=self.grant.environment, topic=frame.topic, since=frame.since
        )
        for wire in result.events:
            await self.socket.send_json(P.event_frame(wire))
            self.events_sent += 1
        await self.socket.send_json(
            P.replay_done(frame.topic, result.count, result.truncated, result.next_since)
        )

    async def _authorize(self, topic: str) -> bool:
        from database.models import Topic

        spec = None
        row = await Topic.get_or_none(environment=self.grant.environment, name=topic)
        if row is not None:
            spec = TopicSpec(row.name, row.visibility, row.environment)
        return bool(authorize_subscription(topic, self.grant, spec))

    # -- delivery bookkeeping -------------------------------------

    def note_delivery(self, report: DeliveryReport) -> None:
        # coarse per-session counters; exact per-event rows are sampled elsewhere
        self.events_sent += 1
        if report.dropped:
            self.events_dropped += 1

    async def _record_ack(self, event_id: str) -> None:
        from database.models import DeliveryAttempt

        with contextlib.suppress(Exception):
            await DeliveryAttempt.filter(
                connection_id=self.connection_id, event_id=event_id
            ).update(acknowledged=True, acknowledged_at=datetime.now(UTC))

    # -- Connection row ------------------------------------------

    async def _open_row(self, instance_id: str) -> None:
        from database.models import Connection

        with contextlib.suppress(Exception):
            self._row = await Connection.create(
                id=self.connection_id,
                environment=self.grant.environment,
                transport=self.transport,
                instance=instance_id,
                principal_kind="token",
                principal_id=self.grant.user_id,
                user_id=self.grant.user_id,
                organization_id=self.grant.organization_id,
                client=self.client,
                ip=self.ip,
                subscriptions=[],
                status="open",
            )

    async def _save_subs(self) -> None:
        from database.models import Connection

        with contextlib.suppress(Exception):
            await Connection.filter(id=self.connection_id).update(
                subscriptions=sorted(self.topics),
                last_heartbeat_at=datetime.now(UTC),
            )

    async def _close_row(self, code: int, reason: str) -> None:
        from database.models import Connection

        with contextlib.suppress(Exception):
            await Connection.filter(id=self.connection_id).update(
                status="closed",
                close_code=code,
                close_reason=reason[:200],
                disconnected_at=datetime.now(UTC),
                events_sent=self.events_sent,
                events_dropped=self.events_dropped,
            )
