"""Realtime protocol + session behaviour.

Driven through a scripted in-memory socket rather than a real WebSocket, so the
protocol loop, server-side authorization and hub fan-out are all exercised on
the test's own event loop.
"""

from __future__ import annotations

import asyncio

import pytest
from sillo.websockets import WebSocketDisconnect

from app.auth import mint_realtime_token
from domain.topics import Grant
from realtime.protocol import ClientFrame, ProtocolError
from realtime.session import RealtimeSession

# -- protocol unit ----------------------------------------------------------


def test_client_frame_parsing():
    f = ClientFrame.parse({"type": "subscribe", "topic": "tasks", "ref": "c1"})
    assert f.type == "subscribe" and f.topic == "tasks" and f.ref == "c1"
    with pytest.raises(ProtocolError):
        ClientFrame.parse({"type": "subscribe"})  # no topic
    with pytest.raises(ProtocolError):
        ClientFrame.parse({"type": "nope"})
    with pytest.raises(ProtocolError):
        ClientFrame.parse("not a dict")
    with pytest.raises(ProtocolError):
        ClientFrame.parse({"type": "ack"})  # no id


# -- scripted socket ------------------------------------------------------


class ScriptedSocket:
    def __init__(self, inbound: list[dict]):
        self._inbound = list(inbound)
        self.sent: list[dict] = []
        self.closed = False
        self.headers = {}
        self.query_params = {}

    async def accept(self):
        pass

    async def receive_json(self):
        if self._inbound:
            return self._inbound.pop(0)
        # let queued writes flush, then behave like a hung-up client
        await asyncio.sleep(0.05)
        raise WebSocketDisconnect(1000, "client gone")

    async def send_json(self, payload):
        self.sent.append(payload)

    async def close(self, code=1000, reason=""):
        self.closed = True


async def _run(socket: ScriptedSocket, grant: Grant):
    await RealtimeSession(socket, grant).run()


async def test_subscribe_receive_and_replay(client, producer_env):
    # publish two events on `tasks` before subscribing (for replay), one after.
    await client.post("/api/v1/events", headers=producer_env.auth,
                      json={"event": "task.created", "topic": "tasks", "data": {"task_id": "t1"}})
    await client.post("/api/v1/events", headers=producer_env.auth,
                      json={"event": "task.started", "topic": "tasks", "data": {"task_id": "t1"}})

    grant = Grant(environment="development")
    socket = ScriptedSocket([
        {"type": "subscribe", "topic": "tasks", "ref": "r1"},
        {"type": "replay", "topic": "tasks", "since": None},
    ])
    task = asyncio.ensure_future(_run(socket, grant))
    # give the session a moment to subscribe + process replay
    await asyncio.sleep(0.02)

    # a live event after subscription
    await client.post("/api/v1/events", headers=producer_env.auth,
                      json={"event": "task.completed", "topic": "tasks", "data": {"task_id": "t1"}})
    await asyncio.sleep(0.05)
    await task

    kinds = [f["type"] for f in socket.sent]
    assert kinds[0] == "welcome"
    assert "subscribed" in kinds
    assert "replay_done" in kinds
    events = [f for f in socket.sent if f["type"] == "event"]
    names = [e["event"] for e in events]
    # replay delivered the two prior events; live fan-out delivered the third
    assert "task.created" in names and "task.started" in names
    assert "task.completed" in names


async def test_private_topic_denied(client):
    grant = Grant(environment="development", user_id="42")
    socket = ScriptedSocket([{"type": "subscribe", "topic": "user:99"}])
    await _run(socket, grant)
    errors = [f for f in socket.sent if f["type"] == "error"]
    assert errors and errors[0]["code"] == "forbidden"


async def test_own_user_topic_allowed_and_delivers(client, producer_env):
    grant = Grant(environment="development", user_id="42")
    socket = ScriptedSocket([{"type": "subscribe", "topic": "user:42"}])
    task = asyncio.ensure_future(_run(socket, grant))
    await asyncio.sleep(0.02)
    await client.post("/api/v1/events", headers=producer_env.auth,
                      json={"event": "notification.created", "topic": "user:42",
                            "data": {"title": "hi", "recipient": "42"}})
    await asyncio.sleep(0.05)
    await task
    events = [f for f in socket.sent if f["type"] == "event"]
    assert any(e["event"] == "notification.created" for e in events)


async def test_ping_pong():
    grant = Grant(environment="development")
    socket = ScriptedSocket([{"type": "ping"}])
    await _run(socket, grant)
    assert any(f["type"] == "pong" for f in socket.sent)


async def test_connection_row_lifecycle(client):
    from database.models import Connection

    grant = Grant(environment="development", user_id="7")
    socket = ScriptedSocket([{"type": "subscribe", "topic": "public-topic"}])
    await _run(socket, grant)
    rows = await Connection.filter(environment="development").all()
    assert len(rows) == 1
    assert rows[0].status == "closed"
    assert rows[0].subscriptions == ["public-topic"]


def test_realtime_token_round_trip():
    token, ttl = mint_realtime_token(environment="staging", user_id="9", operator=False)
    from app.auth import grant_from_realtime_token

    grant = grant_from_realtime_token(token)
    assert grant.environment == "staging"
    assert grant.user_id == "9"
    assert ttl > 0
