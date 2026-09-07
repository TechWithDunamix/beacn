# BEACN Python SDK

One file: `sdk/python/beacn.py`. The synchronous client and the history and SSE
consumer use **only the standard library**. Async and WebSocket are optional
extras.

```bash
pip install beacn                 # sync client, SSE consumer, history — no deps
pip install "beacn[async]"        # + httpx     -> AsyncBeacn
pip install "beacn[websocket]"    # + websockets -> AsyncBeacn.subscribe over WS
pip install "beacn[all]"
```

Compatibility: **Python 3.8+**. The core avoids `match`, runtime `X | Y` unions,
and other syntax unavailable on the oldest interpreter BEACN's framework
supports; type information is provided with `# type:` comments.

---

## Sync

```python
from beacn import Beacn, RetryPolicy

beacn = Beacn(
    url="https://beacn.internal",
    api_key="bk_...",
    timeout=30.0,
    retry=RetryPolicy(max_attempts=4, base_delay=0.25, max_delay=20, max_elapsed=90),
    default_topic="payments",           # optional
    default_source="payments-service",  # optional
)

res = beacn.publish("payment.completed", data={"payment_id": "pay_1"},
                    correlation_id="cor_1", idempotency_key="pay_1:completed")
res.id            # "evt_01J..."
res.deduplicated  # 0 or 1

beacn.publish_batch(
    [{"event": "a.one"}, {"event": "a.two"}],
    idempotency_key="import-42",         # -> "import-42:0", "import-42:1"
)
```

### History & replay

```python
page = beacn.history(topic="payments", since="2026-09-01T00:00:00Z", limit=100)
for event in page:            # one page
    ...
for event in page.autopage(): # follows next_cursor
    ...
for event in beacn.iter_events(event_prefix="task.", order="asc"):
    ...

one = beacn.get_event("evt_01J...")
out = beacn.replay("payments", since="evt_01J...")   # {"events": [...], "truncated": ...}
```

### Consuming (SSE, stdlib only)

```python
for event in beacn.subscribe("payments", "deployments"):
    process(event)                 # Event: .id .event .topic .data .kind .severity
```

`subscribe` mints a realtime token, opens the SSE stream, and **reconnects
automatically** with backoff, resuming from the last event id it yielded so no
persisted event in the gap is missed (bounded by retention). Pass
`reconnect=False` to raise `ConnectionClosed` instead, or `last_event_id=...` to
start from a known cursor.

---

## Async

```python
from beacn import AsyncBeacn

async with AsyncBeacn(url="https://beacn.internal", api_key="bk_...") as beacn:
    await beacn.publish("payment.completed", topic="payments", data={})
    events, page = await beacn.history(topic="payments")
    async for event in beacn.subscribe("payments"):   # WebSocket, needs beacn[websocket]
        print(event)
```

`AsyncBeacn.subscribe` connects over the WebSocket protocol, sends `subscribe`
for each topic, replays from `last_event_id` on reconnect, answers heartbeats,
and reconnects with capped backoff.

---

## Errors

```
BeacnError
├─ APIError(status, code, details, request_id)
│  ├─ AuthError          401 / 403
│  ├─ NotFound           404
│  ├─ ValidationError    422
│  └─ RateLimitError     429  (.retry_after)
└─ ConnectionClosed      the stream ended and reconnect was disabled
```

Every request carries an `X-Request-Id`; it is on `APIError.request_id` for
correlating with server logs.

## Retries

`RetryPolicy` — exponential backoff with full jitter. Retries on connection
errors, `429` (honouring `Retry-After`) and `5xx`, and **only for idempotent
requests**: `GET`/`PUT`/`DELETE`, or a publish that carries an
`idempotency_key`. Bounded by both `max_attempts` and `max_elapsed`; there is no
infinite retry.
