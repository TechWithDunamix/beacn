# BEACN REST API

Two surfaces:

- **`/api/v1/*`** — producer & consumer. Auth: `Authorization: Bearer bk_<key>`.
- **`/api/control/*`** — control plane. Auth: a browser session (dashboard) or a
  CLI bearer session token; every mutation is RBAC-checked. Session-authenticated
  writes must also send `X-BEACN-Control: 1` (SPA CSRF defence).

All responses are JSON. Errors:

```json
{ "error": { "code": "invalid", "message": "…", "details": … } }
```

`code` is stable: `unauthenticated` (401), `forbidden` (403), `not_found` (404),
`invalid` / `payload_too_large` (422/413), `conflict` (409),
`rate_limited` (429, with `Retry-After`), `unavailable` (503).

Send `X-Request-Id`; it is echoed back on the response and in error bodies.

---

## `/api/v1` — events

### `POST /api/v1/events`  · scope `events:publish`

Single, or batch via `{"events": [...]}` (max 500). Body per event: the
[envelope](EVENT_MODEL.md) producer fields.

`201` on accept, `200` if every event was a duplicate. Partial batch:

```json
{ "accepted": 2, "deduplicated": 0,
  "events": [{"id":"evt_…","event":"…","topic":"…","deduplicated":false}],
  "rejected": [{"index": 1, "code": "invalid", "message": "…"}] }
```

Rate limited per key (`INGEST_RATE_PER_MINUTE` / `INGEST_BURST`); cost = number
of events in the request.

### `GET /api/v1/events`  · scope `events:read`

Cursor pagination. Query: `topic`, `event`, `event_prefix`, `producer_id`,
`kind`, `severity`, `correlation_id`, `user_id`, `since`, `until` (ISO-8601),
`order` (`desc` default), `limit` (≤ 200), `cursor`.

```json
{ "events": [ … ], "page": { "count": 50, "next_cursor": "evt_…", "has_more": true } }
```

### `GET /api/v1/events/{id}`  · scope `events:read`

### `POST /api/v1/events/replay`  · scope `events:replay`

Body: `{ "topic": "...", "since": "evt_…" | null, "limit": 1000 }`.

```json
{ "events": [ … ],
  "replay": { "count": 12, "truncated": false,
              "earliest_available": "evt_…", "next_since": null } }
```

`truncated: true` means retention removed events between `since` and
`earliest_available` — you have a gap.

---

## `/api/v1` — other

| method + path | scope | notes |
|---|---|---|
| `GET /api/v1/topics` | `topics:read` | topic rows for the key's environment |
| `GET /api/v1/tasks` · `GET /api/v1/tasks/{task_id}` | `tasks:read` | BEACN-observed tasks |
| `GET /api/v1/notifications` | `notifications:read` | `?recipient=`, `?unread=1` |
| `POST /api/v1/notifications/{id}/read` | `notifications:write` | |
| `GET /api/v1/connections` | `connections:read` | realtime connections in the environment |
| `POST /api/v1/realtime/tokens` | `events:read` | mint a realtime JWT; body may set `user_id`, `organization_id`, `project_ids`, `topic_patterns`, `ttl_seconds` |
| `GET /api/v1/whoami` | — | echoes the key identity and its rate-limit budget |

---

## `/api/control` — control plane (RBAC)

| path | permission |
|---|---|
| `POST /auth/login` · `GET /auth/whoami` · `POST /auth/logout` | — / authenticated |
| `GET /dashboard?environment=` | `settings.read` |
| `GET/POST /producers` · `POST /producers/{id}/status` | `producers.read` / `producers.write` |
| `GET/POST /keys` · `POST /keys/{id}/revoke` · `POST /keys/{id}/rotate` | `apikeys.read` / `apikeys.write` |
| `GET/POST /topics` | `topics.read` / `topics.write` |
| `GET /connections` · `POST /connections/{id}/terminate` | `connections.read` / `connections.write` |
| `GET/POST /subscriptions` | `subscriptions.read` / `subscriptions.write` |
| `GET /audit` | `audit.read` |
| `GET /users` | `users.read` |
| `POST /users` (create) · `POST /users/role` · `POST /users/active` | `users.write` |
| `POST /realtime/token` | `events.read` (operator token) |
| `GET /health` | — |

An API key secret is returned **once**, from `POST /keys` and `POST /keys/{id}/rotate`,
and never again.

---

## `/health` and `/metrics`

- `GET /health` — checks the database and the bus; `200` healthy, `503` not.
- `GET /metrics` — Prometheus text exposition (see [OBSERVABILITY.md](OBSERVABILITY.md)).
