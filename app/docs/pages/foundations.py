"""Foundations — what BEACN is, how it is put together, the event model, and
the delivery guarantees it makes and does not make."""

from __future__ import annotations

from typing import Any

from app.docs.blocks import cards, code, heading, note, para, steps, table, terms

PAGES: tuple[dict[str, Any], ...] = (
    # =====================================================================
    {
        "slug": "introduction",
        "section": "foundations",
        "title": "What BEACN is",
        "summary": "Centralised realtime event infrastructure — and, deliberately, not a Celery dashboard.",
        "blocks": [
            para(
                "BEACN sits between the backend systems that make things happen and the "
                "frontends and services that need to know. Backends **publish events**; "
                "consumers **subscribe** to them over WebSocket or Server-Sent Events. Tasks, "
                "notifications and messages are a thin semantic layer on top of one generic "
                "event model — they are not four separate systems."
            ),
            para(
                "The single most important sentence in this documentation is this one: **the "
                "core abstraction is an event.** Everything else — the realtime protocol, the "
                "SDKs, the control plane, the task and notification views — is built around "
                "that abstraction, and almost every design decision follows from taking it "
                "seriously."
            ),
            code(
                """
 Django ─┐                                            ┌─ browser apps
 Celery ─┤   POST /api/v1/events   (API key,          │
 cron   ─┼──────────────►  BEACN   scoped, isolated)  │─► WS  /realtime
 Go svc ─┤   ingest → validate → dedupe → persist →   │   SSE /api/v1/sse
 …       ─┘        route → fan out                    └─► services
""",
                lang="text",
                caption="Producers on the left, consumers on the right, BEACN in the middle.",
            ),

            heading("Celery is one producer"),
            para(
                "BEACN is frequently mistaken for a task-queue dashboard because a Celery "
                "worker is an obvious thing to point at it. That reading is wrong, and the "
                "architecture actively resists it: there is no Celery-specific assumption "
                "anywhere in the core. A Celery worker publishes `task.started`, "
                "`task.completed` and `task.failed` — and so could a Go service, a PHP "
                "application, a cron job, or a future Kafka consumer, producing events that "
                "are indistinguishable downstream."
            ),
            para(
                "The [Celery integration](/docs/producers) is an adapter that maps Celery's "
                "lifecycle signals onto those generic events. It is 150 lines, it lives "
                "outside the core, and BEACN would work identically if it did not exist."
            ),
            note(
                "If you are evaluating BEACN as \"a better Flower\", you will be "
                "disappointed by the parts that are not about tasks and puzzled by the parts "
                "that are about topics, environments and replay. Evaluate it as event "
                "infrastructure that happens to observe tasks well.",
                tone="caution",
                title="A framing that will mislead you",
            ),

            heading("The four semantic kinds"),
            para(
                "BEACN keeps a clean conceptual distinction between four things that happen "
                "in a backend, while representing all of them as events on a topic. The "
                "`kind` is **derived from the event name**, never declared by the producer."
            ),
            terms([
                ("Event — *something happened*",
                 "The default. `payment.completed`, `deployment.finished`, `user.signed_up`. "
                 "A fact about the past. Most of what flows through BEACN is this."),
                ("Task — *asynchronous work is occurring*",
                 "`task.created`, `task.started`, `task.progress`, `task.retrying`, "
                 "`task.completed`, `task.failed`, `task.revoked`. BEACN additionally folds "
                 "these into a `tasks` row keyed on `data.task_id`, so the control plane can "
                 "show a task's lifecycle without the consumer reassembling it."),
                ("Notification — *someone needs to know*",
                 "`notification.created`. BEACN writes a `notifications` row with recipient, "
                 "channel and delivery status. The event still travels on its topic."),
                ("Message — *addressed to a particular consumer or channel*",
                 "`message.created`, `chat.message.created`. Delivered to its topic verbatim; "
                 "no extra bookkeeping. The `kind` exists so a chat client can filter."),
            ]),
            para(
                "This is covered in full on [The event envelope](/docs/event-model). The "
                "point here is that they *coexist* in one model rather than fragmenting into "
                "four subsystems with four APIs and four sets of operational tooling."
            ),

            heading("What you get from centralising this"),
            cards([
                ("One realtime interface for every frontend",
                 "A browser app subscribes to BEACN once and receives payments, deployments, "
                 "task progress, notifications and chat through the same connection and the "
                 "same protocol — instead of a bespoke WebSocket endpoint per backend team."),
                ("Producers do not run WebSocket servers",
                 "A Django app makes one authenticated HTTP POST. It never holds a socket, "
                 "never worries about fan-out, backpressure or slow consumers, and never "
                 "ships a realtime library to the browser."),
                ("Durable history and replay, for free",
                 "Every persisted event is queryable and replayable within its retention "
                 "window. A consumer that was offline reconnects and asks for what it missed "
                 "— see [Replay](/docs/delivery-semantics)."),
                ("Environment isolation as a property, not a convention",
                 "`development`, `staging` and `production` never cross. It is a column that "
                 "leads every index and is read from the credential, never the request body."),
            ]),

            heading("What BEACN is not"),
            steps([
                "**Not a message queue.** There is no worker-pull model, no acknowledgement-"
                "gated redelivery, no dead-letter queue. Live delivery is fire-and-forget; "
                "durability and catch-up come from the event store plus replay. If you need "
                "at-least-once *work distribution*, use a queue and publish events about it.",
                "**Not a database you query for state.** BEACN stores events, not the current "
                "value of things. `payment.completed` tells you a payment completed; it does "
                "not answer \"is this payment refundable right now\".",
                "**Not exactly-once.** It is not offered and not implemented. Every event "
                "carries a globally sortable id and consumers deduplicate — "
                "[Delivery semantics](/docs/delivery-semantics) is blunt about this.",
                "**Not a Celery replacement.** Celery still runs your tasks. BEACN observes "
                "them.",
            ]),

            heading("Built on Sillo"),
            para(
                "The backend is a [Sillo](https://sillo.build) application. Sillo supplies "
                "the routing, middleware, sessions, RBAC, the Record ORM, migrations, the "
                "console, the job queue and the WebSocket stack; `sillo-wire` (imported as "
                "`sillo_wire`) supplies the non-blocking per-connection fan-out. BEACN adds "
                "the event domain and no framework of its own."
            ),
        ],
    },

    # =====================================================================
    {
        "slug": "architecture",
        "section": "foundations",
        "title": "System architecture",
        "summary": "Ingestion, the event bus, the realtime hub, persistence, and how a single event travels through all of them.",
        "blocks": [
            para(
                "This page follows one event from the HTTP POST that creates it to the "
                "browser that receives it, naming every component it passes through. Later "
                "pages go deep on each; this is the map."
            ),
            code(
                """
 producer                                            consumer
 ────────                                             ────────
   │ POST /api/v1/events                                 ▲ WS frame / SSE event
   ▼                                                     │
 ┌─────────────────────────────────────────────────────┴──────────┐
 │  routes/api/v1.py            authenticate (API key) + scope     │
 │       │                                                         │
 │       ▼                                                         │
 │  domain.events.Envelope.ingest   validate · derive kind · cap   │
 │       │                                                         │
 │       ▼                                                         │
 │  app.services.ingest                                            │
 │    ├─ idempotency  (EventIdempotency, 24h)                      │
 │    ├─ persist      (Event row — if the topic persists)          │
 │    ├─ semantic     (Task upsert / Notification insert)          │
 │    └─ fan out ─► realtime.Realtime.publish                      │
 │                        │                                        │
 │                        ▼                                        │
 │            realtime.bus.EventBus     in-process | Redis pub/sub  │
 │                        │  (one channel per environment)         │
 │                        ▼                                        │
 │            sillo_wire.Hub            local, non-blocking fan-out │
 │                        │  bounded queue + writer task per peer  │
 │                        ▼                                        │
 │            RealtimeSession (WS)  /  SSE stream                   │
 └────────────────────────────────────────────────────────────────┘
                          │
                 persistent database  (SQLite dev · Postgres prod)
""",
                lang="text",
            ),

            heading("Ingestion"),
            para(
                "`POST /api/v1/events` accepts a single event or a batch of up to 500. The "
                "request authenticates with an API key (`Authorization: Bearer bk_...`), "
                "which fixes the `producer` and the `environment` — the body cannot spoof "
                "either. Each raw event is validated and normalised by "
                "`domain.events.Envelope.ingest`, which lives in the framework-free domain "
                "layer so the same validation runs whether the caller is the REST endpoint, "
                "the CLI, or the Celery adapter."
            ),
            para(
                "Validation failures in a batch are *partial*: valid events are accepted and "
                "the response lists the rejected ones by index. Nothing is stored halfway."
            ),

            heading("Idempotency and persistence"),
            para(
                "If the producer supplied an `idempotency_key`, a marker row keyed on "
                "`(environment, producer, key)` is claimed first; a repeat within 24 hours "
                "returns the original event id and a `200` rather than a `201`. The unique "
                "constraint makes concurrent duplicate publishes race safely."
            ),
            para(
                "The event is then written to the `events` table — unless the topic has a "
                "row that sets `persist = false`, in which case it is a live-only topic with "
                "no history and no replay. `task.*` events additionally upsert a `tasks` row; "
                "`notification.*` events insert a `notifications` row. Persistence happens "
                "**before** fan-out, so a consumer that later replays never sees an event the "
                "live stream skipped."
            ),

            heading("The event bus"),
            para(
                "`realtime.bus.EventBus` carries the serialised event to every BEACN "
                "instance. Two implementations, one interface:"
            ),
            table(
                ["Backend", "When", "Behaviour"],
                [
                    ["`InProcessBus`", "single process (default; the whole test suite)",
                     "delivers straight to the local hub"],
                    ["`RedisBus`", "`BEACN_BUS=redis` + `REDIS_URL`",
                     "publishes to one Redis channel per environment; every instance "
                     "subscribes once and re-fans-out locally. Publishing also delivers "
                     "locally immediately, and the subscriber loop de-dupes by event id so "
                     "the local copy is not delivered twice."],
                ],
            ),
            note(
                "Redis being unavailable degrades `RedisBus` to local-only fan-out and logs "
                "it; it never blocks ingestion or persistence. Redis is used for fan-out, "
                "presence and rate-limit coordination — it is **never** the database.",
                tone="info",
                title="Redis is optional",
            ),

            heading("The realtime hub"),
            para(
                "Each instance holds one `sillo_wire.Hub`. When the bus hands it "
                "`(topic, event)`, it broadcasts to every local peer joined to that topic. "
                "Each peer has a **bounded queue and its own writer task**, so a broadcast "
                "only ever enqueues — one client that has stopped reading cannot stall the "
                "delivery to everyone else in the topic. When a queue fills, the overflow "
                "policy decides what happens (drop-oldest by default). See "
                "[The realtime protocol](/docs/realtime-protocol) for the backpressure detail."
            ),

            heading("The connection"),
            para(
                "A WebSocket connection is a `RealtimeSession`: it owns the peer, runs the "
                "protocol loop, authorises every `subscribe` and `replay` against the "
                "connection's grant, answers heartbeats, and guarantees the peer leaves "
                "every topic and the `Connection` row is closed when the socket ends — "
                "including when a handler raises. SSE connections reuse the same hub through "
                "a lighter adapter."
            ),

            heading("The control plane"),
            para(
                "The dashboard (`routes/web/`) and the control API (`routes/api/control.py`) "
                "are a second surface, authenticated with an operator session or a CLI "
                "bearer token and gated by RBAC. They manage producers, keys, topics, "
                "subscriptions, connections and operators, and read the numbers the "
                "dashboard shows. The producer plane and the control plane never share a "
                "credential."
            ),

            heading("Horizontal scaling"),
            para(
                "Multiple instances sit behind a load balancer with no sticky-session "
                "requirement. A producer connected to instance A reaches a consumer on "
                "instance C because the bus fans the event to every instance. The database "
                "is the single source of truth; Redis carries only ephemeral coordination. "
                "See [Scaling](/docs/scaling)."
            ),
        ],
    },

    # =====================================================================
    {
        "slug": "event-model",
        "section": "foundations",
        "title": "The event envelope",
        "summary": "Required fields, optional metadata, producer payload, the kinds, and the rules that are enforced at ingestion.",
        "blocks": [
            para(
                "Every event BEACN accepts is normalised into one envelope. The producer "
                "controls a small required core and a set of optional metadata; BEACN owns "
                "the rest and will not let the body override it."
            ),
            code(
                """
{
  "id":              "evt_01J9Z8M7Q0X3F2K5V8B1N4C6D7",   // server — ULID, sortable
  "event":           "payment.completed",                 // producer — REQUIRED
  "topic":           "payments",                          // producer — REQUIRED*
  "kind":            "event",                             // server — derived from `event`
  "producer":        "payments-api",                      // server — from the API key
  "source":          "payments-service",                  // producer — optional
  "environment":     "production",                        // server — from the API key
  "timestamp":       "2026-09-06T20:00:00Z",              // server — ingestion time
  "occurred_at":     "2026-09-06T19:59:58Z",              // producer — optional
  "correlation_id":  "cor_7f3c...",                       // producer — optional
  "request_id":      "req_9a1e...",                       // producer — optional
  "user_id":         "usr_123",                           // producer — optional
  "organization_id": "org_123",                           // producer — optional
  "project_id":      "prj_9",                             // producer — optional
  "schema_version":  "1",                                 // producer — default "1"
  "severity":        "info",                              // producer — default "info"
  "idempotency_key": "pay_123:completed",                 // producer — optional
  "data": { "payment_id": "pay_123", "amount": 50000 }    // producer — any JSON, <= 256 KiB
}
""",
                lang="json",
            ),
            note(
                "`topic` is only *technically* optional: if a producer omits it, BEACN "
                "defaults it to the first dotted segment of `event` (`payment.completed` → "
                "`payments`). Set it explicitly in anything real.",
                tone="info",
            ),

            heading("Required, optional, server-set"),
            table(
                ["Category", "Fields"],
                [
                    ["**Required** (producer)", "`event`; `topic` (or it is derived)"],
                    ["**Server-set, immutable**", "`id`, `producer`, `environment`, `timestamp`, `kind`"],
                    ["**Optional metadata** (producer)",
                     "`source`, `occurred_at`, `correlation_id`, `request_id`, `user_id`, "
                     "`organization_id`, `project_id`, `schema_version` (default `\"1\"`), "
                     "`severity` (default `info`), `idempotency_key`"],
                    ["**Producer payload**", "`data` — any JSON object, at most 256 KiB serialised"],
                ],
            ),
            para(
                "`producer` and `environment` in a request body are **ignored**. This is not "
                "a validation nicety — it is the isolation boundary. A compromised producer "
                "cannot publish into production by setting a string, and cannot impersonate "
                "another producer."
            ),

            heading("Field rules enforced at ingestion"),
            terms([
                ("`event`",
                 "Dotted name, segments of `[A-Za-z0-9_-]`, one to eight segments. "
                 "`payment.completed`, `deployment.progress`, `task.failed`. An empty name, "
                 "a name with spaces, or `a..b` is rejected."),
                ("`topic`",
                 "A name, optionally namespaced with a single colon: `payments`, `user:123`, "
                 "`organization:456`, `project:789`, `chat:room-general`. Invalid characters "
                 "are rejected."),
                ("`severity`",
                 "One of `debug`, `info`, `notice`, `warning`, `error`, `critical`. Anything "
                 "else is a `422`."),
                ("`data`",
                 "Must be a JSON object and must be JSON-serialisable. Serialised size is "
                 "checked against the 256 KiB cap **before** anything is written."),
                ("`occurred_at`",
                 "Advisory only. The server `timestamp` is authoritative for ordering; "
                 "`occurred_at` is metadata for when the underlying thing happened if that "
                 "differs from when it was published. Clock skew here never affects ordering."),
            ]),

            heading("The id"),
            para(
                "`id` is `evt_` plus a 26-character ULID whose leading 48 bits are a "
                "millisecond timestamp. It is **monotonic within a process** — two ids "
                "minted in the same millisecond still compare in creation order, because the "
                "random component is incremented rather than redrawn."
            ),
            para(
                "The consequence is worth stating: **ordering by `id` is ordering by time**, "
                "so event history and replay are plain primary-key range scans with no "
                "offset and no separate sort column. A cursor in the pagination API *is* an "
                "event id."
            ),

            heading("Kinds are derived, not declared"),
            table(
                ["`event` starts with", "`kind`", "Side effect at ingestion"],
                [
                    ["`task.`", "`task`", "upsert a `tasks` row on `data.task_id`"],
                    ["`notification.`", "`notification`", "insert a `notifications` row"],
                    ["`message.` / `chat.` / `*.message.*`", "`message`", "none — delivered verbatim"],
                    ["anything else", "`event`", "none"],
                ],
            ),
            para(
                "A `task.*` event is still an ordinary event on its topic. A consumer "
                "subscribed to `tasks` receives `task.started`, `task.completed` and the "
                "rest as `event` frames; the control plane *additionally* reads the `tasks` "
                "table it maintained. The two views do not disagree because the table is "
                "built from the same events."
            ),
            note(
                "A terminal task (`completed`, `failed`, `revoked`) is never moved backwards "
                "by a late-arriving non-terminal event. Ordering across producers and "
                "instances is not guaranteed, so this rule is applied on the way into the "
                "`tasks` row.",
                tone="caution",
                title="Task lifecycle and out-of-order events",
            ),

            heading("Task and notification `data` conventions"),
            para(
                "BEACN reads a handful of keys out of `data` when it builds the `tasks` and "
                "`notifications` rows. They are conventions, not schema — an event missing "
                "them still publishes fine, it just carries less into the derived row."
            ),
            table(
                ["Kind", "`data` keys BEACN understands"],
                [
                    ["task",
                     "`task_id` (**required for a row**), `name`, `status`, `progress` (0–1), "
                     "`attempt`, `error`, `result`, `duration_ms`, `started_at`, `finished_at`"],
                    ["notification",
                     "`recipient` (falls back to `user_id`), `type`, `title`, `body` (or "
                     "`message`), `channel` (`in_app` \\| `email` \\| `sms` \\| `webhook`), "
                     "`delivery_status`"],
                ],
            ),

            heading("Immutability"),
            para(
                "There is no endpoint to update or delete an event. Retention removes whole "
                "rows on a schedule; nothing edits one in place. If you published something "
                "wrong, publish a correcting event — consumers that care about the earlier "
                "one saw it already. This is why replay is bounded, and why consumers "
                "deduplicate: see [Delivery semantics](/docs/delivery-semantics)."
            ),
        ],
    },

    # =====================================================================
    {
        "slug": "delivery-semantics",
        "section": "foundations",
        "title": "Delivery semantics, idempotency and replay",
        "summary": "What BEACN guarantees, what it does not, and how a consumer builds gap-free processing on top of it.",
        "blocks": [
            para(
                "This is the page to read before you rely on BEACN for anything that "
                "matters. It is deliberately blunt."
            ),

            heading("Live delivery is at-most-once"),
            para(
                "When an event is published, BEACN enqueues it on every currently-connected "
                "subscriber's bounded queue and moves on. There is no acknowledgement gate "
                "and no redelivery. If a subscriber's queue is full, the overflow policy "
                "(drop-oldest by default) sheds messages; if a subscriber is not connected, "
                "it simply does not receive the event live."
            ),
            para(
                "This is a choice, and the right one for a fan-out system: the alternative — "
                "blocking the broadcast until the slowest consumer acknowledges — lets one "
                "stalled client set the pace for a whole topic. BEACN sheds instead, counts "
                "what it shed (`beacn_events_dropped_total`, and per-connection), and lets "
                "the consumer catch up from the durable store."
            ),

            heading("Replay is the at-least-once path"),
            para(
                "Every persisted event can be replayed. A consumer that wants no gaps does "
                "this:"
            ),
            steps([
                "Subscribe to the topic and start receiving live events.",
                "Record the `id` of the last event it has *processed* (not merely received).",
                "On every reconnect, before trusting the live stream again, call `replay` "
                "for that topic `since` the recorded id. BEACN returns every persisted event "
                "with a larger id, in order.",
                "Process the replayed events, deduplicating against ids already seen, then "
                "resume live processing.",
            ], ordered=True),
            para(
                "The [Python SDK](/docs/python-sdk) and [TypeScript SDK](/docs/typescript-sdk) "
                "both do steps 2–4 automatically inside `subscribe()`."
            ),
            note(
                "If your `since` id is older than the oldest event still retained for that "
                "topic, some events between your cursor and the oldest retained one are "
                "**gone** — retention removed them. The replay response then has "
                "`truncated: true` and `earliest_available`, so you know you have a hole "
                "rather than believing you caught up cleanly. BEACN will not pretend "
                "otherwise.",
                tone="critical",
                title="Replay is bounded by retention",
            ),

            heading("Exactly-once is not offered"),
            para(
                "There is no configuration that turns it on, because it is not implemented. "
                "Duplicates *will* reach a consumer: a producer retried a publish, a "
                "reconnect replayed an overlapping window, the bus redelivered on a Redis "
                "blip. The contract BEACN gives you instead is:"
            ),
            steps([
                "Every event has a **globally useful, sortable id** (`evt_` + ULID).",
                "Consumers deduplicate on that id. A small LRU set of recently-seen ids is "
                "enough for the reconnect case; a persistent set is needed only if you "
                "cannot tolerate a duplicate across a consumer restart.",
                "Effects should be **idempotent** where you can make them so — `UPSERT` "
                "rather than `INSERT`, `SET status = 'paid'` rather than `balance += x`.",
            ]),

            heading("Producer-side idempotency"),
            para(
                "A producer that might retry a publish should send an `idempotency_key`. "
                "BEACN keys a marker on `(environment, producer, idempotency_key)` for 24 "
                "hours (`IDEMPOTENCY_TTL_HOURS`). A repeat within the window returns the "
                "**original** event id, `deduplicated: true`, and HTTP `200` instead of "
                "`201` — no second event is created or fanned out."
            ),
            code(
                """
# a Celery task that publishes on completion — safe to retry
beacn.publish(
    "task.completed",
    topic="tasks",
    data={"task_id": task_id, "name": name, "duration_ms": elapsed_ms},
    idempotency_key=f"{task_id}:completed",   # one per (task, lifecycle point)
)
""",
                lang="python",
            ),
            table(
                ["Situation", "Key shape"],
                [
                    ["One event per business fact", "the fact's id — `pay_123:completed`"],
                    ["A batch import that may be re-run", "`import-42:{index}` per event (the SDK derives this from a batch key)"],
                    ["A periodic job that must not double-count", "`report-{name}-{date}`"],
                ],
            ),
            note(
                "After the TTL the marker is swept and the key is free again. Do not use an "
                "`idempotency_key` for events you *want* to be able to re-emit later.",
                tone="caution",
            ),

            heading("Ordering"),
            para(
                "Within a single producer publishing serially, ids are assigned in call "
                "order and consumers see them in that order (modulo the caveat below). "
                "Across producers, across a batch, and across instances, **order is not "
                "guaranteed** — two events published in the same millisecond by different "
                "producers can arrive either way round."
            ),
            para(
                "If you need a total order for a stream, put a sequence number in `data` at "
                "the producer and let the consumer sort or gate on it. BEACN's `id` gives "
                "you a *stable* order for replay and pagination; it does not give you the "
                "producer's causal order for free."
            ),

            heading("Failure behaviour, summarised"),
            table(
                ["Failure", "What BEACN does"],
                [
                    ["A consumer is slow", "bounded queue overflows per its policy; drops are counted; the rest of the topic is unaffected"],
                    ["A consumer disconnects", "it stops receiving live; it replays on reconnect"],
                    ["Redis is down (`RedisBus`)", "degrades to local-only fan-out, retries connect with backoff; ingestion and persistence unaffected"],
                    ["The database is down", "ingestion returns `503`; the SDK retries with backoff and jitter; live traffic already in flight still fans out"],
                    ["A malformed publish", "`422` with a field-level error list; nothing is stored"],
                    ["A duplicate publish", "idempotency key → original id, `deduplicated: true`, `200`"],
                    ["Instance shutdown (`SIGTERM`)", "stop accepting, send close `1001` to sockets, flush writers, drain the bus"],
                ],
            ),
            para("The retry policy is covered per client on the SDK pages; there is no infinite retry anywhere."),
        ],
    },
)
