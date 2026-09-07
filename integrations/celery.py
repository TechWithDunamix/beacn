"""Celery → BEACN adapter.

Celery is **one producer**. This module observes Celery's task lifecycle signals
and republishes them as generic BEACN `task.*` events through the Python SDK.
BEACN itself has no Celery dependency — a Go worker or a cron job emitting the
same `task.*` events is indistinguishable downstream.

Usage (in your Celery app / worker bootstrap)::

    from beacn import Beacn
    from beacn_celery import install   # this module, packaged alongside the SDK

    beacn = Beacn(url="https://beacn.internal", api_key="bk_...")
    install(beacn, source="orders-worker")

The mapping is also exposed as a pure function, `event_for`, so it can be unit
tested and reused by non-Celery producers.
"""

from __future__ import annotations

from typing import Any

TOPIC = "tasks"

# Celery signal name -> BEACN event name
_SIGNAL_EVENT = {
    "before_task_publish": "task.created",
    "task_prerun": "task.started",
    "task_retry": "task.retrying",
    "task_success": "task.completed",
    "task_failure": "task.failed",
    "task_revoked": "task.revoked",
}


def event_for(
    signal: str,
    *,
    task_id: str,
    name: str | None = None,
    retries: int | None = None,
    error: str | None = None,
    result: Any = None,
    runtime_ms: int | None = None,
    correlation_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(beacn_event_name, data)`` for a Celery signal.

    Raises ``KeyError`` for a signal this adapter does not map.
    """
    event = _SIGNAL_EVENT[signal]
    data: dict[str, Any] = {"task_id": str(task_id)}
    if name:
        data["name"] = name
    if retries is not None:
        data["attempt"] = int(retries) + 1
    if error is not None:
        data["error"] = str(error)[:8000]
    if result is not None:
        data["result"] = _safe(result)
    if runtime_ms is not None:
        data["duration_ms"] = int(runtime_ms)
    if extra:
        data.update(extra)
    return event, data


def _safe(value: Any) -> Any:
    import json

    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return repr(value)


def install(beacn: Any, *, source: str | None = None, topic: str = TOPIC, correlation_header: str = "beacn_correlation_id") -> None:
    """Connect Celery's task signals to `beacn.publish`.

    `beacn` is a `beacn.Beacn` (sync) instance. Publishing failures are swallowed
    with a log line — task observability must never take down a worker.
    """
    import logging

    try:
        from celery import signals
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("install() requires Celery: pip install celery") from exc

    log = logging.getLogger("beacn.celery")

    def _emit(signal: str, **kw: Any) -> None:
        try:
            event, data = event_for(signal, **kw)
        except KeyError:
            return
        try:
            beacn.publish(
                event,
                topic=topic,
                data=data,
                source=source,
                severity="error" if event == "task.failed" else "info",
                correlation_id=kw.get("correlation_id"),
                idempotency_key=f"{data['task_id']}:{event}",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("BEACN publish failed for %s: %s", event, exc)

    @signals.before_task_publish.connect(weak=False)
    def _before_publish(sender=None, headers=None, body=None, **_: Any) -> None:
        headers = headers or {}
        _emit(
            "before_task_publish",
            task_id=headers.get("id", "unknown"),
            name=sender,
            correlation_id=(headers.get(correlation_header)),
        )

    @signals.task_prerun.connect(weak=False)
    def _prerun(task_id=None, task=None, **_: Any) -> None:
        _emit("task_prerun", task_id=task_id, name=getattr(task, "name", None),
              correlation_id=_corr(task, correlation_header))

    @signals.task_retry.connect(weak=False)
    def _retry(request=None, reason=None, sender=None, **_: Any) -> None:
        _emit("task_retry", task_id=getattr(request, "id", "unknown"),
              name=getattr(sender, "name", None), retries=getattr(request, "retries", 0),
              error=str(reason))

    @signals.task_success.connect(weak=False)
    def _success(sender=None, result=None, **_: Any) -> None:
        req = getattr(sender, "request", None)
        _emit("task_success", task_id=getattr(req, "id", "unknown"),
              name=getattr(sender, "name", None), result=result,
              runtime_ms=_runtime_ms(sender))

    @signals.task_failure.connect(weak=False)
    def _failure(task_id=None, exception=None, sender=None, **_: Any) -> None:
        _emit("task_failure", task_id=task_id, name=getattr(sender, "name", None),
              error=repr(exception))

    @signals.task_revoked.connect(weak=False)
    def _revoked(request=None, **_: Any) -> None:
        _emit("task_revoked", task_id=getattr(request, "id", "unknown"),
              name=getattr(request, "task", None))


def _corr(task: Any, header: str) -> str | None:
    req = getattr(task, "request", None)
    if req is None:
        return None
    return (getattr(req, "headers", None) or {}).get(header)


def _runtime_ms(sender: Any) -> int | None:
    req = getattr(sender, "request", None)
    runtime = getattr(req, "runtime", None) if req else None
    return int(runtime * 1000) if runtime else None
