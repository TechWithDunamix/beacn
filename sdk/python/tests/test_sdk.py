"""Python SDK — sync + async, publishing, history, replay, retries, errors, SSE."""

from __future__ import annotations

import threading
import time

import pytest
from beacn import (
    AuthError,
    Beacn,
    Event,
    RetryPolicy,
    ValidationError,
)


def test_publish_returns_id(sdk):
    result = sdk.publish("payment.completed", topic="payments", data={"amount": 100})
    assert result.accepted == 1
    assert result.id.startswith("evt_")


def test_publish_idempotent(sdk):
    r1 = sdk.publish("order.created", topic="orders", idempotency_key="sdk-k1")
    r2 = sdk.publish("order.created", topic="orders", idempotency_key="sdk-k1")
    assert r1.id == r2.id
    assert r2.deduplicated == 1


def test_batch(sdk):
    r = sdk.publish_batch([
        {"event": "a.one", "topic": "batch"},
        {"event": "a.two", "topic": "batch"},
    ])
    assert r.accepted == 2


def test_history_pagination(sdk):
    for i in range(15):
        sdk.publish("hist.item", topic="hist", data={"i": i})
    seen = list(sdk.iter_events(topic="hist", limit=5))
    assert len({e.id for e in seen}) == 15
    assert all(isinstance(e, Event) for e in seen)


def test_get_event_and_replay(sdk):
    r = sdk.publish("rp.item", topic="rp1")
    fetched = sdk.get_event(r.id)
    assert fetched.id == r.id
    out = sdk.replay("rp1", since=None)
    assert any(e["id"] == r.id for e in out["events"])


def test_auth_error(live_server):
    bad = Beacn(url=live_server["http"], api_key="bk_deadbeef_nope")
    with pytest.raises(AuthError):
        bad.publish("a.b")


def test_validation_error(sdk):
    with pytest.raises(ValidationError):
        sdk.publish("not a valid name")


def test_whoami(sdk):
    who = sdk.whoami()
    assert who["environment"] == "development"


def test_retry_policy_backoff_is_bounded():
    p = RetryPolicy(base_delay=1, multiplier=2, max_delay=10, jitter=False)
    assert p.delay_for(1) == 1
    assert p.delay_for(3) == 4
    assert p.delay_for(10) == 10  # capped
    assert p.should_retry(1, 503, None, True) is True
    assert p.should_retry(1, 503, None, False) is False  # non-idempotent
    assert p.should_retry(1, 400, None, True) is False


def test_retry_on_rate_limit(live_server, monkeypatch):
    """A 429 with Retry-After is retried and eventually succeeds."""
    from app.services.ratelimit import limiter

    # squeeze the bucket so the first call 429s, then refills fast
    limiter._buckets.clear()
    limiter.rate = 50.0
    limiter.burst = 1.0
    client = Beacn(
        url=live_server["http"], api_key=live_server["api_key"],
        retry=RetryPolicy(max_attempts=5, base_delay=0.05),
    )
    client.publish("rl.one", topic="rl", idempotency_key="rl-a")  # consume the token
    # this one should 429 then retry-succeed within a couple hundred ms
    r = client.publish("rl.two", topic="rl", idempotency_key="rl-b")
    assert r.accepted == 1
    from app.config import config

    limiter.rate = config.ingest_rate_per_minute / 60.0
    limiter.burst = float(config.ingest_burst)
    limiter._buckets.clear()


def test_sse_subscribe_delivers_live_events(sdk, live_server):
    received = []

    def consume():
        for event in sdk.subscribe("sse-topic"):
            received.append(event)
            if len(received) >= 2:
                return

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    time.sleep(1.0)  # let the SSE stream connect + subscribe
    sdk.publish("sse.one", topic="sse-topic")
    sdk.publish("sse.two", topic="sse-topic")
    t.join(timeout=8)
    assert len(received) >= 2
    assert {e.event for e in received} == {"sse.one", "sse.two"}


@pytest.mark.asyncio
async def test_async_client(live_server):
    from beacn import AsyncBeacn

    async with AsyncBeacn(url=live_server["http"], api_key=live_server["api_key"]) as client:
        r = await client.publish("async.evt", topic="async-topic", data={"ok": True})
        assert r.accepted == 1
        events, page = await client.history(topic="async-topic")
        assert any(e.event == "async.evt" for e in events)
        who = await client.whoami()
        assert who["environment"] == "development"
