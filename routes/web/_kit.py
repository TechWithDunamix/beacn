"""The dashboard's route guard, and the decorators that apply it.

Every dashboard route runs the same checks in order:

    1. signed in?                 → /login
    2. is the session still live? → /login  (UserSession revocation)
    3. permission for this route  → 403 page, or a flash-back for an action

The guard is attached as the route's `auth=`, not as a handler wrapper, so
`route.auth` is discoverable — a test asserts every dashboard route has one.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from sillo.auth import useAuth
from sillo.auth.exceptions import AuthenticationFailed
from sillo.auth.exceptions import PermissionDenied as AuthPermissionDenied
from sillo.core.http import HttpContext
from sillo.responses import redirect
from sillo_inertia import back, render, set_flash

from app.authz import PermissionDenied, require

GATE_ATTR = "_beacn_gate"

__all__ = [
    "GATE_ATTR",
    "DashboardGate",
    "action",
    "client_ip",
    "form",
    "page",
    "public",
    "session_is_live",
]


class DashboardGate(useAuth):
    def __init__(self, *permissions: str, is_action: bool = False) -> None:
        super().__init__(required=True)
        self.permissions = permissions
        self.is_action = is_action

    async def authenticate(self, ctx: HttpContext) -> bool:  # type: ignore[override]
        user = _user_or_none(ctx)
        if user is None:
            raise AuthenticationFailed("Sign in to continue.")
        if not await session_is_live(ctx):
            raise AuthenticationFailed("This session has been revoked.")
        ctx.state.auth_user = user
        if self.permissions:
            try:
                await require(user, *self.permissions)
            except PermissionDenied as error:
                ctx.state.missing_permission = error.permission
                raise AuthPermissionDenied(error.permission) from error
        return True


def _user_or_none(ctx: HttpContext) -> Any | None:
    try:
        user = ctx.user
    except Exception:  # noqa: BLE001
        return None
    return user if getattr(user, "is_authenticated", False) else None


async def session_is_live(ctx: HttpContext) -> bool:
    """Whether the `UserSession` row behind this cookie is still valid.

    A request whose session was never registered (made before this tracking
    existed, or in a test that signs in directly) is allowed through — failing
    closed here would log everyone out. A row that exists but is revoked or
    expired returns False, which is what makes "disable operator" and "sign
    out" take effect before the cookie's own expiry.
    """
    session = getattr(ctx, "session", None)
    if session is None:
        return True
    key = session.get("beacn_session_key")
    if not key:
        return True
    from database.models import UserSession

    row = await UserSession.get_or_none(key_hash=key)
    return row is None or row.is_live


async def _unauthorized(ctx: HttpContext) -> Any:
    if ctx.headers.get("X-Inertia", "").lower() == "true":
        from sillo_inertia import location

        return location("/login")
    return redirect("/login")


async def _forbidden(ctx: HttpContext) -> Any:
    permission = getattr(ctx.state, "missing_permission", None)
    if getattr(ctx.state, "is_action", None):
        set_flash(ctx, "error", f"You do not have permission to do that ({permission}).")
        return back(fallback="/", ctx=ctx)
    return await render("errors/Forbidden", {"permission": permission}, status_code=403, ctx=ctx)


def page(*permissions: str) -> Callable[..., Any]:
    def decorate(handler: Callable[..., Any]) -> Callable[..., Any]:
        gate = DashboardGate(*permissions)
        gate.unauthorized = _unauthorized
        gate.forbidden = _forbidden
        setattr(handler, GATE_ATTR, gate)
        return handler

    return decorate


def action(*permissions: str) -> Callable[..., Any]:
    def decorate(handler: Callable[..., Any]) -> Callable[..., Any]:
        gate = DashboardGate(*permissions, is_action=True)
        gate.unauthorized = _unauthorized

        async def forbidden(ctx: HttpContext) -> Any:
            ctx.state.is_action = True
            return await _forbidden(ctx)

        gate.forbidden = forbidden

        @functools.wraps(handler)
        async def wrapper(ctx: HttpContext, *args: Any, **kwargs: Any) -> Any:
            ctx.state.is_action = True
            return await handler(ctx, *args, **kwargs)

        setattr(wrapper, GATE_ATTR, gate)
        return wrapper

    return decorate


def public(handler: Callable[..., Any]) -> Callable[..., Any]:
    setattr(handler, GATE_ATTR, None)
    handler._beacn_public = True
    return handler


async def form(ctx: HttpContext) -> dict[str, Any]:
    content_type = (ctx.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            return dict(await ctx.json)
        except ValueError:
            return {}
    try:
        data = await ctx.form
    except ValueError:
        return {}
    return {key: data[key] for key in data}


def client_ip(ctx: HttpContext) -> str | None:
    forwarded = ctx.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    client = getattr(ctx, "client", None)
    return getattr(client, "host", None)
