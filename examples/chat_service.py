"""Example producer: a chat service.

Publishes `message.created` (kind = message) to a room topic and, for DMs, to
the recipient's private `user:<id>` topic.

Run:  python examples/chat_service.py --burst 50
"""

from __future__ import annotations

import random

from _common import Ticker, client_for, jitter, now_iso, publish, rid, run_cli

ROOMS = ["room-general", "room-incidents", "room-payments", "room-random"]
PEOPLE = [rid("usr", 6) for _ in range(8)]
LINES = [
    "shipping it", "can someone review the PR?", "prod looks healthy",
    "the p99 spiked around 14:20", "rolled back, investigating",
    "lunch?", "who owns the billing worker", "done", "+1", "on it",
]


def _message(client, t: Ticker) -> None:
    sender = random.choice(PEOPLE)
    message_id = rid("msg")
    dm = random.random() < 0.3

    if dm:
        recipient = random.choice([p for p in PEOPLE if p != sender])
        topic = f"user:{recipient}"
        data = {"message_id": message_id, "from": sender, "to": recipient,
                "text": random.choice(LINES), "at": now_iso(), "dm": True}
    else:
        room = random.choice(ROOMS)
        topic = f"chat:{room}"
        data = {"message_id": message_id, "room": room, "from": sender,
                "text": random.choice(LINES), "at": now_iso()}

    publish(client, "message.created", topic=topic, data=data, user_id=sender)


def run(t: Ticker) -> None:
    client = client_for("chat-service")
    print("chat-service: publishing message.created to chat:* and user:* topics")
    while t.running():
        _message(client, t)
        t.wait(jitter(0.8))


if __name__ == "__main__":
    run_cli(run)
