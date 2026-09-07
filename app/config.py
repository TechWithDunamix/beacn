"""Settings, read once from the environment.

Twelve-factor: every setting has a working default and a deployment changes
behaviour with environment variables only. `app_env` is a label, not a switch —
the only thing that branches on it is `check_production`, a boot-time guard.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

INSECURE_SECRET = "dev-only-insecure-secret-key"

#: The three isolation environments BEACN understands. An API key, an event, a
#: topic and a realtime connection all carry one of these and never cross.
ENVIRONMENTS = ("development", "staging", "production")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "BEACN"))
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "local"))
    app_url: str = field(default_factory=lambda: os.getenv("APP_URL", "http://localhost:8000"))
    debug: bool = field(default_factory=lambda: _bool("APP_DEBUG", True))
    secret_key: str = field(default_factory=lambda: os.getenv("SECRET_KEY", INSECURE_SECRET))

    # ---- Database -------------------------------------------------------
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL", f"sqlite://{BASE_DIR / 'storage' / 'beacn.db'}"
        )
    )
    db_pool_size: int = field(default_factory=lambda: _int("DB_POOL_SIZE", 10))
    db_echo: bool = field(default_factory=lambda: _bool("DB_ECHO", False))
    db_generate_schemas: bool = field(default_factory=lambda: _bool("DB_GENERATE_SCHEMAS", True))

    # ---- Event bus / Redis -------------------------------------------------
    #: "memory" (single process, the default) or "redis" (cross-instance fanout).
    bus_backend: str = field(default_factory=lambda: os.getenv("BEACN_BUS", "memory"))
    redis_url: str = field(
        default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    #: Prefix on every Redis key/channel so many BEACN installs can share one Redis.
    redis_namespace: str = field(default_factory=lambda: os.getenv("REDIS_NAMESPACE", "beacn"))
    queue_backend: str = field(default_factory=lambda: os.getenv("QUEUE_BACKEND", "memory"))

    # ---- Ingestion limits ----------------------------------------------
    ingest_rate_per_minute: int = field(
        default_factory=lambda: _int("INGEST_RATE_PER_MINUTE", 6000)
    )
    ingest_burst: int = field(default_factory=lambda: _int("INGEST_BURST", 600))
    max_request_bytes: int = field(
        default_factory=lambda: _int("MAX_REQUEST_BYTES", 4 * 1024 * 1024)
    )
    idempotency_ttl_hours: int = field(default_factory=lambda: _int("IDEMPOTENCY_TTL_HOURS", 24))

    # ---- Retention ----------------------------------------------------
    event_retention_hours: int = field(
        default_factory=lambda: _int("EVENT_RETENTION_HOURS", 24 * 7)
    )
    task_retention_hours: int = field(
        default_factory=lambda: _int("TASK_RETENTION_HOURS", 24 * 30)
    )
    notification_retention_hours: int = field(
        default_factory=lambda: _int("NOTIFICATION_RETENTION_HOURS", 24 * 30)
    )
    connection_retention_hours: int = field(
        default_factory=lambda: _int("CONNECTION_RETENTION_HOURS", 24 * 3)
    )
    #: Only 1 in N delivery attempts is persisted once a topic exceeds this many
    #: live subscribers. Keeps `delivery_attempts` bounded during fanout storms.
    delivery_sample_threshold: int = field(
        default_factory=lambda: _int("DELIVERY_SAMPLE_THRESHOLD", 50)
    )

    # ---- Realtime ----------------------------------------------------
    heartbeat_ms: int = field(default_factory=lambda: _int("REALTIME_HEARTBEAT_MS", 25000))
    connection_max_seconds: int = field(
        default_factory=lambda: _int("REALTIME_CONNECTION_MAX_SECONDS", 60 * 60 * 12)
    )
    per_connection_queue: int = field(default_factory=lambda: _int("REALTIME_QUEUE", 512))
    realtime_token_ttl_seconds: int = field(
        default_factory=lambda: _int("REALTIME_TOKEN_TTL_SECONDS", 3600)
    )
    replay_max_events: int = field(default_factory=lambda: _int("REPLAY_MAX_EVENTS", 1000))

    # ---- Sessions ----------------------------------------------------
    session_cookie_name: str = field(
        default_factory=lambda: os.getenv("SESSION_COOKIE", "beacn_session")
    )
    session_lifetime: int = field(default_factory=lambda: _int("SESSION_LIFETIME", 60 * 60 * 12))
    cookie_secure: bool = field(
        default_factory=lambda: _bool(
            "COOKIE_SECURE", os.getenv("APP_ENV", "local") == "production"
        )
    )

    # ---- Front end ----------------------------------------------------
    vite_dev: bool = field(default_factory=lambda: _bool("VITE_DEV", True))
    vite_dev_server: str = field(
        default_factory=lambda: os.getenv("VITE_DEV_SERVER", "http://localhost:5173")
    )

    @property
    def scheme(self) -> str:
        return "https" if self.app_url.startswith("https://") else "http"

    @property
    def uses_redis(self) -> bool:
        return self.bus_backend == "redis" or self.queue_backend == "redis"


config = Config()


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [config.app_url]


def check_production() -> list[str]:
    """Configuration that is unsafe with APP_ENV=production. Returned, not raised."""
    warnings: list[str] = []
    if config.app_env != "production":
        return warnings
    if config.secret_key == INSECURE_SECRET:
        warnings.append("SECRET_KEY is the development default.")
    if config.debug:
        warnings.append("APP_DEBUG is on.")
    if not config.cookie_secure:
        warnings.append("COOKIE_SECURE is off; session cookies would ride plain HTTP.")
    if config.database_url.startswith("sqlite://"):
        warnings.append("DATABASE_URL is SQLite; use Postgres in production.")
    if config.bus_backend != "redis":
        warnings.append(
            "BEACN_BUS is not 'redis'; multi-instance fanout will not work across processes."
        )
    return warnings
