# Observability

## Metrics — `GET /metrics`

Prometheus text exposition, hand-written (no `prometheus_client` dependency).

| metric | type | notes |
|---|---|---|
| `beacn_up` | gauge | 1 while serving |
| `beacn_realtime_connections` | gauge | live connections on this instance |
| `beacn_realtime_subscriptions` | gauge | topic subscriptions on this instance |
| `beacn_frames_sent_total` | counter | frames written to sockets by this instance |
| `beacn_events_delivered_total` | counter | successful local deliveries |
| `beacn_events_dropped_total` | counter | queue overflows (slow consumers) |
| `beacn_bus_ok{backend}` | gauge | 1 if the bus backend is reachable |
| `beacn_events_persisted{environment}` | gauge | events stored in the last 24h |
| `beacn_connections_open` | gauge | open connections across all instances (DB) |
| `beacn_tasks_running` | gauge | tasks in `started`/`retrying` |

Counters are per-process; scrape every instance and sum.

## Logging

Structured via Python's `logging`, namespaced: `beacn.ingest`, `beacn.bus`,
`beacn.realtime`, `beacn.celery`. Errors in delivery, fan-out and the Redis
listener are isolated — one failure never kills a loop — and logged with the
event or connection id.

## Correlation ids

A producer sets `correlation_id` on an event; it is stored, indexed
(`(environment, correlation_id)`), returned on every consumer frame, and
queryable:

```
GET /api/v1/events?correlation_id=cor_123
```

End-to-end trace of one business action:

```
HTTP request  (X-Correlation-ID / Django BeacnMiddleware assigns cor_123)
   → producer publishes  payment.completed        correlation_id=cor_123
   → BEACN ingests, persists (evt_…), routes to topic "payments"
   → bus fans out to every instance
   → each instance delivers to subscribed connections   (event frame carries cor_123)
   → frontend receives it
```

`GET /api/v1/events?correlation_id=cor_123` returns every event in that chain,
in order, with their producers and topics. `X-Request-Id` (sent by the SDK,
echoed by the API, present in error bodies) narrows it to a single HTTP call.

## Delivery attempts

`delivery_attempts` rows record (event → connection) outcomes —
`delivered` / `dropped` / `failed`, latency, ack. Written only when a subscriber
was connected at publish time, and sampled 1-in-N once a topic exceeds
`DELIVERY_SAMPLE_THRESHOLD` live subscribers so a fan-out storm cannot flood the
table. The dashboard's delivery success rate is computed from them.
