# BEACN Python SDK

One file: `sdk/python/beacn.py`. The synchronous client and the history and SSE
consumer use **only the standard library**. Async and WebSocket are optional
extras.

From this repository, the SDK is `sdk/python/beacn.py`, separate from the
server's installed packages. For a source-checkout example:

```sh
PYTHONPATH=sdk/python python your_consumer.py
```

For a separate consumer virtual environment, install the SDK from this checkout
with `pip install ./sdk/python` (run from the repository root), or use
`pip install './sdk/python[all]'` for optional transports. The server and SDK
currently share the distribution name `beacn`; keep them in separate virtual
environments to avoid replacing one with the other.

The sync module uses the standard library. Async REST requires `httpx` and
async WebSocket subscription additionally requires `websockets` in the consumer's
environment. Do not assume installing this repository's server distribution
makes `from beacn import Beacn` available; its wheel packages are the server
modules, not `sdk/python/beacn.py`.

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

`subscribe` mints a realtime token and opens the SSE stream. On connection errors
it reconnects with backoff and sends the last yielded id as `Last-Event-ID`.
The current BEACN SSE route does **not** read that header or replay stored events,
so reconnecting can leave gaps. `last_event_id=...` supplies the header; it does
not guarantee server-side catch-up. A clean server stream close ends iteration.
Pass `reconnect=False` to surface connection failures as `ConnectionClosed`.
Use explicit REST replay or WebSocket replay for recovery, checkpoint after
processing, and deduplicate overlapping deliveries. See [Operations](OPERATIONS.md).

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
