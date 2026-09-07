"""The app assembles, boots and answers."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_health_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] == "ok"
    assert body["bus"]["backend"] == "memory"


async def test_metrics_exposition(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert "beacn_up 1" in r.text
    assert r.headers["content-type"].startswith("text/plain")


async def test_login_page_public(client):
    r = await client.get("/login")
    assert r.status_code == 200


async def test_dashboard_requires_auth(client):
    r = await client.get("/")
    assert r.status_code in (302, 409)


async def test_api_requires_key(client):
    r = await client.get("/api/v1/events")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"
