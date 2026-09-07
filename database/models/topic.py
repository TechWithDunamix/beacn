"""Topics and subscriptions.

A **Topic** row is optional: an event may be published to a topic that has no
row, in which case its visibility is derived (`domain/topics.py::default_spec`).
A row exists when someone wants to *configure* a topic — pin its visibility, set
retention, or attach an access policy. A **Subscription** records a durable
interest (a service consumer, a webhook target); ad-hoc WebSocket subscriptions
are tracked on `Connection`, not here.
"""

from __future__ import annotations

from sillo.record import Model
from tortoise import fields

from domain.ids import new_ulid

__all__ = ["Subscription", "Topic"]

VISIBILITIES = ("public", "private", "internal")


class Topic(Model):
    id = fields.CharField(max_length=32, pk=True)
    environment = fields.CharField(max_length=20, index=True)
    name = fields.CharField(max_length=200)
    visibility = fields.CharField(max_length=16, default="public")
    description = fields.CharField(max_length=400, null=True)

    #: per-topic retention override in hours; null → use the global default
    retention_hours = fields.IntField(null=True)
    #: whether matching events are written to the durable store at all
    persist = fields.BooleanField(default=True)

    #: denormalised, refreshed by the stats job
    event_count = fields.BigIntField(default=0)
    subscriber_count = fields.IntField(default=0)
    producer_count = fields.IntField(default=0)
    last_event_at = fields.DatetimeField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    created_by_id = fields.IntField(null=True)

    class Meta:
        table = "topics"
        unique_together = (("environment", "name"),)

    def __str__(self) -> str:
        return f"{self.name} ({self.environment})"

    @classmethod
    async def ensure(cls, environment: str, name: str) -> Topic:
        row = await cls.get_or_none(environment=environment, name=name)
        if row is None:
            row = await cls.create(id=new_ulid(), environment=environment, name=name)
        return row


class Subscription(Model):
    """A durable, server-side consumer of a topic (a service or a webhook)."""

    id = fields.CharField(max_length=32, pk=True)
    environment = fields.CharField(max_length=20, index=True)
    topic = fields.CharField(max_length=200, index=True)
    #: "service" (a long-lived consumer identified by an API key) or "webhook"
    kind = fields.CharField(max_length=16, default="service")
    label = fields.CharField(max_length=160, null=True)
    api_key = fields.ForeignKeyField(
        "models.ApiKey", related_name="subscriptions", null=True, on_delete=fields.SET_NULL
    )
    #: webhook delivery target, if kind == webhook
    endpoint = fields.CharField(max_length=500, null=True)
    #: last event id this subscription is known to have consumed (for replay)
    cursor = fields.CharField(max_length=32, null=True)

    status = fields.CharField(max_length=16, default="active")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "subscriptions"
        indexes = (("environment", "topic", "status"),)

    @classmethod
    async def create_for(cls, **kw) -> Subscription:
        return await cls.create(id=new_ulid(), **kw)
