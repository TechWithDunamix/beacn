"""Test helpers — builders for the fixtures the suite needs."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from database.models import ApiKey, Producer, User, UserSession


@dataclass
class KeyBundle:
    producer: Producer
    api_key: ApiKey
    secret: str

    @property
    def auth(self) -> dict:
        return {"Authorization": f"Bearer {self.secret}"}


async def make_producer(name: str = "Payments API", environment: str = "development") -> Producer:
    return await Producer.create_for(name=name, environment=environment)


async def make_api_key(
    *,
    name: str = "test",
    environment: str = "development",
    scopes: str = "events:publish events:read",
    producer: Producer | None = None,
) -> KeyBundle:
    producer = producer or await make_producer(environment=environment)
    key, secret = await ApiKey.issue(producer=producer, name=name, scopes=scopes)
    return KeyBundle(producer=producer, api_key=key, secret=secret)


async def make_user(email: str, *, role: str = "ReadOnly", superuser: bool = False) -> User:
    user = User(email=email, username=email, is_active=True, is_superuser=superuser)
    user.set_password("correct horse battery staple")
    await user.save()
    from sillo.permissions import Group

    group = await Group.get_or_none(name=role)
    if group is not None:
        await group.add_user(user)
    return user


async def cli_token(user: User) -> str:
    token = secrets.token_urlsafe(40)
    await UserSession.create(
        user_id=user.pk,
        key_hash=hashlib.sha256(token.encode()).hexdigest(),
        kind="cli",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        last_seen_at=datetime.now(UTC),
    )
    return token


def control_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "X-BEACN-Control": "1"}
