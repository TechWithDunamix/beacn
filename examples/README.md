# BEACN examples

Six small programs that behave like real backend services — each holds one
BEACN API key and publishes a stream of events with the Python SDK — plus a
consumer that subscribes and prints. Use them to fill the dashboard with
realistic data and to see the whole pipeline end to end.

| script | acts as | publishes |
|---|---|---|
| `payments_api.py` | a payments API | `payment.initiated/authorized/completed/failed/refunded` → `payments` |
| `deployment_service.py` | a CI/deploy system | `deployment.started/progress/completed/failed` → `deployments` |
| `orders_worker.py` | a background worker (Celery-shaped) | `task.created/started/progress/retrying/completed/failed` → `tasks` |
| `chat_service.py` | a chat service | `message.created` → `chat:<room>` and `user:<id>` |
| `notification_service.py` | a notification service | `notification.created` → `user:<id>` |
| `cron_reports.py` | a cron job | `report.generated` → `reports` |
| `consumer.py` | a frontend/consumer | subscribes over SSE and prints |
| `run_all.py` | — | runs all six producers at once |

Each producer sets a `correlation_id` per unit of work, so an event chain
(e.g. one payment) is one query in the Events explorer.

## Setup

```bash
# 1. the server must be running
beacn serve

# 2. create the example producers + API keys (writes examples/keys.json)
python examples/bootstrap.py --email you@example.com
#    password: hidden prompt, or set BEACN_PASSWORD
```

`bootstrap.py` signs in to the control plane as an operator and creates one
producer per script in the `development` environment. `keys.json` holds the
secrets and is git-ignored.

## Inject data

```bash
# fill the dashboard fast — each producer fires 40 iterations then exits
python examples/run_all.py --burst 40

# or a continuous, realistic mixed stream
python examples/run_all.py                 # Ctrl-C to stop
python examples/run_all.py --rate 3        # 3x faster
python examples/run_all.py --duration 120  # two minutes, then stop
```

Run one at a time instead:

```bash
python examples/payments_api.py --burst 30
python examples/orders_worker.py --rate 2
python examples/deployment_service.py
```

## Watch it arrive

```bash
python examples/consumer.py                         # payments, tasks, deployments
python examples/consumer.py tasks reports
python examples/consumer.py 'chat:room-general'     # private topics work — the
                                                    # minted token is scoped to them
```

## Where to look in the dashboard

- **Dashboard** — events/sec, throughput sparkline, top producers/topics, recent events.
- **Events** — filter by topic (`payments`), `event_prefix` (`task.`), producer, severity;
  click a payment event → **Event detail** → "See the whole correlation chain".
- **Tasks** — populated by `orders_worker.py`: name, status, attempts, duration.
- **Notifications** — populated by `notification_service.py`.
- **Connections** — shows `consumer.py` (and any browser) while subscribed.
- **Producers** / **API keys** — the six registered by `bootstrap.py`.

## Reset

```bash
rm examples/keys.json          # then re-run bootstrap.py for fresh keys
# to wipe the data: stop the server, delete storage/beacn.db, `beacn migrate`
```
