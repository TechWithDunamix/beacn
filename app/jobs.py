"""Background work: retention, denormalised counters, connection reaping.

Each job is small and idempotent — the scheduler makes no promise one finishes
before the next tick. None is in the ingestion or delivery path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sillo.work.queue.job import Job

from app.config import config

__all__ = ["ALL_JOBS", "SCHEDULE", "run_all_once"]


class SweepIdempotency(Job):
    queue = "beacn"

    async def handle(self) -> Any:
        from app.services.ingest import sweep_idempotency

        return {"removed": await sweep_idempotency()}


class PruneEvents(Job):
    queue = "beacn"

    async def handle(self) -> Any:
        from database.models import Event, Topic

        now = datetime.now(UTC)
        default_cutoff = now - timedelta(hours=config.event_retention_hours)
        # Topics with their own retention are pruned individually.
        removed = 0
        custom = await Topic.filter(retention_hours__not_isnull=True).values(
            "environment", "name", "retention_hours"
        )
        custom_keys = {(c["environment"], c["name"]) for c in custom}
        for c in custom:
            cutoff = now - timedelta(hours=c["retention_hours"])
            removed += await Event.filter(
                environment=c["environment"], topic=c["name"], published_at__lt=cutoff
            ).delete()
        # Everything else on the global default.
        qs = Event.filter(published_at__lt=default_cutoff)
        for env, name in custom_keys:
            qs = qs.exclude(environment=env, topic=name)
        removed += await qs.delete()
        return {"removed": removed}


class PruneTasksAndNotifications(Job):
    queue = "beacn"

    async def handle(self) -> Any:
        from database.models import DeliveryAttempt, Notification, Task

        now = datetime.now(UTC)
        tasks = await Task.filter(
            updated_at__lt=now - timedelta(hours=config.task_retention_hours),
            status__in=["completed", "failed", "revoked"],
        ).delete()
        notes = await Notification.filter(
            created_at__lt=now - timedelta(hours=config.notification_retention_hours)
        ).delete()
        attempts = await DeliveryAttempt.filter(
            created_at__lt=now - timedelta(hours=config.connection_retention_hours)
        ).delete()
        return {"tasks": tasks, "notifications": notes, "delivery_attempts": attempts}


class ReapConnections(Job):
    queue = "beacn"

    async def handle(self) -> Any:
        from database.models import Connection

        now = datetime.now(UTC)
        # Rows for closed connections past retention.
        removed = await Connection.filter(
            status="closed",
            disconnected_at__lt=now - timedelta(hours=config.connection_retention_hours),
        ).delete()
        # Connections marked "open" but with no heartbeat for a long time and no
        # owning session in this process are almost certainly dead instances.
        stale = await Connection.filter(
            status="open",
            connected_at__lt=now - timedelta(seconds=config.connection_max_seconds * 2),
        ).update(status="closed", close_reason="stale (no heartbeat)", disconnected_at=now)
        return {"removed": removed, "closed_stale": stale}


class RefreshCounters(Job):
    queue = "beacn"

    async def handle(self) -> Any:
        from tortoise.functions import Count, Max

        from database.models import Event, Producer, Topic

        touched = 0
        topic_rows = (
            await Event.all()
            .annotate(n=Count("id"), last=Max("published_at"))
            .group_by("environment", "topic")
            .values("environment", "topic", "n", "last")
        )
        by_topic = {(r["environment"], r["topic"]): r for r in topic_rows}
        for topic in await Topic.all():
            row = by_topic.get((topic.environment, topic.name))
            if row:
                topic.event_count = row["n"]
                topic.last_event_at = row["last"]
                await topic.save(update_fields=["event_count", "last_event_at"])
                touched += 1

        prod_rows = (
            await Event.all()
            .annotate(n=Count("id"), last=Max("published_at"))
            .group_by("producer_id")
            .values("producer_id", "n", "last")
        )
        by_prod = {r["producer_id"]: r for r in prod_rows}
        for producer in await Producer.all():
            row = by_prod.get(producer.id)
            if row:
                producer.event_count = row["n"]
                producer.last_event_at = row["last"]
                await producer.save(update_fields=["event_count", "last_event_at"])
        return {"topics_refreshed": touched}


ALL_JOBS: tuple[type[Job], ...] = (
    SweepIdempotency,
    PruneEvents,
    PruneTasksAndNotifications,
    ReapConnections,
    RefreshCounters,
)

SCHEDULE: tuple[tuple[type[Job], int], ...] = (
    (RefreshCounters, 60),
    (ReapConnections, 120),
    (SweepIdempotency, 900),
    (PruneTasksAndNotifications, 1800),
    (PruneEvents, 3600),
)


async def run_all_once() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for job_class, _ in SCHEDULE:
        try:
            results[job_class.__name__] = await job_class().handle()
        except Exception as error:  # noqa: BLE001
            results[job_class.__name__] = {"error": str(error)}
    return results
