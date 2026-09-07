"""Example producer: a background worker, Celery-shaped.

Emits the same `task.*` events `integrations/celery.py` produces from Celery's
signals — built here with `integrations.celery.event_for` so the payload shape
is identical. These populate BEACN's Tasks page (name, status, attempts,
duration) without any Celery dependency.

    task.created -> task.started -> [task.progress] -> [task.retrying] ->
        task.completed | task.failed

Run:  python examples/orders_worker.py --burst 40
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _common import Ticker, client_for, jitter, publish, rid, run_cli  # noqa: E402

from integrations.celery import event_for  # noqa: E402

TASK_NAMES = [
    "orders.process", "orders.reserve_stock", "invoices.render_pdf",
    "email.send_receipt", "search.reindex_order", "webhooks.deliver",
]


def _emit(client, signal, correlation, **kw):
    event, data = event_for(signal, **kw)
    publish(
        client, event, topic="tasks", data=data, correlation_id=correlation,
        severity="error" if event == "task.failed" else "info",
        idempotency_key=f"{data['task_id']}:{event}",
    )


def _task(client, t: Ticker) -> None:
    correlation = rid("cor")
    task_id = rid("celery", 20)
    name = random.choice(TASK_NAMES)

    _emit(client, "before_task_publish", correlation, task_id=task_id, name=name)
    t.wait(jitter(0.3))
    _emit(client, "task_prerun", correlation, task_id=task_id, name=name)

    for _ in range(random.randint(0, 3)):
        t.wait(jitter(0.4))
        # progress isn't a Celery signal; emit it as a raw task.progress event
        publish(client, "task.progress", topic="tasks", correlation_id=correlation,
                data={"task_id": task_id, "name": name, "progress": round(random.uniform(0.1, 0.95), 2)})

    attempt = 0
    while attempt < 2 and random.random() < 0.25:
        t.wait(jitter(0.5))
        _emit(client, "task_retry", correlation, task_id=task_id, name=name,
              retries=attempt, error=random.choice(["ConnectionError", "TimeoutError", "429 from upstream"]))
        attempt += 1

    t.wait(jitter(0.6))
    if random.random() < 0.12:
        _emit(client, "task_failure", correlation, task_id=task_id, name=name,
              error=random.choice(["ValueError('bad sku')", "IntegrityError", "OperationalError: deadlock"]))
    else:
        _emit(client, "task_success", correlation, task_id=task_id, name=name,
              runtime_ms=random.randint(80, 9000), result={"ok": True, "rows": random.randint(1, 50)})


def run(t: Ticker) -> None:
    client = client_for("orders-worker")
    print("orders-worker: publishing task.* to topic 'tasks'")
    while t.running():
        _task(client, t)
        t.wait(jitter(0.9))


if __name__ == "__main__":
    run_cli(run)
