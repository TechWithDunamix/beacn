"""Event bus fan-out — in-process always, Redis when a server is reachable."""

from __future__ import annotations

import asyncio
import os

import pytest

from realtime.bus import InProcessBus, RedisBus, build_bus

pytestmark = pytest.mark.asyncio


async def test_in_process_bus_delivers_locally():
    bus = InProcessBus()
    got: list = []

    async def local(topic, wire):
        got.append((topic, wire["id"]))

    bus.on_local_delivery(local)
    await bus.start()
    await bus.publish("development", "t", {"id": "evt_1"})
    assert got == [("t", "evt_1")]
    h = await bus.health()
    assert h["ok"] and h["backend"] == "memory"
    await bus.stop()


async def test_build_bus_selects_backend():
    assert isinstance(build_bus("memory", redis_url="", namespace="x"), InProcessBus)
    assert isinstance(build_bus("redis", redis_url="redis://localhost:6379/0", namespace="x"), RedisBus)


def _redis_url() -> str | None:
    return os.getenv("REDIS_TEST_URL")


@pytest.mark.skipif(not _redis_url(), reason="no REDIS_TEST_URL")
async def test_redis_bus_cross_instance():
    url = _redis_url()
    a = RedisBus(url, namespace="beacn-test")
    b = RedisBus(url, namespace="beacn-test")
    got_b: list = []

    async def local_a(topic, wire):
        pass

    async def local_b(topic, wire):
        got_b.append(wire["id"])

    a.on_local_delivery(local_a)
    b.on_local_delivery(local_b)
    await a.start()
    await b.start()
    # b must be subscribed before a publishes
    await b._ensure_subscribed("development")
    await asyncio.sleep(0.2)
    await a.publish("development", "t", {"id": "evt_x"})
    await asyncio.sleep(0.5)
    assert "evt_x" in got_b
    await a.stop()
    await b.stop()


async def test_redis_bus_degrades_without_server_and_still_delivers_local():
    bus = RedisBus("redis://127.0.0.1:6399/0", namespace="beacn-test")  # nothing there
    got: list = []

    async def local(topic, wire):
        got.append(wire["id"])

    bus.on_local_delivery(local)
    await bus.start()
    await bus.publish("development", "t", {"id": "evt_local"})
    assert got == ["evt_local"]  # local delivery unaffected by Redis being down
    await bus.stop()
