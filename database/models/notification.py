"""Notification activity.

A notification is an event whose name starts `notification.`. BEACN stores a
row so the control plane can show delivery status and read/unread state; the
event itself is still delivered on its topic like any other.
"""

from __future__ import annotations

from sillo.record import Model
from tortoise import fields

from domain.ids import new_ulid

__all__ = ["Notification"]


class Notification(Model):
    id = fields.CharField(max_length=32, pk=True)  # ntf_<ulid>
    environment = fields.CharField(max_length=20)
    event_id = fields.CharField(max_length=32, index=True)

    #: opaque recipient identifier supplied by the producer (data.recipient)
    recipient = fields.CharField(max_length=200, index=True)
    #: e.g. "billing", "security", "digest" — from data.type
    type = fields.CharField(max_length=80, default="general")
    title = fields.CharField(max_length=300, null=True)
    body = fields.TextField(null=True)
    channel = fields.CharField(max_length=40, default="in_app")  # in_app | email | sms | webhook
    topic = fields.CharField(max_length=200)

    producer_name = fields.CharField(max_length=120, null=True)
    severity = fields.CharField(max_length=12, default="info")

    delivery_status = fields.CharField(max_length=16, default="delivered")  # delivered|failed|pending
    read_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "notifications"
        indexes = (("environment", "recipient", "read_at"), ("environment", "created_at"))

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    @classmethod
    async def from_event(cls, env) -> Notification:
        data = env.data or {}
        return await cls.create(
            id=new_ulid(),
            environment=env.environment,
            event_id=env.id,
            recipient=str(data.get("recipient") or data.get("user_id") or env.user_id or "unknown"),
            type=str(data.get("type") or "general")[:80],
            title=(data.get("title") or None),
            body=(data.get("body") or data.get("message") or None),
            channel=str(data.get("channel") or "in_app")[:40],
            topic=env.topic,
            producer_name=env.producer,
            severity=env.severity,
            delivery_status=str(data.get("delivery_status") or "delivered")[:16],
        )
