"""Dashboard page handlers.

Each renders an Inertia page with its first screen of real data resolved
server-side (from the same service layer the API uses). The React pages refresh
and paginate against `/api/control/*` with the session cookie.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sillo.core.http import HttpContext
from sillo_inertia import render

from app.config import ENVIRONMENTS
from app.services import history as history_service
from app.services import stats
from database.models import (
    ApiKey,
    AuditEvent,
    Connection,
    Notification,
    Producer,
    Task,
    Topic,
)
from routes.web._kit import page

__all__ = [
    "dashboard", "events", "event_detail", "topics", "connections",
    "tasks", "producers", "api_keys", "audit_log", "notifications", "settings",
    "users",
]


def _env(ctx: HttpContext) -> str:
    value = ctx.query_params.get("env") or ctx.query_params.get("environment") or "development"
    return value if value in ENVIRONMENTS else "development"


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


@page("settings.read")
async def dashboard(ctx: HttpContext) -> Any:
    environment = _env(ctx)
    return await render(
        "Dashboard",
        {
            "environment": environment,
            "summary": await stats.dashboard(environment),
            "top_producers": await stats.top_producers(environment),
            "top_topics": await stats.top_topics(environment),
            "recent_events": await stats.recent_events(environment),
            "throughput": await stats.throughput_series(environment),
        },
        ctx=ctx,
    )


@page("events.read")
async def events(ctx: HttpContext) -> Any:
    environment = _env(ctx)
    q = ctx.query_params
    query = history_service.HistoryQuery(
        environment=environment,
        topic=q.get("topic") or None,
        event_prefix=q.get("event_prefix") or None,
        producer_id=q.get("producer_id") or None,
        kind=q.get("kind") or None,
        severity=q.get("severity") or None,
        correlation_id=q.get("correlation_id") or None,
        cursor=q.get("cursor") or None,
        limit=50,
    )
    result = await history_service.query(query, include_meta=False)
    producers = await Producer.filter(environment=environment).order_by("name")
    return await render(
        "Events",
        {
            "environment": environment,
            "filters": {
                "topic": q.get("topic"),
                "event_prefix": q.get("event_prefix"),
                "kind": q.get("kind"),
                "severity": q.get("severity"),
                "producer_id": q.get("producer_id"),
            },
            "producers": [{"id": p.id, "name": p.name} for p in producers],
            **result.to_dict(),
        },
        ctx=ctx,
    )


@page("events.read")
async def event_detail(ctx: HttpContext, event_id: str) -> Any:
    environment = _env(ctx)
    row = await history_service.get_one(environment, event_id)
    from database.models import DeliveryAttempt

    attempts = []
    if row is not None:
        attempts = await DeliveryAttempt.filter(
            environment=environment, event_id=event_id
        ).order_by("-created_at").limit(200)
    return await render(
        "EventDetail",
        {
            "environment": environment,
            "event": row.to_wire(include_meta=True) if row else None,
            "raw": (row.data if row else None),
            "delivery_attempts": [
                {
                    "connection_id": a.connection_id,
                    "outcome": a.outcome,
                    "detail": a.detail,
                    "latency_ms": a.latency_ms,
                    "acknowledged": a.acknowledged,
                    "at": _iso(a.created_at),
                }
                for a in attempts
            ],
        },
        ctx=ctx,
    )


@page("topics.read")
async def topics(ctx: HttpContext) -> Any:
    environment = _env(ctx)
    rows = await Topic.filter(environment=environment).order_by("-event_count", "name")
    return await render(
        "Topics",
        {
            "environment": environment,
            "topics": [
                {
                    "id": t.id, "name": t.name, "visibility": t.visibility, "persist": t.persist,
                    "retention_hours": t.retention_hours, "description": t.description,
                    "event_count": t.event_count, "subscriber_count": t.subscriber_count,
                    "last_event_at": _iso(t.last_event_at),
                }
                for t in rows
            ],
        },
        ctx=ctx,
    )


@page("connections.read")
async def connections(ctx: HttpContext) -> Any:
    environment = _env(ctx)
    rows = await Connection.filter(environment=environment).order_by("-connected_at").limit(200)
    return await render(
        "Connections",
        {
            "environment": environment,
            "connections": [
                {
                    "id": c.id, "transport": c.transport, "status": c.status, "instance": c.instance,
                    "user_id": c.user_id, "organization_id": c.organization_id, "client": c.client,
                    "ip": c.ip, "subscriptions": c.subscriptions, "events_sent": c.events_sent,
                    "events_dropped": c.events_dropped, "connected_at": _iso(c.connected_at),
                    "disconnected_at": _iso(c.disconnected_at),
                    "duration_seconds": round(c.duration_seconds, 1),
                }
                for c in rows
            ],
        },
        ctx=ctx,
    )


@page("tasks.read")
async def tasks(ctx: HttpContext) -> Any:
    environment = _env(ctx)
    q = ctx.query_params
    qs = Task.filter(environment=environment)
    if q.get("status"):
        qs = qs.filter(status=q["status"])
    rows = await qs.order_by("-updated_at").limit(80)
    return await render(
        "Tasks",
        {
            "environment": environment,
            "status": q.get("status"),
            "tasks": [
                {
                    "id": t.id, "task_id": t.task_id, "name": t.name, "topic": t.topic,
                    "producer": t.producer_name, "status": t.status, "progress": t.progress,
                    "attempts": t.attempts, "duration_ms": t.duration_ms, "error": t.error,
                    "created_at": _iso(t.created_at), "started_at": _iso(t.started_at),
                    "finished_at": _iso(t.finished_at), "correlation_id": t.correlation_id,
                }
                for t in rows
            ],
        },
        ctx=ctx,
    )


@page("notifications.read")
async def notifications(ctx: HttpContext) -> Any:
    environment = _env(ctx)
    rows = await Notification.filter(environment=environment).order_by("-id").limit(80)
    return await render(
        "Notifications",
        {
            "environment": environment,
            "notifications": [
                {
                    "id": n.id, "recipient": n.recipient, "type": n.type, "title": n.title,
                    "body": n.body, "channel": n.channel, "severity": n.severity,
                    "delivery_status": n.delivery_status, "read": n.is_read,
                    "event_id": n.event_id, "created_at": _iso(n.created_at),
                }
                for n in rows
            ],
        },
        ctx=ctx,
    )


@page("producers.read")
async def producers(ctx: HttpContext) -> Any:
    rows = await Producer.all().order_by("-last_event_at", "name")
    return await render(
        "Producers",
        {
            "environments": list(ENVIRONMENTS),
            "producers": [
                {
                    "id": p.id, "name": p.name, "slug": p.slug, "environment": p.environment,
                    "description": p.description, "default_source": p.default_source,
                    "status": p.status, "event_count": p.event_count,
                    "last_event_at": _iso(p.last_event_at), "created_at": _iso(p.created_at),
                }
                for p in rows
            ],
        },
        ctx=ctx,
    )


@page("apikeys.read")
async def api_keys(ctx: HttpContext) -> Any:
    from database.models import SCOPES

    rows = await ApiKey.all().prefetch_related("producer").order_by("-created_at")
    producers = await Producer.all().order_by("name")
    return await render(
        "ApiKeys",
        {
            "available_scopes": list(SCOPES),
            "producers": [
                {"id": p.id, "name": p.name, "environment": p.environment} for p in producers
            ],
            "keys": [
                {
                    "id": k.id, "name": k.name, "prefix": k.prefix, "masked": k.masked,
                    "environment": k.environment, "scopes": k.scope_list, "status": k.status,
                    "producer": k.producer.name if k.producer_id else None,
                    "request_count": k.request_count, "last_used_at": _iso(k.last_used_at),
                    "expires_at": _iso(k.expires_at), "created_at": _iso(k.created_at),
                }
                for k in rows
            ],
        },
        ctx=ctx,
    )


@page("audit.read")
async def audit_log(ctx: HttpContext) -> Any:
    rows = await AuditEvent.all().order_by("-id").limit(150)
    return await render(
        "AuditLog",
        {
            "events": [
                {
                    "id": e.id, "action": e.action, "actor": e.actor_label, "origin": e.origin,
                    "resource_type": e.resource_type, "resource_id": e.resource_id,
                    "resource_label": e.resource_label, "environment": e.environment,
                    "before": e.before, "after": e.after, "at": _iso(e.created_at),
                }
                for e in rows
            ]
        },
        ctx=ctx,
    )


@page("users.read")
async def users(ctx: HttpContext) -> Any:
    from app.authz import CATALOGUE, ROLES
    from database.models import User

    rows = await User.all().order_by("email")
    out = []
    for user in rows:
        out.append(
            {
                "id": user.pk,
                "email": user.email,
                "name": user.name,
                "title": user.title,
                "active": user.is_active,
                "superuser": user.is_superuser,
                "roles": sorted(await user.get_groups()),
                "last_login": _iso(user.last_login),
            }
        )
    return await render(
        "Users",
        {
            "users": out,
            "roles": list(ROLES),
            "role_descriptions": {name: desc for name, (desc, _) in ROLES.items()},
            "permissions": CATALOGUE,
        },
        ctx=ctx,
    )


@page("settings.read")
async def settings(ctx: HttpContext) -> Any:
    from app.config import config
    from realtime import get_realtime

    return await render(
        "Settings",
        {
            "config": {
                "app_env": config.app_env,
                "bus_backend": config.bus_backend,
                "queue_backend": config.queue_backend,
                "event_retention_hours": config.event_retention_hours,
                "task_retention_hours": config.task_retention_hours,
                "ingest_rate_per_minute": config.ingest_rate_per_minute,
                "heartbeat_ms": config.heartbeat_ms,
                "environments": list(ENVIRONMENTS),
            },
            "bus_health": await get_realtime().health(),
        },
        ctx=ctx,
    )
