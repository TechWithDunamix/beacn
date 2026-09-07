"""Every model BEACN defines, in one namespace.

`database/config.py` names this module as the one Tortoise scans, so a model not
imported here does not exist as far as the schema is concerned.

`sillo.users` is deliberately absent — BEACN's own `User` sets
`table = "users"`. `sillo.permissions` *is* scanned (see `database/config.py`).
"""

from database.models.audit import AuditEvent
from database.models.connection import Connection
from database.models.event import DeliveryAttempt, Event, EventIdempotency
from database.models.identity import LoginEvent, User, UserSession
from database.models.notification import Notification
from database.models.producer import SCOPES, ApiKey, Producer, hash_secret
from database.models.task import Task
from database.models.topic import Subscription, Topic

__all__ = [
    "ApiKey",
    "AuditEvent",
    "Connection",
    "DeliveryAttempt",
    "Event",
    "EventIdempotency",
    "LoginEvent",
    "Notification",
    "Producer",
    "SCOPES",
    "Subscription",
    "Task",
    "Topic",
    "User",
    "UserSession",
    "hash_secret",
]
