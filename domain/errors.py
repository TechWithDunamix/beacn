"""Domain-level errors.

These are transport-agnostic. The REST layer maps them to status codes
(`routes/api/_common.py`), the realtime layer maps them to `error` frames, and
the SDK re-raises structured equivalents.
"""

from __future__ import annotations

from typing import Any


class BeacnError(Exception):
    """Base class. Carries a stable machine `code` and optional `details`."""

    code = "error"
    status = 400

    def __init__(self, message: str, *, details: Any = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            out["details"] = self.details
        return out


class ValidationError(BeacnError):
    code = "invalid"
    status = 422


class AuthenticationError(BeacnError):
    code = "unauthenticated"
    status = 401


class AuthorizationError(BeacnError):
    code = "forbidden"
    status = 403


class NotFoundError(BeacnError):
    code = "not_found"
    status = 404


class ConflictError(BeacnError):
    code = "conflict"
    status = 409


class PayloadTooLargeError(BeacnError):
    code = "payload_too_large"
    status = 413


class RateLimitedError(BeacnError):
    code = "rate_limited"
    status = 429

    def __init__(self, message: str, *, retry_after: float = 1.0, **kw: Any) -> None:
        super().__init__(message, **kw)
        self.retry_after = retry_after


class DependencyError(BeacnError):
    """A backing service (database) is unavailable."""

    code = "unavailable"
    status = 503
