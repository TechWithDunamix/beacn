"""A Prometheus text-exposition endpoint, dependency-free.

`prometheus_client` is not a BEACN dependency — the exposition format is a
handful of lines of text and hand-writing it keeps the install light and avoids
a global registry that fights the test suite. If a deployment wants the client
library's process/GC collectors, mount them alongside this route.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sillo.core.http.response import PlainTextResponse

_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


def _line(name: str, value: Any, labels: dict | None = None) -> str:
    if labels:
        rendered = ",".join(f'{k}="{v}"' for k, v in labels.items())
        return f"{name}{{{rendered}}} {value}"
    return f"{name} {value}"


async def collect() -> list[str]:
    from database.models import Connection, Event, Task
    from realtime import get_realtime

    rt = get_realtime()
    out: list[str] = []

    out.append("# HELP beacn_up 1 if the process is serving")
    out.append("# TYPE beacn_up gauge")
    out.append(_line("beacn_up", 1))

    out.append("# HELP beacn_realtime_connections Local live realtime connections")
    out.append("# TYPE beacn_realtime_connections gauge")
    out.append(_line("beacn_realtime_connections", rt.local_connection_count()))
    out.append(_line("beacn_realtime_subscriptions", rt.local_subscription_count()))

    out.append("# HELP beacn_frames_sent_total Frames written to sockets by this process")
    out.append("# TYPE beacn_frames_sent_total counter")
    out.append(_line("beacn_frames_sent_total", rt.frames_sent))
    out.append(_line("beacn_events_delivered_total", rt.events_delivered))
    out.append(_line("beacn_events_dropped_total", rt.events_dropped))

    bus = await rt.health()
    out.append("# HELP beacn_bus_ok Whether the event bus backend is reachable")
    out.append("# TYPE beacn_bus_ok gauge")
    out.append(_line("beacn_bus_ok", 1 if bus.get("ok") else 0, {"backend": bus.get("backend", "?")}))

    try:
        from app.config import ENVIRONMENTS

        since = datetime.now(UTC) - timedelta(hours=24)
        out.append("# HELP beacn_events_persisted Persisted events in the last 24h, by environment")
        out.append("# TYPE beacn_events_persisted gauge")
        for environment in ENVIRONMENTS:
            n = await Event.filter(environment=environment, published_at__gte=since).count()
            out.append(_line("beacn_events_persisted", n, {"environment": environment}))
        open_conns = await Connection.filter(status="open").count()
        out.append(_line("beacn_connections_open", open_conns))
        running = await Task.filter(status__in=["started", "retrying"]).count()
        out.append(_line("beacn_tasks_running", running))
    except Exception:  # noqa: BLE001 — metrics must never 500
        out.append("# database metrics unavailable")

    return out


async def metrics_endpoint(ctx) -> PlainTextResponse:
    body = "\n".join(await collect()) + "\n"
    return PlainTextResponse(body=body, content_type=_CONTENT_TYPE)
