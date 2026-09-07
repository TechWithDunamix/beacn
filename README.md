# BEACN

**Centralized realtime event, task, notification and message infrastructure for
backend applications.**

BEACN sits between backend producers and frontend/consumer applications. Backend
systems — Django apps, Celery workers, cron jobs, Sillo services, Go
microservices, anything — **publish events**. Frontends and services **subscribe**
over WebSocket or SSE. Tasks, notifications and messages are a thin semantic
layer on one generic event model.

> BEACN is event infrastructure, not a Celery dashboard. Celery is one producer.
> Django is one producer. A Sillo app is one producer. A browser is one consumer.

```
 Django ─┐                                            ┌─ browser app
 Celery ─┤   POST /api/v1/events (API key, scoped)    │
 cron   ─┼──────────────►  BEACN  ──────────────►  WS /realtime
 Go svc ─┤   ingest→validate→dedupe→persist→fanout   │  SSE /sse
 …       ─┘        (bus: in-process | Redis)          └─ services
```

Built on the local **Sillo** framework — its routing, middleware, sessions,
RBAC, Record ORM, migrations, console, queue and WebSocket stack — plus
**sillo-wire** for non-blocking per-connection fan-out.

---

## What's here

| Path | What |
|---|---|
| `domain/` | Framework-free core: the event envelope, id generation, topic authorization, errors |
| `app/` | Config, auth (API keys + RBAC), services (ingest, history, replay, rate-limit, stats, retention), bootstrap |
| `database/models/` | Events, producers, API keys, topics, subscriptions, tasks, notifications, connections, delivery attempts, audit, users |
| `realtime/` | The event bus (`InProcessBus` / `RedisBus`), the `sillo_wire` hub, the WS protocol and per-connection session |
| `routes/api/v1.py` | Producer/consumer REST API |
| `routes/api/control.py` | Control-plane API (RBAC-checked; the CLI's backend) |
| `routes/api/realtime.py` | `/realtime` WebSocket + `/api/v1/sse` |
| `routes/web/` | The Inertia/React control-plane dashboard |
| `observability/metrics.py` | Prometheus text exposition at `/metrics` |
| `cli/` | The `beacn` console |
| `integrations/` | Celery and Django adapters (BEACN has no dependency on either) |
| `sdk/python/beacn.py` | The official Python SDK — one file, stdlib-only sync core |
| `sdk/typescript/` | The official browser/client SDK |
| `docs/` | Architecture, event model, realtime protocol, SDK, deployment, … |

---

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[server,dev]"          # or: pip install -e ".[server,redis,postgres]"

beacn migrate                                    # create tables, seed the RBAC catalogue
beacn user create you@example.com --role Admin --admin   # the first operator (prompts for a password)
beacn serve --reload                             # http://localhost:8000
```

More operators: `beacn user create teammate@example.com --role Developer`, or the
dashboard's **Operators** page. `beacn user role`, `beacn user disable` / `enable`,
`beacn user password` round it out — the account commands wrap
`sillo.users.commands` and add BEACN's role assignment.

Register a producer and issue a key (via the CLI, once you `beacn login`), or in
the dashboard under **Producers** → **API keys**. Then:

```python
from beacn import Beacn

beacn = Beacn(url="http://localhost:8000", api_key="bk_...")
beacn.publish("payment.completed", topic="payments", data={"payment_id": "pay_1"})

for event in beacn.subscribe("payments"):     # SSE, stdlib only
    print(event.event, event.data)
```

```bash
curl -XPOST http://localhost:8000/api/v1/events \
  -H "Authorization: Bearer bk_..." \
  -d '{"event":"deployment.completed","topic":"deployments","data":{"status":"success"}}'
```

---

## Delivery semantics (read this)

- **Live delivery is at-most-once.** Every connection has a bounded queue; a slow
  consumer's overflow policy decides what is dropped. No ack is required for
  liveness.
- **Replay is the at-least-once path.** Persisted events can be replayed from the
  durable store, bounded by retention. A consumer that wants no gaps records the
  last id it processed and, on reconnect, `replay`s from there before trusting
  the live stream.
- **Exactly-once is not offered.** Every event has a globally sortable ULID
  (`evt_…`); consumers dedupe.
- **Idempotency:** a producer that sets `idempotency_key` gets the same `evt_…`
  id back on a repeat within a 24h window (`200`, `deduplicated: true`) instead of
  a second event.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and
[`docs/REALTIME.md`](docs/REALTIME.md).

---

## Horizontal scaling

Multiple BEACN instances behind a load balancer. A producer on instance A
reaches a consumer on instance C via the **event bus**:

- `BEACN_BUS=memory` (default) — single process. What the test suite runs on.
- `BEACN_BUS=redis` + `REDIS_URL=…` — Redis pub/sub, one channel per
  environment. Redis being unavailable degrades the bus to local-only fan-out
  and never blocks ingestion.

Redis is used for fan-out, presence and rate-limit coordination only. **Durable
state is the database** — SQLite for development, Postgres for production.

---

## Tests

```bash
pytest                                   # backend: domain, API, realtime, RBAC, bus, CLI
pytest sdk/python/tests -o testpaths=sdk/python/tests   # SDK against a real server
cd sdk/typescript && npm test            # TS SDK
ruff check .
```

---

## Environments

Every API key, event, topic and realtime connection carries one of
`development` / `staging` / `production` and never crosses. The environment
comes from the API key or the signed realtime token — never from the request
body.
