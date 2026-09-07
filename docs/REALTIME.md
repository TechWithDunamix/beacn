# BEACN realtime protocol

One WebSocket endpoint, JSON frames.

```
GET /realtime?token=<realtime-jwt | bk_api-key>
```

The `token` is either a short-lived JWT minted by
`POST /api/v1/realtime/tokens` (or `POST /api/control/realtime/token` for an
operator), or a raw API key with the `events:read` scope for a service consumer.

SSE fallback (read-only, no client→server frames):

```
GET /api/v1/sse?token=<...>&topics=a,b,c
```

---

## Frames

### Client → server

| frame | fields | meaning |
|---|---|---|
| `subscribe` | `topic`, `ref?` | ask to receive events on `topic` |
| `unsubscribe` | `topic` | stop receiving |
| `replay` | `topic`, `since?` | send persisted events on `topic` with `id > since` |
| `ack` | `id` | acknowledge processing of event `id` (bookkeeping) |
| `ping` | — | liveness |

### Server → client

| frame | fields |
|---|---|
| `welcome` | `connection_id`, `heartbeat_ms` |
| `subscribed` | `topic`, `ref?` |
| `unsubscribed` | `topic` |
| `event` | `id`, `event`, `topic`, `kind`, `producer`, `timestamp`, `data`, `seq?`, … |
| `replay_done` | `topic`, `count`, `truncated`, `next_since` |
| `error` | `code`, `message`, `topic?`, `ref?` |
| `pong` | — |

Example session:

```json
→ {"type":"welcome","connection_id":"con_01J...","heartbeat_ms":25000}
← {"type":"subscribe","topic":"tasks","ref":"c1"}
→ {"type":"subscribed","topic":"tasks","ref":"c1"}
← {"type":"replay","topic":"tasks","since":"evt_01J8..."}
→ {"type":"event","id":"evt_01J9...","event":"task.completed","topic":"tasks","data":{}}
→ {"type":"replay_done","topic":"tasks","count":3,"truncated":false,"next_since":null}
→ {"type":"event","id":"evt_01JA...","event":"task.failed","topic":"tasks","data":{}}
```

---

## Authorization

Every `subscribe` and `replay` is authorized **server-side** against the
connection's grant (`domain/topics.py`). The frontend's opinion is never
consulted.

| topic shape | who may subscribe |
|---|---|
| `payments`, `deployments`, … (public) | anyone authenticated in the same environment |
| `user:<id>` | the connection whose token carries `uid == <id>` |
| `organization:<id>` | token with `org == <id>` |
| `project:<id>` | token whose `projects` contains `<id>` |
| topic row marked `private` | a matching `topics` glob pattern in the token, or an operator token |
| `system`, `audit` | token with the `system:read` scope, or an operator token |

A cross-environment subscribe is always refused.

---

## Lifecycle & backpressure

- **Heartbeat.** The server sends `heartbeat_ms` in `welcome`. If a client sends
  nothing for 3× that interval the server closes the connection. Clients should
  `ping` when idle.
- **Connection expiry.** Connections are closed after
  `REALTIME_CONNECTION_MAX_SECONDS` (default 12h); reconnect with a fresh token.
- **Slow consumers.** Each connection has a bounded queue
  (`REALTIME_QUEUE`, default 512). Overflow policy is `drop_oldest` by default
  (`drop_newest` / `close` are available). Drops are counted and exported at
  `/metrics` (`beacn_events_dropped_total`) and on the connection row.
- **Graceful shutdown.** On `SIGTERM` the instance stops accepting, sends close
  `1001` to every socket, flushes writer tasks and drains the bus.
- **Reconnect + replay.** On reconnect, `replay` each topic `since` the last
  `id` you processed. If `truncated` is `true`, retention removed events between
  your cursor and `earliest_available` — you have a gap, handle it.
