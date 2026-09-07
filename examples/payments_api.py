"""Example producer: a payments API.

Each "transaction" is a chain of events sharing one `correlation_id`:

    payment.initiated -> payment.authorized -> payment.completed | payment.failed
    (and, later, sometimes payment.refunded)

Run one burst:   python examples/payments_api.py --burst 30
Run live:        python examples/payments_api.py --rate 2
"""

from __future__ import annotations

import random

from _common import Ticker, client_for, jitter, publish, rid, run_cli

CURRENCIES = ["usd", "eur", "gbp", "ngn"]
METHODS = ["card", "bank_transfer", "wallet", "apple_pay"]


def _transaction(client, t: Ticker) -> None:
    correlation = rid("cor")
    payment_id = rid("pay")
    org = rid("org", 6)
    user = rid("usr", 8)
    amount = random.choice([1999, 4900, 12000, 50000, 250000, 999])
    common = dict(
        topic="payments",
        correlation_id=correlation,
        organization_id=org,
        user_id=user,
    )
    data = {
        "payment_id": payment_id,
        "amount": amount,
        "currency": random.choice(CURRENCIES),
        "method": random.choice(METHODS),
        "merchant_id": rid("mch", 6),
    }

    publish(client, "payment.initiated", data=data, **common)
    t.wait(jitter(0.4))

    if random.random() < 0.06:
        publish(client, "payment.failed", severity="warning",
                data={**data, "reason": "card_declined"}, **common)
        return

    publish(client, "payment.authorized", data=data, **common)
    t.wait(jitter(0.6))

    if random.random() < 0.1:
        publish(client, "payment.failed", severity="error",
                data={**data, "reason": random.choice(["insufficient_funds", "3ds_timeout", "risk_block"])},
                **common)
        return

    publish(client, "payment.completed", data={**data, "captured": amount}, **common)

    if random.random() < 0.12:
        t.wait(jitter(1.5))
        refund = random.choice([amount, amount // 2])
        publish(client, "payment.refunded", severity="notice",
                data={**data, "refunded": refund, "reason": "customer_request"}, **common)


def run(t: Ticker) -> None:
    client = client_for("payments-api")
    print("payments-api: publishing to topic 'payments'")
    while t.running():
        _transaction(client, t)
        t.wait(jitter(1.2))


if __name__ == "__main__":
    run_cli(run)
