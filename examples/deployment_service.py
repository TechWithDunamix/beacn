"""Example producer: a deployment / CI system.

    deployment.started -> deployment.progress (xN) -> deployment.completed | deployment.failed

Run:  python examples/deployment_service.py --burst 15
"""

from __future__ import annotations

import random

from _common import Ticker, client_for, jitter, publish, rid, run_cli

SERVICES = ["orders-api", "payments-api", "web", "search-indexer", "billing-worker", "gateway"]
STAGES = ["build", "test", "push image", "migrate", "rollout", "healthcheck", "switch traffic"]
ENVS = ["staging", "production"]


def _deployment(client, t: Ticker) -> None:
    correlation = rid("cor")
    deployment_id = rid("dep")
    service = random.choice(SERVICES)
    version = f"v{random.randint(1, 4)}.{random.randint(0, 20)}.{random.randint(0, 9)}"
    target = random.choice(ENVS)
    base = dict(topic="deployments", correlation_id=correlation)
    data = {"deployment_id": deployment_id, "service": service, "version": version, "target": target}

    publish(client, "deployment.started", data={**data, "triggered_by": rid("usr", 6)}, **base)

    stages = STAGES[: random.randint(4, len(STAGES))]
    fail_at = random.randint(1, len(stages) - 1) if random.random() < 0.15 else None
    for i, stage in enumerate(stages):
        t.wait(jitter(0.5))
        pct = round((i + 1) / len(stages) * 100)
        if i == fail_at:
            publish(client, "deployment.failed", severity="error",
                    data={**data, "stage": stage, "pct": pct,
                          "error": random.choice(["migration failed", "healthcheck timeout", "image pull error"])},
                    **base)
            return
        publish(client, "deployment.progress", data={**data, "stage": stage, "pct": pct}, **base)

    t.wait(jitter(0.5))
    publish(client, "deployment.completed", severity="notice",
            data={**data, "pct": 100, "duration_ms": random.randint(45_000, 400_000)}, **base)


def run(t: Ticker) -> None:
    client = client_for("deployment-service")
    print("deployment-service: publishing to topic 'deployments'")
    while t.running():
        _deployment(client, t)
        t.wait(jitter(4.0))


if __name__ == "__main__":
    run_cli(run)
