"""Audit log for administrative actions on the control plane.

Distinct from the event store: this records what an *authenticated operator*
changed (a key revoked, a topic reconfigured, a connection terminated), not what
producers published.
"""

from __future__ import annotations

from sillo.record import Model
from tortoise import fields

from domain.ids import new_ulid

__all__ = ["AuditEvent"]


class AuditEvent(Model):
    id = fields.CharField(max_length=32, pk=True)  # aud_<ulid>
    action = fields.CharField(max_length=80, index=True)
    actor_id = fields.IntField(null=True)
    actor_label = fields.CharField(max_length=200, default="system")
    #: web | cli | system
    origin = fields.CharField(max_length=16, default="web")

    resource_type = fields.CharField(max_length=40, null=True)
    resource_id = fields.CharField(max_length=64, null=True)
    resource_label = fields.CharField(max_length=240, null=True)
    environment = fields.CharField(max_length=20, null=True)

    before = fields.JSONField(null=True)
    after = fields.JSONField(null=True)
    correlation_id = fields.CharField(max_length=200, null=True)
    ip = fields.CharField(max_length=64, null=True)

    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "audit_events"
        indexes = (("resource_type", "resource_id"), ("actor_id", "created_at"))

    @classmethod
    async def record(cls, **kw) -> AuditEvent:
        kw.setdefault("id", new_ulid())
        return await cls.create(**kw)
