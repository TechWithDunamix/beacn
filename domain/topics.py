"""Topic authorization — pure, server-side, no I/O.

A consumer presents a set of *grants* (derived from its realtime token or API
key) and asks to subscribe to a topic string. `authorize_subscription` decides.
The realtime layer calls this on **every** subscribe; the frontend's opinion is
never consulted.

Rules
-----
* ``public`` topics: anyone authenticated in the same environment.
* Namespaced private topics — ``user:<id>``, ``organization:<id>``,
  ``project:<id>`` — require the matching claim in the grant.
* A topic row marked ``private`` requires an explicit allow entry
  (``topics`` list on the grant) or a wildcard pattern that covers it.
* ``system`` and ``audit`` topics require the ``system:read`` scope.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass, field

PUBLIC = "public"
PRIVATE = "private"
INTERNAL = "internal"  # system / audit — operator-only


@dataclass(frozen=True)
class Grant:
    """What a connection is allowed to see. Built from a token or API key."""

    environment: str
    user_id: str | None = None
    organization_id: str | None = None
    project_ids: frozenset[str] = field(default_factory=frozenset)
    scopes: frozenset[str] = field(default_factory=frozenset)
    #: glob patterns this connection may subscribe to regardless of namespace
    topic_patterns: tuple[str, ...] = ()
    #: True for operator/admin realtime tokens minted from the control plane
    operator: bool = False

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or "*" in self.scopes or self.operator


@dataclass(frozen=True)
class TopicSpec:
    """The persisted facts about a topic, or a synthesised default."""

    name: str
    visibility: str = PUBLIC
    environment: str | None = None


def _namespace(topic: str) -> tuple[str, str | None]:
    if ":" in topic:
        head, tail = topic.split(":", 1)
        return head, tail
    return topic, None


def default_spec(topic: str, environment: str) -> TopicSpec:
    """The visibility a topic has when there is no row for it."""
    head, ident = _namespace(topic)
    if head in ("system", "audit"):
        return TopicSpec(topic, INTERNAL, environment)
    if head in ("user", "organization", "project", "connection", "session") and ident:
        return TopicSpec(topic, PRIVATE, environment)
    return TopicSpec(topic, PUBLIC, environment)


def matches_pattern(topic: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(topic, p) for p in patterns)


class Decision:
    __slots__ = ("allowed", "reason", "code")

    def __init__(self, allowed: bool, reason: str = "", code: str = "forbidden") -> None:
        self.allowed = allowed
        self.reason = reason
        self.code = code

    def __bool__(self) -> bool:
        return self.allowed


ALLOW = Decision(True)


def authorize_subscription(topic: str, grant: Grant, spec: TopicSpec | None = None) -> Decision:
    """Return a `Decision`. `spec` is the topic row if one exists, else `None`."""
    if not topic:
        return Decision(False, "empty topic", "invalid")
    spec = spec or default_spec(topic, grant.environment)

    if spec.environment and spec.environment != grant.environment:
        return Decision(False, "topic belongs to a different environment", "forbidden")

    if grant.operator:
        return ALLOW

    if matches_pattern(topic, grant.topic_patterns):
        return ALLOW

    head, ident = _namespace(topic)

    if spec.visibility == INTERNAL or head in ("system", "audit"):
        if grant.has_scope("system:read"):
            return ALLOW
        return Decision(False, "system topics require system:read", "forbidden")

    if head == "user" and ident:
        return ALLOW if ident == grant.user_id else Decision(
            False, "not your user topic", "forbidden"
        )
    if head == "organization" and ident:
        return ALLOW if ident == grant.organization_id else Decision(
            False, "not your organization", "forbidden"
        )
    if head == "project" and ident:
        return ALLOW if ident in grant.project_ids else Decision(
            False, "project not in your grant", "forbidden"
        )

    if spec.visibility == PRIVATE:
        return Decision(False, "private topic requires an explicit grant", "forbidden")

    # public
    return ALLOW
