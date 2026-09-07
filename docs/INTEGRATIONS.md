# Integrations

BEACN has **no dependency** on Celery, Django, or anything else. These adapters
live outside the core and convert a framework's lifecycle into generic BEACN
events. Writing one for a new language or framework is the same shape.

## Celery

`integrations/celery.py`. Observes Celery's task signals and republishes them as
`task.*` events through the Python SDK.

```python
# worker bootstrap
from beacn import Beacn
from integrations.celery import install

beacn = Beacn(url="https://beacn.internal", api_key="bk_...")
install(beacn, source="orders-worker")   # topic defaults to "tasks"
```

| Celery signal | BEACN event |
|---|---|
| `before_task_publish` | `task.created` |
| `task_prerun` | `task.started` |
| `task_retry` | `task.retrying` (`data.attempt`) |
| `task_success` | `task.completed` (`data.duration_ms`, `data.result`) |
| `task_failure` | `task.failed` (`data.error`, `severity: error`) |
| `task_revoked` | `task.revoked` |

Each publish carries `idempotency_key = "<task_id>:<event>"`, so a signal
delivered twice does not create two events. Publish failures are logged and
swallowed — task observability never takes down a worker.

The mapping is also a pure function, `event_for(signal, task_id=..., ...)`, for
non-Celery producers or unit tests.

## Django

`integrations/django.py`.

```python
# settings.py
from beacn import Beacn
BEACN = Beacn(url="https://beacn.internal", api_key="bk_...")
MIDDLEWARE = [..., "integrations.django.BeacnMiddleware"]
```

- `BeacnMiddleware` stamps a `correlation_id` on every request (from
  `X-Correlation-ID` or fresh) and exposes `request.beacn.publish(...)` with the
  id already attached; it echoes the id on the response.
- `publish_model_event(instance, "user.created")` — a one-liner for `post_save` /
  `post_delete` handlers.

## Sillo

A Sillo service is a producer like any other — use the Python SDK directly, or
bridge `sillo.events` emissions:

```python
from beacn import Beacn
beacn = Beacn(url=..., api_key=...)

@app.events.on("order.placed")
async def _mirror(order):
    beacn.publish("order.placed", topic="orders", data=order.to_dict())
```

## Any other producer

Publish the same envelope over REST. A deployment system:

```
POST /api/v1/events   {"event":"deployment.started","topic":"deployments","data":{"deployment_id":"dep_1"}}
POST /api/v1/events   {"event":"deployment.progress","topic":"deployments","data":{"deployment_id":"dep_1","pct":40}}
POST /api/v1/events   {"event":"deployment.completed","topic":"deployments","data":{"deployment_id":"dep_1","status":"success"}}
```

A chat system publishes `message.created` to `chat:<room>`. A notification
service publishes `notification.created` to `user:<id>`. The frontend consumes
all of them through one BEACN WebSocket.
