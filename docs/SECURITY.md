# Security

## Authentication

| plane | credential | how |
|---|---|---|
| Producers / consumers | **API key** `bk_<prefix>_<secret>` | `Authorization: Bearer …`. Only `sha256(full_key)` is stored. Shown once at creation. Bound to one producer + one environment. |
| Control plane (dashboard) | **session cookie** | `sillo` session middleware + a `UserSession` row checked for revocation on every request. |
| Control plane (CLI) | **bearer session token** | issued by `POST /api/control/auth/login`, 30-day expiry, revocable, stored `0600` at `~/.config/beacn/credentials.json`. |
| Realtime | **short-lived JWT** or an API key | JWT minted by `POST /api/v1/realtime/tokens` / `POST /api/control/realtime/token`, carries `env` + identity claims + topic patterns. |

## Authorization

### API key scopes

`events:publish`, `events:read`, `events:replay`, `topics:read`, `tasks:read`,
`notifications:read`, `notifications:write`, `connections:read`, `system:read`.
A key holds a subset; the ingestion and query endpoints check the specific scope
they need. `*` exists for bootstrap keys only.

### Control-plane RBAC

Roles are `sillo.permissions` groups. Defaults, each a superset of the last:

| role | holds |
|---|---|
| **ReadOnly** | every `*.read` permission |
| **Developer** | + `events.publish`, `events.replay`, `subscriptions.write` |
| **Operator** | + `topics.write`, `producers.write`, `apikeys.write`, `connections.write` |
| **Admin** | the whole catalogue, including `users.write` |

Separate permissions gate publishing, reading, replay, topic/producer/key/
connection/user management, config and audit. `is_superuser` is the Owner escape
hatch, checked first. The catalogue is in `app/authz.py::CATALOGUE`.

**Operator accounts.** The first one is created locally with
`beacn user create <email> --role Admin --admin` (hidden prompt, or
`$BEACN_PASSWORD` in CI). After that, an account holder with `users.write`
adds more — `beacn user create` / the dashboard **Operators** page /
`POST /api/control/users` — all of which run the framework's
`sillo.users.commands` for the row and BEACN's group assignment for the role.
A superuser also has to clear the framework password policy; the ordinary path
requires at least 10 characters. Disabling (`beacn user disable`) is reversible
and revokes the account's live sessions immediately; you cannot disable your
own account.

### Realtime topics

Authorized server-side on **every** `subscribe` and `replay` — see
[REALTIME.md](REALTIME.md). The frontend is never trusted to decide whether it
may see a private topic.

## Environment isolation

`development` / `staging` / `production`. The environment is part of the API
key, the realtime token, every event, every topic and every connection. It leads
every database index. It is **never** read from a request body — a payload that
sets `"environment": "production"` is ignored. A cross-environment subscribe is
refused.

## Rate limiting & abuse

- Per-key token bucket on publishing (`INGEST_RATE_PER_MINUTE`, `INGEST_BURST`);
  `429` + `Retry-After`. Per-instance by design — it protects one process from a
  runaway producer.
- Request body cap (`MAX_REQUEST_BYTES`, default 4 MiB) and payload cap
  (`data` ≤ 256 KiB) checked before parsing/persisting.
- Batch cap of 500 events per request.
- Idempotency markers dedupe replayed publishes within 24h.

## Transport & headers

- CORS defaults to the app's own URL only; `allow_credentials` with `*` is
  refused by browsers and not offered.
- The JSON API is exempt from the CSRF token middleware because it authenticates
  on `Authorization` alone and ignores cookies. Session-authenticated
  control-plane writes additionally require an `X-BEACN-Control` header, which a
  cross-site form cannot set without a CORS preflight the config does not grant.
- `SECRET_KEY`, `COOKIE_SECURE`, SQLite-in-production and a non-Redis bus are
  all refused at boot when `APP_ENV=production` (`app/config.py::check_production`).

## Audit

Every control-plane mutation writes an `audit_events` row: actor, action,
resource, before/after, origin (`web`/`cli`/`system`), ip, timestamp. Distinct
from the event store, which records what *producers* published.
