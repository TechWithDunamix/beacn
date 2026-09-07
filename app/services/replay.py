"""Missed-event replay from the durable store.

A consumer that disconnected after `evt_X` reconnects and asks to `replay` a
topic `since=evt_X`. BEACN returns every persisted event on that topic with
`id > evt_X`, in order, up to `config.replay_max_events`.

**Honest about gaps.** If `evt_X` is older than the oldest event still retained
for that topic, some events between `evt_X` and the oldest retained one are gone
— retention removed them. The result then has `truncated=True` and
`earliest_available` so the consumer knows it has a hole rather than believing
it caught up cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import config
from database.models import Event, Topic
from domain.topics import Grant, authorize_subscription


@dataclass
class ReplayResult:
    events: list[dict]
    truncated: bool
    earliest_available: str | None
    next_since: str | None

    @property
    def count(self) -> int:
        return len(self.events)


async def replay(
    *,
    environment: str,
    topic: str,
    since: str | None,
    limit: int | None = None,
    include_meta: bool = False,
) -> ReplayResult:
    limit = min(config.replay_max_events, limit or config.replay_max_events)

    base = Event.filter(environment=environment, topic=topic)

    oldest = await base.order_by("id").first()
    earliest_available = oldest.id if oldest else None

    truncated = False
    if since and earliest_available and since < earliest_available:
        # The client's cursor predates everything we still hold for this topic.
        truncated = True

    qs = base
    if since:
        qs = qs.filter(id__gt=since)
    rows = await qs.order_by("id").limit(limit + 1)

    more = len(rows) > limit
    rows = rows[:limit]
    next_since = rows[-1].id if rows and more else None
    if more:
        truncated = True

    return ReplayResult(
        events=[r.to_wire(include_meta=include_meta) for r in rows],
        truncated=truncated,
        earliest_available=earliest_available,
        next_since=next_since,
    )


async def authorize(topic: str, grant: Grant) -> bool:
    spec = None
    row = await Topic.get_or_none(environment=grant.environment, name=topic)
    if row is not None:
        from domain.topics import TopicSpec

        spec = TopicSpec(row.name, row.visibility, row.environment)
    return bool(authorize_subscription(topic, grant, spec))
