"""The BEACN event envelope.

One dataclass, no ORM, no framework. `Envelope.ingest()` takes what a producer
sent plus the server-authoritative context (producer, environment, ids) and
returns a validated, immutable envelope. `routes/api` and the realtime layer
both build events through here so validation lives in exactly one place.

Design notes:

* **Server fields win.** `producer`, `environment`, `id` and `timestamp` are
  set by BEACN from the authenticated key and cannot be spoofed by the payload.
* **Kinds are derived, not declared.** `task.*`, `notification.*` and message
  names get a `kind` so the semantic layers can find them, but they are still
  ordinary events on a topic.
* **Immutable.** Frozen dataclass; `data` is deep-copied and frozen-ish on the
  way in.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from .errors import PayloadTooLargeError, ValidationError
from .ids import EVENT, new_id

# --- limits & vocabularies --------------------------------------------------

MAX_DATA_BYTES = 256 * 1024
MAX_EVENT_NAME = 200
MAX_TOPIC_NAME = 200
MAX_BATCH = 500

SEVERITIES = ("debug", "info", "notice", "warning", "error", "critical")
DEFAULT_SEVERITY = "info"
DEFAULT_SCHEMA_VERSION = "1"

# A dotted, lowercase-ish name: segments of [a-z0-9_-], 1..8 segments.
_EVENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(\.[A-Za-z0-9][A-Za-z0-9_-]*){0,7}$")
# Topic: a name, optionally namespaced with one colon (user:123, project:789).
_TOPIC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*(:[A-Za-z0-9][A-Za-z0-9_.:-]*)?$")

KIND_EVENT = "event"
KIND_TASK = "task"
KIND_NOTIFICATION = "notification"
KIND_MESSAGE = "message"

# Task lifecycle names BEACN understands natively (others still pass through).
TASK_STATES = {
    "task.created": "created",
    "task.started": "started",
    "task.progress": "started",
    "task.retrying": "retrying",
    "task.completed": "completed",
    "task.succeeded": "completed",
    "task.failed": "failed",
    "task.revoked": "revoked",
    "task.cancelled": "revoked",
}


def _kind_for(event_name: str) -> str:
    head = event_name.split(".", 1)[0]
    if head == "task":
        return KIND_TASK
    if head == "notification":
        return KIND_NOTIFICATION
    if head in ("message", "chat") or ".message." in f".{event_name}.":
        return KIND_MESSAGE
    return KIND_EVENT


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_dt(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=UTC)
    if isinstance(value, str):
        raw = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValidationError(f"{field_name} is not a valid timestamp", details=value) from exc
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    raise ValidationError(f"{field_name} is not a valid timestamp", details=value)


def _clean_str(value: Any, field_name: str, *, max_len: int, required: bool = False) -> str | None:
    if value is None or value == "":
        if required:
            raise ValidationError(f"{field_name} is required")
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string", details=repr(value))
    value = value.strip()
    if not value:
        if required:
            raise ValidationError(f"{field_name} is required")
        return None
    if len(value) > max_len:
        raise ValidationError(f"{field_name} is longer than {max_len} characters")
    return value


@dataclass(frozen=True)
class ProducerContext:
    """Server-authoritative facts about who is publishing. Never from the body."""

    producer: str
    producer_id: str | int | None
    environment: str
    api_key_id: str | int | None = None


@dataclass(frozen=True)
class Envelope:
    id: str
    event: str
    topic: str
    producer: str
    environment: str
    timestamp: datetime
    kind: str = KIND_EVENT
    source: str | None = None
    occurred_at: datetime | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    user_id: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
    schema_version: str = DEFAULT_SCHEMA_VERSION
    severity: str = DEFAULT_SEVERITY
    idempotency_key: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)
    # populated for kind == task
    task_id: str | None = None
    task_name: str | None = None
    task_status: str | None = None
    # not serialized to consumers; used for delivery bookkeeping
    producer_id: str | int | None = None
    api_key_id: str | int | None = None

    # -- construction ------------------------------------------------------

    @classmethod
    def ingest(
        cls,
        body: Mapping[str, Any],
        ctx: ProducerContext,
        *,
        now: datetime | None = None,
        event_id: str | None = None,
    ) -> Envelope:
        """Validate a producer payload against server context. Raises `ValidationError`."""
        if not isinstance(body, Mapping):
            raise ValidationError("event must be a JSON object")

        event_name = _clean_str(body.get("event"), "event", max_len=MAX_EVENT_NAME, required=True)
        if not _EVENT_RE.match(event_name):
            raise ValidationError(
                "event must be a dotted name like 'payment.completed'", details=event_name
            )

        topic = _clean_str(body.get("topic"), "topic", max_len=MAX_TOPIC_NAME)
        if topic is None:
            # A sensible default: the first segment of the event name.
            topic = event_name.split(".", 1)[0]
        if not _TOPIC_RE.match(topic):
            raise ValidationError("topic contains invalid characters", details=topic)

        severity = (body.get("severity") or DEFAULT_SEVERITY)
        if severity not in SEVERITIES:
            raise ValidationError(
                f"severity must be one of {', '.join(SEVERITIES)}", details=severity
            )

        data = body.get("data", {})
        if data is None:
            data = {}
        if not isinstance(data, Mapping):
            raise ValidationError("data must be a JSON object")
        try:
            encoded = json.dumps(data, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValidationError("data is not JSON-serialisable", details=str(exc)) from exc
        if len(encoded.encode("utf-8")) > MAX_DATA_BYTES:
            raise PayloadTooLargeError(
                f"data exceeds the {MAX_DATA_BYTES // 1024} KiB limit"
            )
        data = copy.deepcopy(data)

        schema_version = _clean_str(
            body.get("schema_version") or DEFAULT_SCHEMA_VERSION, "schema_version", max_len=32
        )
        kind = _kind_for(event_name)
        ts = now or _utcnow()

        env = cls(
            id=event_id or new_id(EVENT),
            event=event_name,
            topic=topic,
            producer=ctx.producer,
            environment=ctx.environment,
            timestamp=ts,
            kind=kind,
            source=_clean_str(body.get("source"), "source", max_len=200),
            occurred_at=_parse_dt(body.get("occurred_at"), "occurred_at"),
            correlation_id=_clean_str(body.get("correlation_id"), "correlation_id", max_len=200),
            request_id=_clean_str(body.get("request_id"), "request_id", max_len=200),
            user_id=_clean_str(body.get("user_id"), "user_id", max_len=200),
            organization_id=_clean_str(body.get("organization_id"), "organization_id", max_len=200),
            project_id=_clean_str(body.get("project_id"), "project_id", max_len=200),
            schema_version=schema_version or DEFAULT_SCHEMA_VERSION,
            severity=severity,
            idempotency_key=_clean_str(
                body.get("idempotency_key"), "idempotency_key", max_len=200
            ),
            data=data,
            producer_id=ctx.producer_id,
            api_key_id=ctx.api_key_id,
        )
        if kind == KIND_TASK:
            env = env._with_task_fields()
        return env

    def _with_task_fields(self) -> Envelope:
        d = self.data or {}
        task_id = d.get("task_id") or d.get("id")
        return replace(
            self,
            task_id=str(task_id) if task_id is not None else None,
            task_name=(d.get("name") or d.get("task") or None),
            task_status=TASK_STATES.get(self.event) or d.get("status") or None,
        )

    # -- serialisation ---------------------------------------------------

    def to_wire(self, *, include_meta: bool = True) -> dict[str, Any]:
        """The shape a consumer receives (REST history rows and WS `event` frames)."""
        out: dict[str, Any] = {
            "id": self.id,
            "event": self.event,
            "topic": self.topic,
            "kind": self.kind,
            "producer": self.producer,
            "environment": self.environment,
            "timestamp": _iso(self.timestamp),
            "severity": self.severity,
            "schema_version": self.schema_version,
            "data": dict(self.data),
        }
        if self.source:
            out["source"] = self.source
        if self.occurred_at:
            out["occurred_at"] = _iso(self.occurred_at)
        for key in ("correlation_id", "request_id", "user_id", "organization_id", "project_id"):
            value = getattr(self, key)
            if value:
                out[key] = value
        if self.kind == KIND_TASK and include_meta:
            out["task"] = {
                "id": self.task_id,
                "name": self.task_name,
                "status": self.task_status,
            }
        return out

    def storage_row(self) -> dict[str, Any]:
        """Column values for the `events` table (see database/models/event.py)."""
        return {
            "id": self.id,
            "environment": self.environment,
            "event": self.event,
            "topic": self.topic,
            "kind": self.kind,
            "producer_id": self.producer_id,
            "producer_name": self.producer,
            "source": self.source,
            "severity": self.severity,
            "schema_version": self.schema_version,
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "idempotency_key": self.idempotency_key,
            "occurred_at": self.occurred_at,
            "published_at": self.timestamp,
            "data": dict(self.data),
        }


def parse_batch(body: Any) -> list[Mapping[str, Any]]:
    """Pull the list of raw events out of a single- or batch-shaped request body."""
    if isinstance(body, Mapping):
        if "events" in body and isinstance(body["events"], list):
            items = body["events"]
        else:
            items = [body]
    elif isinstance(body, list):
        items = body
    else:
        raise ValidationError("request body must be an object or a list of objects")
    if not items:
        raise ValidationError("no events in request")
    if len(items) > MAX_BATCH:
        raise ValidationError(f"batch is larger than {MAX_BATCH} events")
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise ValidationError(f"events[{i}] must be an object")
    return items
