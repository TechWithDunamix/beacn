"""Operating — auth and RBAC, horizontal scaling, observability, production
deployment, and a troubleshooting guide."""

from __future__ import annotations

from typing import Any

from app.docs.blocks import code, heading, note, para, steps, table, terms

PAGES: tuple[dict[str, Any], ...] = (
    # =====================================================================
    {
        "slug": "authentication",
        "section": "operate",
        "title": "Authentication and authorization",
        "summary": "The two credential planes, API-key scopes, control-plane RBAC, realtime tokens, and environment isolation.",
        "blocks": [
            para(
                "BEACN has two independent credential planes. They never share a secret and "
                "never authorize each other's operations."
            ),

            heading("The producer plane — API keys"),
            table(
                ["", ""],
                [
                    ["Format", "`Authorization: Bearer bk_<prefix>_<secret>`"],
                    ["Storage", "only `sha256(full_key)` is stored; the `prefix` is kept in clear so a key can be named in the UI and logs"],
                    ["Binding", "one producer, one environment — both fixed on the key, never taken from a request body"],
                    ["Lifetime", "optional `expires_at`; revocable, which takes effect on the next request"],
                    ["Shown", "once, at creation and at rotation, and never again"],
                ],
            ),
            para("Scopes, checked per route:"),
            table(
                ["Scope", "Grants"],
                [
                    ["`events:publish`", "`POST /api/v1/events`"],
                    ["`events:read`", "history, event detail, minting a realtime token"],
                    ["`events:replay`", "`POST /api/v1/events/replay`"],
                    ["`topics:read`", "`GET /api/v1/topics`"],
                    ["`tasks:read` / `notifications:read` / `notifications:write`", "the task and notification endpoints"],
                    ["`connections:read`", "`GET /api/v1/connections`"],
                    ["`system:read`", "subscribing to `system` and `audit` topics; an operator-equivalent realtime grant"],
                ],
            ),
            note(
                "A real producer usually holds only `events:publish`. Give a key the reads "
                "it needs and nothing more — a leaked publish-only key cannot exfiltrate "
                "your event history.",
                tone="caution",
            ),

            heading("The control plane — operators and RBAC"),
            para(
                "The dashboard authenticates with a session cookie; the CLI with a bearer "
                "session token from `beacn login`. Both resolve to a `User` and both run the "
                "**same** RBAC check — the CLI is not a way around authorization. Roles are "
                "`sillo.permissions` groups; the permission catalogue is in "
                "`app/authz.py::CATALOGUE`."
            ),
            table(
                ["Role", "Holds"],
                [
                    ["**ReadOnly**", "every `*.read` permission"],
                    ["**Developer**", "+ `events.publish`, `events.replay`, `subscriptions.write`"],
                    ["**Operator**", "+ `topics.write`, `producers.write`, `apikeys.write`, `connections.write`"],
                    ["**Admin**", "the whole catalogue, including `users.write`"],
                ],
            ),
            para(
                "Separate permissions gate publishing, reading, replay, and topic / producer "
                "/ key / connection / user management, plus config and audit. `is_superuser` "
                "is the Owner escape hatch, checked before any role — the account that "
                "bootstrapped the installation cannot lock itself out by editing its own "
                "role."
            ),

            heading("Managing operators"),
            para(
                "The account commands wrap `sillo.users.commands` and add BEACN's role "
                "assignment; they are also on the dashboard's **Operators** page and at "
                "`POST /api/control/users`."
            ),
            code(
                """
beacn user create sre@example.com --role Operator     # hidden prompt / $BEACN_PASSWORD
beacn user role   sre@example.com Developer
beacn user disable leaver@example.com                 # reversible; revokes live sessions
beacn user list
""",
                lang="bash",
            ),

            heading("Realtime tokens"),
            para(
                "A browser never holds an API key. Your backend mints a short-lived JWT "
                "(`REALTIME_TOKEN_TTL_SECONDS`, default 1h) carrying the signed-in user's "
                "`uid`, `org`, `projects` and any `topic_patterns` — and nothing else. Every "
                "`subscribe` on the resulting connection is checked against those claims "
                "([Topics](/docs/topics))."
            ),
            code(
                """
# your backend, holding an events:read key
POST /api/v1/realtime/tokens
{ "user_id": "usr_42", "organization_id": "org_9", "project_ids": ["prj_1"],
  "topic_patterns": ["chat:room-*"] }

{ "token": "eyJ...", "expires_in": 3600, "environment": "production" }
""",
                lang="json",
            ),

            heading("Environment isolation"),
            para(
                "`development`, `staging` and `production` are not a naming convention — they "
                "are a column that leads every index on `events`, and every query is scoped "
                "to one of them. The environment is read from the API key or the signed "
                "realtime token, **never** from a request body. A payload that sets "
                "`\"environment\": \"production\"` is ignored, and a cross-environment "
                "subscribe is refused."
            ),

            heading("Transport hardening"),
            steps([
                "CORS defaults to `$APP_URL` only. `allow_credentials` with `*` is refused "
                "by browsers and is not offered.",
                "The JSON API is exempt from the CSRF token middleware because it "
                "authenticates on `Authorization` alone and ignores cookies. "
                "Session-authenticated control-plane writes additionally require an "
                "`X-BEACN-Control` header — a header a cross-site form cannot set without a "
                "CORS preflight the config does not grant.",
                "A production boot is refused if `SECRET_KEY` is the dev default, "
                "`APP_DEBUG` is on, cookies are not `Secure`, the database is SQLite, or the "
                "bus is not Redis.",
                "Every control-plane mutation writes an `audit_events` row: actor, action, "
                "resource, before/after, origin, ip, timestamp.",
            ], ordered=True),
        ],
    },

    # =====================================================================
    {
        "slug": "scaling",
        "section": "operate",
        "title": "Horizontal scaling and Redis",
        "summary": "Running multiple instances, how the bus makes fan-out cross-instance, and what degrades when Redis is unavailable.",
        "blocks": [
            para(
                "BEACN is designed for more than one instance. A producer connected to "
                "instance A must be able to reach a consumer connected to instance C, and "
                "the piece that makes that true is the event bus. "
                "[Deployment](/docs/deployment) covers the process topology; this page is "
                "about the bus."
            ),
            code(
                """
                 Load balancer   (no sticky sessions required)
        ┌──────────────┼──────────────┐
     BEACN 1        BEACN 2        BEACN 3
        └──────────────┼──────────────┘
                     Redis   (BEACN_BUS=redis)     ephemeral fan-out only
                       │
                    Postgres                       the single source of truth
""",
                lang="text",
            ),

            heading("How the bus fans out"),
            steps([
                "An event is ingested on whichever instance received the POST. It is "
                "persisted there, and delivered to that instance's local subscribers "
                "immediately.",
                "The same instance publishes the serialised event to one Redis channel — "
                "`<namespace>:evt:<environment>` — so there is one channel per environment, "
                "not per topic.",
                "Every instance subscribes to that channel once. On receiving an event it "
                "re-fans-out to its own local hub. The publishing instance de-dupes by "
                "event id so its local copy is not delivered twice.",
            ], ordered=True),
            para(
                "The consequence: subscriptions are local to an instance, but publishes "
                "reach every instance. There is no coordination protocol, no leader, and no "
                "shared subscription table."
            ),

            heading("What Redis is and is not for"),
            table(
                ["Redis carries", "Redis is never"],
                [
                    ["cross-instance event fan-out (pub/sub)", "the event store"],
                    ["rate-limit coordination (optional)", "the source of truth for producers, keys, topics or users"],
                    ["presence and ephemeral coordination", "durable in any sense BEACN relies on"],
                ],
            ),
            note(
                "If Redis is unavailable, `RedisBus` **degrades to local-only fan-out**: "
                "each instance keeps serving its own connected consumers, logs the "
                "degradation, and retries the connection with backoff. Ingestion, "
                "persistence and replay are completely unaffected. `/metrics` reports "
                "`beacn_bus_ok{backend=\"redis\"} 0` and the Settings page shows *degraded*.",
                tone="ok",
                title="Redis outage is a partition, not an outage",
            ),

            heading("Sizing"),
            steps([
                "Run the benchmark (`python -m benchmarks.run`) on your target hardware for "
                "the single-process ceiling. Then put Postgres and Redis in the path and "
                "re-measure — persistence is the bottleneck and now includes network and "
                "`fsync`.",
                "Scale the `web` process horizontally. Throughput is roughly linear in web "
                "processes until Postgres saturates.",
                "Run `beacn work` as its own process on a timer (cron, or a scheduler "
                "container), exactly one runner. It is idempotent if two overlap.",
                "Watch `beacn_events_dropped_total`. Rising means consumers are slower than "
                "the stream — tune `REALTIME_QUEUE`, change the overflow policy, or split "
                "the topic. It is not a CPU problem.",
            ], ordered=True),

            heading("What does not scale by adding instances"),
            para(
                "The publish **rate limit** is per instance by design (it protects one "
                "process from a runaway producer). A single hot topic with tens of "
                "thousands of subscribers is still bounded by one instance's ability to "
                "walk its local subscriber list — shard such a topic (`orders:shard-0` … "
                "`orders:shard-15`) at the producer and have consumers subscribe to the "
                "shard for their key range."
            ),
        ],
    },

    # =====================================================================
    {
        "slug": "observability",
        "section": "operate",
        "title": "Observability",
        "summary": "The metrics endpoint, structured logs, correlation ids, and tracing one business action end to end.",
        "blocks": [
            heading("Metrics — GET /metrics"),
            para(
                "Prometheus text exposition, hand-written — there is no `prometheus_client` "
                "dependency and no global registry to fight the test suite. Counters are "
                "per-process; scrape every instance and sum."
            ),
            table(
                ["Metric", "Type", "Notes"],
                [
                    ["`beacn_up`", "gauge", "1 while serving"],
                    ["`beacn_realtime_connections`", "gauge", "live connections on this instance"],
                    ["`beacn_realtime_subscriptions`", "gauge", "topic subscriptions on this instance"],
                    ["`beacn_frames_sent_total`", "counter", "frames written to sockets by this instance"],
                    ["`beacn_events_delivered_total`", "counter", "successful local deliveries"],
                    ["`beacn_events_dropped_total`", "counter", "queue overflows — slow consumers"],
                    ["`beacn_bus_ok{backend}`", "gauge", "1 if the bus backend is reachable"],
                    ["`beacn_events_persisted{environment}`", "gauge", "events stored in the last 24h"],
                    ["`beacn_connections_open`", "gauge", "open connections across all instances (from the DB)"],
                    ["`beacn_tasks_running`", "gauge", "tasks in `started` / `retrying`"],
                ],
            ),

            heading("Logs"),
            para(
                "Structured via Python's `logging`, namespaced: `beacn.ingest`, `beacn.bus`, "
                "`beacn.realtime`, `beacn.celery`. Errors in delivery, fan-out and the Redis "
                "listener are **isolated** — one failure never kills a loop — and logged "
                "with the event or connection id."
            ),

            heading("Correlation ids"),
            para(
                "A producer sets `correlation_id` on an event ([the event "
                "envelope](/docs/event-model)). BEACN stores it, indexes it "
                "(`(environment, correlation_id)`), returns it on every consumer frame, and "
                "makes it queryable:"
            ),
            code(
                """
GET /api/v1/events?correlation_id=cor_123&order=asc
""",
                lang="text",
            ),
            para("End-to-end trace of one business action:"),
            code(
                """
HTTP request           X-Correlation-ID: cor_123   (or Django BeacnMiddleware assigns it)
   → producer publishes   payment.initiated        correlation_id=cor_123
   → BEACN ingests, persists evt_A, routes to topic "payments"
   → bus fans evt_A to every instance
   → each instance delivers to subscribed connections   (frame carries cor_123)
   → producer publishes   payment.authorized  → payment.completed   (same cor_123)
   → frontend has the whole chain
""",
                lang="text",
            ),
            para(
                "`GET /api/v1/events?correlation_id=cor_123` returns every event in that "
                "chain, in order, with their producers and topics. `X-Request-Id` (sent by "
                "the SDK, echoed by the API, present in error bodies) narrows it to a single "
                "HTTP call."
            ),

            heading("Delivery attempts"),
            para(
                "`delivery_attempts` rows record (event → connection) outcomes — "
                "`delivered` / `dropped` / `failed`, latency, ack. They are written only "
                "when a subscriber was connected at publish time, and sampled 1-in-N once a "
                "topic exceeds `DELIVERY_SAMPLE_THRESHOLD` live subscribers so a fan-out "
                "storm cannot flood the table. The dashboard's delivery success rate is "
                "computed from them; when there are none it shows *—* rather than a "
                "fabricated number."
            ),

            heading("The dashboard"),
            para(
                "The **Dashboard** page polls `/api/control/dashboard` every few seconds: "
                "events/sec, a throughput sparkline, top producers and topics, recent "
                "events, delivery success, open connections, tasks running and failed. Every "
                "number is computed from the durable store plus this instance's live "
                "counters — an empty installation shows zeros and empty states, never "
                "placeholder data."
            ),
        ],
    },

    # =====================================================================
    {
        "slug": "deployment",
        "section": "operate",
        "title": "Production deployment",
        "summary": "Processes, Postgres, Redis, migrations, health checks, and the container images.",
        "blocks": [
            heading("Processes"),
            code(
                """
beacn migrate                              # once per deploy, from ONE process
beacn serve --host 0.0.0.0 --port 8000     # the web tier — scale this
#   or: uvicorn app.main:app --workers 4
beacn work                                 # maintenance jobs — run on a timer
""",
                lang="bash",
            ),
            para(
                "`beacn work` runs retention pruning, denormalised-counter refresh, "
                "idempotency sweeping and connection reaping once. Schedule it every few "
                "minutes with cron or a scheduler container. Exactly one runner; it is "
                "idempotent if two overlap."
            ),

            heading("Configuration for production"),
            para("The full list is on [Configuration](/docs/configuration); the settings that matter most here:"),
            terms([
                ("`APP_ENV=production`", "turns on the boot safety check — see below"),
                ("`SECRET_KEY`", "a long random string; signs sessions and realtime JWTs"),
                ("`DATABASE_URL`", "`postgres://…` — `pip install \"beacn[postgres]\"`"),
                ("`DB_GENERATE_SCHEMAS`", "`true` on the web process only; `false` on workers"),
                ("`BEACN_BUS=redis` + `REDIS_URL`", "required for multi-instance fan-out"),
                ("`COOKIE_SECURE=true`", "if TLS terminates before BEACN, set it explicitly"),
                ("`CORS_ORIGINS`", "the exact origins your dashboards and browser SDKs load from"),
                ("`VITE_DEV=false`", "serve the built `static/build/` assets"),
            ]),
            note(
                "With `APP_ENV=production` the process **refuses to boot** if `SECRET_KEY` "
                "is the dev default, `APP_DEBUG` is on, `COOKIE_SECURE` is off, "
                "`DATABASE_URL` is SQLite, or `BEACN_BUS` is not `redis`. It is a guard, not "
                "a branch — it changes nothing about behaviour, it only declines an unsafe "
                "start.",
                tone="critical",
            ),

            heading("Database"),
            steps([
                "**SQLite** is fine for a single instance and development. Not for "
                "production — concurrent writers and no network.",
                "**Postgres**: the schema is portable — no array columns, no JSON in a "
                "`WHERE` clause, every timestamp timezone-aware. Nothing needs a manual "
                "tuning pass to work.",
                "For very high event volume, range-partition `events` by `id` prefix. The "
                "schema does not depend on it; add it when a single table's index "
                "maintenance becomes the bottleneck.",
                "Retention keeps growth bounded. Size `EVENT_RETENTION_HOURS` to your query "
                "needs; long-term analytics should consume events into a warehouse, not "
                "query the event store.",
            ], ordered=True),

            heading("Health and readiness"),
            para(
                "`GET /health` checks the database and the bus: `200` healthy, `503` if the "
                "database is unreachable. Use it as both the liveness and readiness probe. "
                "The bus being *degraded* (Redis down) is **not** unhealthy — that is "
                "Redis-optional by design, and returning `503` for it would take a whole "
                "cluster out for a Redis blip."
            ),

            heading("Containers"),
            para(
                "`Dockerfile` builds the frontend in a Node stage and installs "
                "`beacn[server,redis,postgres]` in a slim Python runtime. "
                "`docker-compose.yml` brings up two `web` replicas plus Postgres, Redis, a "
                "one-shot `migrate` and a `worker` loop — a working reference for the "
                "process topology, not a production manifest."
            ),
            code(
                """
docker compose up --build
#   migrate runs once, web waits for it, worker loops `beacn work` every 120s
#   dashboard on http://localhost:8000
""",
                lang="bash",
            ),

            heading("Rolling a deploy"),
            steps([
                "Run `beacn migrate` from an init container or a release step — not from "
                "every replica.",
                "Roll the `web` tier. In-flight WebSocket connections receive close `1001` "
                "on the old instances; SDK clients reconnect to the new ones and replay.",
                "The bus needs no coordination for a rolling deploy — new and old instances "
                "share the same Redis channel and fan out to each other.",
            ], ordered=True),
        ],
    },

    # =====================================================================
    {
        "slug": "troubleshooting",
        "section": "operate",
        "title": "Troubleshooting",
        "summary": "The failures people actually hit, and what each one means.",
        "blocks": [
            heading("Publishing"),
            terms([
                ("`401 unauthenticated` on a key that should work",
                 "The key is revoked, expired, or belongs to a different environment than "
                 "you think. Check **API keys** in the dashboard. A malformed bearer value "
                 "(missing the `bk_` prefix, wrong number of `_` segments) also 401s."),
                ("`403 forbidden` with `\"scope\": \"events:publish\"`",
                 "The key exists and is valid but does not carry that scope. Rotate it with "
                 "the scopes you need, or issue a new one — scopes are set at creation."),
                ("`422` with `details.index`",
                 "A batch had an invalid event at that position. The valid ones in the same "
                 "request **were** accepted; check the `accepted` count and the `rejected` "
                 "array before re-sending the whole batch."),
                ("`429` under normal load",
                 "The per-key token bucket. It is per instance — if you have one instance "
                 "and a bursty producer, raise `INGEST_BURST`. If you have many instances "
                 "and are hitting it, the limiter is doing its job on one hot key; spread "
                 "the producer across keys or raise the limit deliberately."),
                ("`413 payload_too_large`",
                 "The request body is over `MAX_REQUEST_BYTES` (4 MiB) or a single `data` is "
                 "over 256 KiB. Put a reference in `data`, not the payload."),
                ("`503 unavailable`",
                 "The database is unreachable. The SDK retries this automatically with "
                 "backoff; a non-SDK producer should too. Live realtime traffic already in "
                 "flight is unaffected."),
            ]),

            heading("Consuming"),
            terms([
                ("The WebSocket connects, then closes with 1008",
                 "The token failed auth at connect time — expired JWT, wrong signing key "
                 "(different `SECRET_KEY` between the minting backend and BEACN), or a raw "
                 "API key without `events:read`."),
                ("`subscribe` returns an `error` frame with `code: forbidden`",
                 "The grant does not cover that topic. For `user:<id>` the token's `uid` "
                 "must match; for a `private` topic row the token needs a matching "
                 "`topic_patterns` glob or must be operator-minted. The connection stays "
                 "open — other subscriptions are fine."),
                ("Events stop arriving but the socket is still open",
                 "Either you sent nothing for 3× the heartbeat and the server is about to "
                 "close you (send `ping` when idle), or your queue overflowed and "
                 "`drop_oldest` is silently shedding. Check `beacn_events_dropped_total` and "
                 "the connection row's dropped count."),
                ("`replay_done` has `truncated: true`",
                 "Your `since` cursor is older than the oldest retained event for that "
                 "topic. Events in the gap are gone. Either your consumer was offline longer "
                 "than `EVENT_RETENTION_HOURS`, or that topic has a short per-topic "
                 "retention."),
                ("Duplicate events reach the consumer",
                 "Expected — see [Delivery semantics](/docs/delivery-semantics). Deduplicate "
                 "on `event.id`. A reconnect that replays an overlapping window is the "
                 "common cause."),
            ]),

            heading("Realtime tokens"),
            terms([
                ("`invalid realtime token: Signature verification failed`",
                 "The backend minting tokens and the BEACN instance verifying them have "
                 "different `SECRET_KEY` values. They must match."),
                ("A browser can subscribe to topics it should not see",
                 "The minting call passed `topic_patterns` that are too broad, or "
                 "`operator: true`, or a `system:read` scope. The token carries exactly what "
                 "you put in it — mint the narrowest grant that works."),
            ]),

            heading("Scaling and the bus"),
            terms([
                ("A consumer on one instance misses events published to another",
                 "`BEACN_BUS` is still `memory`. Set it to `redis` and give every instance "
                 "the same `REDIS_URL` and `REDIS_NAMESPACE`."),
                ("`beacn_bus_ok{backend=\"redis\"}` is 0 but events still flow locally",
                 "Redis is unreachable and the bus has degraded to local-only fan-out. "
                 "Cross-instance delivery is paused; everything else works. Fix Redis; the "
                 "bus reconnects on its own."),
                ("The dashboard's delivery success rate shows —",
                 "There are no `delivery_attempts` rows in the window. Either no subscribers "
                 "were connected when events were published, or the topic is above the "
                 "sampling threshold and the sample is empty. It is not an error."),
            ]),

            heading("Operators and login"),
            terms([
                ("`beacn user create` — \"default_connection … cannot be None\"",
                 "The `User` model's manager was not bound. This is fixed in "
                 "`database/models/identity.py` (`User.objects.model = User`); if you see it "
                 "you are on stale code — reinstall with `pip install -e .`."),
                ("\"unable to open database file\" on first run",
                 "The SQLite directory did not exist. `database/config.py` now creates it; "
                 "if you still see it, a stale non-editable `pip install .` is shadowing the "
                 "checkout and its paths point into `site-packages`. `pip uninstall beacn` "
                 "then `pip install -e .`."),
                ("Login redirects straight back to the login page",
                 "A CSRF or session-cookie mismatch. The dashboard's axios client reads "
                 "`XSRF-TOKEN` and sends `X-XSRF-TOKEN`; if you are calling the login route "
                 "yourself, prime the cookie with a `GET /login` first and echo it back."),
            ]),

            heading("Getting more detail"),
            steps([
                "`beacn doctor` — checks configuration, the database and the bus, and prints "
                "what is wrong.",
                "`GET /health` — the database and bus status as JSON.",
                "`GET /metrics` — the counters. A rising `beacn_events_dropped_total` or a "
                "zero `beacn_bus_ok` explains most \"events are missing\" reports.",
                "Server logs under the `beacn.*` namespaces carry the event or connection "
                "id for every isolated failure.",
            ], ordered=True),
        ],
    },
)
