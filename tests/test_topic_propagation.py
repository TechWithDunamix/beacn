"""A topic's `propagate_to` list: publish once, land on every target too.

Covers the two properties that must hold regardless of how a merchant wires
their topics together: propagation is exactly one hop (a cycle of topics
naming each other must not fan out forever), and a propagated copy is never
silently dropped by the idempotency check that exists for the *original*
event, not for copies of it — the actual bug this feature's first draft had.
"""

from __future__ import annotations

import pytest

from app.services.ingest import invalidate_topic_cache
from database.models import Event, Topic
from tests.helpers import cli_token, control_headers, make_api_key

pytestmark = pytest.mark.asyncio


async def _topic(environment: str, name: str, propagate_to: list[str] | None = None) -> Topic:
    from domain.ids import new_ulid

    row = await Topic.create(
        id=new_ulid(), environment=environment, name=name, propagate_to=propagate_to or []
    )
    invalidate_topic_cache()
    return row


async def _events_on(environment: str, topic: str) -> list[Event]:
    return await Event.filter(environment=environment, topic=topic).order_by("id")


class TestPropagation:
    async def test_publishing_fires_on_every_target(self, client):
        bundle = await make_api_key()
        env = bundle.producer.environment
        await _topic(env, "orders", propagate_to=["audit-log", "analytics"])

        r = await client.post(
            "/api/v1/events",
            headers=bundle.auth,
            json={"event": "order.created", "topic": "orders", "data": {"amount": 42}},
        )
        assert r.status_code == 201

        orders = await _events_on(env, "orders")
        audit = await _events_on(env, "audit-log")
        analytics = await _events_on(env, "analytics")
        assert len(orders) == 1
        assert len(audit) == 1
        assert len(analytics) == 1

        # Same event, same data, but each is its own row — not the original
        # appearing under three topics.
        ids = {orders[0].id, audit[0].id, analytics[0].id}
        assert len(ids) == 3
        for row in (audit[0], analytics[0]):
            assert row.event == "order.created"
            assert row.data == {"amount": 42}

    async def test_a_cycle_does_not_fan_out_forever(self, client):
        bundle = await make_api_key()
        env = bundle.producer.environment
        await _topic(env, "a", propagate_to=["b"])
        await _topic(env, "b", propagate_to=["a"])

        r = await client.post(
            "/api/v1/events", headers=bundle.auth, json={"event": "x.y", "topic": "a"},
        )
        assert r.status_code == 201

        # One hop each way, then stop: "a" has the original, "b" has the one
        # copy propagation put there — never a second copy back on "a".
        assert len(await _events_on(env, "a")) == 1
        assert len(await _events_on(env, "b")) == 1

    async def test_propagated_copy_is_not_swallowed_by_the_originals_idempotency_key(self, client):
        """The bug this feature actually shipped with once: `_dedupe` keys on
        `(environment, producer_id, idempotency_key)` with no topic in it, so
        a propagated copy that kept the original's key looked like a repeat
        of the event still being accepted, and was dropped instead of
        propagated."""
        bundle = await make_api_key()
        env = bundle.producer.environment
        await _topic(env, "orders", propagate_to=["audit-log"])

        r = await client.post(
            "/api/v1/events",
            headers=bundle.auth,
            json={"event": "order.created", "topic": "orders", "idempotency_key": "ord-1"},
        )
        assert r.status_code == 201
        assert len(await _events_on(env, "audit-log")) == 1

    async def test_a_topic_naming_itself_is_not_a_second_copy(self, client):
        bundle = await make_api_key()
        env = bundle.producer.environment
        await _topic(env, "orders", propagate_to=["orders"])

        r = await client.post(
            "/api/v1/events", headers=bundle.auth, json={"event": "x.y", "topic": "orders"},
        )
        assert r.status_code == 201
        assert len(await _events_on(env, "orders")) == 1

    async def test_no_propagate_to_behaves_as_before(self, client):
        bundle = await make_api_key()
        env = bundle.producer.environment
        r = await client.post(
            "/api/v1/events", headers=bundle.auth, json={"event": "x.y", "topic": "plain"},
        )
        assert r.status_code == 201
        assert len(await _events_on(env, "plain")) == 1


class TestControlApiValidation:
    async def test_saving_a_propagate_to_list(self, client, admin_user):
        token = await cli_token(admin_user)
        r = await client.post(
            "/api/control/topics",
            headers=control_headers(token),
            json={"name": "orders", "environment": "development", "propagate_to": ["audit-log", "orders", "audit-log"]},
        )
        assert r.status_code == 201
        # Self and the repeat are both dropped, not rejected outright — a
        # merchant clicking the same topic twice in a picker is not a
        # validation error, just a no-op on that entry.
        assert r.json()["topic"]["propagate_to"] == ["audit-log"]

    async def test_rejects_an_invalid_topic_name(self, client, admin_user):
        token = await cli_token(admin_user)
        r = await client.post(
            "/api/control/topics",
            headers=control_headers(token),
            json={"name": "orders", "environment": "development", "propagate_to": ["not a valid topic!"]},
        )
        assert r.status_code == 422

    async def test_rejects_a_non_list(self, client, admin_user):
        token = await cli_token(admin_user)
        r = await client.post(
            "/api/control/topics",
            headers=control_headers(token),
            json={"name": "orders", "environment": "development", "propagate_to": "audit-log"},
        )
        assert r.status_code == 422
