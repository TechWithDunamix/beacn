"""Create the example producers and their API keys.

Signs in to the control plane with an operator account, creates one producer
per simulator, issues each an API key, and writes the secrets to
`examples/keys.json` (git-ignored). Idempotent: re-running reuses existing
producers and issues fresh keys.

    python examples/bootstrap.py --email you@example.com
    # password: hidden prompt, or $BEACN_PASSWORD

Needs the BEACN server running (`beacn serve`) and an operator with the
`producers.write` and `apikeys.write` permissions (any Operator or Admin).
"""

from __future__ import annotations

import argparse
import getpass
import json
import os

import httpx
from _common import BEACN_URL, ENVIRONMENT, KEYS_FILE, PRODUCERS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default=os.getenv("BEACN_EMAIL", ""), help="Operator email.")
    ap.add_argument("--url", default=BEACN_URL)
    ap.add_argument("--environment", default=ENVIRONMENT)
    args = ap.parse_args()

    email = args.email or input("Operator email: ").strip()
    password = os.getenv("BEACN_PASSWORD") or getpass.getpass("Password: ")

    s = httpx.Client(base_url=args.url.rstrip("/"), timeout=30.0)

    r = s.post("/api/control/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        print(f"login failed ({r.status_code}): {r.text[:200]}")
        return 1
    token = r.json()["token"]
    hdr = {"Authorization": f"Bearer {token}", "X-BEACN-Control": "1"}
    print(f"signed in as {email}\n")

    existing = {p["slug"]: p for p in s.get("/api/control/producers", headers=hdr).json()["producers"]
                if p["environment"] == args.environment}

    secrets: dict[str, str] = {}
    for slug, scopes in PRODUCERS.items():
        producer = existing.get(slug)
        if producer is None:
            cr = s.post("/api/control/producers", headers=hdr, json={
                "name": slug.replace("-", " ").title(),
                "slug": slug,
                "environment": args.environment,
                "description": f"BEACN example — {slug}",
                "default_source": slug,
            })
            if cr.status_code not in (200, 201):
                print(f"! could not create {slug}: {cr.text[:200]}")
                continue
            producer = cr.json()["producer"]
            print(f"  + producer {slug}  ({producer['id']})")
        else:
            print(f"  = producer {slug}  ({producer['id']}) already exists")

        kr = s.post("/api/control/keys", headers=hdr, json={
            "producer_id": producer["id"],
            "name": f"{slug} example key",
            "scopes": scopes,
        })
        if kr.status_code not in (200, 201):
            print(f"! could not issue key for {slug}: {kr.text[:200]}")
            continue
        secrets[slug] = kr.json()["key"]["secret"]
        print(f"    key {kr.json()['key']['prefix']}  scopes: {scopes}")

    KEYS_FILE.write_text(json.dumps(secrets, indent=2))
    print(f"\nwrote {len(secrets)} keys to {KEYS_FILE.relative_to(KEYS_FILE.parents[1])}")
    print("next:  python examples/run_all.py --burst 40      (fill the dashboard)")
    print("       python examples/run_all.py                 (live stream)")
    print("       python examples/consumer.py payments tasks  (watch it arrive)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
