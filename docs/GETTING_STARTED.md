# Getting started

This guide runs a local BEACN server, creates an operator and a scoped producer
key, then publishes and reads an event. Use Python 3.11+ and Node/npm or Bun for
the dashboard. SQLite and the in-process bus are sufficient for this guide.

## Install and start

From the repository root:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[server,dev]'
cp .env.example .env
# Replace SECRET_KEY in .env with a value from: openssl rand -hex 32
npm ci
npm run build
```

Remove inline `# ...` comments after values in the copied `.env`: the CLI
environment loader treats them as part of the value. Also check whether an
existing `/etc/beacn/beacn.env` is supplying server settings on this machine.

Set `VITE_DEV=false` in `.env` to use the built dashboard. For hot reload, leave
`VITE_DEV=true` and run `npm run dev` in another terminal instead.

```sh
beacn migrate
beacn user create you@example.com --role Admin --admin
beacn serve --reload --host 127.0.0.1 --port 8000
```

The user command prompts for a password. Open `http://127.0.0.1:8000` to sign in.
Local settings are for development; use the [deployment guide](DEPLOYMENT.md)
for production. The Makefile provides equivalents: `make setup`, `make admin
e=you@example.com`, `make dev`, and `make frontend-dev`.

## Create credentials

In another terminal with the virtual environment active:

```sh
beacn login
beacn producer create checkout --environment development
# Replace prd_REPLACE with the producer id printed above.
beacn key create prd_REPLACE --name checkout-publisher --scopes events:publish
beacn key create prd_REPLACE --name logs-consumer --scopes 'events:read events:replay'
```

Store the two returned secrets separately; they are shown only once. Operator
sessions manage producers and keys. Producer keys authorize application API
calls; they do not grant dashboard access. A key's producer determines its
isolation environment. A request body cannot choose another environment.

## Publish an event

Set the publisher key in your shell without committing it:

```sh
export BEACN_PUBLISH_KEY='bk_REPLACE'
curl --fail-with-body http://127.0.0.1:8000/api/v1/events \
  -H "Authorization: Bearer $BEACN_PUBLISH_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"event":"checkout.completed","topic":"logs","data":{"order_id":"ord_123"},"idempotency_key":"ord_123:completed"}'
```

A new event returns HTTP 201. Repeating the same idempotency key within the
configured window returns the existing event instead. A repeat of this single
event returns HTTP 200. See the [event contract](EVENT_MODEL.md) for all fields.

## Read and subscribe

```sh
export BEACN_READ_KEY='bk_REPLACE'
curl --fail-with-body 'http://127.0.0.1:8000/api/v1/events?topic=logs&limit=20' \
  -H "Authorization: Bearer $BEACN_READ_KEY"
curl --no-buffer --get http://127.0.0.1:8000/api/v1/sse \
  --data-urlencode "token=$BEACN_READ_KEY" --data-urlencode 'topics=logs'
```

Publish another event while the stream is open. The SSE connection begins with
`welcome`, then receives live events. It does not replay history automatically.
For a browser, mint a short-lived realtime JWT on your backend rather than
shipping a producer API key to the browser. See [realtime](REALTIME.md).

The Python SDK is a separate distribution/source file from the server package.
When working from this checkout, make its module available explicitly:

```sh
PYTHONPATH=sdk/python python - <<'PY'
import os
from beacn import Beacn
client = Beacn(url="http://127.0.0.1:8000", api_key=os.environ["BEACN_READ_KEY"])
for event in client.subscribe("logs"):
    print(event.id, event.data)
PY
```

## Archive logs with Logsman

Logsman subscribes to `logs` and persists a validated log payload in MongoDB.
BEACN's envelope and Logsman's payload are different contracts. To send a
Logsman-compatible event, publish:

```json
{
  "event": "log.created",
  "topic": "logs",
  "idempotency_key": "log_123",
  "data": {
    "id": "log_123",
    "type": "info",
    "source": "checkout",
    "destination": "payments",
    "data": {"message": "checkout completed"},
    "tags": ["checkout"]
  }
}
```

Give Logsman a key with `events:read` in the same environment as the publisher.
`events:replay` is additionally needed for explicit replay/backfill work. Logsman
currently consumes the live SSE stream; it does not persist a durable cursor.
Do not assume it catches up automatically after downtime.

## Next steps

- [API reference](API.md): filtering, replay, tokens and control-plane routes.
- [Operations](OPERATIONS.md): deployment checks, backups, failures and recovery.
- [Security](SECURITY.md): key scopes, topic grants and environment boundaries.
