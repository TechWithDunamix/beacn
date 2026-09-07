"""Integration adapters — the pure mapping, and end-to-end into the event store."""

from __future__ import annotations

import pytest

from integrations.celery import event_for


def test_celery_signal_mapping():
    ev, data = event_for("task_prerun", task_id="c-1", name="orders.process")
    assert ev == "task.started"
    assert data == {"task_id": "c-1", "name": "orders.process"}

    ev, data = event_for("task_retry", task_id="c-1", name="x", retries=1, error="boom")
    assert ev == "task.retrying"
    assert data["attempt"] == 2
    assert data["error"] == "boom"

    ev, data = event_for("task_failure", task_id="c-1", error="ValueError('x')")
    assert ev == "task.failed"

    ev, data = event_for("task_success", task_id="c-1", result={"n": 3}, runtime_ms=42)
    assert ev == "task.completed"
    assert data["duration_ms"] == 42
    assert data["result"] == {"n": 3}


def test_celery_mapping_rejects_unknown_signal():
    with pytest.raises(KeyError):
        event_for("task_unknown", task_id="c-1")


async def test_celery_events_flow_into_tasks_table(client, producer_env):
    """Publishing the `task.*` events a Celery worker would produce yields a Task row."""
    tid = "celery-uuid-123"
    for ev, data in [
        event_for("task_prerun", task_id=tid, name="orders.process"),
        event_for("task_retry", task_id=tid, name="orders.process", retries=0, error="timeout"),
        event_for("task_success", task_id=tid, name="orders.process", runtime_ms=3812),
    ]:
        r = await client.post("/api/v1/events", headers=producer_env.auth,
                              json={"event": ev, "topic": "tasks", "data": data})
        assert r.status_code == 201

    got = await client.get(f"/api/v1/tasks/{tid}", headers=producer_env.auth)
    task = got.json()["task"]
    assert task["name"] == "orders.process"
    assert task["status"] == "completed"
    assert task["attempts"] == 1
    assert task["duration_ms"] is not None


async def test_notification_event_creates_notification_row(client, producer_env):
    r = await client.post("/api/v1/events", headers=producer_env.auth, json={
        "event": "notification.created", "topic": "user:88",
        "data": {"recipient": "88", "type": "billing", "title": "Invoice ready",
                 "body": "Your invoice is available.", "channel": "email"},
    })
    assert r.status_code == 201
    lst = await client.get("/api/v1/notifications?recipient=88", headers=producer_env.auth)
    rows = lst.json()["notifications"]
    assert len(rows) == 1
    assert rows[0]["type"] == "billing"
    assert rows[0]["channel"] == "email"
    assert rows[0]["read"] is False

    marked = await client.post(f"/api/v1/notifications/{rows[0]['id']}/read", headers=producer_env.auth)
    assert marked.json()["read"] is True
