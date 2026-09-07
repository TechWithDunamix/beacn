"""Job queue connection. Memory on a laptop, Redis when QUEUE_BACKEND=redis."""

from __future__ import annotations

from typing import Any

from app.config import config

__all__ = ["bind_jobs", "connection", "queue_url"]

_connection: Any = None


def queue_url() -> str | None:
    return config.redis_url if config.queue_backend == "redis" else None


def connection() -> Any:
    global _connection
    if _connection is None:
        from sillo.work.queue import SyncConnection

        url = queue_url()
        _connection = SyncConnection(url) if url else SyncConnection()
    return _connection


def bind_jobs() -> None:
    from app.jobs import ALL_JOBS

    conn = connection()
    for job in ALL_JOBS:
        job.on_connection(conn)
