"""BEACN domain layer — framework-free, I/O-free.

The event envelope, id generation, topic authorization and error types. Nothing
here imports Sillo, Tortoise or the HTTP layer, so it is trivially unit-testable
and could be lifted into another runtime unchanged.
"""

from .errors import (
    AuthenticationError,
    AuthorizationError,
    BeacnError,
    ConflictError,
    DependencyError,
    NotFoundError,
    PayloadTooLargeError,
    RateLimitedError,
    ValidationError,
)
from .events import (
    DEFAULT_SEVERITY,
    KIND_EVENT,
    KIND_MESSAGE,
    KIND_NOTIFICATION,
    KIND_TASK,
    MAX_BATCH,
    MAX_DATA_BYTES,
    SEVERITIES,
    Envelope,
    ProducerContext,
    parse_batch,
)
from .ids import new_id, new_ulid, ulid_of
from .topics import Grant, TopicSpec, authorize_subscription, default_spec

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "BeacnError",
    "ConflictError",
    "DependencyError",
    "NotFoundError",
    "PayloadTooLargeError",
    "RateLimitedError",
    "ValidationError",
    "DEFAULT_SEVERITY",
    "KIND_EVENT",
    "KIND_MESSAGE",
    "KIND_NOTIFICATION",
    "KIND_TASK",
    "MAX_BATCH",
    "MAX_DATA_BYTES",
    "SEVERITIES",
    "Envelope",
    "ProducerContext",
    "parse_batch",
    "new_id",
    "new_ulid",
    "ulid_of",
    "Grant",
    "TopicSpec",
    "authorize_subscription",
    "default_spec",
]
