"""The event bus — cross-instance fanout and coordination.

The bus carries an already-serialised event (the wire dict a consumer receives)
from the instance that ingested it to *every* BEACN instance, each of which then
delivers locally through its `Hub` (see `realtime/hub.py`). This is what makes a
producer on instance A reach a consumer on instance C.

Two implementations, one interface:

* `InProcessBus` — no dependencies, single process. The default; the whole test
  suite runs on it.
* `RedisBus` — Redis pub/sub, one channel per environment. Publishing also
  delivers locally straight away, so the publishing instance never waits for the
  round trip; the subscriber loop de-dupes by event id so the local copy is not
  delivered twice.

The bus is **not** durable. A consumer that needs gap-free delivery replays from
the database (`services/replay.py`). Redis being unavailable degrades the bus to
local-only fanout and never blocks ingestion.
"""

from __future__ import annotations

import abc
import asyncio
import contextlib
import json
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable

logger = logging.getLogger("beacn.bus")

#: called with (topic, wire_event_dict); registered by the realtime layer
LocalDelivery = Callable[[str, dict], Awaitable[None]]

RECONNECT_DELAY = 2.0
POLL_INTERVAL = 0.2


class EventBus(abc.ABC):
    def __init__(self) -> None:
        self._local: LocalDelivery | None = None
        self._running = False

    def on_local_delivery(self, fn: LocalDelivery) -> None:
        self._local = fn

    async def _deliver_local(self, topic: str, wire: dict) -> None:
        if self._local is None:
            return
        try:
            await self._local(topic, wire)
        except Exception:  # noqa: BLE001 — one bad delivery must not kill the loop
            logger.exception("local delivery failed for topic %s", topic)

    @property
    def running(self) -> bool:
        return self._running

    @abc.abstractmethod
    async def start(self) -> None: ...

    @abc.abstractmethod
    async def stop(self) -> None: ...

    @abc.abstractmethod
    async def publish(self, environment: str, topic: str, wire: dict) -> None: ...

    @abc.abstractmethod
    async def health(self) -> dict: ...


class InProcessBus(EventBus):
    name = "memory"

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def publish(self, environment: str, topic: str, wire: dict) -> None:
        await self._deliver_local(topic, wire)

    async def health(self) -> dict:
        return {"backend": "memory", "ok": True, "detail": "single process"}


class _SeenSet:
    """Bounded FIFO of recently-seen ids for de-dup on the publishing instance."""

    def __init__(self, capacity: int = 20000) -> None:
        self._cap = capacity
        self._d: OrderedDict[str, None] = OrderedDict()

    def add(self, key: str) -> bool:
        """True if newly added, False if it was already present."""
        if key in self._d:
            return False
        self._d[key] = None
        if len(self._d) > self._cap:
            self._d.popitem(last=False)
        return True


class RedisBus(EventBus):
    name = "redis"

    def __init__(self, url: str, *, namespace: str = "beacn") -> None:
        super().__init__()
        self._url = url
        self._ns = namespace
        self._client = None
        self._pubsub = None
        self._task: asyncio.Task | None = None
        self._channels: set[str] = set()
        self._seen = _SeenSet()
        self._lock = asyncio.Lock()
        self._degraded = False

    def _channel(self, environment: str) -> str:
        return f"{self._ns}:evt:{environment}"

    def _connect(self):
        if self._client is None:
            try:
                import redis.asyncio as aioredis
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "BEACN_BUS=redis needs the 'redis' package (pip install 'beacn[redis]')"
                ) from exc
            self._client = aioredis.from_url(self._url)
        return self._client

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        try:
            self._connect()
            self._pubsub = self._client.pubsub()
            self._task = asyncio.ensure_future(self._listen())
        except Exception as exc:  # noqa: BLE001
            logger.warning("RedisBus start failed, degraded to local-only: %s", exc)
            self._degraded = True

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.aclose()
            self._pubsub = None
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.aclose()
            self._client = None

    async def _ensure_subscribed(self, environment: str) -> None:
        channel = self._channel(environment)
        if channel in self._channels or self._pubsub is None:
            return
        async with self._lock:
            with contextlib.suppress(Exception):
                await self._pubsub.subscribe(channel)
                self._channels.add(channel)

    async def publish(self, environment: str, topic: str, wire: dict) -> None:
        # Local first — never blocked by Redis.
        self._seen.add(wire.get("id", ""))
        await self._deliver_local(topic, wire)
        if self._degraded or self._client is None:
            return
        await self._ensure_subscribed(environment)
        payload = json.dumps({"topic": topic, "event": wire}, separators=(",", ":"))
        try:
            await self._client.publish(self._channel(environment), payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RedisBus publish failed (local delivery already done): %s", exc)
            self._degraded = True

    async def _listen(self) -> None:
        while self._running:
            try:
                if self._pubsub is None or not self._channels:
                    await asyncio.sleep(POLL_INTERVAL)
                    continue
                async with self._lock:
                    message = await self._pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=POLL_INTERVAL
                    )
                if not message or message.get("type") != "message":
                    continue
                raw = message.get("data")
                frame = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                wire = frame["event"]
                if not self._seen.add(wire.get("id", "")):
                    continue  # our own publish, already delivered locally
                self._degraded = False
                await self._deliver_local(frame["topic"], wire)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("RedisBus listener error, reconnecting: %s", exc)
                self._degraded = True
                await asyncio.sleep(RECONNECT_DELAY)
                with contextlib.suppress(Exception):
                    self._connect()
                    self._pubsub = self._client.pubsub()
                    if self._channels:
                        await self._pubsub.subscribe(*self._channels)
                    self._degraded = False

    async def health(self) -> dict:
        ok = False
        detail = "not connected"
        try:
            if self._client is not None:
                ok = bool(await self._client.ping())
                detail = "degraded (local-only fanout)" if self._degraded else "connected"
        except Exception as exc:  # noqa: BLE001
            detail = f"unreachable: {exc}"
        return {
            "backend": "redis",
            "ok": ok,
            "degraded": self._degraded,
            "channels": sorted(self._channels),
            "detail": detail,
        }


def build_bus(backend: str, *, redis_url: str, namespace: str) -> EventBus:
    if backend == "redis":
        return RedisBus(redis_url, namespace=namespace)
    return InProcessBus()
