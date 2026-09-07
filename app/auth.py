"""Authentication for both planes.

* **Producer plane** — `Authorization: Bearer bk_<prefix>_<secret>`. Resolved to
  an `ApiKey` + `Producer`, checked for liveness and scope. Only the SHA-256 of
  the secret is ever compared.
* **Realtime plane** — a short-lived JWT minted by the control plane
  (`mint_realtime_token`) *or* an API key used directly by a service consumer.
  Either way the result is a `domain.topics.Grant`, which is all the realtime
  authorizer needs.

Nothing here trusts a client-supplied identity. `environment`, `user_id`,
`organization_id` and topic patterns come from the signed token or the key row.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sillo.helpers import jwt

from app.config import config
from database.models import ApiKey, Producer, hash_secret
from domain.errors import AuthenticationError, AuthorizationError
from domain.topics import Grant

REALTIME_ISSUER = "beacn"
REALTIME_AUDIENCE = "beacn:realtime"


# --------------------------------------------------------------------------
# Producer plane
# --------------------------------------------------------------------------


def _bearer(header: str | None) -> str:
    header = header or ""
    if not header.lower().startswith("bearer "):
        raise AuthenticationError("missing bearer token")
    token = header[7:].strip()
    if not token:
        raise AuthenticationError("empty bearer token")
    return token


async def resolve_api_key(authorization: str | None, *, ip: str | None = None) -> tuple[ApiKey, Producer]:
    """Resolve and validate an API key. Raises `AuthenticationError`."""
    token = _bearer(authorization)
    if not token.startswith("bk_") or token.count("_") < 2:
        raise AuthenticationError("malformed API key")
    _, prefix, _secret = token.split("_", 2)

    key = await ApiKey.get_or_none(prefix=prefix)
    if key is None or key.secret_hash != hash_secret(token):
        raise AuthenticationError("unknown or invalid API key")
    if not key.is_live:
        raise AuthenticationError("API key is revoked or expired")

    await key.fetch_related("producer")
    producer = key.producer
    if producer is None or producer.status != "active":
        raise AuthenticationError("producer is disabled")

    # Best-effort last-used bookkeeping; never fail a request over it.
    key.request_count = (key.request_count or 0) + 1
    key.last_used_at = datetime.now(UTC)
    key.last_used_ip = ip
    try:
        await key.save(update_fields=["request_count", "last_used_at", "last_used_ip"])
    except Exception:  # noqa: BLE001
        pass
    return key, producer


def require_scope(key: ApiKey, scope: str) -> None:
    if not key.has_scope(scope):
        raise AuthorizationError(
            f"API key is missing the {scope!r} scope", code="forbidden", details={"scope": scope}
        )


# --------------------------------------------------------------------------
# Realtime plane
# --------------------------------------------------------------------------


def mint_realtime_token(
    *,
    environment: str,
    user_id: str | None = None,
    organization_id: str | None = None,
    project_ids: list[str] | None = None,
    scopes: list[str] | None = None,
    topic_patterns: list[str] | None = None,
    operator: bool = False,
    ttl_seconds: int | None = None,
) -> tuple[str, int]:
    """Return ``(jwt, expires_in_seconds)``."""
    ttl = ttl_seconds or config.realtime_token_ttl_seconds
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": REALTIME_ISSUER,
        "aud": REALTIME_AUDIENCE,
        "iat": now,
        "exp": now + ttl,
        "env": environment,
        "operator": bool(operator),
    }
    if user_id:
        claims["uid"] = user_id
    if organization_id:
        claims["org"] = organization_id
    if project_ids:
        claims["projects"] = list(project_ids)
    if scopes:
        claims["scopes"] = list(scopes)
    if topic_patterns:
        claims["topics"] = list(topic_patterns)
    return jwt.encode(claims, config.secret_key), ttl


def grant_from_realtime_token(token: str) -> Grant:
    try:
        claims = jwt.decode(
            token,
            config.secret_key,
            audience=REALTIME_AUDIENCE,
            issuer=REALTIME_ISSUER,
        )
    except Exception as exc:  # noqa: BLE001 — jwt raises several types
        raise AuthenticationError(f"invalid realtime token: {exc}") from exc
    return Grant(
        environment=claims.get("env", "development"),
        user_id=claims.get("uid"),
        organization_id=claims.get("org"),
        project_ids=frozenset(claims.get("projects") or ()),
        scopes=frozenset(claims.get("scopes") or ()),
        topic_patterns=tuple(claims.get("topics") or ()),
        operator=bool(claims.get("operator")),
    )


async def grant_from_api_key_token(token: str) -> Grant:
    """A service consumer that connects to `/realtime` with its API key directly."""
    key, producer = await resolve_api_key(f"Bearer {token}")
    require_scope(key, "events:read")
    scopes = set(key.scope_list)
    return Grant(
        environment=producer.environment,
        user_id=None,
        organization_id=None,
        project_ids=frozenset(),
        scopes=frozenset(scopes),
        topic_patterns=(),
        operator="system:read" in scopes,
    )


async def grant_from_realtime_credential(raw: str) -> Grant:
    """Accept either a minted JWT or a raw API key on the realtime endpoint."""
    raw = raw.strip()
    if raw.startswith("bk_"):
        return await grant_from_api_key_token(raw)
    return grant_from_realtime_token(raw)
