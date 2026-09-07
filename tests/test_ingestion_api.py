"""POST /api/v1/events — auth, validation, batching, idempotency, isolation."""

from __future__ import annotations

import pytest

from tests.helpers import make_api_key

pytestmark = pytest.mark.asyncio


async def test_publish_single_event(client, producer_env):
    r = await client.post(
        "/api/v1/events",
        headers=producer_env.auth,
        json={"event": "payment.completed", "topic": "payments", "data": {"amount": 500}},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["accepted"] == 1
    assert body["events"][0]["id"].startswith("evt_")
    assert body["events"][0]["topic"] == "payments"


async def test_publish_batch(client, producer_env):
    r = await client.post(
        "/api/v1/events",
        headers=producer_env.auth,
        json={"events": [{"event": "a.one"}, {"event": "a.two"}, {"event": "a.three"}]},
    )
    assert r.status_code == 201
    assert r.json()["accepted"] == 3


async def test_partial_batch_reports_rejections(client, producer_env):
    r = await client.post(
        "/api/v1/events",
        headers=producer_env.auth,
        json={"events": [{"event": "ok.one"}, {"event": "bad name"}, {"event": "ok.two"}]},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["accepted"] == 2
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["index"] == 1


async def test_idempotency_returns_same_id(client, producer_env):
    payload = {"event": "order.created", "topic": "orders", "idempotency_key": "abc-123"}
    first = await client.post("/api/v1/events", headers=producer_env.auth, json=payload)
    second = await client.post("/api/v1/events", headers=producer_env.auth, json=payload)
    assert first.status_code == 201
    assert second.status_code == 200  # all deduplicated
    assert second.json()["deduplicated"] == 1
    assert first.json()["events"][0]["id"] == second.json()["events"][0]["id"]


async def test_missing_key_rejected(client):
    r = await client.post("/api/v1/events", json={"event": "a.b"})
    assert r.status_code == 401


async def test_wrong_scope_rejected(client):
    bundle = await make_api_key(scopes="events:read")  # no publish
    r = await client.post("/api/v1/events", headers=bundle.auth, json={"event": "a.b"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"


async def test_revoked_key_rejected(client, producer_env):
    await producer_env.api_key.revoke("test")
    r = await client.post("/api/v1/events", headers=producer_env.auth, json={"event": "a.b"})
    assert r.status_code == 401


async def test_environment_isolation_on_read(client):
    dev = await make_api_key(environment="development", scopes="events:publish events:read")
    prod = await make_api_key(environment="production", scopes="events:publish events:read")
    await client.post("/api/v1/events", headers=dev.auth, json={"event": "dev.only", "topic": "t"})
    await client.post("/api/v1/events", headers=prod.auth, json={"event": "prod.only", "topic": "t"})

    r_dev = await client.get("/api/v1/events", headers=dev.auth)
    r_prod = await client.get("/api/v1/events", headers=prod.auth)
    dev_names = {e["event"] for e in r_dev.json()["events"]}
    prod_names = {e["event"] for e in r_prod.json()["events"]}
    assert "dev.only" in dev_names and "prod.only" not in dev_names
    assert "prod.only" in prod_names and "dev.only" not in prod_names


async def test_rate_limit_returns_429(client):
    bundle = await make_api_key(scopes="events:publish")
    from app.services.ratelimit import limiter

    limiter.rate = 0.0
    limiter._buckets.clear()
    limiter.burst = 2
    ok1 = await client.post("/api/v1/events", headers=bundle.auth, json={"event": "a.b"})
    ok2 = await client.post("/api/v1/events", headers=bundle.auth, json={"event": "a.c"})
    blocked = await client.post("/api/v1/events", headers=bundle.auth, json={"event": "a.d"})
    assert ok1.status_code == 201 and ok2.status_code == 201
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    # restore
    from app.config import config

    limiter.rate = config.ingest_rate_per_minute / 60.0
    limiter.burst = float(config.ingest_burst)


async def test_whoami(client, producer_env):
    r = await client.get("/api/v1/whoami", headers=producer_env.auth)
    assert r.status_code == 200
    assert r.json()["environment"] == "development"
    assert "events:publish" in r.json()["key"]["scopes"]
