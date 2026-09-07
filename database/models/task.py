"""BEACN-observed tasks.

A task is not Celery-specific. Any producer emitting `task.*` events for a
`data.task_id` gets a row here, upserted in place as the lifecycle progresses.
Celery is one such producer (`integrations/celery.py`); a Sillo worker, a Go
service or a cron job emitting the same events are indistinguishable here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sillo.record import Model
from tortoise import fields

from domain.ids import new_ulid

__all__ = ["Task"]

TERMINAL = {"completed", "failed", "revoked"}


class Task(Model):
    id = fields.CharField(max_length=32, pk=True)  # tsk_<ulid>
    environment = fields.CharField(max_length=20)
    #: the producer's own id for the task (Celery task uuid, etc.)
    task_id = fields.CharField(max_length=200)
    name = fields.CharField(max_length=200, null=True)
    topic = fields.CharField(max_length=200, default="tasks")

    producer_id = fields.CharField(max_length=32, null=True)
    producer_name = fields.CharField(max_length=120, null=True)

    status = fields.CharField(max_length=16, default="created")
    progress = fields.FloatField(null=True)  # 0..1
    attempts = fields.IntField(default=0)
    error = fields.TextField(null=True)
    result = fields.JSONField(null=True)

    correlation_id = fields.CharField(max_length=200, null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    started_at = fields.DatetimeField(null=True)
    finished_at = fields.DatetimeField(null=True)
    updated_at = fields.DatetimeField(auto_now=True)
    #: id of the most recent event that touched this row
    last_event_id = fields.CharField(max_length=32, null=True)

    class Meta:
        table = "tasks"
        unique_together = (("environment", "task_id"),)
        indexes = (("environment", "status", "updated_at"), ("environment", "name"))

    @property
    def duration_ms(self) -> int | None:
        if self.started_at and self.finished_at:
            return int((self.finished_at - self.started_at).total_seconds() * 1000)
        return None

    @classmethod
    async def apply_event(cls, env) -> Task | None:
        """Upsert from a `task.*` `domain.events.Envelope`. Returns the row or None."""
        if not env.task_id:
            return None
        row = await cls.get_or_none(environment=env.environment, task_id=env.task_id)
        now = env.timestamp
        if row is None:
            row = cls(
                id=new_ulid(),
                environment=env.environment,
                task_id=env.task_id,
                name=env.task_name,
                topic=env.topic,
                producer_id=env.producer_id if isinstance(env.producer_id, str) else None,
                producer_name=env.producer,
                correlation_id=env.correlation_id,
            )
        if env.task_name and not row.name:
            row.name = env.task_name
        status = env.task_status
        # Never move a terminal task backwards.
        if status and not (row.status in TERMINAL and status not in TERMINAL):
            row.status = status
        data = env.data or {}
        if "progress" in data:
            try:
                row.progress = max(0.0, min(1.0, float(data["progress"])))
            except (TypeError, ValueError):
                pass
        if env.event == "task.retrying":
            row.attempts = int(data.get("attempt") or row.attempts + 1)
        if data.get("error"):
            row.error = str(data["error"])[:8000]
        if data.get("result") is not None:
            row.result = data["result"]
        if status == "started" and row.started_at is None:
            row.started_at = data_dt(data, "started_at") or now
        if status in TERMINAL:
            row.finished_at = data_dt(data, "finished_at") or now
            if row.started_at is None:
                row.started_at = row.finished_at
        row.last_event_id = env.id
        await row.save()
        return row


def data_dt(data: dict, key: str) -> datetime | None:
    value = data.get(key)
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
