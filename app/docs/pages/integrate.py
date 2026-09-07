"""Integrating — the REST API, the two SDKs, and how to write a producer for
Celery, Django, a cron job, or another language."""

from __future__ import annotations

from typing import Any

from app.docs.blocks import cards, code, heading, note, para, steps, table

PAGES: tuple[dict[str, Any], ...] = (
    # =====================================================================
    {
        "slug": "rest-api",
        "section": "integrate",
        "title": "REST API v1",
        "summary": "The producer and consumer HTTP surface: ingestion, history, replay, and the read endpoints.",
        "blocks": [
            para(
                "Everything a producer or a service consumer does over HTTP is under "
                "`/api/v1`, authenticated with an API key. Every route is "
                "environment-isolated — the key names one environment and every read and "
                "write is scoped to it."
            ),
            code(
                """
Authorization: Bearer bk_<prefix>_<secret>
Content-Type:  application/json
X-Request-Id:  req_...        # optional; echoed on the response and in error bodies
""",
                lang="text",
            ),
            para("Errors are a consistent envelope:"),
            code(
                """
{ "error": { "code": "invalid", "message": "severity must be one of debug, info, …",
             "details": { "field": "severity" } } }
""",
                lang="json",
            ),
            table(
                ["`code`", "HTTP", "Meaning"],
                [
                    ["`unauthenticated`", "401", "missing / unknown / revoked / expired key"],
                    ["`forbidden`", "403", "the key lacks the scope this route needs"],
                    ["`not_found`", "404", "no such event / task / notification in this environment"],
                    ["`invalid`", "422", "validation failed (per-field `details`)"],
                    ["`payload_too_large`", "413", "body over `MAX_REQUEST_BYTES` or `data` over 256 KiB"],
                    ["`rate_limited`", "429", "with `Retry-After`"],
                    ["`unavailable`", "503", "the database is unreachable — retry with backoff"],
                ],
            ),

            heading("POST /api/v1/events"),
            para("Scope `events:publish`. Single event, or a batch of up to 500 as `{\"events\": [ ... ]}`."),
            code(
                """
POST /api/v1/events
{ "event": "deployment.completed", "topic": "deployments",
  "data": { "deployment_id": "dep_1", "status": "success" },
  "idempotency_key": "dep_1:completed" }

201  { "accepted": 1, "deduplicated": 0,
       "events": [ { "id": "evt_...", "event": "deployment.completed",
                     "topic": "deployments", "deduplicated": false } ] }
""",
                lang="json",
            ),
            steps([
                "`201` on accept; `200` if **every** event in the request was a duplicate within the idempotency window.",
                "A partial batch still succeeds — valid events are accepted and a `rejected` array lists the failures by index. Nothing is stored halfway.",
                "Rate limited per key; the cost of a request is the number of events in it.",
            ]),

            heading("GET /api/v1/events — history"),
            para(
                "Scope `events:read`. Cursor pagination: the cursor **is** an event id, so "
                "paging is a primary-key range scan. `next_cursor` is the last id returned; "
                "pass it back as `cursor`."
            ),
            table(
                ["Query parameter", "Effect"],
                [
                    ["`topic`", "exact topic"],
                    ["`event`", "exact event name"],
                    ["`event_prefix`", "name prefix — `task.`, `payment.`"],
                    ["`producer_id`", "one producer"],
                    ["`kind`", "`event` \\| `task` \\| `notification` \\| `message`"],
                    ["`severity`", "one severity level"],
                    ["`correlation_id`", "the whole chain of one business action"],
                    ["`user_id`", "events carrying that subject"],
                    ["`since` / `until`", "ISO-8601 timestamps on `published_at`"],
                    ["`order`", "`desc` (default, newest first) or `asc`"],
                    ["`limit`", "≤ 200 (default 50)"],
                    ["`cursor`", "from a prior `next_cursor`"],
                ],
            ),
            code(
                """
GET /api/v1/events?topic=payments&event_prefix=payment.&order=asc&limit=100

{ "events": [ { "id": "evt_...", "event": "payment.initiated", "topic": "payments",
                "producer": "payments-api", "timestamp": "...", "data": { … } }, … ],
  "page": { "count": 100, "next_cursor": "evt_...", "has_more": true } }
""",
                lang="json",
            ),

            heading("GET /api/v1/events/{id}"),
            para("Scope `events:read`. One event, with `delivery` bookkeeping if it is available."),

            heading("POST /api/v1/events/replay"),
            para("Scope `events:replay`. Bounded catch-up from the durable store."),
            code(
                """
POST /api/v1/events/replay
{ "topic": "payments", "since": "evt_01J8...", "limit": 1000 }

{ "events": [ … ],
  "replay": { "count": 12, "truncated": false,
              "earliest_available": "evt_01J7...", "next_since": null } }
""",
                lang="json",
            ),
            note(
                "`truncated: true` means retention removed events between your `since` and "
                "`earliest_available`. You have a gap. See "
                "[Delivery semantics](/docs/delivery-semantics).",
                tone="critical",
            ),

            heading("The read endpoints"),
            table(
                ["Method + path", "Scope", "Notes"],
                [
                    ["`GET /api/v1/topics`", "`topics:read`", "topic rows for the key's environment"],
                    ["`GET /api/v1/tasks` · `GET /api/v1/tasks/{task_id}`", "`tasks:read`", "BEACN-observed tasks with lifecycle folded in"],
                    ["`GET /api/v1/notifications`", "`notifications:read`", "`?recipient=` · `?unread=1`"],
                    ["`POST /api/v1/notifications/{id}/read`", "`notifications:write`", "mark read"],
                    ["`GET /api/v1/connections`", "`connections:read`", "realtime connections in the environment"],
                    ["`POST /api/v1/realtime/tokens`", "`events:read`", "mint a realtime JWT — body sets `user_id`, `organization_id`, `project_ids`, `topic_patterns`, `ttl_seconds`"],
                    ["`GET /api/v1/whoami`", "—", "echoes the key identity and its rate-limit budget"],
                ],
            ),

            heading("The control API"),
            para(
                "`/api/control/*` is a separate surface for the dashboard and the CLI — "
                "producers, keys, topics, subscriptions, connections, operators, audit, the "
                "dashboard numbers. It authenticates with an operator session or a CLI "
                "bearer token and is gated by [RBAC](/docs/authentication), not by API-key "
                "scopes. Session-authenticated writes also require an `X-BEACN-Control` "
                "header — a cross-site form cannot set it without a CORS preflight the "
                "config does not grant."
            ),
        ],
    },

    # =====================================================================
    {
        "slug": "python-sdk",
        "section": "integrate",
        "title": "Python SDK",
        "summary": "One file, standard-library sync core, optional async and WebSocket. Publishing, history, replay, consuming, retries.",
        "blocks": [
            para(
                "`sdk/python/beacn.py` is one self-contained module wrapping "
                "[the REST API](/docs/rest-api) and [the realtime protocol](/docs/realtime-protocol). "
                "The synchronous client and the SSE consumer use **only the standard "
                "library**, so `pip install beacn` pulls in nothing. The async client and "
                "the WebSocket consumer are opt-in extras."
            ),
            code(
                """
pip install beacn                 # sync client, SSE consumer, history — no deps
pip install "beacn[async]"        # + httpx      -> AsyncBeacn
pip install "beacn[websocket]"    # + websockets -> AsyncBeacn.subscribe over WS
""",
                lang="bash",
            ),
            note(
                "Compatibility is **Python 3.8+**. The core avoids `match`, runtime `X | Y` "
                "unions and other syntax unavailable on the oldest supported interpreter; "
                "type information is in `# type:` comments. Do not \"modernise\" it.",
                tone="info",
            ),

            heading("Publishing"),
            code(
                """
from beacn import Beacn, RetryPolicy

beacn = Beacn(
    url="https://beacn.internal",
    api_key="bk_...",
    timeout=30.0,
    retry=RetryPolicy(max_attempts=4, base_delay=0.25, max_delay=20, max_elapsed=90),
    default_topic="payments",           # optional
    default_source="payments-service",  # optional
)

res = beacn.publish("payment.completed",
                    data={"payment_id": "pay_1", "amount": 50000},
                    correlation_id="cor_1",
                    idempotency_key="pay_1:completed")
res.id            # "evt_01J..."
res.deduplicated  # 0 or 1

beacn.publish_batch(
    [{"event": "a.one"}, {"event": "a.two"}],
    idempotency_key="import-42",         # -> "import-42:0", "import-42:1"
)
""",
                lang="python",
            ),

            heading("History and replay"),
            code(
                """
page = beacn.history(topic="payments", since="2026-09-01T00:00:00Z", limit=100)
for event in page:               # one page
    ...
for event in page.autopage():    # follows next_cursor to the end
    ...
for event in beacn.iter_events(event_prefix="task.", order="asc"):
    ...

one = beacn.get_event("evt_01J...")
out = beacn.replay("payments", since="evt_01J...")   # {"events": [...], "replay": {...}}
""",
                lang="python",
            ),

            heading("Consuming — synchronous, standard library"),
            code(
                """
for event in beacn.subscribe("payments", "deployments"):
    process(event)     # Event: .id .event .topic .data .kind .severity .correlation_id
""",
                lang="python",
            ),
            para(
                "`subscribe()` mints a realtime token, opens the SSE stream, and "
                "**reconnects automatically** with backoff, resuming from the last event id "
                "it yielded so no persisted event in the gap is missed (bounded by "
                "retention). `reconnect=False` raises `ConnectionClosed` instead; "
                "`last_event_id=...` starts from a known cursor."
            ),

            heading("Async"),
            code(
                """
from beacn import AsyncBeacn

async with AsyncBeacn(url="https://beacn.internal", api_key="bk_...") as beacn:
    await beacn.publish("payment.completed", topic="payments", data={})
    events, page = await beacn.history(topic="payments")
    async for event in beacn.subscribe("payments"):    # WebSocket; needs beacn[websocket]
        print(event)
""",
                lang="python",
            ),

            heading("Errors"),
            code(
                """
BeacnError
├─ APIError(status, code, details, request_id)
│  ├─ AuthError          401 / 403
│  ├─ NotFound           404
│  ├─ ValidationError    422
│  └─ RateLimitError     429   (.retry_after)
└─ ConnectionClosed      the stream ended and reconnect was disabled
""",
                lang="text",
            ),
            para(
                "Every request carries an `X-Request-Id`; it is on `APIError.request_id` for "
                "correlating with server logs."
            ),

            heading("Retries"),
            para(
                "`RetryPolicy` — exponential backoff with full jitter. Retries on connection "
                "errors, `429` (honouring `Retry-After`) and `5xx`, and **only for "
                "idempotent requests**: `GET`, or a publish that carries an "
                "`idempotency_key`. Bounded by both `max_attempts` and `max_elapsed` — there "
                "is no infinite retry."
            ),
        ],
    },

    # =====================================================================
    {
        "slug": "typescript-sdk",
        "section": "integrate",
        "title": "TypeScript SDK",
        "summary": "The browser/client SDK: channels, the connection state machine, reconnect with replay, typed events.",
        "blocks": [
            para(
                "`@beacn/client` is browser-first — it uses the global `WebSocket` and "
                "`fetch`, and speaks [the realtime protocol](/docs/realtime-protocol). "
                "Inject implementations (`ws`, node fetch) for Node or tests."
            ),
            code(
                """
npm install @beacn/client
""",
                lang="bash",
            ),
            code(
                """
import { Beacn } from "@beacn/client";

const beacn = new Beacn({
  url: "wss://beacn.example.com",   // https:// is accepted too
  token,                            // a realtime JWT, or a bk_ API key
});

const channel = beacn.channel("tasks");
channel.on("task.completed", (event) => console.log(event.id, event.data));
channel.onAny((event) => metrics.count(event.event));
await channel.subscribe();          // connects if needed, resolves on `subscribed`
""",
                lang="typescript",
            ),

            heading("Connection state"),
            code(
                """
beacn.onStateChange((state) => {
  // CONNECTING | CONNECTED | RECONNECTING | DISCONNECTED | FAILED
});
beacn.state;           // current
beacn.connectionId;    // server-assigned con_… after `welcome`
""",
                lang="typescript",
            ),
            para(
                "`connect()` resolves on `welcome`. On an unexpected close the client "
                "**reconnects** with full-jitter backoff (base `reconnectBaseMs`, capped at "
                "15s), re-subscribes every channel, and **replays** each from the last event "
                "id it delivered. After `maxReconnectAttempts` the state becomes `FAILED`. "
                "`disconnect()` closes and does not reconnect."
            ),

            heading("Options"),
            table(
                ["Option", "Default", "Meaning"],
                [
                    ["`url`", "—", "`wss://host` or `https://host`"],
                    ["`token`", "—", "realtime JWT or `bk_` API key"],
                    ["`getToken`", "—", "`() => string | Promise<string>` called before every (re)connect; overrides `token` so an expiring JWT is refreshed"],
                    ["`maxReconnectAttempts`", "`Infinity`", "then `FAILED`"],
                    ["`reconnectBaseMs`", "`500`", "full-jitter, capped at 15000"],
                    ["`heartbeat`", "`true`", "answer idle periods with `ping`"],
                    ["`WebSocketImpl`", "`globalThis.WebSocket`", "inject for Node (`ws`)"],
                    ["`logger`", "no-op", "`{ debug, warn }`"],
                ],
            ),

            heading("Channel"),
            code(
                """
const ch = beacn.channel("user:42");
ch.on("notification.created", handler);   // by event name
ch.onAny(handler);                        // every event on the topic
ch.off("notification.created", handler);
await ch.subscribe();
await ch.replay("evt_01J...");            // catch up from a known cursor
await ch.unsubscribe();
""",
                lang="typescript",
            ),
            para(
                "A forbidden topic rejects **that channel's** `subscribe()` without tearing "
                "down the connection. Handler exceptions are caught so one bad handler never "
                "blocks delivery to the others."
            ),

            heading("Typed events"),
            code(
                """
import type { BeacnEvent } from "@beacn/client";

interface PaymentCompleted extends BeacnEvent {
  event: "payment.completed";
  data: { payment_id: string; amount: number };
}

channel.on("payment.completed", (e) => {
  const p = e as PaymentCompleted;
  charge(p.data.payment_id);
});
""",
                lang="typescript",
            ),
        ],
    },

    # =====================================================================
    {
        "slug": "producers",
        "section": "integrate",
        "title": "Writing a producer",
        "summary": "Celery, Django, a Sillo service, a cron job, another language — the same envelope over the same endpoint.",
        "blocks": [
            para(
                "A producer is anything that publishes the [event envelope](/docs/event-model) "
                "to `POST /api/v1/events` with an API key. BEACN has no dependency on any of "
                "the frameworks below; the adapters live outside the core and convert a "
                "framework's lifecycle into generic events."
            ),

            heading("Celery"),
            para(
                "`integrations/celery.py` observes Celery's task signals and republishes "
                "them as `task.*` events through the Python SDK."
            ),
            code(
                """
# worker bootstrap
from beacn import Beacn
from integrations.celery import install

beacn = Beacn(url="https://beacn.internal", api_key="bk_...")
install(beacn, source="orders-worker")   # topic defaults to "tasks"
""",
                lang="python",
            ),
            table(
                ["Celery signal", "BEACN event"],
                [
                    ["`before_task_publish`", "`task.created`"],
                    ["`task_prerun`", "`task.started`"],
                    ["`task_retry`", "`task.retrying` (`data.attempt`)"],
                    ["`task_success`", "`task.completed` (`data.duration_ms`, `data.result`)"],
                    ["`task_failure`", "`task.failed` (`data.error`, `severity: error`)"],
                    ["`task_revoked`", "`task.revoked`"],
                ],
            ),
            para(
                "Each publish carries `idempotency_key = \"<task_id>:<event>\"`, so a signal "
                "delivered twice does not create two events. Publish failures are logged and "
                "swallowed — task observability never takes down a worker. The mapping is "
                "also a pure function, `event_for(signal, task_id=..., ...)`, for non-Celery "
                "producers and unit tests."
            ),

            heading("Django"),
            code(
                """
# settings.py
from beacn import Beacn
BEACN = Beacn(url="https://beacn.internal", api_key="bk_...")
MIDDLEWARE = [..., "integrations.django.BeacnMiddleware"]
""",
                lang="python",
            ),
            steps([
                "`BeacnMiddleware` stamps a `correlation_id` on every request (from an "
                "inbound `X-Correlation-ID` or a fresh one), exposes "
                "`request.beacn.publish(...)` with the id already attached, and echoes the "
                "id on the response.",
                "`publish_model_event(instance, \"user.created\")` is a one-liner for "
                "`post_save` / `post_delete` signal handlers.",
            ]),

            heading("A Sillo service"),
            code(
                """
from beacn import Beacn
beacn = Beacn(url=..., api_key=...)

@app.events.on("order.placed")
async def _mirror(order):
    beacn.publish("order.placed", topic="orders", data=order.to_dict())
""",
                lang="python",
            ),

            heading("A cron job"),
            para(
                "A backend on a timer is a producer like any other — it just publishes "
                "infrequently. `examples/cron_reports.py` is the pattern: hold a key, "
                "publish `report.generated` on each tick with `correlation_id` and a "
                "`duration_ms`."
            ),

            heading("Another language"),
            para(
                "There is no SDK requirement. Publish the envelope over HTTP:"
            ),
            code(
                """
POST /api/v1/events
Authorization: Bearer bk_...
{ "event": "deployment.started", "topic": "deployments",
  "data": { "deployment_id": "dep_1", "service": "orders-api" } }
""",
                lang="text",
            ),
            para("What a good non-SDK producer still does:"),
            cards([
                ("Retry idempotently",
                 "On a connection error, `429` or `5xx`, retry with exponential backoff and "
                 "jitter — but only if the event carries an `idempotency_key`, so a retry "
                 "cannot double-publish. Bound the retries; never loop forever."),
                ("Batch when it is natural",
                 "One request with `{\"events\": [...]}` (≤ 500) costs one round trip and one "
                 "rate-limit charge of N. Do not batch across unrelated units of work."),
                ("Set correlation ids",
                 "Thread one `correlation_id` through every event of a business action. It "
                 "is the difference between a debuggable system and a pile of events."),
                ("Keep `data` small and JSON-native",
                 "Under 256 KiB, no binary, no framework objects. Put a reference (an id, a "
                 "URL) rather than an attachment."),
            ]),
        ],
    },
)
