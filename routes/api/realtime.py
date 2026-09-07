"""Realtime transports: WebSocket (primary) and SSE (read-only fallback).

Both authenticate from a `token` query parameter — a realtime JWT minted by
`POST /api/v1/realtime/tokens`, or a raw API key for a service consumer. Both
authorize every topic server-side against the connection's `Grant`.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

from sillo.core.http import HttpContext
from sillo.core.routing import Route
from sillo.responses import sse
from sillo.websockets import WebSocketContext
from sillo.websockets.status import WS_1008_POLICY_VIOLATION

from app.auth import grant_from_realtime_credential
from app.config import config
from domain.errors import BeacnError
from domain.ids import CONNECTION, new_id
from realtime import get_realtime
from realtime.session import RealtimeSession


async def realtime_ws(socket: WebSocketContext) -> None:
    token = socket.query_params.get("token") or ""
    if not token:
        await socket.accept()
        await socket.send_json({"type": "error", "code": "unauthenticated", "message": "token required"})
        await socket.close(code=WS_1008_POLICY_VIOLATION, reason="token required")
        return
    try:
        grant = await grant_from_realtime_credential(token)
    except BeacnError as exc:
        await socket.accept()
        await socket.send_json({"type": "error", "code": exc.code, "message": exc.message})
        await socket.close(code=WS_1008_POLICY_VIOLATION, reason=exc.code)
        return

    session = RealtimeSession(
        socket,
        grant,
        transport="ws",
        client=socket.headers.get("user-agent"),
        ip=(socket.headers.get("x-forwarded-for") or "").split(",")[0].strip() or None,
    )
    await session.run()


class _SseSink:
    """A minimal socket-like object so an SSE stream can reuse the wire `Peer`.

    `Peer` (encoding=JSON) writes with `send_json`; the other methods are here
    so it satisfies the same surface a real `WebSocketContext` exposes.
    """

    def __init__(self) -> None:
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=config.per_connection_queue)
        self.closed = False

    async def accept(self) -> None:  # pragma: no cover - never called for SSE
        pass

    async def send_json(self, payload: Any) -> None:
        if not self.closed:
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait(payload)

    async def send_text(self, payload: str) -> None:
        await self.send_json(payload)

    async def send(self, payload: Any) -> None:
        await self.send_json(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True
        with contextlib.suppress(asyncio.QueueFull):
            self.queue.put_nowait(None)


async def realtime_sse(ctx: HttpContext) -> Any:
    token = ctx.query_params.get("token") or ""
    try:
        grant = await grant_from_realtime_credential(token)
    except BeacnError as exc:
        from sillo.responses import json

        return json({"error": exc.to_dict()}, status_code=exc.status)

    from sillo_wire import Peer

    from database.models import Connection, Topic
    from domain.topics import TopicSpec, authorize_subscription

    rt = get_realtime()
    requested = [t.strip() for t in (ctx.query_params.get("topics") or "").split(",") if t.strip()]
    allowed: list[str] = []
    for topic in requested:
        spec = None
        row = await Topic.get_or_none(environment=grant.environment, name=topic)
        if row is not None:
            spec = TopicSpec(row.name, row.visibility, row.environment)
        if authorize_subscription(topic, grant, spec):
            allowed.append(topic)

    sink = _SseSink()
    peer = Peer(sink, identity=grant.user_id, capacity=config.per_connection_queue)
    peer.start()
    connection_id = new_id(CONNECTION)
    for topic in allowed:
        await rt.hub.join(peer, topic)

    with contextlib.suppress(Exception):
        await Connection.create(
            id=connection_id,
            environment=grant.environment,
            transport="sse",
            instance=rt.instance_id,
            user_id=grant.user_id,
            organization_id=grant.organization_id,
            client=ctx.headers.get("user-agent"),
            subscriptions=allowed,
            status="open",
        )

    async def source():
        yield {"type": "welcome", "connection_id": connection_id, "topics": allowed}
        try:
            while True:
                item = await sink.queue.get()
                if item is None:
                    break
                yield {"type": "event", **item} if isinstance(item, dict) else item
        finally:
            for topic in allowed:
                with contextlib.suppress(Exception):
                    await rt.hub.leave(peer, topic)
            await peer.close()
            with contextlib.suppress(Exception):
                await Connection.filter(id=connection_id).update(
                    status="closed", disconnected_at=datetime.now(UTC)
                )

    return sse(source(), keepalive=config.heartbeat_ms / 1000)


sse_route = Route("/api/v1/sse", handler=realtime_sse, methods=["GET"], name="v1.sse")


def register(app) -> None:
    from sillo.core.routing import WebsocketRoute

    app.add_ws_route(WebsocketRoute("/realtime", realtime_ws))
    app.add_route(sse_route)
