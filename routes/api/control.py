"""Control-plane JSON API — `/api/control`.

The dashboard is Inertia and does not use this; the CLI does, and so does any
automation. Every mutating route goes through `control_endpoint(...)` which runs
the same RBAC check the dashboard routes use, so the CLI is not an RBAC bypass.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sillo.core.http import HttpContext
from sillo.core.routing import Route, Router
from sillo.responses import json

from app.auth import mint_realtime_token
from app.config import ENVIRONMENTS, config
from app.services import audit, stats
from app.services.ingest import invalidate_persist_cache
from database.models import (
    SCOPES,
    ApiKey,
    AuditEvent,
    Connection,
    Event,
    LoginEvent,
    Producer,
    Subscription,
    Topic,
    User,
    UserSession,
)
from routes.api._common import client_ip, control_endpoint, ok, read_json

router = Router(prefix="/api/control")


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _env(ctx: HttpContext, default: str = "development") -> str:
    value = ctx.query_params.get("environment") or default
    return value if value in ENVIRONMENTS else default


# ---------------------------------------------------------------------------
# Auth (CLI)
# ---------------------------------------------------------------------------


async def cli_login(ctx: HttpContext) -> Any:
    data = await read_json(ctx) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    ip = client_ip(ctx)

    async def refuse(reason: str, user: User | None = None):
        await LoginEvent.create(
            user_id=getattr(user, "pk", None), email=email or "(blank)",
            successful=False, reason=reason, kind="cli", ip=ip,
        )
        return json({"error": {"code": "unauthenticated", "message": "invalid credentials"}}, status_code=401)

    user = await User.get_or_none(email=email)
    if user is None:
        return await refuse("unknown_user")
    if not user.is_active:
        return await refuse("disabled", user)
    if not user.check_password(password):
        return await refuse("bad_password", user)

    token = secrets.token_urlsafe(40)
    await UserSession.create(
        user_id=user.pk,
        key_hash=hashlib.sha256(token.encode()).hexdigest(),
        kind="cli",
        ip=ip,
        label=(data.get("label") or "beacn CLI")[:120],
        expires_at=datetime.now(UTC) + timedelta(days=30),
        last_seen_at=datetime.now(UTC),
    )
    await user.set_last_login()
    await LoginEvent.create(user_id=user.pk, email=email, successful=True, reason="ok", kind="cli", ip=ip)
    return json({"token": token, "user": {"email": user.email, "name": user.name}, "expires_in_days": 30})


@control_endpoint()
async def cli_whoami(ctx: HttpContext) -> Any:
    from app.authz import permissions_of, role_names_of

    actor = ctx.state.actor
    return ok(
        {
            "email": actor.email,
            "name": actor.name,
            "is_superuser": actor.is_superuser,
            "roles": await role_names_of(actor),
            "permissions": sorted(await permissions_of(actor)),
        }
    )


@control_endpoint()
async def cli_logout(ctx: HttpContext) -> Any:
    header = ctx.headers.get("authorization") or ""
    token = header[7:].strip()
    session = await UserSession.get_or_none(key_hash=hashlib.sha256(token.encode()).hexdigest())
    if session is not None:
        session.revoked_at = datetime.now(UTC)
        session.revoked_reason = "signed out from the CLI"
        await session.save()
    return ok({"ok": True})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@control_endpoint("settings.read")
async def dashboard(ctx: HttpContext) -> Any:
    environment = _env(ctx)
    return ok(
        {
            "summary": await stats.dashboard(environment),
            "top_producers": await stats.top_producers(environment),
            "top_topics": await stats.top_topics(environment),
            "recent_events": await stats.recent_events(environment),
            "throughput": await stats.throughput_series(environment),
        }
    )


# ---------------------------------------------------------------------------
# Producers
# ---------------------------------------------------------------------------


def _producer_json(p: Producer) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "slug": p.slug,
        "environment": p.environment,
        "description": p.description,
        "default_source": p.default_source,
        "status": p.status,
        "event_count": p.event_count,
        "last_event_at": _iso(p.last_event_at),
        "created_at": _iso(p.created_at),
    }


@control_endpoint("producers.read")
async def producers_list(ctx: HttpContext) -> Any:
    qs = Producer.all()
    if ctx.query_params.get("environment"):
        qs = qs.filter(environment=ctx.query_params["environment"])
    rows = await qs.order_by("-last_event_at", "name")
    return ok({"producers": [_producer_json(p) for p in rows]})


@control_endpoint("producers.write")
async def producers_create(ctx: HttpContext) -> Any:
    data = await read_json(ctx) or {}
    name = (data.get("name") or "").strip()
    environment = data.get("environment") or "development"
    if not name:
        return json({"error": {"code": "invalid", "message": "name is required"}}, status_code=422)
    if environment not in ENVIRONMENTS:
        return json({"error": {"code": "invalid", "message": f"environment must be one of {ENVIRONMENTS}"}}, status_code=422)
    producer = await Producer.create_for(
        name=name,
        environment=environment,
        slug=(data.get("slug") or None),
        description=(data.get("description") or None),
        default_source=(data.get("default_source") or None),
        created_by_id=getattr(ctx.state.actor, "pk", None),
    )
    await audit.record(
        action="producer.created", actor=ctx.state.actor, origin="cli",
        resource_type="producer", resource_id=producer.id, resource_label=producer.name,
        environment=environment, ip=client_ip(ctx),
    )
    return ok({"producer": _producer_json(producer)}, status=201)


@control_endpoint("producers.write")
async def producers_set_status(ctx: HttpContext, producer_id: str) -> Any:
    producer = await Producer.get_or_none(id=producer_id)
    if producer is None:
        return json({"error": {"code": "not_found", "message": "no such producer"}}, status_code=404)
    data = await read_json(ctx) or {}
    producer.status = "active" if data.get("active", True) else "disabled"
    await producer.save(update_fields=["status"])
    await audit.record(
        action=f"producer.{producer.status}", actor=ctx.state.actor, origin="cli",
        resource_type="producer", resource_id=producer.id, resource_label=producer.name,
        environment=producer.environment, ip=client_ip(ctx),
    )
    return ok({"producer": _producer_json(producer)})


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------


def _key_json(k: ApiKey) -> dict:
    return {
        "id": k.id,
        "name": k.name,
        "prefix": k.prefix,
        "masked": k.masked,
        "environment": k.environment,
        "scopes": k.scope_list,
        "status": k.status,
        "request_count": k.request_count,
        "last_used_at": _iso(k.last_used_at),
        "expires_at": _iso(k.expires_at),
        "created_at": _iso(k.created_at),
    }


@control_endpoint("apikeys.read")
async def keys_list(ctx: HttpContext) -> Any:
    qs = ApiKey.all().prefetch_related("producer")
    if ctx.query_params.get("environment"):
        qs = qs.filter(environment=ctx.query_params["environment"])
    if ctx.query_params.get("producer_id"):
        qs = qs.filter(producer_id=ctx.query_params["producer_id"])
    rows = await qs.order_by("-created_at")
    out = []
    for k in rows:
        row = _key_json(k)
        row["producer"] = k.producer.name if k.producer_id else None
        out.append(row)
    return ok({"keys": out, "available_scopes": list(SCOPES)})


@control_endpoint("apikeys.write")
async def keys_create(ctx: HttpContext) -> Any:
    data = await read_json(ctx) or {}
    producer_id = data.get("producer_id")
    name = (data.get("name") or "").strip()
    if not name or not producer_id:
        return json({"error": {"code": "invalid", "message": "name and producer_id are required"}}, status_code=422)
    producer = await Producer.get_or_none(id=producer_id)
    if producer is None:
        return json({"error": {"code": "not_found", "message": "no such producer"}}, status_code=404)
    days = int(data.get("expires_in_days") or 0)
    key, secret = await ApiKey.issue(
        producer=producer,
        name=name,
        scopes=data.get("scopes") or "events:publish",
        expires_at=datetime.now(UTC) + timedelta(days=days) if days else None,
        created_by_id=getattr(ctx.state.actor, "pk", None),
    )
    await audit.record(
        action="apikey.created", actor=ctx.state.actor, origin="cli",
        resource_type="api_key", resource_id=key.id, resource_label=f"{key.name} ({key.prefix})",
        environment=key.environment, after={"scopes": key.scope_list}, ip=client_ip(ctx),
    )
    row = _key_json(key)
    # The one and only time the full secret leaves the server.
    row["secret"] = secret
    row["warning"] = "This secret is not stored and cannot be shown again."
    return ok({"key": row}, status=201)


@control_endpoint("apikeys.write")
async def keys_revoke(ctx: HttpContext, key_id: str) -> Any:
    key = await ApiKey.get_or_none(id=key_id)
    if key is None:
        return json({"error": {"code": "not_found", "message": "no such key"}}, status_code=404)
    data = await read_json(ctx) or {}
    await key.revoke(reason=(data.get("reason") or "revoked from the control plane"))
    await audit.record(
        action="apikey.revoked", actor=ctx.state.actor, origin="cli",
        resource_type="api_key", resource_id=key.id, resource_label=f"{key.name} ({key.prefix})",
        environment=key.environment, ip=client_ip(ctx),
    )
    return ok({"key": _key_json(key)})


@control_endpoint("apikeys.write")
async def keys_rotate(ctx: HttpContext, key_id: str) -> Any:
    old = await ApiKey.get_or_none(id=key_id).prefetch_related("producer")
    if old is None:
        return json({"error": {"code": "not_found", "message": "no such key"}}, status_code=404)
    new, secret = await ApiKey.issue(
        producer=old.producer, name=old.name, scopes=old.scopes,
        expires_at=old.expires_at, created_by_id=getattr(ctx.state.actor, "pk", None),
    )
    await old.revoke(reason=f"rotated to {new.prefix}")
    await audit.record(
        action="apikey.rotated", actor=ctx.state.actor, origin="cli",
        resource_type="api_key", resource_id=new.id, resource_label=f"{new.name} ({new.prefix})",
        environment=new.environment, before={"prefix": old.prefix}, after={"prefix": new.prefix},
        ip=client_ip(ctx),
    )
    row = _key_json(new)
    row["secret"] = secret
    row["warning"] = "This secret is not stored and cannot be shown again."
    return ok({"key": row})


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------


def _topic_json(t: Topic) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "environment": t.environment,
        "visibility": t.visibility,
        "persist": t.persist,
        "retention_hours": t.retention_hours,
        "description": t.description,
        "event_count": t.event_count,
        "subscriber_count": t.subscriber_count,
        "producer_count": t.producer_count,
        "last_event_at": _iso(t.last_event_at),
        "created_at": _iso(t.created_at),
    }


@control_endpoint("topics.read")
async def topics_list(ctx: HttpContext) -> Any:
    qs = Topic.all()
    if ctx.query_params.get("environment"):
        qs = qs.filter(environment=ctx.query_params["environment"])
    rows = await qs.order_by("-event_count", "name")
    return ok({"topics": [_topic_json(t) for t in rows]})


@control_endpoint("topics.write")
async def topics_upsert(ctx: HttpContext) -> Any:
    data = await read_json(ctx) or {}
    name = (data.get("name") or "").strip()
    environment = data.get("environment") or "development"
    if not name:
        return json({"error": {"code": "invalid", "message": "name is required"}}, status_code=422)
    row = await Topic.get_or_none(environment=environment, name=name)
    created = row is None
    if row is None:
        from domain.ids import new_ulid

        row = Topic(id=new_ulid(), environment=environment, name=name)
    for field in ("visibility", "description"):
        if field in data and data[field] is not None:
            setattr(row, field, data[field])
    if "persist" in data:
        row.persist = bool(data["persist"])
    if "retention_hours" in data:
        row.retention_hours = int(data["retention_hours"]) if data["retention_hours"] else None
    row.created_by_id = row.created_by_id or getattr(ctx.state.actor, "pk", None)
    await row.save()
    invalidate_persist_cache()
    await audit.record(
        action="topic.created" if created else "topic.updated", actor=ctx.state.actor, origin="cli",
        resource_type="topic", resource_id=row.id, resource_label=row.name,
        environment=environment, after=_topic_json(row), ip=client_ip(ctx),
    )
    return ok({"topic": _topic_json(row)}, status=201 if created else 200)


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


@control_endpoint("connections.read")
async def connections_list(ctx: HttpContext) -> Any:
    qs = Connection.all()
    if ctx.query_params.get("environment"):
        qs = qs.filter(environment=ctx.query_params["environment"])
    if ctx.query_params.get("status"):
        qs = qs.filter(status=ctx.query_params["status"])
    rows = await qs.order_by("-connected_at").limit(300)
    return ok(
        {
            "connections": [
                {
                    "id": c.id,
                    "environment": c.environment,
                    "transport": c.transport,
                    "instance": c.instance,
                    "status": c.status,
                    "user_id": c.user_id,
                    "organization_id": c.organization_id,
                    "client": c.client,
                    "ip": c.ip,
                    "subscriptions": c.subscriptions,
                    "events_sent": c.events_sent,
                    "events_dropped": c.events_dropped,
                    "connected_at": _iso(c.connected_at),
                    "last_heartbeat_at": _iso(c.last_heartbeat_at),
                    "disconnected_at": _iso(c.disconnected_at),
                    "duration_seconds": round(c.duration_seconds, 1),
                }
                for c in rows
            ]
        }
    )


@control_endpoint("connections.write")
async def connection_terminate(ctx: HttpContext, connection_id: str) -> Any:
    row = await Connection.get_or_none(id=connection_id)
    if row is None:
        return json({"error": {"code": "not_found", "message": "no such connection"}}, status_code=404)

    from realtime import get_realtime

    rt = get_realtime()
    session = rt.sessions.get(connection_id)
    if session is not None:
        await session.shutdown(1000, "terminated by operator")
        terminated = "immediate"
    else:
        row.terminate_requested_at = datetime.now(UTC)
        await row.save(update_fields=["terminate_requested_at"])
        terminated = "requested"  # the owning instance drops it on its next sweep

    await audit.record(
        action="connection.terminated", actor=ctx.state.actor, origin="cli",
        resource_type="connection", resource_id=connection_id, resource_label=connection_id,
        environment=row.environment, ip=client_ip(ctx),
    )
    return ok({"connection_id": connection_id, "termination": terminated})


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


@control_endpoint("subscriptions.read")
async def subscriptions_list(ctx: HttpContext) -> Any:
    qs = Subscription.all()
    if ctx.query_params.get("environment"):
        qs = qs.filter(environment=ctx.query_params["environment"])
    rows = await qs.order_by("-created_at")
    return ok(
        {
            "subscriptions": [
                {
                    "id": s.id,
                    "environment": s.environment,
                    "topic": s.topic,
                    "kind": s.kind,
                    "label": s.label,
                    "endpoint": s.endpoint,
                    "cursor": s.cursor,
                    "status": s.status,
                    "created_at": _iso(s.created_at),
                }
                for s in rows
            ]
        }
    )


@control_endpoint("subscriptions.write")
async def subscriptions_create(ctx: HttpContext) -> Any:
    data = await read_json(ctx) or {}
    if not data.get("topic"):
        return json({"error": {"code": "invalid", "message": "topic is required"}}, status_code=422)
    sub = await Subscription.create_for(
        environment=data.get("environment") or "development",
        topic=data["topic"],
        kind=data.get("kind") or "service",
        label=data.get("label"),
        endpoint=data.get("endpoint"),
    )
    await audit.record(
        action="subscription.created", actor=ctx.state.actor, origin="cli",
        resource_type="subscription", resource_id=sub.id, resource_label=sub.topic,
        environment=sub.environment, ip=client_ip(ctx),
    )
    return ok({"subscription_id": sub.id}, status=201)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@control_endpoint("audit.read")
async def audit_list(ctx: HttpContext) -> Any:
    qs = AuditEvent.all()
    if ctx.query_params.get("action"):
        qs = qs.filter(action=ctx.query_params["action"])
    if ctx.query_params.get("resource_type"):
        qs = qs.filter(resource_type=ctx.query_params["resource_type"])
    if ctx.query_params.get("cursor"):
        qs = qs.filter(id__lt=ctx.query_params["cursor"])
    limit = max(1, min(200, int(ctx.query_params.get("limit") or 100)))
    rows = await qs.order_by("-id").limit(limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    return ok(
        {
            "events": [
                {
                    "id": e.id,
                    "action": e.action,
                    "actor": e.actor_label,
                    "origin": e.origin,
                    "resource_type": e.resource_type,
                    "resource_id": e.resource_id,
                    "resource_label": e.resource_label,
                    "environment": e.environment,
                    "before": e.before,
                    "after": e.after,
                    "at": _iso(e.created_at),
                }
                for e in rows
            ],
            "page": {"has_more": more, "next_cursor": rows[-1].id if rows and more else None},
        }
    )


# ---------------------------------------------------------------------------
# Users & roles
# ---------------------------------------------------------------------------


@control_endpoint("users.read")
async def users_list(ctx: HttpContext) -> Any:
    from app.authz import CATALOGUE, ROLES

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
    return ok({"users": out, "roles": list(ROLES), "permissions": CATALOGUE})


@control_endpoint("users.write")
async def users_create(ctx: HttpContext) -> Any:
    """Create an operator account and assign it a role.

    Uses `sillo.users.commands` — the framework's account operations — for the
    row itself, then BEACN's group assignment on top. The same code the
    `beacn user create` command runs.
    """
    from sillo.users import commands as accounts

    from app.authz import ROLES, ensure_roles

    await ensure_roles()
    data = await read_json(ctx) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "ReadOnly").strip()
    superuser = bool(data.get("superuser"))

    if "@" not in email:
        return json({"error": {"code": "invalid", "message": "a valid email is required"}}, status_code=422)
    if role not in ROLES:
        return json(
            {"error": {"code": "invalid", "message": f"role must be one of {', '.join(ROLES)}"}},
            status_code=422,
        )
    if not superuser and len(password) < 10:
        return json(
            {"error": {"code": "invalid", "message": "password must be at least 10 characters"}},
            status_code=422,
        )

    create = accounts.create_admin if superuser else accounts.create_user
    try:
        user = await create(email, email, password, model=User)
    except ValueError as error:
        return json({"error": {"code": "conflict", "message": str(error)}}, status_code=409)

    from sillo.permissions import Group

    group = await Group.get_or_none(name=role)
    if group is not None:
        for existing in await Group.of_user(user):
            await existing.remove_user(user)
        await group.add_user(user)

    await audit.record(
        action="user.created", actor=ctx.state.actor, origin="cli",
        resource_type="user", resource_id=user.pk, resource_label=user.email,
        after={"role": role, "superuser": superuser}, ip=client_ip(ctx),
    )
    return ok(
        {"id": user.pk, "email": user.email, "role": role, "superuser": superuser},
        status=201,
    )


@control_endpoint("users.write")
async def users_set_active(ctx: HttpContext) -> Any:
    data = await read_json(ctx) or {}
    user = await User.get_or_none(email=(data.get("email") or "").strip().lower())
    if user is None:
        return json({"error": {"code": "not_found", "message": "no such user"}}, status_code=404)
    if user.pk == getattr(ctx.state.actor, "pk", None):
        return json({"error": {"code": "conflict", "message": "you cannot disable your own account"}}, status_code=409)
    active = bool(data.get("active", True))
    if active:
        await user.enable()
    else:
        await user.disable(reason=(data.get("reason") or "disabled from the control plane"))
    await audit.record(
        action="user.enabled" if active else "user.disabled", actor=ctx.state.actor, origin="cli",
        resource_type="user", resource_id=user.pk, resource_label=user.email, ip=client_ip(ctx),
    )
    return ok({"email": user.email, "active": user.is_active})


@control_endpoint("users.write")
async def users_set_role(ctx: HttpContext) -> Any:
    from sillo.permissions import Group

    data = await read_json(ctx) or {}
    user = await User.get_or_none(email=(data.get("email") or "").strip().lower())
    role = await Group.get_or_none(name=(data.get("role") or "").strip())
    if user is None or role is None:
        return json({"error": {"code": "not_found", "message": "no such user or role"}}, status_code=404)
    before = sorted(await user.get_groups())
    for existing in await Group.of_user(user):
        await existing.remove_user(user)
    await role.add_user(user)
    await audit.record(
        action="user.role_changed", actor=ctx.state.actor, origin="cli",
        resource_type="user", resource_id=user.pk, resource_label=user.email,
        before={"roles": before}, after={"roles": [role.name]}, ip=client_ip(ctx),
    )
    return ok({"email": user.email, "role": role.name})


# ---------------------------------------------------------------------------
# Realtime token (operator)
# ---------------------------------------------------------------------------


@control_endpoint("events.read")
async def operator_realtime_token(ctx: HttpContext) -> Any:
    data = await read_json(ctx) or {}
    environment = data.get("environment") or "development"
    token, ttl = mint_realtime_token(
        environment=environment,
        scopes=["system:read"],
        operator=True,
        ttl_seconds=data.get("ttl_seconds"),
    )
    return ok({"token": token, "expires_in": ttl, "environment": environment})


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


async def health(ctx: HttpContext) -> Any:
    from realtime import get_realtime

    checks: dict[str, Any] = {"app": config.app_name, "env": config.app_env}
    healthy = True
    try:
        await Event.all().limit(1).count()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = f"failed: {exc}"
        healthy = False
    checks["bus"] = await get_realtime().health()
    if not checks["bus"].get("ok") and config.bus_backend == "redis":
        # degraded, not dead — Redis-optional by design
        checks["bus_note"] = "degraded to local-only fanout"
    return json(checks, status_code=200 if healthy else 503)


for _r in (
    Route("/auth/login", handler=cli_login, methods=["POST"], name="control.login"),
    Route("/auth/logout", handler=cli_logout, methods=["POST"], name="control.logout"),
    Route("/auth/whoami", handler=cli_whoami, methods=["GET"], name="control.whoami"),
    Route("/dashboard", handler=dashboard, methods=["GET"], name="control.dashboard"),
    Route("/producers", handler=producers_list, methods=["GET"], name="control.producers"),
    Route("/producers", handler=producers_create, methods=["POST"], name="control.producers.create"),
    Route("/producers/{producer_id}/status", handler=producers_set_status, methods=["POST"], name="control.producers.status"),
    Route("/keys", handler=keys_list, methods=["GET"], name="control.keys"),
    Route("/keys", handler=keys_create, methods=["POST"], name="control.keys.create"),
    Route("/keys/{key_id}/revoke", handler=keys_revoke, methods=["POST"], name="control.keys.revoke"),
    Route("/keys/{key_id}/rotate", handler=keys_rotate, methods=["POST"], name="control.keys.rotate"),
    Route("/topics", handler=topics_list, methods=["GET"], name="control.topics"),
    Route("/topics", handler=topics_upsert, methods=["POST"], name="control.topics.upsert"),
    Route("/connections", handler=connections_list, methods=["GET"], name="control.connections"),
    Route("/connections/{connection_id}/terminate", handler=connection_terminate, methods=["POST"], name="control.connections.terminate"),
    Route("/subscriptions", handler=subscriptions_list, methods=["GET"], name="control.subscriptions"),
    Route("/subscriptions", handler=subscriptions_create, methods=["POST"], name="control.subscriptions.create"),
    Route("/audit", handler=audit_list, methods=["GET"], name="control.audit"),
    Route("/users", handler=users_list, methods=["GET"], name="control.users"),
    Route("/users", handler=users_create, methods=["POST"], name="control.users.create"),
    Route("/users/active", handler=users_set_active, methods=["POST"], name="control.users.active"),
    Route("/users/role", handler=users_set_role, methods=["POST"], name="control.users.role"),
    Route("/realtime/token", handler=operator_realtime_token, methods=["POST"], name="control.realtime.token"),
    Route("/health", handler=health, methods=["GET"], name="control.health"),
):
    router.add_route(_r)
