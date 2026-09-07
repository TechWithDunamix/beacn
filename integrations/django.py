"""Django → BEACN helpers.

Django is one producer. Two pieces, both optional:

* `BeacnMiddleware` — stamps a `correlation_id` on every request (from an
  inbound `X-Correlation-ID` or a fresh one) and exposes `request.beacn` for
  handlers to publish with the id already attached.
* `publish_model_event(instance, event, **kw)` — a one-liner for `post_save` /
  `post_delete` signal handlers.

Configure with a module-level client::

    # settings.py
    from beacn import Beacn
    BEACN = Beacn(url="https://beacn.internal", api_key="bk_...")
"""

from __future__ import annotations

import uuid
from typing import Any

_CLIENT = None


def configure(client: Any) -> None:
    global _CLIENT
    _CLIENT = client


def _client() -> Any:
    if _CLIENT is not None:
        return _CLIENT
    try:
        from django.conf import settings

        return getattr(settings, "BEACN", None)
    except Exception:  # noqa: BLE001
        return None


class _BoundPublisher:
    def __init__(self, correlation_id: str, request_id: str) -> None:
        self.correlation_id = correlation_id
        self.request_id = request_id

    def publish(self, event: str, topic: str | None = None, data: dict | None = None, **kw: Any):
        client = _client()
        if client is None:
            return None
        kw.setdefault("correlation_id", self.correlation_id)
        kw.setdefault("request_id", self.request_id)
        return client.publish(event, topic=topic, data=data or {}, **kw)


class BeacnMiddleware:
    """Adds `request.beacn` and echoes the correlation id on the response."""

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response

    def __call__(self, request: Any) -> Any:
        cid = request.META.get("HTTP_X_CORRELATION_ID") or f"cor_{uuid.uuid4().hex[:24]}"
        rid = request.META.get("HTTP_X_REQUEST_ID") or f"req_{uuid.uuid4().hex[:24]}"
        request.beacn = _BoundPublisher(cid, rid)
        response = self.get_response(request)
        response["X-Correlation-ID"] = cid
        return response


def publish_model_event(instance: Any, event: str, *, topic: str | None = None, **kw: Any) -> Any:
    client = _client()
    if client is None:
        return None
    data = kw.pop("data", None) or {
        "model": f"{instance._meta.app_label}.{instance._meta.model_name}",
        "pk": str(instance.pk),
    }
    return client.publish(event, topic=topic or instance._meta.app_label, data=data, **kw)
