"""Example producer: a cron job.

A backend on a timer is a producer like any other — it just publishes
infrequently. Emits `report.generated` to topic 'reports'.

Run:  python examples/cron_reports.py --burst 6
"""

from __future__ import annotations

import random

from _common import Ticker, client_for, jitter, publish, rid, run_cli

REPORTS = ["daily_revenue", "failed_payments", "slow_queries", "signup_funnel", "churn"]


def run(t: Ticker) -> None:
    client = client_for("cron-reports")
    print("cron-reports: publishing report.generated to topic 'reports'")
    while t.running():
        report = random.choice(REPORTS)
        publish(
            client, "report.generated", topic="reports", severity="notice",
            correlation_id=rid("cor"),
            data={
                "report": report,
                "rows": random.randint(50, 50_000),
                "duration_ms": random.randint(200, 25_000),
                "window": "24h",
            },
        )
        t.wait(jitter(20.0))


if __name__ == "__main__":
    run_cli(run)
