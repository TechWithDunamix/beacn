"""Every dashboard page renders server-side without error for an admin."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio

PAGES = [
    "/", "/events", "/topics", "/connections", "/tasks",
    "/notifications", "/producers", "/api-keys", "/users", "/audit", "/settings",
]


async def _web_login(client, email: str) -> None:
    # Prime the CSRF cookie, then echo it back in the header the middleware wants.
    await client.get("/login")
    token = client.cookies.get("XSRF-TOKEN")
    r = await client.post(
        "/login",
        data={"email": email, "password": "correct horse battery staple"},
        headers={
            "content-type": "application/x-www-form-urlencoded",
            **({"X-XSRF-TOKEN": token} if token else {}),
        },
    )
    assert r.status_code in (302, 303), f"login -> {r.status_code}: {r.text[:200]}"


@pytest.fixture
async def signed_in(client, admin_user):
    await _web_login(client, "admin@test.local")
    return client


async def test_all_pages_render(signed_in, producer_env):
    # give a few pages something real to show
    for i in range(3):
        await signed_in.post(
            "/api/v1/events", headers=producer_env.auth,
            json={"event": "task.completed", "topic": "tasks", "data": {"task_id": f"t{i}", "name": "x"}},
        )
    for path in PAGES:
        r = await signed_in.get(path, headers={"X-Inertia": "true", "X-Inertia-Version": ""})
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:300]}"
        body = r.json()
        assert body["component"], path


async def test_event_detail_page_renders(signed_in, producer_env):
    pub = await signed_in.post(
        "/api/v1/events", headers=producer_env.auth,
        json={"event": "payment.completed", "topic": "payments", "data": {"amount": 1}},
    )
    event_id = pub.json()["events"][0]["id"]
    r = await signed_in.get(
        f"/events/{event_id}?env=development",
        headers={"X-Inertia": "true", "X-Inertia-Version": ""},
    )
    assert r.status_code == 200
    assert r.json()["props"]["event"]["id"] == event_id


async def test_stale_session_does_not_loop_login_and_dashboard(client, admin_user):
    """A live cookie whose UserSession row is revoked must not redirect-loop.

    The dashboard gate bounces such a request to /login; /login must NOT bounce
    it back to / (it used to, because the framework cookie still looked
    authenticated). Regression for ERR_TOO_MANY_REDIRECTS.
    """
    from datetime import UTC, datetime

    from database.models import UserSession

    await _web_login(client, "admin@test.local")

    # while signed in, / works
    ok = await client.get("/", headers={"X-Inertia": "true", "X-Inertia-Version": ""})
    assert ok.status_code == 200

    # revoke every session for this user, as `beacn user disable` / logout would
    await UserSession.all().update(revoked_at=datetime.now(UTC), revoked_reason="test")

    # / now bounces to /login (Inertia -> 409 with a location, browser -> 302)
    dash = await client.get("/", headers={"X-Inertia": "true", "X-Inertia-Version": ""})
    assert dash.status_code in (302, 409)

    # /login renders the form — it does NOT redirect to /
    login = await client.get("/login")
    assert login.status_code == 200, f"/login -> {login.status_code} (redirect loop)"
    assert "auth/Login" in login.text or "Login" in login.text


async def test_pages_gated_for_readonly(client):
    from tests.helpers import make_user

    await make_user("ro@test.local", role="ReadOnly")
    await _web_login(client, "ro@test.local")
    # ReadOnly holds every *.read permission, so pages render...
    r = await client.get("/producers", headers={"X-Inertia": "true", "X-Inertia-Version": ""})
    assert r.status_code == 200
    # ...but a write endpoint refuses.
    from tests.helpers import cli_token, control_headers

    ro = await make_user("ro2@test.local", role="ReadOnly")
    token = await cli_token(ro)
    w = await client.post(
        "/api/control/producers", headers=control_headers(token),
        json={"name": "X", "environment": "development"},
    )
    assert w.status_code == 403
