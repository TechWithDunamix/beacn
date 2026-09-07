"""BEACN REST API v1 — the producer and consumer surface.

Authenticated with an API key (`Authorization: Bearer bk_...`). Every route is
environment-isolated: the key names one environment and every read and write is
scoped to it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sillo.core.http import HttpContext
from sillo.core.routing import Route, Router

from app.auth import mint_realtime_token
from app.config import config
from app.services import history as history_service
from app.services import ingest as ingest_service
from app.services import replay as replay_service
from app.services.ratelimit import limiter
from database.models import Connection, Notification, Task, Topic
from domain.errors import NotFoundError, ValidationError
from domain.events import Envelope, ProducerContext, parse_batch
from routes.api._common import enforce_size, ok, producer_endpoint, read_json

router = Router(prefix="/api/v1")


def _producer_context(ctx: HttpContext) -> ProducerContext:
    producer = ctx.state.producer
    key = ctx.state.api_key
    return ProducerContext(
        producer=producer.slug,
        producer_id=producer.id,
        environment=producer.environment,
        api_key_id=key.id,
    )


def _parse_dt(value: str | None, field: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} is not a valid ISO-8601 timestamp") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


@producer_endpoint("events:publish")
async def publish_events(ctx: HttpContext) -> Any:
    enforce_size(ctx, config.max_request_bytes)
    body = await read_json(ctx)
    raw_events = parse_batch(body)

    limiter.check(ctx.state.api_key.prefix, cost=len(raw_events))

    pctx = _producer_context(ctx)
    now = datetime.now(UTC)
    envelopes: list[Envelope] = []
    errors: list[dict] = []
    for i, raw in enumerate(raw_events):
        try:
            envelopes.append(Envelope.ingest(raw, pctx, now=now))
        except ValidationError as exc:
            errors.append({"index": i, **exc.to_dict()})
        except Exception as exc:  # noqa: BLE001
            from domain.errors import BeacnError

            if isinstance(exc, BeacnError):
                errors.append({"index": i, **exc.to_dict()})
            else:
                raise

    if errors and not envelopes:
        return ok({"error": {"code": "invalid", "message": "no valid events", "items": errors}},
                  status=422, ctx=ctx)

    result = await ingest_service.ingest(envelopes)
    await ingest_service.touch_producer_stats(ctx.state.producer, result.count, now)

    payload = result.to_dict()
    if errors:
        payload["rejected"] = errors
    status = 200 if result.all_deduplicated else 201
    return ok(payload, status=status, ctx=ctx)


# ---------------------------------------------------------------------------
# Event history & replay
# ---------------------------------------------------------------------------


@producer_endpoint("events:read")
async def list_events(ctx: HttpContext) -> Any:
    q = ctx.query_params
    query = history_service.HistoryQuery(
        environment=ctx.state.producer.environment,
        topic=q.get("topic"),
        event=q.get("event"),
        event_prefix=q.get("event_prefix"),
        producer_id=q.get("producer_id"),
        kind=q.get("kind"),
        severity=q.get("severity"),
        correlation_id=q.get("correlation_id"),
        user_id=q.get("user_id"),
        since=_parse_dt(q.get("since"), "since"),
        until=_parse_dt(q.get("until"), "until"),
        cursor=q.get("cursor"),
        order=q.get("order", "desc"),
        limit=int(q.get("limit") or history_service.DEFAULT_LIMIT),
    )
    page = await history_service.query(query, include_meta=q.get("meta") == "1")
    return ok(page.to_dict(), ctx=ctx)


@producer_endpoint("events:read")
async def get_event(ctx: HttpContext, event_id: str) -> Any:
    row = await history_service.get_one(ctx.state.producer.environment, event_id)
    if row is None:
        raise NotFoundError(f"no event {event_id}")
    return ok({"event": row.to_wire(include_meta=True)}, ctx=ctx)


@producer_endpoint("events:replay")
async def replay_events(ctx: HttpContext) -> Any:
    body = await read_json(ctx)
    topic = (body or {}).get("topic")
    if not topic:
        raise ValidationError("topic is required")
    result = await replay_service.replay(
        environment=ctx.state.producer.environment,
        topic=topic,
        since=(body or {}).get("since"),
        limit=(body or {}).get("limit"),
        include_meta=bool((body or {}).get("meta")),
    )
    return ok(
        {
            "events": result.events,
            "replay": {
                "count": result.count,
                "truncated": result.truncated,
                "earliest_available": result.earliest_available,
                "next_since": result.next_since,
            },
        },
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------


@producer_endpoint("topics:read")
async def list_topics(ctx: HttpContext) -> Any:
    rows = await Topic.filter(environment=ctx.state.producer.environment).order_by("name")
    return ok(
        {
            "topics": [
                {
                    "name": t.name,
                    "visibility": t.visibility,
                    "persist": t.persist,
                    "retention_hours": t.retention_hours or config.event_retention_hours,
                    "event_count": t.event_count,
                    "subscriber_count": t.subscriber_count,
                    "last_event_at": _iso(t.last_event_at),
                }
                for t in rows
            ]
        },
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def _task_json(t: Task) -> dict:
    return {
        "id": t.id,
        "task_id": t.task_id,
        "name": t.name,
        "topic": t.topic,
        "producer": t.producer_name,
        "status": t.status,
        "progress": t.progress,
        "attempts": t.attempts,
        "duration_ms": t.duration_ms,
        "error": t.error,
        "created_at": _iso(t.created_at),
        "started_at": _iso(t.started_at),
        "finished_at": _iso(t.finished_at),
        "correlation_id": t.correlation_id,
    }


@producer_endpoint("tasks:read")
async def list_tasks(ctx: HttpContext) -> Any:
    q = ctx.query_params
    qs = Task.filter(environment=ctx.state.producer.environment)
    if q.get("status"):
        qs = qs.filter(status=q["status"])
    if q.get("name"):
        qs = qs.filter(name=q["name"])
    if q.get("cursor"):
        qs = qs.filter(id__lt=q["cursor"])
    limit = max(1, min(200, int(q.get("limit") or 50)))
    rows = await qs.order_by("-id").limit(limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    return ok(
        {
            "tasks": [_task_json(t) for t in rows],
            "page": {"has_more": more, "next_cursor": rows[-1].id if rows and more else None},
        },
        ctx=ctx,
    )


@producer_endpoint("tasks:read")
async def get_task(ctx: HttpContext, task_id: str) -> Any:
    row = await Task.get_or_none(environment=ctx.state.producer.environment, task_id=task_id)
    if row is None:
        row = await Task.get_or_none(environment=ctx.state.producer.environment, id=task_id)
    if row is None:
        raise NotFoundError(f"no task {task_id}")
    return ok({"task": _task_json(row)}, ctx=ctx)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


@producer_endpoint("notifications:read")
async def list_notifications(ctx: HttpContext) -> Any:
    q = ctx.query_params
    qs = Notification.filter(environment=ctx.state.producer.environment)
    if q.get("recipient"):
        qs = qs.filter(recipient=q["recipient"])
    if q.get("unread") == "1":
        qs = qs.filter(read_at=None)
    if q.get("cursor"):
        qs = qs.filter(id__lt=q["cursor"])
    limit = max(1, min(200, int(q.get("limit") or 50)))
    rows = await qs.order_by("-id").limit(limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    return ok(
        {
            "notifications": [
                {
                    "id": n.id,
                    "recipient": n.recipient,
                    "type": n.type,
                    "title": n.title,
                    "body": n.body,
                    "channel": n.channel,
                    "severity": n.severity,
                    "delivery_status": n.delivery_status,
                    "read": n.is_read,
                    "event_id": n.event_id,
                    "created_at": _iso(n.created_at),
                }
                for n in rows
            ],
            "page": {"has_more": more, "next_cursor": rows[-1].id if rows and more else None},
        },
        ctx=ctx,
    )


@producer_endpoint("notifications:write")
async def mark_notification_read(ctx: HttpContext, notification_id: str) -> Any:
    row = await Notification.get_or_none(
        environment=ctx.state.producer.environment, id=notification_id
    )
    if row is None:
        raise NotFoundError(f"no notification {notification_id}")
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        await row.save(update_fields=["read_at"])
    return ok({"id": row.id, "read": True}, ctx=ctx)


# ---------------------------------------------------------------------------
# Connections (read-only for producers/consumers)
# ---------------------------------------------------------------------------


@producer_endpoint("connections:read")
async def list_connections(ctx: HttpContext) -> Any:
    q = ctx.query_params
    qs = Connection.filter(environment=ctx.state.producer.environment)
    if q.get("status"):
        qs = qs.filter(status=q["status"])
    rows = await qs.order_by("-connected_at").limit(200)
    return ok(
        {
            "connections": [
                {
                    "id": c.id,
                    "transport": c.transport,
                    "status": c.status,
                    "user_id": c.user_id,
                    "organization_id": c.organization_id,
                    "client": c.client,
                    "subscriptions": c.subscriptions,
                    "events_sent": c.events_sent,
                    "connected_at": _iso(c.connected_at),
                    "disconnected_at": _iso(c.disconnected_at),
                    "duration_seconds": round(c.duration_seconds, 1),
                }
                for c in rows
            ]
        },
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# Realtime tokens
# ---------------------------------------------------------------------------


@producer_endpoint("events:read")
async def issue_realtime_token(ctx: HttpContext) -> Any:
    body = await read_json(ctx) or {}
    key = ctx.state.api_key
    producer = ctx.state.producer
    token, ttl = mint_realtime_token(
        environment=producer.environment,
        user_id=body.get("user_id"),
        organization_id=body.get("organization_id"),
        project_ids=body.get("project_ids"),
        scopes=[s for s in key.scope_list if s in ("system:read",)],
        topic_patterns=body.get("topic_patterns"),
        operator=key.has_scope("system:read"),
        ttl_seconds=body.get("ttl_seconds"),
    )
    return ok(
        {"token": token, "expires_in": ttl, "environment": producer.environment},
        status=201,
        ctx=ctx,
    )


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------


@producer_endpoint()
async def whoami(ctx: HttpContext) -> Any:
    key = ctx.state.api_key
    producer = ctx.state.producer
    return ok(
        {
            "producer": {"id": producer.id, "name": producer.name, "slug": producer.slug},
            "environment": producer.environment,
            "key": {"prefix": key.prefix, "scopes": key.scope_list, "name": key.name},
            "rate_limit": limiter.snapshot(key.prefix),
        },
        ctx=ctx,
    )


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


for _r in (
    Route("/events", handler=publish_events, methods=["POST"], name="v1.events.publish"),
    Route("/events", handler=list_events, methods=["GET"], name="v1.events.list"),
    Route("/events/replay", handler=replay_events, methods=["POST"], name="v1.events.replay"),
    Route("/events/{event_id}", handler=get_event, methods=["GET"], name="v1.events.get"),
    Route("/topics", handler=list_topics, methods=["GET"], name="v1.topics.list"),
    Route("/tasks", handler=list_tasks, methods=["GET"], name="v1.tasks.list"),
    Route("/tasks/{task_id}", handler=get_task, methods=["GET"], name="v1.tasks.get"),
    Route("/notifications", handler=list_notifications, methods=["GET"], name="v1.notifications.list"),
    Route(
        "/notifications/{notification_id}/read",
        handler=mark_notification_read,
        methods=["POST"],
        name="v1.notifications.read",
    ),
    Route("/connections", handler=list_connections, methods=["GET"], name="v1.connections.list"),
    Route("/realtime/tokens", handler=issue_realtime_token, methods=["POST"], name="v1.realtime.token"),
    Route("/whoami", handler=whoami, methods=["GET"], name="v1.whoami"),
):
    router.add_route(_r)
