"""The realtime wire protocol — pure frame parsing and building.

JSON frames, documented in `docs/ARCHITECTURE.md` §3 and `docs/REALTIME.md`.
This module has no I/O so the protocol is unit-tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CLIENT_TYPES = {"subscribe", "unsubscribe", "replay", "ack", "ping"}


class ProtocolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ClientFrame:
    type: str
    topic: str | None = None
    since: str | None = None
    id: str | None = None
    ref: str | None = None  # client-supplied correlation for the reply

    @classmethod
    def parse(cls, raw: Any) -> ClientFrame:
        if not isinstance(raw, dict):
            raise ProtocolError("invalid", "frame must be a JSON object")
        ftype = raw.get("type")
        if ftype not in CLIENT_TYPES:
            raise ProtocolError("invalid", f"unknown frame type {ftype!r}")
        topic = raw.get("topic")
        if ftype in ("subscribe", "unsubscribe", "replay"):
            if not isinstance(topic, str) or not topic:
                raise ProtocolError("invalid", f"{ftype} requires a topic")
        if ftype == "ack" and not raw.get("id"):
            raise ProtocolError("invalid", "ack requires an id")
        return cls(
            type=ftype,
            topic=topic if isinstance(topic, str) else None,
            since=raw.get("since") if isinstance(raw.get("since"), str) else None,
            id=raw.get("id") if isinstance(raw.get("id"), str) else None,
            ref=raw.get("ref") if isinstance(raw.get("ref"), str) else None,
        )


def welcome(connection_id: str, heartbeat_ms: int) -> dict:
    return {"type": "welcome", "connection_id": connection_id, "heartbeat_ms": heartbeat_ms}


def subscribed(topic: str, ref: str | None = None) -> dict:
    out = {"type": "subscribed", "topic": topic}
    if ref:
        out["ref"] = ref
    return out


def unsubscribed(topic: str) -> dict:
    return {"type": "unsubscribed", "topic": topic}


def event_frame(wire: dict, *, seq: int | None = None) -> dict:
    out = {"type": "event", **wire}
    if seq is not None:
        out["seq"] = seq
    return out


def replay_done(topic: str, count: int, truncated: bool, next_since: str | None) -> dict:
    return {
        "type": "replay_done",
        "topic": topic,
        "count": count,
        "truncated": truncated,
        "next_since": next_since,
    }


def error_frame(code: str, message: str, *, topic: str | None = None, ref: str | None = None) -> dict:
    out = {"type": "error", "code": code, "message": message}
    if topic:
        out["topic"] = topic
    if ref:
        out["ref"] = ref
    return out


def pong() -> dict:
    return {"type": "pong"}
