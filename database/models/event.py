"""The durable event store.

`Event.id` is a ULID (`domain/ids.py`), so ordering by `id` *is* ordering by
time and range scans on `id` need no separate timestamp index. Every read is
scoped by `environment` first — that column leads every index — so one
installation's environments never scan each other's rows.

Immutable: there is no update path. Retention deletes whole rows.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sillo.record import Model
from tortoise import fields

__all__ = ["DeliveryAttempt", "Event", "EventIdempotency"]


class Event(Model):
    #: `evt_<ulid>`
    id = fields.CharField(max_length=32, pk=True)
    environment = fields.CharField(max_length=20)
    event = fields.CharField(max_length=200)
    topic = fields.CharField(max_length=200)
    kind = fields.CharField(max_length=16, default="event")  # event|task|notification|message

    producer_id = fields.CharField(max_length=32, null=True)
    producer_name = fields.CharField(max_length=120, null=True)
    source = fields.CharField(max_length=200, null=True)
    severity = fields.CharField(max_length=12, default="info")
    schema_version = fields.CharField(max_length=32, default="1")

    correlation_id = fields.CharField(max_length=200, null=True)
    request_id = fields.CharField(max_length=200, null=True)
    user_id = fields.CharField(max_length=200, null=True)
    organization_id = fields.CharField(max_length=200, null=True)
    project_id = fields.CharField(max_length=200, null=True)
    idempotency_key = fields.CharField(max_length=200, null=True)

    #: producer-defined payload. Stored whole; never indexed field-by-field.
    data = fields.JSONField(default=dict)

    occurred_at = fields.DatetimeField(null=True)
    published_at = fields.DatetimeField(index=True)

    #: fanout bookkeeping, updated once after delivery
    delivered_count = fields.IntField(default=0)
    subscriber_count = fields.IntField(default=0)

    class Meta:
        table = "events"
        # Every query leads with `environment`. `id` trails so each index is
        # also time-ordered.
        indexes = (
            ("environment", "topic", "id"),
            ("environment", "event", "id"),
            ("environment", "producer_id", "id"),
            ("environment", "kind", "id"),
            ("environment", "correlation_id"),
        )

    def __str__(self) -> str:
        return f"{self.id} {self.event}"

    @classmethod
    async def from_storage_row(cls, row: dict) -> Event:
        return await cls.create(**row)

    def to_wire(self, *, include_meta: bool = True) -> dict:
        out = {
            "id": self.id,
            "event": self.event,
            "topic": self.topic,
            "kind": self.kind,
            "producer": self.producer_name,
            "environment": self.environment,
            "severity": self.severity,
            "schema_version": self.schema_version,
            "timestamp": _iso(self.published_at),
            "data": self.data or {},
        }
        if self.source:
            out["source"] = self.source
        if self.occurred_at:
            out["occurred_at"] = _iso(self.occurred_at)
        for key in ("correlation_id", "request_id", "user_id", "organization_id", "project_id"):
            value = getattr(self, key)
            if value:
                out[key] = value
        if include_meta:
            out["delivery"] = {
                "delivered": self.delivered_count,
                "subscribers": self.subscriber_count,
            }
        return out


class EventIdempotency(Model):
    """One row per (environment, producer, idempotency_key). Swept after the TTL."""

    id = fields.IntField(pk=True)
    environment = fields.CharField(max_length=20)
    producer_id = fields.CharField(max_length=32, null=True)
    idempotency_key = fields.CharField(max_length=200)
    event_id = fields.CharField(max_length=32)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "event_idempotency"
        unique_together = (("environment", "producer_id", "idempotency_key"),)


class DeliveryAttempt(Model):
    """A single (event → connection) delivery outcome.

    Only written when a subscriber was connected at publish time, and sampled
    once a topic exceeds `delivery_sample_threshold` live subscribers.
    """

    id = fields.BigIntField(pk=True)
    environment = fields.CharField(max_length=20)
    event_id = fields.CharField(max_length=32, index=True)
    connection_id = fields.CharField(max_length=32, index=True)
    topic = fields.CharField(max_length=200)
    #: delivered | dropped | failed
    outcome = fields.CharField(max_length=12)
    detail = fields.CharField(max_length=200, null=True)
    latency_ms = fields.IntField(null=True)
    acknowledged = fields.BooleanField(default=False)
    acknowledged_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "delivery_attempts"
        indexes = (("environment", "created_at"),)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
