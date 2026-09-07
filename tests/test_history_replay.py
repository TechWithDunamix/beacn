"""Event history pagination and retention-aware replay."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _publish(client, auth, n, topic="stream", event="thing.happened"):
    for i in range(n):
        await client.post("/api/v1/events", headers=auth,
                          json={"event": event, "topic": topic, "data": {"i": i}})


async def test_cursor_pagination_is_stable_and_complete(client, producer_env):
    await _publish(client, producer_env.auth, 25)
    seen = []
    cursor = None
    for _ in range(10):
        url = "/api/v1/events?topic=stream&limit=10"
        if cursor:
            url += f"&cursor={cursor}"
        r = await client.get(url, headers=producer_env.auth)
        page = r.json()
        seen += [e["id"] for e in page["events"]]
        cursor = page["page"]["next_cursor"]
        if not page["page"]["has_more"]:
            break
    assert len(seen) == 25
    assert len(set(seen)) == 25
    assert seen == sorted(seen, reverse=True)  # newest first, no dupes/gaps


async def test_filters_narrow_results(client, producer_env):
    await _publish(client, producer_env.auth, 3, topic="a", event="alpha.x")
    await _publish(client, producer_env.auth, 4, topic="b", event="beta.y")
    r = await client.get("/api/v1/events?topic=b", headers=producer_env.auth)
    assert {e["topic"] for e in r.json()["events"]} == {"b"}
    r2 = await client.get("/api/v1/events?event_prefix=alpha.", headers=producer_env.auth)
    assert all(e["event"].startswith("alpha.") for e in r2.json()["events"])


async def test_replay_since_returns_only_newer(client, producer_env):
    await _publish(client, producer_env.auth, 5, topic="rp")
    first_page = (await client.get("/api/v1/events?topic=rp&order=asc", headers=producer_env.auth)).json()
    third_id = first_page["events"][2]["id"]

    r = await client.post("/api/v1/events/replay", headers=producer_env.auth,
                          json={"topic": "rp", "since": third_id})
    body = r.json()
    ids = [e["id"] for e in body["events"]]
    assert all(i > third_id for i in ids)
    assert body["replay"]["count"] == 2
    assert body["replay"]["truncated"] is False


async def test_replay_flags_truncation_when_cursor_predates_retained(client, producer_env):
    await _publish(client, producer_env.auth, 3, topic="rt")
    r = await client.post("/api/v1/events/replay", headers=producer_env.auth,
                          json={"topic": "rt", "since": "evt_00000000000000000000000000"})
    body = r.json()
    assert body["replay"]["truncated"] is True
    assert body["replay"]["earliest_available"] is not None


async def test_replay_requires_scope(client):
    from tests.helpers import make_api_key

    bundle = await make_api_key(scopes="events:publish events:read")  # no replay
    r = await client.post("/api/v1/events/replay", headers=bundle.auth, json={"topic": "x"})
    assert r.status_code == 403


async def test_non_persisted_topic_is_not_stored(client, producer_env, admin_user):
    from tests.helpers import cli_token, control_headers

    token = await cli_token(admin_user)
    await client.post("/api/control/topics", headers=control_headers(token),
                      json={"name": "ephemeral", "environment": "development", "persist": False})
    await _publish(client, producer_env.auth, 3, topic="ephemeral")
    r = await client.get("/api/v1/events?topic=ephemeral", headers=producer_env.auth)
    assert r.json()["events"] == []
