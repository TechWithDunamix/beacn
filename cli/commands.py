"""The `beacn` command set."""

from __future__ import annotations

import asyncio
import json as jsonlib
from typing import Any

from sillo.console import Argument, Command, Flag, Option

from cli.client import ApiClient, CliError, clear_token, save_token

__all__ = ["COMMANDS"]


# --------------------------------------------------------------------------
# base classes
# --------------------------------------------------------------------------


#: Read a password from here when there is no terminal (CI seeding an account).
#: `SILLO_PASSWORD` is honoured too, so scripts written against the framework's
#: own `user:*` commands keep working.
PASSWORD_ENV = ("BEACN_PASSWORD", "SILLO_PASSWORD")


class _Base(Command):
    def emit(self, payload: Any) -> None:
        self.line(jsonlib.dumps(payload, indent=2, default=str))

    @property
    def json_out(self) -> bool:
        return bool(self.flag("json"))

    def read_password(self, question: str = "Password", *, confirm: bool = True) -> str:
        """Hidden prompt, or an env var when the shell is not interactive.

        Mirrors `sillo.users.console.UserCommand.read_password` so the BEACN
        account commands behave exactly like the framework's built-in ones.
        """
        import os

        for name in PASSWORD_ENV:
            value = os.environ.get(name)
            if value:
                return value
        if not self.prompt.interactive:
            self.fail(
                f"No terminal to read a password from. Set {PASSWORD_ENV[0]} instead."
            )
        return self.secret(question, confirm=confirm)


class ApiCommand(_Base):
    arguments = [Flag("json", help="Machine-readable JSON output.")]

    def run(self, api: ApiClient) -> int | None:  # pragma: no cover - overridden
        raise NotImplementedError

    def handle(self) -> int:
        try:
            return self.run(ApiClient()) or 0
        except CliError as exc:
            for line in str(exc).splitlines():
                self.line(line)
            return 1


class LocalCommand(_Base):
    arguments = [Flag("json", help="Machine-readable JSON output.")]

    async def run_async(self) -> int | None:  # pragma: no cover - overridden
        raise NotImplementedError

    def handle(self) -> int:
        try:
            return asyncio.run(self._with_db()) or 0
        except CliError as exc:
            self.line(str(exc))
            return 1

    async def _with_db(self) -> int | None:
        from database.config import database

        async with database():
            return await self.run_async()


# --------------------------------------------------------------------------
# session
# --------------------------------------------------------------------------


class Login(_Base):
    name = "login"
    help = "Sign in and store a CLI token."
    arguments = [
        Argument("email", help="Operator email."),
        Option("url", default="", help="BEACN base URL (default $BEACN_URL or localhost:8000)."),
        Flag("json"),
    ]

    def handle(self) -> int:
        import os
        from getpass import getpass

        import httpx

        url = (self.option("url") or os.getenv("BEACN_URL") or "http://localhost:8000").rstrip("/")
        email = self.argument("email")
        password = getpass("Password: ")
        try:
            resp = httpx.post(f"{url}/api/control/auth/login",
                              json={"email": email, "password": password}, timeout=30.0)
        except httpx.HTTPError as exc:
            self.line(f"cannot reach {url}: {exc}")
            return 1
        if resp.status_code != 200:
            self.line("Those credentials do not match our records.")
            return 1
        data = resp.json()
        path = save_token(url, data["token"], email)
        self.line(f"Signed in as {data['user']['name']} — token stored at {path}")
        return 0


class Logout(ApiCommand):
    name = "logout"
    help = "Revoke the stored CLI token."

    def run(self, api: ApiClient) -> int:
        try:
            api.post("/api/control/auth/logout")
        except CliError:
            pass
        clear_token()
        self.line("Signed out.")
        return 0


class Whoami(ApiCommand):
    name = "whoami"
    help = "Show the signed-in operator and their permissions."

    def run(self, api: ApiClient) -> int:
        me = api.get("/api/control/auth/whoami")
        if self.json_out:
            self.emit(me)
            return 0
        self.line(f"{me['name']} <{me['email']}>  superuser={me['is_superuser']}")
        self.line(f"roles: {', '.join(me['roles']) or '(none)'}")
        return 0


# --------------------------------------------------------------------------
# local
# --------------------------------------------------------------------------


class Serve(_Base):
    name = "serve"
    help = "Run the BEACN server with uvicorn."
    arguments = [
        Option("host", default="127.0.0.1"),
        Option("port", default="8000"),
        Flag("reload", help="Auto-reload on code changes (development)."),
        Flag("json"),
    ]

    def handle(self) -> int:
        import uvicorn

        uvicorn.run(
            "app.main:app",
            host=self.option("host"),
            port=int(self.option("port")),
            reload=self.flag("reload"),
        )
        return 0


class Migrate(LocalCommand):
    name = "migrate"
    help = "Create missing tables and seed the permission catalogue."

    async def run_async(self) -> int:
        from tortoise import Tortoise

        from app.authz import ensure_roles

        await Tortoise.generate_schemas(safe=True)
        await ensure_roles()
        self.line("Schema is up to date; roles seeded.")
        return 0


class Doctor(LocalCommand):
    name = "doctor"
    help = "Check configuration, database and the event bus."

    async def run_async(self) -> int:
        from app.config import check_production, config
        from database.models import Event
        from realtime import get_realtime

        report: dict[str, Any] = {"app_env": config.app_env, "checks": {}}
        ok = True

        try:
            await Event.all().limit(1).count()
            report["checks"]["database"] = "ok"
        except Exception as exc:  # noqa: BLE001
            report["checks"]["database"] = f"FAIL: {exc}"
            ok = False

        rt = get_realtime()
        await rt.start()
        report["checks"]["bus"] = await rt.health()
        if config.bus_backend == "redis" and not report["checks"]["bus"].get("ok"):
            report["checks"]["bus_warning"] = "Redis unreachable — fanout is local-only"

        warnings = check_production()
        if warnings:
            report["checks"]["production_warnings"] = warnings
            if config.app_env == "production":
                ok = False

        if self.json_out:
            self.emit(report)
        else:
            self.line(f"environment: {config.app_env}")
            for k, v in report["checks"].items():
                self.line(f"  {k}: {v}")
        return 0 if ok else 1


# The account commands live in `cli/users.py` — they wrap `sillo.users.commands`
# (the framework's account operations, written as plain functions for exactly
# this) and add BEACN's role assignment on top. See COMMANDS at the bottom.


# --------------------------------------------------------------------------
# producers & keys
# --------------------------------------------------------------------------


class ProducerCreate(ApiCommand):
    name = "producer create"
    help = "Register a producer."
    arguments = [
        Argument("name"),
        Option("environment", default="development"),
        Option("description", default=""),
        Flag("json"),
    ]

    def run(self, api: ApiClient) -> int:
        out = api.post("/api/control/producers", json_body={
            "name": self.argument("name"),
            "environment": self.option("environment"),
            "description": self.option("description") or None,
        })["producer"]
        if self.json_out:
            self.emit(out)
        else:
            self.line(f"{out['id']}  {out['name']}  ({out['environment']})")
        return 0


class ProducerList(ApiCommand):
    name = "producer list"
    help = "List producers."
    arguments = [Option("environment", default=""), Flag("json")]

    def run(self, api: ApiClient) -> int:
        params = {"environment": self.option("environment")} if self.option("environment") else None
        rows = api.get("/api/control/producers", params=params)["producers"]
        if self.json_out:
            self.emit(rows)
            return 0
        for p in rows:
            self.line(f"{p['id']}  {p['name']:<28} {p['environment']:<12} events={p['event_count']}")
        return 0


class KeyCreate(ApiCommand):
    name = "key create"
    help = "Issue an API key for a producer. The secret is shown once."
    arguments = [
        Argument("producer_id"),
        Option("name", default="key"),
        Option("scopes", default="events:publish"),
        Option("expires_in_days", default="0"),
        Flag("json"),
    ]

    def run(self, api: ApiClient) -> int:
        out = api.post("/api/control/keys", json_body={
            "producer_id": self.argument("producer_id"),
            "name": self.option("name"),
            "scopes": self.option("scopes"),
            "expires_in_days": int(self.option("expires_in_days") or 0),
        })["key"]
        if self.json_out:
            self.emit(out)
        else:
            self.line(f"id:     {out['id']}")
            self.line(f"secret: {out['secret']}")
            self.line(out["warning"])
        return 0


class KeyList(ApiCommand):
    name = "key list"
    help = "List API keys."
    arguments = [Option("environment", default=""), Flag("json")]

    def run(self, api: ApiClient) -> int:
        params = {"environment": self.option("environment")} if self.option("environment") else None
        rows = api.get("/api/control/keys", params=params)["keys"]
        if self.json_out:
            self.emit(rows)
            return 0
        for k in rows:
            self.line(f"{k['id']}  {k['masked']:<20} {k['environment']:<12} {k['status']:<9} "
                      f"{','.join(k['scopes'])}")
        return 0


class KeyRevoke(ApiCommand):
    name = "key revoke"
    help = "Revoke an API key."
    arguments = [Argument("key_id"), Option("reason", default="revoked from the CLI"), Flag("json")]

    def run(self, api: ApiClient) -> int:
        api.post(f"/api/control/keys/{self.argument('key_id')}/revoke",
                 json_body={"reason": self.option("reason")})
        self.line("Revoked.")
        return 0


class TopicList(ApiCommand):
    name = "topic list"
    help = "List topics."
    arguments = [Option("environment", default=""), Flag("json")]

    def run(self, api: ApiClient) -> int:
        params = {"environment": self.option("environment")} if self.option("environment") else None
        rows = api.get("/api/control/topics", params=params)["topics"]
        if self.json_out:
            self.emit(rows)
            return 0
        for t in rows:
            self.line(f"{t['name']:<30} {t['visibility']:<9} events={t['event_count']:<8} "
                      f"persist={t['persist']}")
        return 0


# --------------------------------------------------------------------------
# events (use an API key, not the operator token)
# --------------------------------------------------------------------------


def _key_client() -> tuple[str, str]:
    import os

    url = os.getenv("BEACN_URL", "http://localhost:8000").rstrip("/")
    key = os.getenv("BEACN_API_KEY")
    if not key:
        raise CliError("Set BEACN_API_KEY (a bk_... key) to publish or inspect events.")
    return url, key


class EventsPublish(_Base):
    name = "events publish"
    help = "Publish one event with an API key ($BEACN_API_KEY)."
    arguments = [
        Argument("event"),
        Option("topic", default=""),
        Option("data", default="{}", help="JSON payload."),
        Option("idempotency_key", default=""),
        Flag("json"),
    ]

    def handle(self) -> int:
        import httpx

        try:
            url, key = _key_client()
            data = jsonlib.loads(self.option("data") or "{}")
        except (CliError, ValueError) as exc:
            self.line(str(exc))
            return 1
        body: dict[str, Any] = {"event": self.argument("event"), "data": data}
        if self.option("topic"):
            body["topic"] = self.option("topic")
        if self.option("idempotency_key"):
            body["idempotency_key"] = self.option("idempotency_key")
        resp = httpx.post(f"{url}/api/v1/events", json=body,
                          headers={"Authorization": f"Bearer {key}"}, timeout=30.0)
        if resp.status_code >= 400:
            self.line(f"{resp.status_code}: {resp.text[:300]}")
            return 1
        out = resp.json()
        self.line(out["events"][0]["id"] if not self.json_out else jsonlib.dumps(out, indent=2))
        return 0


class EventsInspect(_Base):
    name = "events inspect"
    help = "Fetch one event by id with an API key."
    arguments = [Argument("event_id"), Flag("json")]

    def handle(self) -> int:
        import httpx

        try:
            url, key = _key_client()
        except CliError as exc:
            self.line(str(exc))
            return 1
        resp = httpx.get(f"{url}/api/v1/events/{self.argument('event_id')}",
                         headers={"Authorization": f"Bearer {key}"}, timeout=30.0)
        if resp.status_code >= 400:
            self.line(f"{resp.status_code}: {resp.text[:300]}")
            return 1
        self.line(jsonlib.dumps(resp.json()["event"], indent=2))
        return 0


class EventsReplay(_Base):
    name = "events replay"
    help = "Replay a topic from a cursor with an API key."
    arguments = [
        Argument("topic"),
        Option("since", default=""),
        Option("limit", default="100"),
        Flag("json"),
    ]

    def handle(self) -> int:
        import httpx

        try:
            url, key = _key_client()
        except CliError as exc:
            self.line(str(exc))
            return 1
        body = {"topic": self.argument("topic"), "limit": int(self.option("limit") or 100)}
        if self.option("since"):
            body["since"] = self.option("since")
        resp = httpx.post(f"{url}/api/v1/events/replay", json=body,
                          headers={"Authorization": f"Bearer {key}"}, timeout=60.0)
        if resp.status_code >= 400:
            self.line(f"{resp.status_code}: {resp.text[:300]}")
            return 1
        out = resp.json()
        if self.json_out:
            self.line(jsonlib.dumps(out, indent=2))
            return 0
        for e in out["events"]:
            self.line(f"{e['id']}  {e['event']}")
        r = out["replay"]
        self.line(f"— {r['count']} event(s), truncated={r['truncated']}")
        return 0


class EventsTail(_Base):
    name = "events tail"
    help = "Stream live events for a topic over SSE ($BEACN_API_KEY)."
    arguments = [Argument("topic"), Flag("json")]

    def handle(self) -> int:
        import sys

        sys.path.insert(0, "sdk/python")
        try:
            from beacn import Beacn  # the SDK, reused

            url, key = _key_client()
        except (CliError, ImportError) as exc:
            self.line(str(exc))
            return 1
        client = Beacn(url=url, api_key=key)
        try:
            for event in client.subscribe(self.argument("topic")):
                if self.json_out:
                    self.line(jsonlib.dumps(event.raw))
                else:
                    self.line(f"{event.timestamp}  {event.event:<30} {jsonlib.dumps(event.data)}")
        except KeyboardInterrupt:
            return 0
        return 0


class Work(LocalCommand):
    name = "work"
    help = "Run every scheduled maintenance job once (retention, counters, reaping)."

    async def run_async(self) -> int:
        from app.jobs import run_all_once

        results = await run_all_once()
        self.emit(results) if self.json_out else [
            self.line(f"{name}: {res}") for name, res in results.items()
        ]
        return 0


from cli.users import USER_COMMANDS  # noqa: E402  (avoids a circular import at module top)

COMMANDS = (
    Login, Logout, Whoami,
    Serve, Migrate, Doctor, Work,
    *USER_COMMANDS,
    ProducerCreate, ProducerList,
    KeyCreate, KeyList, KeyRevoke,
    TopicList,
    EventsPublish, EventsInspect, EventsReplay, EventsTail,
)
