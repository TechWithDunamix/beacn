"""SDK integration tests run against a real BEACN server.

A uvicorn process is started in a background thread on an ephemeral port with a
temp-file SQLite database. A producer and a full-scope API key are seeded before
the server starts. The SDK then talks to it over real HTTP/SSE — nothing is
mocked.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "sdk" / "python"))


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("beacn") / "sdk.db"
    os.environ["DATABASE_URL"] = f"sqlite://{db_path}"
    os.environ["SECRET_KEY"] = "sdk-test-secret"
    os.environ["APP_ENV"] = "test"
    os.environ["VITE_DEV"] = "true"
    os.environ["DB_GENERATE_SCHEMAS"] = "true"
    os.environ["BEACN_BUS"] = "memory"
    os.environ["INGEST_RATE_PER_MINUTE"] = "100000"
    os.environ["INGEST_BURST"] = "10000"

    import asyncio

    from tortoise import Tortoise

    from app.authz import ensure_roles
    from database.config import MODEL_MODULES
    from database.models import ApiKey, Producer

    secret_box = {}

    async def seed():
        await Tortoise.init(db_url=os.environ["DATABASE_URL"], modules={"models": MODEL_MODULES})
        await Tortoise.generate_schemas()
        await ensure_roles()
        producer = await Producer.create_for(name="SDK Producer", environment="development")
        key, secret = await ApiKey.issue(
            producer=producer, name="sdk",
            scopes="events:publish events:read events:replay topics:read tasks:read "
                   "notifications:read connections:read system:read",
        )
        secret_box["secret"] = secret
        await Tortoise.close_connections()

    asyncio.new_event_loop().run_until_complete(seed())

    port = _free_port()
    import uvicorn

    from app.bootstrap import create_app

    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    import urllib.request

    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.15)
    else:
        raise RuntimeError("server did not start")

    yield {
        "http": f"http://127.0.0.1:{port}",
        "ws": f"ws://127.0.0.1:{port}",
        "api_key": secret_box["secret"],
    }

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def sdk(live_server):
    from beacn import Beacn

    return Beacn(url=live_server["http"], api_key=live_server["api_key"])
