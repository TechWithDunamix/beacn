# BEACN documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System, database, bus, scaling, failure strategy, risks |
| [EVENT_MODEL.md](EVENT_MODEL.md) | The envelope, required/optional/server fields, kinds, idempotency |
| [REALTIME.md](REALTIME.md) | WebSocket + SSE protocol, authorization, backpressure, reconnect |
| [API.md](API.md) | REST API v1 (producer/consumer) and the control-plane API |
| [SDK_PYTHON.md](SDK_PYTHON.md) | Official Python SDK — sync, async, consumers, retries |
| [SDK_TYPESCRIPT.md](SDK_TYPESCRIPT.md) | Official browser/client SDK |
| [CLI.md](CLI.md) | The `beacn` console |
| [INTEGRATIONS.md](INTEGRATIONS.md) | Celery, Django, Sillo, and writing a new producer |
| [SECURITY.md](SECURITY.md) | Auth, RBAC, scopes, rate limiting, environment isolation |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Configuration, Postgres, Redis, running multiple instances |
| [OBSERVABILITY.md](OBSERVABILITY.md) | Metrics, logs, correlation ids, tracing a request end to end |
| [PERFORMANCE.md](PERFORMANCE.md) | Benchmark harness, methodology, indicative numbers |

## Reading order

1. **ARCHITECTURE** for the shape of the system and the delivery-semantics
   contract.
2. **EVENT_MODEL** before you publish anything.
3. **REALTIME** before you consume anything.
4. **SDK_PYTHON** / **SDK_TYPESCRIPT** for the client you'll actually use.
5. **DEPLOYMENT** + **SECURITY** before production.

## Architectural decisions worth knowing

- **The core abstraction is an event.** Tasks, notifications and messages are a
  semantic layer keyed off the event name — not separate systems. See
  EVENT_MODEL.
- **Redis is optional.** `InProcessBus` is the default and the only backend the
  test suite needs; `RedisBus` adds cross-instance fan-out and degrades to
  local-only when Redis is down. Redis is never the database.
- **Environment isolation is structural.** It is a column that leads every
  index, and it is read from the credential, never the request body.
- **Exactly-once is not claimed.** At-most-once live + at-least-once replay +
  ULIDs for dedupe. Documented, tested, honest about retention gaps.
- **The Python SDK's sync core is stdlib-only.** `pip install beacn` pulls in
  nothing; async and WebSocket are opt-in extras.
