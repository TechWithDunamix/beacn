# Performance

BEACN ships a benchmark harness rather than a performance claim. See
[`benchmarks/README.md`](../benchmarks/README.md) for the methodology and the
caveats — the short version:

```bash
python -m benchmarks.run --events 20000 --batch 100 --peers 200
```

measures ingestion throughput and latency percentiles (service path and HTTP
path), and local WebSocket fan-out under backpressure, against an **in-process**
instance (SQLite `:memory:`, `InProcessBus`). Those conditions isolate BEACN's
own overhead; they are for catching regressions, not for sizing a cluster.

## How to size a real deployment

1. Run the benchmark on your target hardware to get the single-process ceiling.
2. Put Postgres and Redis in the path and re-measure — persistence is the
   bottleneck and it now includes network + `fsync`.
3. Scale the `web` process horizontally behind a load balancer; the bus
   (`BEACN_BUS=redis`) makes fan-out cross-instance. Throughput is roughly
   linear in web processes until the database saturates.
4. Watch `/metrics`: `beacn_events_dropped_total` rising means consumers are
   slower than the stream and the per-connection queue (`REALTIME_QUEUE`) or
   the overflow policy needs tuning, not more CPU.

## What is optimised, and what is not

- **Ordering by `id`** — every history and replay query is a primary-key range
  scan; there is no offset pagination and no separate sort column.
- **`environment` leads every index** — one installation's environments never
  scan each other's rows.
- **Persistence before fan-out** — a replay never misses an event the live
  stream skipped; the cost is that ingestion latency includes one insert.
- **Fan-out never blocks** (`sillo_wire`) — a stalled consumer cannot slow the
  room; it is shed instead.
- Not yet optimised: batch inserts (`Event.create` per row), and a shared
  cross-instance rate limiter (the current one is per-process by design).
