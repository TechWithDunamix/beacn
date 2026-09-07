# BEACN — Architecture

BEACN is centralized realtime event infrastructure. Backend systems **publish
events**; frontend and service consumers **subscribe** to them over WebSocket or
SSE. Everything else — tasks, notifications, messages — is a semantic layer on
one generic event model.

> BEACN is event infrastructure, not a Celery dashboard. Celery is one producer.
> Django is one producer. A Sillo app is one producer. A browser is one consumer.

---

## 1. System architecture

```
 Producers (any language)                       Consumers
 ─────────────────────────                       ─────────────────────────
 Django · Celery · cron · Go · PHP · Sillo       Browser apps · services
        │  REST  /api/v1/events                        ▲   WS /realtime
        │  (API key, scoped, env-isolated)             │   SSE /sse
        ▼                                              │
 ┌─────────────────────────────────────────────────────┴────────────────┐
 │                              BEACN instance                          │
 │                                                                     │
 │  ingestion → validation → idempotency → persistence → routing → bus │
 │      (domain.events)      (IdempotencyKey) (Event)   (Topic ACL)    │
 │                                                             │       │
 │  realtime.Hub  ← bus.subscribe(topic)  ──────────────────────┘       │
 │      │  per-connection bounded queue + writer task (sillo-wire)      │
 │      ▼                                                              │
 │  WebSocket / SSE  connection registry (Connection)                  │
 └───────────────────────────────┬────────────────────────────────────┘
                                 │  EventBus (fanout + coordination)
                    ┌────────────┴─────────────┐
                    │  in-process   |   Redis  │   pub/sub, presence, rate-limit
                    └────────────┬─────────────┘
                                 │
                        Persistent database
              (events, producers, api keys, topics, subs,
               delivery attempts, tasks, notifications, audit)
```

### Horizontal scaling

Multiple BEACN instances sit behind a load balancer. A producer connected to
instance A must reach a consumer connected to instance C. This is the job of the
**EventBus**:

- `InProcessBus` — single process. Default. Used in dev and tests.
- `RedisBus` — Redis pub/sub. One channel per environment; the payload carries
  the topic. Every instance subscribes once and re-fans-out locally through its
  `Hub`. Enabled with `BEACN_BUS=redis` + `REDIS_URL`.

The database is the single source of truth for durable state. Redis is
**never** the database — it carries only ephemeral fanout, presence, and
rate-limit counters.

---

## 2. Event model

The canonical envelope (`domain/events.py::Envelope`):

| field | required | who sets it | notes |
|---|---|---|---|
| `id` | server | server | `evt_` + 26-char ULID, globally sortable |
| `event` | **yes** | producer | dotted name, e.g. `payment.completed` |
| `topic` | **yes** | producer | routing key; ACL-checked |
| `producer` | server | server | resolved from the API key |
| `source` | no | producer | free string, e.g. `payments-service` |
| `timestamp` | server | server | RFC3339 UTC; ingestion time |
| `occurred_at` | no | producer | when the thing happened, if different |
| `environment` | server | server | from the API key; never client-trusted |
| `correlation_id` | no | producer | trace across systems |
| `request_id` | no | producer | one HTTP request |
| `user_id` | no | producer | subject, opaque string |
| `organization_id` | no | producer | tenant, opaque string |
| `schema_version` | no | producer | default `"1"` |
| `severity` | no | producer | `debug|info|notice|warning|error|critical` |
| `idempotency_key` | no | producer | dedupe within a 24h window |
| `data` | no | producer | arbitrary JSON, ≤ 256 KiB |

**Semantic kinds** are derived from the `event` name prefix, not separate
tables:

- `task.*` → also written to `tasks` (upsert on `task_id` in `data`)
- `notification.*` → also written to `notifications`
- `*.message.*` / `message.*` / `chat.*` → `kind = "message"`, delivered to the
  `topic` verbatim
- everything else → `kind = "event"`

Events are immutable after publication. There is no update or delete endpoint.
Retention removes them wholesale.

---

## 3. Realtime protocol

One WebSocket endpoint: `GET /realtime?token=<jwt|api-key>`. JSON frames.

### Client → server

```json
{"type": "subscribe",   "topic": "tasks", "id": "c1"}
{"type": "unsubscribe", "topic": "tasks"}
{"type": "replay",      "topic": "tasks", "since": "evt_01J..."}
{"type": "ack",         "id": "evt_01J..."}
{"type": "ping"}
```

### Server → client

```json
{"type": "welcome", "connection_id": "con_01J...", "heartbeat_ms": 25000}
{"type": "subscribed",   "topic": "tasks"}
{"type": "unsubscribed", "topic": "tasks"}
{"type": "event", "id": "evt_01J...", "event": "task.completed", "topic": "tasks",
 "seq": 42, "timestamp": "...", "data": {}}
{"type": "replay_done", "topic": "tasks", "count": 12, "truncated": false}
{"type": "error", "code": "forbidden", "message": "not allowed on topic org:9"}
{"type": "pong"}
```

Authorization is server-side on every `subscribe`. A private topic
(`user:*`, `organization:*`, `project:*`, or a topic row with
`visibility != public`) is matched against the token's claims. The frontend is
never trusted.

### Delivery semantics

- Live delivery is **at-most-once** (bounded per-connection queue, overflow
  policy: drop-oldest by default). No ack requirement for liveness.
- `replay` provides **at-least-once** recovery from the durable store, bounded
  by retention. A consumer that wants no gaps: subscribe, record the last
  `id` it processed, and on reconnect `replay since=<that id>` before trusting
  the live stream.
- **Exactly-once is not offered.** Every event has a ULID; consumers dedupe.

---

## 4. Authentication & authorization

Two planes:

1. **Producer plane** — API keys. `Authorization: Bearer bk_<prefix>_<secret>`.
   Only the SHA-256 of the secret is stored. A key is bound to one
   `environment` and one `producer`, and carries scopes
   (`events:publish`, `events:read`, `events:replay`, `topics:read`, …).
   Shown once at creation.
2. **Control plane** — session cookie for the dashboard, bearer session token
   for the CLI. RBAC via `sillo.permissions`: roles `Admin`, `Operator`,
   `Developer`, `ReadOnly` map to a permission catalogue
   (`app/authz.py::CATALOGUE`).

Realtime tokens: a short-lived JWT minted by `POST /api/v1/realtime/tokens`
(control-plane auth) carrying `environment`, `user_id`, `organization_id`,
`project_ids`, and an allow-list of topic patterns. An API key may also be
used directly for service-to-service consumers.

---

## 5. Persistence

SQLite in dev, Postgres in production (`DATABASE_URL`). Every column is
portable between the two — no array columns, no JSON in `WHERE`.

Key tables and indexes:

- `events` — `(environment, id)` PK-ish ordering, indexes on
  `(environment, topic, id)`, `(environment, event, id)`,
  `(environment, producer_id, id)`, `(environment, correlation_id)`.
  `id` is a ULID so range scans on `id` are time-ordered with no separate
  timestamp index.
- `event_idempotency` — `(environment, producer_id, idempotency_key)` unique,
  `created_at` for the sweeper. 24h retention.
- `delivery_attempts` — per (event, connection) — only written when a
  subscriber is connected at publish time; sampled under load.
- `tasks` — `(environment, task_id)` unique; updated in place from `task.*`.
- `notifications`, `producers`, `api_keys`, `topics`, `subscriptions`,
  `connections`, `audit_events`, `users`.

Growth is handled by **retention** (`RetentionPolicy` per topic, default 7d for
events, 30d for tasks/notifications) plus a scheduled `prune` job. Postgres
deployments can additionally range-partition `events` by `id` prefix; the schema
does not depend on it.

---

## 6. Failure strategy

| failure | behaviour |
|---|---|
| Redis down | `RedisBus` degrades to local-only fanout, logs, retries connect with backoff. Ingestion and persistence unaffected. |
| Database down | Ingestion returns `503`; SDK retries with backoff+jitter. Realtime keeps serving live traffic from the bus. |
| Slow consumer | Bounded queue; overflow policy drop-oldest / drop-newest / close. `DeliveryReport` counters exported. |
| Malformed publish | `422` with a field-level error list. Never partially stored. |
| Duplicate publish | Idempotency key → same `evt_` id returned, `deduplicated: true`, `200` not `201`. |
| Instance shutdown | `SIGTERM` → stop accepting, send `close` (1001) to sockets, flush writers, drain bus. |
| Retry storms | Per-key token-bucket rate limit; `429` with `Retry-After`. No infinite retries in the SDK (max attempts + max elapsed). |

---

## 7. Risks (identified up front)

1. **No Redis in dev/CI.** Mitigation: `InProcessBus` is the default and the
   only one the test suite requires; Redis tests skip when unreachable.
2. **SQLite write contention** across web + worker + scheduler. Mitigation:
   only the web process runs `generate_schemas`; workers wait. Same pattern as
   Janus.
3. **`get_or_none` is an async def**, not a chainable queryset (Sillo quirk).
   All prefetch goes through `await obj.fetch_related(...)`.
4. **CSRF on the JSON API.** `/api/**` is exempt from CSRF; it authenticates on
   `Authorization` alone and ignores cookies.
5. **Envelope size / fanout amplification.** 256 KiB payload cap; topics with
   > N subscribers get delivery sampling for `delivery_attempts` rows.
6. **Clock skew** on `occurred_at`. Server `timestamp` is authoritative for
   ordering; `occurred_at` is advisory metadata only.
