"""Example consumer: subscribe and print.

The other side of BEACN — a frontend or service consuming the stream. Uses the
Python SDK's `subscribe()` (Server-Sent Events, standard library only), which
mints a realtime token, streams events, and reconnects with backoff.

    python examples/consumer.py                       # payments, tasks, deployments
    python examples/consumer.py tasks reports
    python examples/consumer.py 'chat:room-general' 'user:*'   # private topics work too
"""

from __future__ import annotations

import json
import sys

from _common import client_for

DEFAULT_TOPICS = ["payments", "tasks", "deployments"]


def main() -> int:
    topics = sys.argv[1:] or DEFAULT_TOPICS
    client = client_for("payments-api")  # any example key carries events:read
    print(f"subscribing to: {', '.join(topics)}   (Ctrl-C to stop)\n")
    try:
        for event in client.subscribe(*topics):
            payload = json.dumps(event.data, separators=(",", ":"))
            if len(payload) > 120:
                payload = payload[:117] + "..."
            print(f"{event.timestamp}  {event.topic:<20} {event.event:<28} {payload}")
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
