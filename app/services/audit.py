"""Control-plane audit trail."""

from __future__ import annotations

from typing import Any

from database.models import AuditEvent


def snapshot(obj: Any, fields: tuple[str, ...]) -> dict:
    return {f: _plain(getattr(obj, f, None)) for f in fields}


def _plain(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


async def record(
    *,
    action: str,
    actor: Any = None,
    origin: str = "web",
    resource_type: str | None = None,
    resource_id: Any = None,
    resource_label: str | None = None,
    environment: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip: str | None = None,
    correlation_id: str | None = None,
) -> AuditEvent:
    actor_label = "system"
    actor_id = None
    if actor is not None:
        actor_id = getattr(actor, "pk", None)
        actor_label = getattr(actor, "email", None) or str(actor)
    return await AuditEvent.record(
        action=action,
        actor_id=actor_id,
        actor_label=actor_label,
        origin=origin,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        resource_label=resource_label,
        environment=environment,
        before=before,
        after=after,
        ip=ip,
        correlation_id=correlation_id,
    )
