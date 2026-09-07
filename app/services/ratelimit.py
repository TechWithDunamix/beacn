"""Per-key publish rate limiting — an in-process token bucket.

Sized from `config.ingest_rate_per_minute` (sustained) and `config.ingest_burst`
(bucket depth). This is per-instance: behind a load balancer the effective limit
is `N * rate`, which is the intended behaviour — the limit protects a single
process from a runaway producer, not the cluster from aggregate load (that is
what capacity planning is for). A Redis-backed shared bucket can be swapped in
by implementing the same `check()` signature.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.config import config
from domain.errors import RateLimitedError


@dataclass
class _Bucket:
    tokens: float
    updated: float


class TokenBucketLimiter:
    def __init__(self, rate_per_minute: int | None = None, burst: int | None = None) -> None:
        self.rate = (rate_per_minute or config.ingest_rate_per_minute) / 60.0
        self.burst = float(burst or config.ingest_burst)
        self._buckets: dict[str, _Bucket] = {}

    def _bucket(self, key: str, now: float) -> _Bucket:
        b = self._buckets.get(key)
        if b is None:
            b = _Bucket(tokens=self.burst, updated=now)
            self._buckets[key] = b
        return b

    def check(self, key: str, cost: int = 1, *, now: float | None = None) -> None:
        """Consume `cost` tokens or raise `RateLimitedError`."""
        now = now if now is not None else time.monotonic()
        b = self._bucket(key, now)
        elapsed = now - b.updated
        b.tokens = min(self.burst, b.tokens + elapsed * self.rate)
        b.updated = now
        if b.tokens < cost:
            deficit = cost - b.tokens
            retry_after = max(0.1, deficit / self.rate) if self.rate else 60.0
            raise RateLimitedError(
                "publish rate limit exceeded",
                retry_after=round(retry_after, 2),
                details={"limit_per_minute": int(self.rate * 60), "burst": int(self.burst)},
            )
        b.tokens -= cost

    def snapshot(self, key: str) -> dict:
        b = self._buckets.get(key)
        return {
            "tokens": round(b.tokens, 1) if b else self.burst,
            "burst": int(self.burst),
            "rate_per_minute": int(self.rate * 60),
        }

    def prune(self, older_than: float = 3600.0) -> int:
        now = time.monotonic()
        stale = [k for k, b in self._buckets.items() if now - b.updated > older_than]
        for k in stale:
            del self._buckets[k]
        return len(stale)


#: process-wide singleton, used by the ingestion endpoint
limiter = TokenBucketLimiter()
