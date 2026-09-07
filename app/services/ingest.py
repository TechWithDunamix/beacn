"""Event ingestion — validate → dedupe → persist → fan out.

Called by `POST /api/v1/events`, by the CLI (`beacn events publish`) and by the
Celery integration. One entry point, `ingest`, so every producer path shares the
same idempotency, persistence and delivery rules.

Delivery semantics (see `docs/ARCHITECTURE.md` §3): persistence happens before
fanout, so a consumer that later replays from the store never sees an event the
live stream skipped. Fanout is best-effort at-most-once; the durable store plus
`replay` is the at-least-once path.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from tortoise.exceptions import IntegrityError

from app.config import config
from database.models import (
    Event,
    EventIdempotency,
    Notification,
    Producer,
    Task,
    Topic,
)
from domain.events import KIND_NOTIFICATION, KIND_TASK, Envelope
from realtime import get_realtime

logger = logging.getLogger("beacn.ingest")


@dataclass
class Accepted:
    id: str
    event: str
    topic: str
    deduplicated: bool = False


@dataclass
class IngestResult:
    accepted: list[Accepted] = field(default_factory=list)
    deduplicated: int = 0

    @property
    def count(self) -> int:
        return len(self.accepted)

    @property
    def all_deduplicated(self) -> bool:
        return self.count > 0 and self.deduplicated == self.count

    def to_dict(self) -> dict:
        return {
            "accepted": self.count,
            "deduplicated": self.deduplicated,
            "events": [
                {
                    "id": a.id,
                    "event": a.event,
                    "topic": a.topic,
                    "deduplicated": a.deduplicated,
                }
                for a in self.accepted
            ],
        }


# in-process cache of which (env, topic) should be persisted — refreshed lazily
_persist_cache: dict[tuple[str, str], bool] = {}


async def _should_persist(environment: str, topic: str) -> bool:
    key = (environment, topic)
    if key not in _persist_cache:
        row = await Topic.get_or_none(environment=environment, name=topic)
        _persist_cache[key] = True if row is None else bool(row.persist)
    return _persist_cache[key]


def invalidate_persist_cache() -> None:
    _persist_cache.clear()


async def ingest(
    envelopes: Sequence[Envelope],
    *,
    persist: bool = True,
    fan_out: bool = True,
) -> IngestResult:
    result = IngestResult()
    rt = get_realtime() if fan_out else None

    for env in envelopes:
        deduped_id = await _dedupe(env)
        if deduped_id is not None:
            result.accepted.append(
                Accepted(id=deduped_id, event=env.event, topic=env.topic, deduplicated=True)
            )
            result.deduplicated += 1
            continue

        stored = persist and await _should_persist(env.environment, env.topic)
        if stored:
            try:
                await Event.from_storage_row(env.storage_row())
            except IntegrityError:
                # id collision is astronomically unlikely; treat as already done
                logger.warning("event id collision on %s", env.id)

        if env.kind == KIND_TASK:
            try:
                await Task.apply_event(env)
            except Exception:  # noqa: BLE001
                logger.exception("task upsert failed for %s", env.id)
        elif env.kind == KIND_NOTIFICATION:
            try:
                await Notification.from_event(env)
            except Exception:  # noqa: BLE001
                logger.exception("notification insert failed for %s", env.id)

        if rt is not None:
            wire = env.to_wire()
            try:
                await rt.publish(env.environment, env.topic, wire)
            except Exception:  # noqa: BLE001
                logger.exception("fanout failed for %s", env.id)

        result.accepted.append(Accepted(id=env.id, event=env.event, topic=env.topic))

    return result


async def _dedupe(env: Envelope) -> str | None:
    """Return the id of a prior event with the same idempotency key, or None.

    Creating the marker row is what claims the key; the unique constraint makes
    two concurrent publishes race safely — the loser reads the winner's row.
    """
    if not env.idempotency_key:
        return None
    pid = env.producer_id if isinstance(env.producer_id, str) else None
    existing = await EventIdempotency.get_or_none(
        environment=env.environment,
        producer_id=pid,
        idempotency_key=env.idempotency_key,
    )
    if existing is not None:
        return existing.event_id
    try:
        await EventIdempotency.create(
            environment=env.environment,
            producer_id=pid,
            idempotency_key=env.idempotency_key,
            event_id=env.id,
        )
        return None
    except IntegrityError:
        again = await EventIdempotency.get_or_none(
            environment=env.environment,
            producer_id=pid,
            idempotency_key=env.idempotency_key,
        )
        return again.event_id if again else None


async def touch_producer_stats(producer: Producer, count: int, when: datetime | None = None) -> None:
    producer.event_count = (producer.event_count or 0) + count
    producer.last_event_at = when or datetime.now(UTC)
    try:
        await producer.save(update_fields=["event_count", "last_event_at"])
    except Exception:  # noqa: BLE001
        pass


async def sweep_idempotency(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=config.idempotency_ttl_hours)
    return await EventIdempotency.filter(created_at__lt=cutoff).delete()
