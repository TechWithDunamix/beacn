"""Run every example producer at once.

Each simulator runs in its own thread with its own API key, exactly as six
separate backend services would. Two modes:

    python examples/run_all.py --burst 40     # each fires 40 iterations, then exits
                                              #   -> fills the dashboard quickly
    python examples/run_all.py                # live mixed stream until Ctrl-C
    python examples/run_all.py --rate 3       # 3x faster live stream
    python examples/run_all.py --duration 120 # live for two minutes, then stop
"""

from __future__ import annotations

import argparse
import threading
import time

import chat_service
import cron_reports
import deployment_service
import notification_service
import orders_worker
import payments_api
from _common import Ticker

SIMULATORS = [
    payments_api,
    deployment_service,
    orders_worker,
    chat_service,
    notification_service,
    cron_reports,
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--burst", type=int, default=None, help="Iterations per simulator, then exit.")
    ap.add_argument("--rate", type=float, default=1.0, help="Live speed multiplier.")
    ap.add_argument("--duration", type=float, default=0.0, help="Live seconds (0 = until Ctrl-C).")
    args = ap.parse_args()

    stop = threading.Event()
    threads: list[threading.Thread] = []
    for mod in SIMULATORS:
        ticker = Ticker(stop, burst=args.burst, rate=args.rate)
        th = threading.Thread(
            target=_guard(mod.run), args=(ticker,), name=mod.__name__.split(".")[-1], daemon=True
        )
        th.start()
        threads.append(th)

    mode = f"burst x{args.burst}" if args.burst else (
        f"live {args.duration}s" if args.duration else "live (Ctrl-C to stop)"
    )
    print(f"\n>>> {len(threads)} producers running — {mode}\n")

    try:
        if args.burst:
            for th in threads:
                th.join()
        elif args.duration:
            time.sleep(args.duration)
            stop.set()
            for th in threads:
                th.join(timeout=5)
        else:
            while any(th.is_alive() for th in threads):
                time.sleep(0.5)
    except KeyboardInterrupt:
        stop.set()
        for th in threads:
            th.join(timeout=5)

    print("\n>>> done. Open the dashboard, or: python examples/consumer.py")
    return 0


def _guard(fn):
    def wrapped(ticker: Ticker) -> None:
        try:
            fn(ticker)
        except SystemExit as exc:  # a missing key etc. — surface it, don't kill the rest
            print(f"! {fn.__module__}: {exc}")

    return wrapped


if __name__ == "__main__":
    raise SystemExit(main())
