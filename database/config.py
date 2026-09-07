"""Database wiring — one definition shared by the app, the CLI and tests."""

from __future__ import annotations

import re
from pathlib import Path

from sillo.record import DatabaseConfig, DatabaseManager

from app.config import config

#: `sillo.permissions.models` supplies the RBAC tables BEACN's control plane
#: uses as they ship (Permission, Group, UserGroup, GroupPermission). BEACN's
#: own `User` claims `table = "users"`, so `sillo.users` is deliberately absent.
MODEL_MODULES = ["database.models", "sillo.permissions.models"]
MIGRATIONS_MODULE = "database.migrations"


def _ensure_sqlite_dir(url: str) -> None:
    """Create the parent directory of a file-backed SQLite database.

    SQLite raises a bare "unable to open database file" when the directory does
    not exist — which is what a fresh checkout hits, since `storage/` is not
    tracked. `sqlite://:memory:` and non-sqlite URLs are left alone.
    """
    match = re.match(r"^sqlite://(?!:memory:)(?://)?(.+)$", url)
    if not match:
        return
    path = Path(match.group(1)).expanduser()
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


def database_config(*, generate_schemas: bool | None = None) -> DatabaseConfig:
    _ensure_sqlite_dir(config.database_url)
    return DatabaseConfig(
        url=config.database_url,
        pool_size=config.db_pool_size,
        echo=config.db_echo,
        generate_schemas=(
            config.db_generate_schemas if generate_schemas is None else generate_schemas
        ),
    )


def database(*, generate_schemas: bool | None = None) -> DatabaseManager:
    """A manager for scripts that use the ORM outside a request."""
    manager = DatabaseManager(database_config(generate_schemas=generate_schemas))
    manager.register_models(*MODEL_MODULES).set_migrations(MIGRATIONS_MODULE)
    return manager
