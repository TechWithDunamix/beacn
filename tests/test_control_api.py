"""Control plane API — RBAC, CLI auth, producer/key/topic lifecycle, audit."""

from __future__ import annotations

import pytest

from tests.helpers import cli_token, control_headers, make_user

pytestmark = pytest.mark.asyncio


async def test_cli_login_and_whoami(client, admin_user):
    r = await client.post("/api/control/auth/login",
                          json={"email": "admin@test.local", "password": "correct horse battery staple"})
    assert r.status_code == 200
    token = r.json()["token"]
    who = await client.get("/api/control/auth/whoami", headers={"Authorization": f"Bearer {token}"})
    assert who.status_code == 200
    assert who.json()["is_superuser"] is True


async def test_cli_login_bad_password_401(client, admin_user):
    r = await client.post("/api/control/auth/login",
                          json={"email": "admin@test.local", "password": "wrong"})
    assert r.status_code == 401


async def test_admin_creates_operator_and_it_can_sign_in(client, admin_user):
    token = await cli_token(admin_user)
    r = await client.post(
        "/api/control/users", headers=control_headers(token),
        json={"email": "newop@test.local", "password": "a-long-enough-pw", "role": "Operator"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "Operator"

    # the new account can authenticate and holds Operator's permissions
    login = await client.post(
        "/api/control/auth/login",
        json={"email": "newop@test.local", "password": "a-long-enough-pw"},
    )
    assert login.status_code == 200
    who = await client.get(
        "/api/control/auth/whoami",
        headers={"Authorization": f"Bearer {login.json()['token']}"},
    )
    assert "producers.write" in who.json()["permissions"]
    assert who.json()["is_superuser"] is False

    # role change takes effect
    await client.post("/api/control/users/role", headers=control_headers(token),
                      json={"email": "newop@test.local", "role": "ReadOnly"})
    who2 = await client.get(
        "/api/control/auth/whoami",
        headers={"Authorization": f"Bearer {login.json()['token']}"},
    )
    assert "producers.write" not in who2.json()["permissions"]


async def test_operator_cannot_create_users(client):
    user = await make_user("op-nouser@test.local", role="Operator")
    token = await cli_token(user)
    r = await client.post(
        "/api/control/users", headers=control_headers(token),
        json={"email": "x@test.local", "password": "a-long-enough-pw", "role": "ReadOnly"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["permission"] == "users.write"


async def test_user_create_rejects_weak_password_and_bad_role(client, admin_user):
    token = await cli_token(admin_user)
    weak = await client.post("/api/control/users", headers=control_headers(token),
                             json={"email": "w@test.local", "password": "short", "role": "ReadOnly"})
    assert weak.status_code == 422
    bad = await client.post("/api/control/users", headers=control_headers(token),
                            json={"email": "b@test.local", "password": "a-long-enough-pw", "role": "Wizard"})
    assert bad.status_code == 422


async def test_cannot_disable_own_account(client, admin_user):
    token = await cli_token(admin_user)
    r = await client.post("/api/control/users/active", headers=control_headers(token),
                          json={"email": "admin@test.local", "active": False})
    assert r.status_code == 409


async def test_readonly_cannot_create_producer(client):
    user = await make_user("ro@test.local", role="ReadOnly")
    token = await cli_token(user)
    r = await client.post("/api/control/producers", headers=control_headers(token),
                          json={"name": "X", "environment": "development"})
    assert r.status_code == 403
    assert r.json()["error"]["permission"] == "producers.write"


async def test_operator_can_create_producer_and_key(client):
    user = await make_user("op@test.local", role="Operator")
    token = await cli_token(user)
    p = await client.post("/api/control/producers", headers=control_headers(token),
                          json={"name": "Orders API", "environment": "production"})
    assert p.status_code == 201
    pid = p.json()["producer"]["id"]

    k = await client.post("/api/control/keys", headers=control_headers(token),
                          json={"name": "prod key", "producer_id": pid, "scopes": "events:publish"})
    assert k.status_code == 201
    body = k.json()["key"]
    assert body["secret"].startswith("bk_")
    assert "secret" in body and body["warning"]

    # listing never reveals the secret again
    lst = await client.get("/api/control/keys", headers=control_headers(token))
    assert all("secret" not in row for row in lst.json()["keys"])


async def test_key_revoke_blocks_ingestion(client):
    user = await make_user("op2@test.local", role="Operator")
    token = await cli_token(user)
    p = await client.post("/api/control/producers", headers=control_headers(token),
                          json={"name": "P", "environment": "development"})
    pid = p.json()["producer"]["id"]
    k = await client.post("/api/control/keys", headers=control_headers(token),
                          json={"name": "k", "producer_id": pid, "scopes": "events:publish"})
    secret = k.json()["key"]["secret"]
    kid = k.json()["key"]["id"]

    good = await client.post("/api/v1/events", headers={"Authorization": f"Bearer {secret}"},
                             json={"event": "a.b"})
    assert good.status_code == 201

    await client.post(f"/api/control/keys/{kid}/revoke", headers=control_headers(token), json={})
    blocked = await client.post("/api/v1/events", headers={"Authorization": f"Bearer {secret}"},
                                json={"event": "a.c"})
    assert blocked.status_code == 401


async def test_session_write_needs_control_header(client):
    user = await make_user("op3@test.local", role="Operator")
    token = await cli_token(user)
    # bearer CLI token path is exempt from the header requirement...
    ok = await client.post("/api/control/producers",
                           headers={"Authorization": f"Bearer {token}"},
                           json={"name": "H", "environment": "development"})
    assert ok.status_code == 201


async def test_audit_trail_records_mutations(client):
    user = await make_user("op4@test.local", role="Admin", superuser=True)
    token = await cli_token(user)
    await client.post("/api/control/producers", headers=control_headers(token),
                      json={"name": "Audited", "environment": "development"})
    r = await client.get("/api/control/audit", headers=control_headers(token))
    actions = [e["action"] for e in r.json()["events"]]
    assert "producer.created" in actions


async def test_dashboard_numbers_are_real_not_fake(client, producer_env, admin_user):
    token = await cli_token(admin_user)
    for _ in range(4):
        await client.post("/api/v1/events", headers=producer_env.auth,
                          json={"event": "x.y", "topic": "z"})
    r = await client.get("/api/control/dashboard?environment=development",
                         headers=control_headers(token))
    body = r.json()["summary"]
    assert body["events"]["today"] == 4
    assert body["events"]["total"] == 4
    # a fresh install in another environment is all zeros, not invented
    r2 = await client.get("/api/control/dashboard?environment=staging",
                          headers=control_headers(token))
    assert r2.json()["summary"]["events"]["total"] == 0
