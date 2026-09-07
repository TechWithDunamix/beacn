"""The dashboard's route table. Every entry is an exact path (no subtree),
so the `/api/**` routers coexist without an ordering rule."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sillo.core.routing import Route

from routes.web import auth, docs, pages
from routes.web._kit import GATE_ATTR

__all__ = ["routes"]


def _r(path: str, handler: Callable[..., Any], *, methods: list[str] | None = None, name: str | None = None) -> Route:
    return Route(
        path,
        handler=handler,
        methods=methods or ["GET"],
        name=name,
        auth=getattr(handler, GATE_ATTR, None),
    )


routes: list[Route] = [
    _r("/login", auth.login, name="login"),
    _r("/login", auth.login_submit, methods=["POST"], name="login.submit"),
    _r("/logout", auth.logout, methods=["POST"], name="logout"),

    _r("/", pages.dashboard, name="dashboard"),
    _r("/events", pages.events, name="events"),
    _r("/events/{event_id}", pages.event_detail, name="events.detail"),
    _r("/topics", pages.topics, name="topics"),
    _r("/connections", pages.connections, name="connections"),
    _r("/tasks", pages.tasks, name="tasks"),
    _r("/notifications", pages.notifications, name="notifications"),
    _r("/producers", pages.producers, name="producers"),
    _r("/api-keys", pages.api_keys, name="api-keys"),
    _r("/users", pages.users, name="users"),
    _r("/audit", pages.audit_log, name="audit"),
    _r("/settings", pages.settings, name="settings"),

    _r("/docs", docs.docs_index, name="docs"),
    _r("/docs/search", docs.docs_search, name="docs.search"),
    _r("/docs/{slug:str}", docs.docs_page, name="docs.page"),
]
