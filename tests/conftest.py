"""Test fixtures.

Every test runs against a fresh in-memory SQLite database and the real
`create_app()` application. The client is httpx over `ASGITransport` (not
`sillo.testclient.TestClient`) so handlers and the Tortoise connection share one
event loop — see the Janus conftest for the full reasoning.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite://:memory:")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("VITE_DEV", "true")  # emit dev-server tags; no build needed in tests
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DB_GENERATE_SCHEMAS", "false")
os.environ.setdefault("BEACN_BUS", "memory")
os.environ.setdefault("INGEST_RATE_PER_MINUTE", "100000")
os.environ.setdefault("INGEST_BURST", "5000")

import httpx  # noqa: E402
import pytest  # noqa: E402
from tortoise import Tortoise  # noqa: E402

from app.authz import ensure_roles  # noqa: E402
from database.config import MODEL_MODULES  # noqa: E402
from realtime import get_realtime, reset_realtime  # noqa: E402


@pytest.fixture(autouse=True)
async def database():
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": MODEL_MODULES})
    await Tortoise.generate_schemas()
    await ensure_roles()
    reset_realtime()
    rt = get_realtime()
    await rt.start()
    yield
    await rt.stop()
    reset_realtime()
    await Tortoise._drop_databases()
    await Tortoise.close_connections()


@pytest.fixture
def app():
    from app.bootstrap import create_app

    return create_app()


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", follow_redirects=False
    ) as http_client:
        yield http_client


@pytest.fixture
async def producer_env():
    """A producer + a full-scope API key in the `development` environment."""
    from tests.helpers import make_api_key

    return await make_api_key(scopes="events:publish events:read events:replay topics:read "
                                     "tasks:read notifications:read notifications:write "
                                     "connections:read system:read")


@pytest.fixture
async def admin_user():
    from tests.helpers import make_user

    return await make_user("admin@test.local", role="Admin", superuser=True)
