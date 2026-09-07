"""The numbers the dashboard reads.

Every figure is computed from the durable store plus this process's live
realtime counters. Nothing here is fabricated — an empty installation returns
zeros, and the dashboard renders empty states for them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from tortoise.functions import Count

from database.models import (
    ApiKey,
    Connection,
    DeliveryAttempt,
    Event,
    Producer,
    Task,
    Topic,
)
from realtime import get_realtime


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def dashboard(environment: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    day_ago = now - timedelta(hours=24)
    hour_ago = now - timedelta(hours=1)
    minute_ago = now - timedelta(minutes=1)

    events_today = await Event.filter(environment=environment, published_at__gte=day_ago).count()
    events_last_hour = await Event.filter(environment=environment, published_at__gte=hour_ago).count()
    events_last_minute = await Event.filter(
        environment=environment, published_at__gte=minute_ago
    ).count()
    total_events = await Event.filter(environment=environment).count()

    attempts = await DeliveryAttempt.filter(
        environment=environment, created_at__gte=day_ago
    ).count()
    delivered = await DeliveryAttempt.filter(
        environment=environment, created_at__gte=day_ago, outcome="delivered"
    ).count()
    failed = await DeliveryAttempt.filter(
        environment=environment, created_at__gte=day_ago, outcome__in=["dropped", "failed"]
    ).count()
    success_rate = round(delivered / attempts, 4) if attempts else None

    rt = get_realtime()
    open_connections = await Connection.filter(environment=environment, status="open").count()

    tasks_running = await Task.filter(
        environment=environment, status__in=["started", "retrying"]
    ).count()
    tasks_failed_today = await Task.filter(
        environment=environment, status="failed", updated_at__gte=day_ago
    ).count()

    return {
        "environment": environment,
        "events": {
            "per_second": round(events_last_minute / 60, 2),
            "last_minute": events_last_minute,
            "last_hour": events_last_hour,
            "today": events_today,
            "total": total_events,
        },
        "delivery": {
            "attempts_24h": attempts,
            "delivered_24h": delivered,
            "failed_24h": failed,
            "success_rate": success_rate,
        },
        "realtime": {
            "connections_open": open_connections,
            "connections_this_instance": rt.local_connection_count(),
            "subscriptions_this_instance": rt.local_subscription_count(),
            "frames_sent_this_instance": rt.frames_sent,
            "events_dropped_this_instance": rt.events_dropped,
        },
        "tasks": {"running": tasks_running, "failed_today": tasks_failed_today},
        "producers": {
            "total": await Producer.filter(environment=environment).count(),
            "active": await Producer.filter(environment=environment, status="active").count(),
        },
        "keys": {
            "active": await ApiKey.filter(environment=environment, status="active").count(),
        },
        "topics": await Topic.filter(environment=environment).count(),
    }


async def top_producers(environment: str, limit: int = 8) -> list[dict]:
    rows = (
        await Event.filter(environment=environment)
        .annotate(n=Count("id"))
        .group_by("producer_name")
        .order_by("-n")
        .limit(limit)
        .values("producer_name", "n")
    )
    return [{"producer": r["producer_name"] or "unknown", "events": r["n"]} for r in rows]


async def top_topics(environment: str, limit: int = 8) -> list[dict]:
    rows = (
        await Event.filter(environment=environment)
        .annotate(n=Count("id"))
        .group_by("topic")
        .order_by("-n")
        .limit(limit)
        .values("topic", "n")
    )
    return [{"topic": r["topic"], "events": r["n"]} for r in rows]


async def recent_events(environment: str, limit: int = 12) -> list[dict]:
    rows = await Event.filter(environment=environment).order_by("-id").limit(limit)
    return [r.to_wire() for r in rows]


async def throughput_series(environment: str, minutes: int = 60) -> list[dict]:
    """Events per minute for the last `minutes`, bucketed in Python.

    A single scan of the recent rows, bucketed by `published_at` — portable
    between SQLite and Postgres without date functions in SQL.
    """
    now = datetime.now(UTC)
    start = now - timedelta(minutes=minutes)
    rows = await Event.filter(environment=environment, published_at__gte=start).values_list(
        "published_at", flat=True
    )
    buckets: dict[int, int] = {}
    for ts in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        idx = int((ts - start).total_seconds() // 60)
        buckets[idx] = buckets.get(idx, 0) + 1
    return [
        {"minute": _iso(start + timedelta(minutes=i)), "count": buckets.get(i, 0)}
        for i in range(minutes)
    ]
