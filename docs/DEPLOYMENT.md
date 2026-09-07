# Deployment

## Configuration (environment variables)

| var | default | meaning |
|---|---|---|
| `APP_ENV` | `local` | label; `production` turns on `check_production` |
| `APP_DEBUG` | `true` | |
| `SECRET_KEY` | dev default | **set this** in production |
| `APP_URL` | `http://localhost:8000` | used for CORS default |
| `DATABASE_URL` | `sqlite://storage/beacn.db` | `postgres://user:pw@host/db` in production |
| `DB_GENERATE_SCHEMAS` | `true` | only the web process should do this; workers set `false` |
| `BEACN_BUS` | `memory` | `redis` for cross-instance fan-out |
| `REDIS_URL` | `redis://localhost:6379/0` | |
| `REDIS_NAMESPACE` | `beacn` | key/channel prefix; many installs can share one Redis |
| `QUEUE_BACKEND` | `memory` | `redis` for the maintenance job queue |
| `INGEST_RATE_PER_MINUTE` / `INGEST_BURST` | `6000` / `600` | per-key publish rate limit |
| `MAX_REQUEST_BYTES` | `4194304` | request body cap |
| `EVENT_RETENTION_HOURS` | `168` (7d) | default; per-topic override on the topic row |
| `TASK_RETENTION_HOURS` / `NOTIFICATION_RETENTION_HOURS` | `720` (30d) | |
| `CONNECTION_RETENTION_HOURS` | `72` | closed connection rows + delivery attempts |
| `REALTIME_HEARTBEAT_MS` | `25000` | sent to clients in `welcome` |
| `REALTIME_CONNECTION_MAX_SECONDS` | `43200` (12h) | hard connection lifetime |
| `REALTIME_QUEUE` | `512` | per-connection outbound queue depth |
| `REALTIME_TOKEN_TTL_SECONDS` | `3600` | minted realtime JWT lifetime |
| `REPLAY_MAX_EVENTS` | `1000` | cap per replay request |
| `COOKIE_SECURE` | `production` ⇒ `true` | session/CSRF cookie `Secure` flag |
| `CORS_ORIGINS` | `$APP_URL` | comma-separated |

`APP_ENV=production` **refuses to boot** if `SECRET_KEY` is the default,
`APP_DEBUG` is on, `COOKIE_SECURE` is off, `DATABASE_URL` is SQLite, or
`BEACN_BUS` is not `redis`.

## Processes

```
beacn migrate                # once per deploy, from ONE process
beacn serve --host 0.0.0.0 --port 8000     # web (scale this)
#   or: uvicorn app.main:app --workers 4
beacn work                   # maintenance jobs, run on a timer (cron / a scheduler)
```

`beacn work` runs retention pruning, denormalised-counter refresh, idempotency
sweeping and connection reaping once. Schedule it every few minutes. Exactly one
runner; it is idempotent if two overlap.

## Multiple instances

```
                 Load balancer  (sticky not required)
        ┌──────────────┼──────────────┐
     BEACN 1        BEACN 2        BEACN 3
        └──────────────┼──────────────┘
                     Redis   (BEACN_BUS=redis)
                       │
                    Postgres
```

Every instance subscribes once per environment to the Redis channel and
re-fans-out locally. A producer on instance 1 reaches a consumer on instance 3.
If Redis drops, each instance keeps serving its own sockets and reconnects with
backoff; ingestion and persistence are unaffected.

## Database

- **SQLite** is fine for a single instance and development. Not for production
  (concurrent writers, no network).
- **Postgres**: `pip install "beacn[postgres]"`, set `DATABASE_URL`. The schema
  is portable — no array columns, no JSON in `WHERE`, every timestamp tz-aware.
  For very high event volume, range-partition `events` by `id` prefix; nothing
  in the code depends on it.
- Retention keeps growth bounded. Size `EVENT_RETENTION_HOURS` to your query
  needs; long-term analytics should consume events into a warehouse.

## Docker

`Dockerfile` builds the frontend and installs `beacn[server,redis,postgres]`.
`docker-compose.yml` brings up BEACN + Postgres + Redis.

## Health & readiness

- Liveness/readiness probe: `GET /health` (`200` healthy, `503` if the database
  is unreachable). The bus being degraded is **not** unhealthy — it is
  Redis-optional by design.
