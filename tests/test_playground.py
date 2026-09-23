"""Dashboard Playground — mint a producer-attached token and publish as that
producer through the control plane. See `routes/api/control.py`.
"""

from __future__ import annotations

import pytest

from tests.helpers import cli_token, control_headers, make_user

pytestmark = pytest.mark.asyncio


async def _operator_token():
    user = await make_user("pg-op@test.local", role="Operator")
    return control_headers(await cli_token(user))


async def test_playground_token_requires_producer_id(client):
    headers = await _operator_token()
    r = await client.post("/api/control/playground/token", headers=headers,
                          json={"environment": "development"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid"


async def test_playground_token_unknown_producer_404(client):
    headers = await _operator_token()
    r = await client.post("/api/control/playground/token", headers=headers,
                          json={"environment": "development", "producer_id": "prd_nope"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_playground_token_mints_watch_only_grant(client, producer_env):
    from app.auth import grant_from_realtime_token

    headers = await _operator_token()
    r = await client.post("/api/control/playground/token", headers=headers,
                          json={"environment": "development",
                                "producer_id": producer_env.producer.id})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expires_in"] > 0
    assert body["producer"]["id"] == producer_env.producer.id

    grant = grant_from_realtime_token(body["token"])
    assert grant.environment == "development"
    assert grant.producer_id == producer_env.producer.id
    assert grant.operator is False
    assert grant.topic_patterns == ("*",)


async def test_playground_publish_ingests_a_real_event(client, producer_env):
    headers = await _operator_token()
    r = await client.post("/api/control/playground/publish", headers=headers, json={
        "environment": "development",
        "producer_id": producer_env.producer.id,
        "event": {"event": "playground.ping", "topic": "pg-topic", "data": {"ok": True}},
    })
    assert r.status_code == 201, r.text

    listed = await client.get(
        "/api/v1/events", headers=producer_env.auth, params={"topic": "pg-topic"}
    )
    names = [e["event"] for e in listed.json().get("events", [])]
    assert "playground.ping" in names


async def test_playground_publish_is_audited(client, producer_env):
    op_headers = await _operator_token()
    await client.post("/api/control/playground/publish", headers=op_headers, json={
        "environment": "development",
        "producer_id": producer_env.producer.id,
        "event": {"event": "playground.audited", "topic": "pg-topic"},
    })
    audit = await client.get("/api/control/audit", headers=op_headers)
    actions = [row["action"] for row in audit.json()["events"]]
    assert "playground.published" in actions


async def test_playground_publish_rejects_bad_event_body(client, producer_env):
    headers = await _operator_token()
    r = await client.post("/api/control/playground/publish", headers=headers, json={
        "environment": "development",
        "producer_id": producer_env.producer.id,
        "event": "not-an-object",
    })
    assert r.status_code == 422


async def test_playground_publish_unknown_producer_404(client):
    headers = await _operator_token()
    r = await client.post("/api/control/playground/publish", headers=headers, json={
        "environment": "development",
        "producer_id": "prd_nope",
        "event": {"event": "x.y"},
    })
    assert r.status_code == 404


async def test_playground_publish_needs_publish_permission(client, producer_env):
    # ReadOnly has events.read (so it may mint a watch-only token) but not
    # events.publish — publishing is the consequential half of the split.
    user = await make_user("pg-ro@test.local", role="ReadOnly")
    headers = control_headers(await cli_token(user))
    r = await client.post("/api/control/playground/publish", headers=headers, json={
        "environment": "development",
        "producer_id": producer_env.producer.id,
        "event": {"event": "x.y"},
    })
    assert r.status_code == 403


async def test_grant_from_api_key_token_attributes_producer(client, producer_env):
    from app.auth import grant_from_api_key_token

    grant = await grant_from_api_key_token(producer_env.secret)
    assert grant.producer_id == producer_env.producer.id
