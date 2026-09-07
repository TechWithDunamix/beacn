"""Cursor-paginated reads of the durable event store.

The cursor *is* an event id (a ULID), so pagination is a plain range scan on the
primary key with no offset and no separate sort column. `next_cursor` is the id
of the last row returned; pass it back as `cursor` for the next page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from database.models import Event

MAX_LIMIT = 200
DEFAULT_LIMIT = 50


@dataclass
class HistoryQuery:
    environment: str
    topic: str | None = None
    event: str | None = None
    event_prefix: str | None = None
    producer_id: str | None = None
    kind: str | None = None
    severity: str | None = None
    correlation_id: str | None = None
    user_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    cursor: str | None = None
    order: str = "desc"  # desc = newest first
    limit: int = DEFAULT_LIMIT

    def clamped_limit(self) -> int:
        return max(1, min(MAX_LIMIT, self.limit or DEFAULT_LIMIT))


@dataclass
class Page:
    events: list[dict[str, Any]]
    next_cursor: str | None
    has_more: bool
    count: int

    def to_dict(self) -> dict:
        return {
            "events": self.events,
            "page": {
                "count": self.count,
                "next_cursor": self.next_cursor,
                "has_more": self.has_more,
            },
        }


async def query(q: HistoryQuery, *, include_meta: bool = False) -> Page:
    qs = Event.filter(environment=q.environment)
    if q.topic:
        qs = qs.filter(topic=q.topic)
    if q.event:
        qs = qs.filter(event=q.event)
    if q.event_prefix:
        qs = qs.filter(event__startswith=q.event_prefix)
    if q.producer_id:
        qs = qs.filter(producer_id=q.producer_id)
    if q.kind:
        qs = qs.filter(kind=q.kind)
    if q.severity:
        qs = qs.filter(severity=q.severity)
    if q.correlation_id:
        qs = qs.filter(correlation_id=q.correlation_id)
    if q.user_id:
        qs = qs.filter(user_id=q.user_id)
    if q.since:
        qs = qs.filter(published_at__gte=q.since)
    if q.until:
        qs = qs.filter(published_at__lte=q.until)

    descending = q.order != "asc"
    if q.cursor:
        qs = qs.filter(id__lt=q.cursor) if descending else qs.filter(id__gt=q.cursor)

    qs = qs.order_by("-id" if descending else "id")
    limit = q.clamped_limit()
    rows = await qs.limit(limit + 1)

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = rows[-1].id if rows and has_more else None
    return Page(
        events=[r.to_wire(include_meta=include_meta) for r in rows],
        next_cursor=next_cursor,
        has_more=has_more,
        count=len(rows),
    )


async def get_one(environment: str, event_id: str) -> Event | None:
    return await Event.get_or_none(environment=environment, id=event_id)
