"""Signing in and out — the only unguarded pages, and the only place a
`UserSession` row is created."""

from __future__ import annotations

import contextlib
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from sillo.auth.session_auth import login as session_login
from sillo.auth.session_auth import logout as session_logout
from sillo.core.http import HttpContext
from sillo.responses import redirect
from sillo_inertia import render, set_errors, set_flash

from app.config import config
from app.services import audit
from database.models import LoginEvent, User, UserSession
from routes.web._kit import client_ip, form, public, session_is_live

__all__ = ["login", "login_submit", "logout"]


@public
async def login(ctx: HttpContext) -> Any:
    """The sign-in screen.

    An already-signed-in visitor is sent to the dashboard — but only if their
    session is also *live*. The framework session cookie can outlive the
    `UserSession` row behind it (the row was revoked, expired, or the database
    was rebuilt). Redirecting such a visitor to `/` produced a redirect loop:
    the dashboard gate bounced them back here for a dead session, and this
    handler bounced them to `/` for a live cookie. So a stale identity is
    cleared here and the form is rendered.
    """
    try:
        authenticated = bool(getattr(ctx.user, "is_authenticated", False))
    except Exception:  # noqa: BLE001
        authenticated = False

    if authenticated and await session_is_live(ctx):
        return redirect("/")
    if authenticated:
        # Live cookie, dead session — break the loop.
        session_logout(ctx)
        _forget_session_key(ctx)

    return await render("auth/Login", {"app_name": config.app_name})


def _forget_session_key(ctx: HttpContext) -> None:
    """Drop `beacn_session_key` from the session. `Session` has `__delitem__`
    but no `pop`, so this is the safe spelling."""
    session = getattr(ctx, "session", None)
    if session is not None:
        with contextlib.suppress(Exception):
            del session["beacn_session_key"]


@public
async def login_submit(ctx: HttpContext) -> Any:
    data = await form(ctx)
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    ip = client_ip(ctx)
    agent = ctx.headers.get("user-agent")

    async def refuse(reason: str, user: User | None = None) -> Any:
        await LoginEvent.create(
            user_id=getattr(user, "pk", None), email=email or "(blank)", successful=False,
            reason=reason, kind="web", ip=ip, user_agent=(agent or "")[:400] or None,
        )
        set_errors(ctx, {"email": "Those credentials do not match our records."})
        return redirect("/login")

    if not email or not password:
        return await refuse("missing_fields")
    user = await User.get_or_none(email=email)
    if user is None:
        return await refuse("unknown_user")
    if not user.is_active:
        return await refuse("disabled", user)
    if not user.check_password(password):
        return await refuse("bad_password", user)

    session_login(ctx, user)
    raw_key = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw_key.encode()).hexdigest()
    ctx.session["beacn_session_key"] = digest
    await UserSession.create(
        user_id=user.pk, key_hash=digest, kind="web", ip=ip,
        user_agent=(agent or "")[:400] or None,
        expires_at=datetime.now(UTC) + timedelta(seconds=config.session_lifetime),
        last_seen_at=datetime.now(UTC),
    )
    await user.set_last_login()
    await LoginEvent.create(
        user_id=user.pk, email=email, successful=True, reason="ok", kind="web", ip=ip,
        user_agent=(agent or "")[:400] or None,
    )
    await audit.record(
        action="user.signed_in", actor=user, origin="web", resource_type="user",
        resource_id=user.pk, resource_label=user.email, ip=ip,
    )
    return redirect("/")


@public
async def logout(ctx: HttpContext) -> Any:
    key = ctx.session.get("beacn_session_key") if hasattr(ctx, "session") else None
    if key:
        row = await UserSession.get_or_none(key_hash=key)
        if row is not None:
            row.revoked_at = datetime.now(UTC)
            row.revoked_reason = "signed out"
            await row.save()
    session_logout(ctx)
    _forget_session_key(ctx)
    set_flash(ctx, "success", "You have been signed out.")
    return redirect("/login")
