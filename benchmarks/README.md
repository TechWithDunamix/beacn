# BEACN benchmarks

```bash
python -m benchmarks.run [--events 20000] [--batch 100] [--peers 200]
```

## What is measured

| bench | path | isolates |
|---|---|---|
| `ingest (service, batch=1)` | `app.services.ingest.ingest()` directly | envelope validation + idempotency + one persist + one fan-out, per event |
| `ingest (service, batch=100)` | same, batched | amortised per-event cost |
| `ingest (HTTP, batch=100)` | `POST /api/v1/events` via `httpx.ASGITransport` | the above + ASGI + auth + JSON parse |
| `local fan-out` | `Realtime.publish` → `sillo_wire.Hub` → N in-process peers | per-connection queue + writer scheduling |

## Methodology and caveats

- **In-process.** SQLite `:memory:`, `InProcessBus`, one event loop, one
  process. There is no network, no disk sync, no Postgres planner, no Redis
  round trip, no load balancer. This is deliberate: the goal is to catch
  regressions in **BEACN's own overhead**, not to state a capacity number.
- **Rate limiting is disabled** (`INGEST_RATE_PER_MINUTE` set huge) so the
  limiter does not shape the result.
- **The HTTP figure runs on a single client connection.** Real throughput is
  higher with concurrent clients and multiple worker processes, and lower once
  Postgres and the network are in the path. Do not extrapolate.
- **Fan-out `deliveries` is intentionally less than `events × peers`.** The
  benchmark publishes a burst faster than the writer tasks drain; each peer's
  bounded queue overflows and the drop-oldest policy sheds the backlog. That is
  the slow-consumer guarantee working, and it is why a fan-out number is a
  *delivery rate under backpressure*, not a "we delivered everything" claim.

## Indicative results

From a run on macOS / Python 3.12 / x86-64 (`--events 3000 --batch 100
--peers 100`) — **your numbers will differ**:

```
ingest (service, batch=1)    ~1,700 events/s   p50 0.46ms  p99 1.2ms
ingest (service, batch=100)  ~1,900 events/s   p50 0.49ms  p99 0.58ms
ingest (HTTP,    batch=100)  ~1,700 events/s   p50 0.58ms  p99 0.68ms
local fan-out (100 peers)    ~5,000 events/s   ~16,000 deliveries/s
```

The single-process persist path is the ceiling here; a production deployment
scales it horizontally (more `web` processes) with Postgres and Redis behind
them. Measure your own deployment before making any promise about it.
