"""Example producer: a notification service.

Publishes `notification.created` (kind = notification) to `user:<id>`. These
populate BEACN's Notifications page with recipient, type, channel and delivery
status.

Run:  python examples/notification_service.py --burst 40
"""

from __future__ import annotations

import random

from _common import Ticker, client_for, jitter, publish, rid, run_cli

RECIPIENTS = [rid("usr", 6) for _ in range(10)]
KINDS = {
    "billing": ("Invoice ready", "Your invoice for this month is available."),
    "security": ("New sign-in", "A new device signed in to your account."),
    "digest": ("Weekly summary", "Here is what happened in your projects this week."),
    "mention": ("You were mentioned", "Someone mentioned you in room-incidents."),
    "system": ("Maintenance window", "Scheduled maintenance this Sunday 02:00 UTC."),
}
CHANNELS = ["in_app", "email", "sms", "webhook"]


def _notification(client, t: Ticker) -> None:
    recipient = random.choice(RECIPIENTS)
    ntype = random.choice(list(KINDS))
    title, body = KINDS[ntype]
    channel = random.choice(CHANNELS)
    delivery = "delivered" if random.random() > 0.08 else random.choice(["failed", "pending"])
    publish(
        client, "notification.created", topic=f"user:{recipient}",
        severity="warning" if ntype == "security" else "info",
        user_id=recipient,
        data={
            "recipient": recipient, "type": ntype, "title": title, "body": body,
            "channel": channel, "delivery_status": delivery,
        },
    )


def run(t: Ticker) -> None:
    client = client_for("notification-service")
    print("notification-service: publishing notification.created to user:* topics")
    while t.running():
        _notification(client, t)
        t.wait(jitter(1.4))


if __name__ == "__main__":
    run_cli(run)
