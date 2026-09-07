"""Realtime connection registry.

One row per WebSocket/SSE connection, created on connect and closed on
disconnect. `subscriptions` is a JSON list of topic strings, rewritten as the
client subscribes and unsubscribes. Rows for closed connections are kept for a
few days (`connection_retention_hours`) so the control plane can show recent
history, then pruned.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sillo.record import Model
from tortoise import fields

__all__ = ["Connection"]


class Connection(Model):
    id = fields.CharField(max_length=32, pk=True)  # con_<ulid>
    environment = fields.CharField(max_length=20, index=True)
    transport = fields.CharField(max_length=8, default="ws")  # ws | sse

    #: which BEACN instance owns the live socket (hostname:pid) — for "terminate"
    instance = fields.CharField(max_length=120, null=True)

    principal_kind = fields.CharField(max_length=16, default="token")  # token | api_key
    principal_id = fields.CharField(max_length=120, null=True)
    user_id = fields.CharField(max_length=200, null=True)
    organization_id = fields.CharField(max_length=200, null=True)
    client = fields.CharField(max_length=200, null=True)  # User-Agent / SDK name
    ip = fields.CharField(max_length=64, null=True)

    subscriptions = fields.JSONField(default=list)
    events_sent = fields.BigIntField(default=0)
    events_dropped = fields.BigIntField(default=0)

    status = fields.CharField(max_length=16, default="open")  # open | closed
    close_code = fields.IntField(null=True)
    close_reason = fields.CharField(max_length=200, null=True)

    connected_at = fields.DatetimeField(auto_now_add=True, index=True)
    last_heartbeat_at = fields.DatetimeField(null=True)
    disconnected_at = fields.DatetimeField(null=True)
    #: set by the control plane to ask the owning instance to drop the socket
    terminate_requested_at = fields.DatetimeField(null=True)

    class Meta:
        table = "connections"
        indexes = (("environment", "status"), ("status", "connected_at"))

    @property
    def duration_seconds(self) -> float:
        end = self.disconnected_at or datetime.now(UTC)
        start = self.connected_at
        if start and start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        return (end - start).total_seconds() if start else 0.0
