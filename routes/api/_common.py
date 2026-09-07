"""Shared plumbing for the JSON API.

Two decorators, two audiences:

* `producer_endpoint(*scopes)` — authenticates an **API key**, checks scopes,
  and injects `ctx.state.api_key` / `ctx.state.producer`. This is the ingestion
  and consumer surface.
* `control_endpoint(*permissions)` — authenticates a **control-plane actor** (a
  browser session or a CLI bearer token) and runs the RBAC `require` check.

Both translate `domain.errors.BeacnError` into a consistent envelope:

    {"error": {"code": "...", "message": "...", "details": ...}}
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sillo.core.http import HttpContext
from sillo.responses import json

from app.auth import require_scope, resolve_api_key
from app.authz import PermissionDenied, require
from domain.errors import AuthenticationError, BeacnError

REQUEST_ID_HEADER = "x-request-id"
CORRELATION_HEADER = "x-correlation-id"


def client_ip(ctx: HttpContext) -> str | None:
    fwd = ctx.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    client = getattr(ctx, "client", None)
    return getattr(client, "host", None) if client else None


def _error(exc: BeacnError, ctx: HttpContext | None = None) -> Any:
    headers = {}
    if getattr(exc, "retry_after", None):
        headers["Retry-After"] = str(exc.retry_after)
    if ctx is not None:
        rid = ctx.headers.get(REQUEST_ID_HEADER)
        if rid:
            headers["X-Request-Id"] = rid
    return json({"error": exc.to_dict()}, status_code=exc.status, headers=headers or None)


async def read_json(ctx: HttpContext) -> Any:
    try:
        return await ctx.json
    except Exception as exc:  # noqa: BLE001
        raise BeacnError("request body is not valid JSON", code="invalid") from exc


def enforce_size(ctx: HttpContext, limit: int) -> None:
    raw = ctx.headers.get("content-length")
    if raw and raw.isdigit() and int(raw) > limit:
        from domain.errors import PayloadTooLargeError

        raise PayloadTooLargeError(f"request body exceeds {limit} bytes")


def producer_endpoint(*scopes: str) -> Callable:
    def decorate(handler: Callable) -> Callable:
        async def wrapper(ctx: HttpContext, **kwargs: Any) -> Any:
            try:
                key, producer = await resolve_api_key(
                    ctx.headers.get("authorization"), ip=client_ip(ctx)
                )
                for scope in scopes:
                    require_scope(key, scope)
                ctx.state.api_key = key
                ctx.state.producer = producer
                return await handler(ctx, **kwargs)
            except BeacnError as exc:
                return _error(exc, ctx)

        wrapper.__name__ = handler.__name__
        wrapper._scopes = scopes
        return wrapper

    return decorate


async def control_actor(ctx: HttpContext):
    """A signed-in operator, from a session cookie or a CLI bearer token."""
    user = None
    try:
        user = ctx.user
    except Exception:  # noqa: BLE001
        user = None
    if user is not None and getattr(user, "is_authenticated", False):
        # Session-cookie auth on a state-changing API needs a CSRF defence.
        # `/api/**` is exempt from the token middleware (it is a bearer API),
        # so the dashboard's XHR client proves same-origin intent with a custom
        # header instead — a header a cross-site form cannot set without a CORS
        # preflight, which our CORS config only grants the app's own origin.
        method = getattr(ctx, "method", "GET").upper()
        if method not in ("GET", "HEAD", "OPTIONS") and not ctx.headers.get("x-beacn-control"):
            raise AuthenticationError("missing X-BEACN-Control header on a session-authenticated write")
        return user

    header = ctx.headers.get("authorization") or ""
    if header.lower().startswith("bearer ") and not header[7:].strip().startswith("bk_"):
        from database.models import UserSession

        token = header[7:].strip()
        digest = hashlib.sha256(token.encode()).hexdigest()
        session = await UserSession.get_or_none(key_hash=digest)
        if session is not None and session.is_live:
            await session.fetch_related("user")
            if session.user is not None and session.user.is_active:
                session.last_seen_at = datetime.now(UTC)
                await session.save(update_fields=["last_seen_at"])
                return session.user
    raise AuthenticationError("authentication required")


def control_endpoint(*permissions: str) -> Callable:
    def decorate(handler: Callable) -> Callable:
        async def wrapper(ctx: HttpContext, **kwargs: Any) -> Any:
            try:
                actor = await control_actor(ctx)
                await require(actor, *permissions)
                ctx.state.actor = actor
                return await handler(ctx, **kwargs)
            except PermissionDenied as exc:
                return json(
                    {"error": {"code": "forbidden", "message": str(exc), "permission": exc.permission}},
                    status_code=403,
                )
            except BeacnError as exc:
                return _error(exc, ctx)

        wrapper.__name__ = handler.__name__
        return wrapper

    return decorate


def ok(payload: dict, status: int = 200, ctx: HttpContext | None = None) -> Any:
    headers = None
    if ctx is not None:
        rid = ctx.headers.get(REQUEST_ID_HEADER)
        if rid:
            headers = {"X-Request-Id": rid}
    return json(payload, status_code=status, headers=headers)
