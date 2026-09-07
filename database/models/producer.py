"""Producers and their API keys.

A **Producer** is a backend application or service that publishes to BEACN —
"Orders API", "Celery Workers", "Deployment Service". It is scoped to one
environment. An **ApiKey** authenticates a producer over REST; only the SHA-256
of the secret is stored and the secret is shown exactly once.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from sillo.record import Model
from tortoise import fields

from domain.ids import new_ulid

__all__ = ["ApiKey", "Producer", "SCOPES", "hash_secret"]

#: Every scope a key can carry. `*` is a wildcard granted only to bootstrap keys.
SCOPES = (
    "events:publish",
    "events:read",
    "events:replay",
    "topics:read",
    "tasks:read",
    "notifications:read",
    "notifications:write",
    "connections:read",
    "system:read",
)


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class Producer(Model):
    id = fields.CharField(max_length=32, pk=True)
    name = fields.CharField(max_length=120)
    slug = fields.CharField(max_length=140, index=True)
    environment = fields.CharField(max_length=20, index=True)
    description = fields.CharField(max_length=400, null=True)
    #: free-text service identity a producer stamps on its events (`source`)
    default_source = fields.CharField(max_length=200, null=True)
    status = fields.CharField(max_length=16, default="active")  # active | disabled

    #: denormalised counters, refreshed by the stats job — so the producer list
    #: sorts by volume without aggregating the events table per row.
    event_count = fields.BigIntField(default=0)
    last_event_at = fields.DatetimeField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    created_by_id = fields.IntField(null=True)

    class Meta:
        table = "producers"
        unique_together = (("environment", "slug"),)

    def __str__(self) -> str:
        return f"{self.name} ({self.environment})"

    @classmethod
    async def create_for(
        cls, *, name: str, environment: str, slug: str | None = None, **extra
    ) -> Producer:
        slug = (slug or name.lower().replace(" ", "-")).strip()
        return await cls.create(
            id=new_ulid(), name=name.strip(), slug=slug, environment=environment, **extra
        )


class ApiKey(Model):
    id = fields.CharField(max_length=32, pk=True)
    producer = fields.ForeignKeyField(
        "models.Producer", related_name="api_keys", on_delete=fields.CASCADE
    )
    environment = fields.CharField(max_length=20, index=True)
    name = fields.CharField(max_length=120)
    #: `bk_<prefix>` — the public half, stored in clear so a key can be named
    #: in the UI and in logs. 8 url-safe chars.
    prefix = fields.CharField(max_length=16, unique=True, index=True)
    secret_hash = fields.CharField(max_length=64, index=True)
    scopes = fields.CharField(max_length=400, default="events:publish")

    status = fields.CharField(max_length=16, default="active")  # active | revoked
    revoked_at = fields.DatetimeField(null=True)
    revoked_reason = fields.CharField(max_length=200, null=True)
    expires_at = fields.DatetimeField(null=True)

    request_count = fields.BigIntField(default=0)
    last_used_at = fields.DatetimeField(null=True)
    last_used_ip = fields.CharField(max_length=64, null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    created_by_id = fields.IntField(null=True)

    class Meta:
        table = "api_keys"
        indexes = (("environment", "status"),)

    # -- lifecycle ------------------------------------------------------

    @classmethod
    async def issue(
        cls,
        *,
        producer: Producer,
        name: str,
        scopes: str,
        expires_at: datetime | None = None,
        created_by_id: int | None = None,
    ) -> tuple[ApiKey, str]:
        """Create a key and return ``(row, full_secret)``. The secret is never stored."""
        # Hex, not url-safe base64: the prefix sits between two "_" delimiters
        # in the key string, so it must never itself contain "_" or "-".
        prefix = secrets.token_hex(4)
        while await cls.exists(prefix=prefix):
            prefix = secrets.token_hex(4)
        secret_body = secrets.token_urlsafe(32)
        full = f"bk_{prefix}_{secret_body}"
        row = await cls.create(
            id=new_ulid(),
            producer=producer,
            environment=producer.environment,
            name=name.strip(),
            prefix=prefix,
            secret_hash=hash_secret(full),
            scopes=_normalise_scopes(scopes),
            expires_at=expires_at,
            created_by_id=created_by_id,
        )
        return row, full

    @property
    def scope_list(self) -> list[str]:
        return [s for s in self.scopes.split() if s]

    def has_scope(self, scope: str) -> bool:
        parts = self.scope_list
        return scope in parts or "*" in parts

    @property
    def is_live(self) -> bool:
        if self.status != "active":
            return False
        if self.expires_at is not None and self.expires_at <= datetime.now(UTC):
            return False
        return True

    async def revoke(self, reason: str = "") -> None:
        self.status = "revoked"
        self.revoked_at = datetime.now(UTC)
        self.revoked_reason = reason or None
        await self.save()

    @property
    def masked(self) -> str:
        return f"bk_{self.prefix}_{'•' * 8}"


def _normalise_scopes(raw: str | list[str]) -> str:
    if isinstance(raw, str):
        parts = raw.replace(",", " ").split()
    else:
        parts = list(raw)
    seen: list[str] = []
    for p in parts:
        p = p.strip()
        if p and p not in seen and (p == "*" or p in SCOPES):
            seen.append(p)
    return " ".join(seen) or "events:publish"
