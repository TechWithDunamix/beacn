# BEACN event model

## The envelope

```json
{
  "id": "evt_01J9Z8M7Q0X3F2K5V8B1N4C6D7",
  "event": "payment.completed",
  "topic": "payments",
  "kind": "event",
  "producer": "payments-api",
  "source": "payments-service",
  "environment": "production",
  "timestamp": "2026-09-06T20:00:00Z",
  "occurred_at": "2026-09-06T19:59:58Z",
  "correlation_id": "cor_...",
  "request_id": "req_...",
  "user_id": "usr_123",
  "organization_id": "org_123",
  "project_id": "prj_9",
  "schema_version": "1",
  "severity": "info",
  "data": { "payment_id": "pay_123", "amount": 50000 }
}
```

### Required vs optional vs server-set

| category | fields |
|---|---|
| **required** (producer) | `event`, `topic` (defaults to the first segment of `event` if omitted) |
| **server-set, immutable** | `id`, `producer`, `environment`, `timestamp`, `kind` |
| **optional metadata** (producer) | `source`, `occurred_at`, `correlation_id`, `request_id`, `user_id`, `organization_id`, `project_id`, `schema_version` (default `"1"`), `severity` (default `info`), `idempotency_key` |
| **producer-defined payload** | `data` — any JSON object, ≤ 256 KiB |

`producer` and `environment` in a request body are **ignored** — they come from
the authenticated API key. This is not a validation nicety; it is the isolation
boundary.

### Rules

- `event` — dotted, `[A-Za-z0-9_-]` segments, 1–8 of them. `payment.completed`,
  `deployment.progress`, `task.failed`.
- `severity` — one of `debug`, `info`, `notice`, `warning`, `error`, `critical`.
- Events are **immutable** after publication. There is no update or delete
  endpoint; retention removes them wholesale.
- `id` is a ULID, so ordering by `id` is ordering by time, and range scans need
  no separate timestamp index.

---

## Kinds — one model, four semantics

`kind` is **derived from the event name**, never declared:

| name prefix | `kind` | side effect |
|---|---|---|
| `task.*` | `task` | upsert a `tasks` row keyed on `data.task_id` |
| `notification.*` | `notification` | insert a `notifications` row |
| `message.*`, `chat.*`, `*.message.*` | `message` | none — delivered to `topic` verbatim |
| anything else | `event` | none |

They still travel as ordinary events on their topic. A consumer subscribed to
`tasks` receives `task.started`, `task.completed`, … as `event` frames; the
control plane additionally reads the `tasks` table it maintained.

### Task lifecycle

`task.created` → `task.started` → (`task.progress` | `task.retrying`)\* →
`task.completed` | `task.failed` | `task.revoked`

`data` conventions BEACN understands: `task_id` (required for a row), `name`,
`status`, `progress` (0–1), `attempt`, `error`, `result`, `duration_ms`,
`started_at`, `finished_at`. A terminal task is never moved backwards by a
late-arriving non-terminal event.

### Notifications

`data` conventions: `recipient` (or falls back to `user_id`), `type`, `title`,
`body` (or `message`), `channel` (`in_app` | `email` | `sms` | `webhook`),
`delivery_status`.

---

## Idempotency

Set `idempotency_key` on a publish. Within `IDEMPOTENCY_TTL_HOURS` (default 24)
a repeat with the same `(environment, producer, idempotency_key)` returns the
**original** event id, `deduplicated: true`, and HTTP `200` (not `201`). After
the TTL the marker is swept and the key is free again.

Batch publishes: pass one `idempotency_key` per event, or let the SDK derive
`"<key>:<index>"` from a batch key.
