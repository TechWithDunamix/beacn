"""Shared plumbing for the example producers.

Each example is a small program that behaves like a real backend service:
it holds one BEACN API key and publishes a stream of events with the Python
SDK. `examples/bootstrap.py` creates the producers and keys and writes
`examples/keys.json`; everything else reads it through here.
"""

from __future__ import annotations

import json
import os
import random
import string
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Use the in-repo SDK without installing it.
sys.path.insert(0, str(ROOT / "sdk" / "python"))

from beacn import APIError, Beacn  # noqa: E402

BEACN_URL = os.getenv("BEACN_URL", "http://localhost:8000")
ENVIRONMENT = os.getenv("BEACN_ENV", "development")
KEYS_FILE = ROOT / "examples" / "keys.json"

#: the producers bootstrap.py creates. Each key gets the same broad read+publish
#: set so any example can also *consume* (subscribe, replay, read tasks and
#: notifications) — a real producer would usually hold only `events:publish`.
_SCOPES = (
    "events:publish events:read events:replay topics:read "
    "tasks:read notifications:read connections:read"
)
PRODUCERS = {name: _SCOPES for name in (
    "payments-api",
    "deployment-service",
    "orders-worker",
    "chat-service",
    "notification-service",
    "cron-reports",
)}


def load_keys() -> dict:
    if not KEYS_FILE.exists():
        raise SystemExit(
            "examples/keys.json is missing — run:\n\n    python examples/bootstrap.py\n"
        )
    return json.loads(KEYS_FILE.read_text())


def client_for(producer: str) -> Beacn:
    keys = load_keys()
    secret = keys.get(producer)
    if not secret:
        raise SystemExit(f"No key for {producer!r}. Re-run: python examples/bootstrap.py")
    return Beacn(url=BEACN_URL, api_key=secret, default_source=producer)


# -- helpers ------------------------------------------------------------


def rid(prefix: str, n: int = 12) -> str:
    return prefix + "_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def jitter(base: float, spread: float = 0.4) -> float:
    return max(0.01, base * (1 + random.uniform(-spread, spread)))


class Ticker:
    """Drives a simulator loop: either a fixed burst, or until stopped."""

    def __init__(self, stop: threading.Event | None = None, *, burst: int | None = None, rate: float = 1.0):
        self.stop = stop or threading.Event()
        self.burst = burst
        self.rate = max(0.05, rate)
        self._done = 0

    def running(self) -> bool:
        if self.stop.is_set():
            return False
        if self.burst is not None and self._done >= self.burst:
            return False
        return True

    def wait(self, seconds: float) -> None:
        self._done += 1
        if self.burst is not None:
            # burst mode floods fast — a tiny pause keeps ordering readable
            self.stop.wait(0.01)
        else:
            self.stop.wait(seconds / self.rate)


def publish(client: Beacn, event: str, **kw) -> str | None:
    """Publish and return the event id, logging a one-liner. Never raises."""
    try:
        res = client.publish(event, **kw)
        eid = res.id or "(dedup)"
        topic = kw.get("topic", event.split(".", 1)[0])
        print(f"  {client._cfg.default_source:<20} {event:<26} {topic:<16} {eid}")
        return res.id
    except APIError as exc:
        print(f"  ! {event}: {exc}")
        return None


def run_cli(run_fn) -> None:
    """Standard `if __name__ == '__main__'` entry point for a simulator."""
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--burst", type=int, default=None, help="Fire N iterations then exit.")
    ap.add_argument("--rate", type=float, default=1.0, help="Speed multiplier for the live loop.")
    ap.add_argument("--duration", type=float, default=0.0, help="Live seconds (0 = until Ctrl-C).")
    args = ap.parse_args()

    stop = threading.Event()
    if args.duration and not args.burst:
        threading.Timer(args.duration, stop.set).start()
    try:
        run_fn(Ticker(stop, burst=args.burst, rate=args.rate))
    except KeyboardInterrupt:
        stop.set()
        print("\nstopped.")
