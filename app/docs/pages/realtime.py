"""Realtime — topics and their authorization, and the wire protocol for
WebSocket and SSE."""

from __future__ import annotations

from typing import Any

from app.docs.blocks import cards, code, heading, note, para, steps, table, terms

PAGES: tuple[dict[str, Any], ...] = (
    # =====================================================================
    {
        "slug": "topics",
        "section": "realtime",
        "title": "Topics, channels and authorization",
        "summary": "How events are routed, which topics are private, and how a subscription is authorized server-side on every attempt.",
        "blocks": [
            para(
                "A **topic** is the routing key on an event and the unit a consumer "
                "subscribes to. Every event has exactly one topic. There is no wildcard "
                "subscribe — a consumer names the topics it wants, over "
                "[the realtime protocol](/docs/realtime-protocol)."
            ),

            heading("Topics do not need to be created"),
            para(
                "An event can be published to a topic that has no row in the database. Its "
                "visibility is then *derived* from its shape:"
            ),
            table(
                ["Topic shape", "Derived visibility", "Who may subscribe"],
                [
                    ["`payments`, `deployments`, `orders` …", "public", "anyone authenticated in the same environment"],
                    ["`user:<id>`", "private", "the connection whose token carries `uid == <id>`"],
                    ["`organization:<id>`", "private", "token with `org == <id>`"],
                    ["`project:<id>`", "private", "token whose `projects` list contains `<id>`"],
                    ["`system`, `audit`", "internal", "token with the `system:read` scope, or an operator token"],
                ],
            ),
            para(
                "A **topic row** exists only when you want to *configure* a topic — pin its "
                "visibility (make a plain-named topic private), set a per-topic retention, "
                "or turn persistence off entirely. Manage rows in the dashboard under "
                "**Topics** or with `POST /api/control/topics`."
            ),
            terms([
                ("`visibility`", "`public`, `private` or `internal` — overrides the derived value"),
                ("`persist`", "`false` makes it a live-only topic: no history, no replay, nothing written to the `events` table"),
                ("`retention_hours`", "per-topic override of `EVENT_RETENTION_HOURS`; blank uses the global default"),
            ]),

            heading("Naming conventions"),
            para(
                "Topics are cheap. The conventions that work well in practice:"
            ),
            cards([
                ("Domain topics for broadcast facts",
                 "`payments`, `deployments`, `orders`, `signups`. Public. A dashboard or an "
                 "internal tool subscribes to the whole stream."),
                ("`user:<id>` for per-user delivery",
                 "Notifications, DMs, \"your export is ready\". Private — a browser session's "
                 "realtime token carries its own `uid` and can only reach its own."),
                ("`organization:<id>` / `project:<id>` for tenant scoping",
                 "A multi-tenant frontend subscribes to its org's topic and receives only "
                 "that tenant's events."),
                ("`chat:<room>` for message channels",
                 "Namespaced so the room list is one prefix scan, and so a token can be "
                 "granted `chat:*` without granting `user:*`."),
            ]),

            heading("Authorization is server-side, on every attempt"),
            para(
                "This is the load-bearing part. `domain/topics.py::authorize_subscription` "
                "is a pure function called on **every** `subscribe` and **every** `replay` "
                "frame, against the connection's *grant*. The frontend's opinion about "
                "whether it may see a topic is never consulted."
            ),
            code(
                """
# what the realtime layer runs for `{"type":"subscribe","topic":"user:42"}`
decision = authorize_subscription(topic="user:42", grant=connection_grant, spec=topic_row_or_None)
if not decision:
    send({"type": "error", "code": decision.code, "message": decision.reason, "topic": "user:42"})
    return
""",
                lang="python",
            ),
            para("A **grant** is built from the connection's credential and carries:"),
            table(
                ["Field", "Source", "Used for"],
                [
                    ["`environment`", "the realtime token or API key", "every topic; a cross-environment subscribe is always refused"],
                    ["`user_id`", "the token's `uid` claim", "matching `user:<id>`"],
                    ["`organization_id`", "the token's `org` claim", "matching `organization:<id>`"],
                    ["`project_ids`", "the token's `projects` claim", "matching `project:<id>`"],
                    ["`scopes`", "the token or the API key", "`system:read` unlocks `system` / `audit`"],
                    ["`topic_patterns`", "the token's `topics` claim", "an explicit glob allow-list — `chat:*`, `secret-*`"],
                    ["`operator`", "an operator-minted token", "sees everything in its environment"],
                ],
            ),

            heading("How a browser gets a grant"),
            steps([
                "The browser authenticates to *your* backend as it already does.",
                "Your backend calls `POST /api/v1/realtime/tokens` with its API key, passing "
                "the signed-in user's `user_id`, `organization_id`, `project_ids` and any "
                "`topic_patterns` it should have.",
                "BEACN returns a short-lived JWT (`REALTIME_TOKEN_TTL_SECONDS`, default 1h) "
                "carrying exactly those claims and the key's environment.",
                "The browser opens `wss://beacn/realtime?token=<jwt>` and subscribes. Every "
                "subscribe is checked against the claims in that JWT.",
            ], ordered=True),
            note(
                "A service consumer can skip the JWT and connect with its API key directly "
                "(`?token=bk_...`), which requires the `events:read` scope. Its grant then "
                "has no user/org claims — it can reach public topics and, with `system:read`, "
                "internal ones, but not `user:*`.",
                tone="info",
            ),

            heading("Presence"),
            para(
                "`sillo_wire` tracks identities per topic — the people in a room, not the "
                "sockets — so one person with a phone and two browser tabs counts once for "
                "`identities()` and is reached by all three for a targeted send. BEACN does "
                "not currently expose a presence API on the realtime protocol; the hub "
                "primitives are there if you build one."
            ),
        ],
    },

    # =====================================================================
    {
        "slug": "realtime-protocol",
        "section": "realtime",
        "title": "The realtime protocol",
        "summary": "The WebSocket frame protocol, the SSE fallback, heartbeats, connection lifecycle and backpressure.",
        "blocks": [
            para(
                "One WebSocket endpoint, JSON frames. If you use an SDK you do not need this "
                "page; if you are writing a client in a language BEACN does not ship an SDK "
                "for, this is the whole contract."
            ),
            code(
                """
GET /realtime?token=<realtime-jwt | bk_api-key>
""",
                lang="text",
            ),
            para(
                "The token is a JWT minted by `POST /api/v1/realtime/tokens` "
                "(or `POST /api/control/realtime/token` for an operator), or a raw API key "
                "with `events:read` for a service consumer. There is no other auth channel — "
                "no header, no cookie."
            ),

            heading("Client → server frames"),
            table(
                ["Frame", "Fields", "Meaning"],
                [
                    ["`subscribe`", "`topic`, `ref?`", "start receiving events on `topic`; `ref` is echoed on the reply"],
                    ["`unsubscribe`", "`topic`", "stop receiving"],
                    ["`replay`", "`topic`, `since?`", "send persisted events on `topic` with `id > since`, then a `replay_done`"],
                    ["`ack`", "`id`", "acknowledge processing of event `id` — bookkeeping only, not required for liveness"],
                    ["`ping`", "—", "liveness; the server answers `pong`"],
                ],
            ),

            heading("Server → client frames"),
            table(
                ["Frame", "Fields"],
                [
                    ["`welcome`", "`connection_id`, `heartbeat_ms`"],
                    ["`subscribed`", "`topic`, `ref?`"],
                    ["`unsubscribed`", "`topic`"],
                    ["`event`", "`id`, `event`, `topic`, `kind`, `producer`, `timestamp`, `severity`, `data`, `seq?`, and any set metadata"],
                    ["`replay_done`", "`topic`, `count`, `truncated`, `next_since`"],
                    ["`error`", "`code`, `message`, `topic?`, `ref?`"],
                    ["`pong`", "—"],
                ],
            ),
            code(
                """
→ {"type":"welcome","connection_id":"con_01J...","heartbeat_ms":25000}
← {"type":"subscribe","topic":"tasks","ref":"c1"}
→ {"type":"subscribed","topic":"tasks","ref":"c1"}
← {"type":"replay","topic":"tasks","since":"evt_01J8..."}
→ {"type":"event","id":"evt_01J9...","event":"task.completed","topic":"tasks","data":{}}
→ {"type":"replay_done","topic":"tasks","count":3,"truncated":false,"next_since":null}
→ {"type":"event","id":"evt_01JA...","event":"task.failed","topic":"tasks","data":{}}
← {"type":"ping"}
→ {"type":"pong"}
""",
                lang="text",
            ),

            heading("Errors do not close the connection"),
            para(
                "A forbidden `subscribe` returns an `error` frame carrying the topic — that "
                "one subscription failed, the connection stays open and its other "
                "subscriptions keep flowing. The connection is closed only for an "
                "authentication failure at connect time (code `1008`), the hard lifetime "
                "limit, or a `SIGTERM` (code `1001`)."
            ),
            table(
                ["`code`", "Meaning"],
                [
                    ["`unauthenticated`", "the token is missing, malformed or expired (connect-time → close 1008)"],
                    ["`forbidden`", "not allowed on that topic (frame-level, connection stays open)"],
                    ["`invalid`", "the frame did not parse or was missing a required field"],
                    ["`expired`", "the connection reached `REALTIME_CONNECTION_MAX_SECONDS`"],
                ],
            ),

            heading("Heartbeat and lifecycle"),
            steps([
                "The server sends `heartbeat_ms` in `welcome`. If the client sends **nothing** "
                "for 3× that interval, the server assumes it is gone and closes the socket. "
                "A client with no traffic to send should `ping`.",
                "Connections are closed after `REALTIME_CONNECTION_MAX_SECONDS` (default 12h). "
                "Reconnect with a fresh token — the old JWT has likely expired anyway.",
                "On graceful shutdown the instance stops accepting, sends close `1001` to "
                "every socket, flushes the per-connection writers and drains the bus. A "
                "client should treat `1001` as \"reconnect immediately, probably to a "
                "different instance\".",
            ], ordered=True),

            heading("Backpressure and slow consumers"),
            para(
                "Each connection has a bounded outbound queue (`REALTIME_QUEUE`, default "
                "512) with its own writer task. A broadcast enqueues and returns; it never "
                "waits on a socket. When the queue is full, the overflow policy decides:"
            ),
            table(
                ["Policy", "Behaviour", "Use for"],
                [
                    ["`drop_oldest` (default)", "discard the head, keep the newest", "state you can reconcile — prices, cursors, progress"],
                    ["`drop_newest`", "reject the incoming event, keep order", "streams where you would rather have a clean prefix and replay the rest"],
                    ["`close`", "disconnect the peer", "consumers that must never miss anything — let them reconnect and replay"],
                ],
            ),
            note(
                "Drops are counted: `beacn_events_dropped_total` at `/metrics`, and per "
                "connection. A rising drop count means your consumers are slower than the "
                "stream — tune the queue, change the policy, or split the topic. It is not a "
                "reason to add CPU.",
                tone="caution",
            ),

            heading("SSE fallback"),
            para(
                "For read-only consumers that cannot hold a WebSocket, "
                "`GET /api/v1/sse?token=<...>&topics=a,b,c` streams the same `event` frames "
                "as Server-Sent Events. There are no client→server frames — the topic set is "
                "fixed at connect time in the query string, and each topic is authorized the "
                "same way. The [Python SDK](/docs/python-sdk)'s synchronous `subscribe()` "
                "uses this, which is why it needs no extra dependency."
            ),

            heading("Reconnect + replay, the client's job"),
            para(
                "The protocol gives you the primitives; gap-free processing is assembled by "
                "the client:"
            ),
            steps([
                "On connect, `subscribe` to each topic.",
                "Remember the `id` of the last event you *processed* per topic.",
                "On reconnect, `subscribe` again, then `replay` each topic `since` that id "
                "**before** processing new live events, deduplicating on id.",
                "If a `replay_done` has `truncated: true`, retention removed events between "
                "your cursor and `earliest_available` — you have a gap. Decide what that "
                "means for your consumer; BEACN will not paper over it.",
            ], ordered=True),
            para(
                "Both official SDKs do all of this inside `subscribe()`. See "
                "[Delivery semantics](/docs/delivery-semantics)."
            ),
        ],
    },
)
