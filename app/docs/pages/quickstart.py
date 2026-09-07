"""Getting started — first events in a few minutes, and the full configuration
reference."""

from __future__ import annotations

from typing import Any

from app.docs.blocks import code, heading, note, para, steps, table, terms

PAGES: tuple[dict[str, Any], ...] = (
    # =====================================================================
    {
        "slug": "quick-start",
        "section": "quickstart",
        "title": "Quick start",
        "summary": "Install, migrate, create an operator, register a producer, publish and consume — end to end.",
        "blocks": [
            heading("Install and run"),
            code(
                """
python -m venv .venv && . .venv/bin/activate
pip install -e ".[server,dev]"          # add ,redis ,postgres for those extras

beacn migrate                           # create tables, seed the RBAC catalogue
beacn user create you@example.com --role Admin --admin
beacn serve --reload                    # http://localhost:8000
""",
                lang="bash",
            ),
            para(
                "`beacn user create` prompts for a password (or reads `$BEACN_PASSWORD` "
                "when there is no terminal). `--admin` marks a superuser and applies the "
                "framework password policy. The `--role` is one of `Admin`, `Operator`, "
                "`Developer`, `ReadOnly` — see [Authentication](/docs/authentication)."
            ),
            note(
                "A fresh checkout uses `sqlite://storage/beacn.db`. That is fine for a "
                "single instance and local work; use Postgres in production — "
                "[Deployment](/docs/deployment).",
                tone="info",
            ),

            heading("Register a producer and issue a key"),
            para(
                "A **producer** is an application or service that publishes to BEACN. It is "
                "scoped to one environment. An **API key** authenticates it; only a hash of "
                "the secret is stored, and the secret is shown exactly once."
            ),
            para("In the dashboard: **Producers** → register → then **API keys** → issue. Or on the CLI:"),
            code(
                """
beacn login you@example.com
beacn producer create "Payments API" --environment development
#  -> prd_01J...

beacn key create prd_01J... --name "payments dev" --scopes "events:publish events:read"
#  -> secret: bk_8593b6c9_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx   (store it now)
""",
                lang="bash",
            ),

            heading("Publish an event"),
            code(
                """
curl -XPOST http://localhost:8000/api/v1/events \\
  -H "Authorization: Bearer bk_8593b6c9_xxxx" \\
  -H "Content-Type: application/json" \\
  -d '{
        "event": "payment.completed",
        "topic": "payments",
        "data": { "payment_id": "pay_123", "amount": 50000 },
        "correlation_id": "cor_abc"
      }'
""",
                lang="bash",
            ),
            code(
                """
{ "accepted": 1, "deduplicated": 0,
  "events": [ { "id": "evt_01M...", "event": "payment.completed",
                "topic": "payments", "deduplicated": false } ] }
""",
                lang="json",
            ),
            para(
                "`201` on accept, `200` if every event in the request was a duplicate of one "
                "seen within the idempotency window. A batch is `{\"events\": [ ... ]}`, up to "
                "500."
            ),

            heading("Consume it"),
            para("With the Python SDK (the synchronous client and SSE consumer are standard-library only):"),
            code(
                """
from beacn import Beacn

beacn = Beacn(url="http://localhost:8000", api_key="bk_8593b6c9_xxxx")

for event in beacn.subscribe("payments"):
    print(event.event, event.data)      # reconnects + replays automatically
""",
                lang="python",
            ),
            para("Or from a browser with the TypeScript SDK:"),
            code(
                """
import { Beacn } from "@beacn/client";

const beacn = new Beacn({ url: "ws://localhost:8000", token });   // realtime JWT or bk_ key
const channel = beacn.channel("payments");
channel.on("payment.completed", (e) => console.log(e.data));
await channel.subscribe();
""",
                lang="typescript",
            ),

            heading("The example producers"),
            para(
                "The repository ships six runnable producer simulators plus a consumer under "
                "`examples/`. They fill the dashboard with realistic data — payments with "
                "correlation chains, Celery-shaped tasks, deployments, chat, notifications, "
                "a cron job."
            ),
            code(
                """
python examples/bootstrap.py --email you@example.com   # creates 6 producers + keys
python examples/run_all.py --burst 40                  # fill the dashboard fast
python examples/run_all.py                             # continuous live stream
python examples/consumer.py payments tasks             # watch it arrive
""",
                lang="bash",
            ),

            heading("Where to look next"),
            terms([
                ("[The event envelope](/docs/event-model)", "before you publish anything non-trivial"),
                ("[The realtime protocol](/docs/realtime-protocol)", "before you write a consumer that is not the SDK"),
                ("[Delivery semantics](/docs/delivery-semantics)", "before you depend on it"),
                ("[Scaling](/docs/scaling)", "before you run more than one instance"),
            ]),
        ],
    },

    # =====================================================================
    {
        "slug": "configuration",
        "section": "quickstart",
        "title": "Configuration",
        "summary": "Every environment variable BEACN reads, its default, and what it changes.",
        "blocks": [
            para(
                "BEACN is configured the twelve-factor way: every setting has a working "
                "default and a deployment changes behaviour with environment variables only. "
                "`APP_ENV` is a label that appears in the UI and health output — the only "
                "thing that branches on it is the production safety check."
            ),

            heading("Application"),
            table(
                ["Variable", "Default", "Meaning"],
                [
                    ["`APP_NAME`", "`BEACN`", "shown in the UI and page titles"],
                    ["`APP_ENV`", "`local`", "label; `production` turns on `check_production`"],
                    ["`APP_DEBUG`", "`true`", "verbose errors; turn off in production"],
                    ["`APP_URL`", "`http://localhost:8000`", "used as the default CORS origin"],
                    ["`SECRET_KEY`", "an insecure dev value", "**set this** — signs sessions and realtime tokens"],
                    ["`CORS_ORIGINS`", "`$APP_URL`", "comma-separated list of allowed browser origins"],
                    ["`COOKIE_SECURE`", "`true` when `APP_ENV=production`", "`Secure` flag on session and CSRF cookies"],
                ],
            ),

            heading("Database"),
            table(
                ["Variable", "Default", "Meaning"],
                [
                    ["`DATABASE_URL`", "`sqlite://storage/beacn.db`", "`postgres://user:pw@host/db` in production"],
                    ["`DB_GENERATE_SCHEMAS`", "`true`", "create missing tables on boot; **only the web process** should do this — workers set `false`"],
                    ["`DB_POOL_SIZE`", "`10`", "connection pool size"],
                    ["`DB_ECHO`", "`false`", "log every SQL statement"],
                ],
            ),
            note(
                "Two processes creating the schema at once race on SQLite (`database is "
                "locked`) and on Postgres's implicit types. The web process owns the schema; "
                "give it `DB_GENERATE_SCHEMAS=true` and everything else `false`.",
                tone="caution",
            ),

            heading("Event bus and Redis"),
            table(
                ["Variable", "Default", "Meaning"],
                [
                    ["`BEACN_BUS`", "`memory`", "`redis` for cross-instance fan-out"],
                    ["`REDIS_URL`", "`redis://localhost:6379/0`", "used by the bus and the queue when either is `redis`"],
                    ["`REDIS_NAMESPACE`", "`beacn`", "key/channel prefix — many BEACN installs can share one Redis"],
                    ["`QUEUE_BACKEND`", "`memory`", "`redis` for the maintenance job queue"],
                ],
            ),

            heading("Ingestion limits"),
            table(
                ["Variable", "Default", "Meaning"],
                [
                    ["`INGEST_RATE_PER_MINUTE`", "`6000`", "sustained publish rate per API key"],
                    ["`INGEST_BURST`", "`600`", "token-bucket depth per API key"],
                    ["`MAX_REQUEST_BYTES`", "`4194304`", "request body cap (4 MiB), checked before parsing"],
                    ["`IDEMPOTENCY_TTL_HOURS`", "`24`", "how long an idempotency marker is honoured"],
                ],
            ),
            para(
                "The rate limit is **per instance** by design — it protects one process "
                "from a runaway producer, not the cluster from aggregate load. Behind N "
                "instances the effective limit is `N × rate`; if you need a hard cluster "
                "cap, do it at the load balancer."
            ),

            heading("Retention"),
            table(
                ["Variable", "Default", "Meaning"],
                [
                    ["`EVENT_RETENTION_HOURS`", "`168` (7 days)", "global default; a topic row can override it per topic"],
                    ["`TASK_RETENTION_HOURS`", "`720` (30 days)", "terminal `tasks` rows past this are pruned"],
                    ["`NOTIFICATION_RETENTION_HOURS`", "`720`", "`notifications` rows"],
                    ["`CONNECTION_RETENTION_HOURS`", "`72`", "closed `connections` rows and `delivery_attempts`"],
                    ["`DELIVERY_SAMPLE_THRESHOLD`", "`50`", "above this many live subscribers on a topic, only 1-in-N delivery attempts are persisted"],
                ],
            ),
            para(
                "Retention is enforced by the `beacn work` job (schedule it every few "
                "minutes — [Deployment](/docs/deployment)). Replay is bounded by "
                "`EVENT_RETENTION_HOURS`: size it to your longest expected consumer outage "
                "plus a margin, and send anything you need long-term into a warehouse."
            ),

            heading("Realtime"),
            table(
                ["Variable", "Default", "Meaning"],
                [
                    ["`REALTIME_HEARTBEAT_MS`", "`25000`", "sent to clients in the `welcome` frame"],
                    ["`REALTIME_CONNECTION_MAX_SECONDS`", "`43200` (12h)", "hard connection lifetime; reconnect with a fresh token"],
                    ["`REALTIME_QUEUE`", "`512`", "per-connection outbound queue depth"],
                    ["`REALTIME_TOKEN_TTL_SECONDS`", "`3600`", "lifetime of a minted realtime JWT"],
                    ["`REPLAY_MAX_EVENTS`", "`1000`", "cap on events returned by one replay request"],
                ],
            ),

            heading("Sessions and the front end"),
            table(
                ["Variable", "Default", "Meaning"],
                [
                    ["`SESSION_COOKIE`", "`beacn_session`", "dashboard session cookie name"],
                    ["`SESSION_LIFETIME`", "`43200` (12h)", "seconds"],
                    ["`VITE_DEV`", "`true`", "`false` serves the built `static/build/` assets; `true` expects the Vite dev server"],
                    ["`VITE_DEV_SERVER`", "`http://localhost:5173`", "where `VITE_DEV=true` loads assets from"],
                ],
            ),

            heading("The production safety check"),
            para(
                "When `APP_ENV=production`, `app/config.py::check_production` refuses to boot "
                "if any of these is true. It is a guard, not a branch — it changes nothing "
                "about how BEACN runs, it only declines to start when the configuration "
                "would be unsafe."
            ),
            steps([
                "`SECRET_KEY` is still the development default.",
                "`APP_DEBUG` is on.",
                "`COOKIE_SECURE` is off (session cookies would ride plain HTTP).",
                "`DATABASE_URL` is SQLite.",
                "`BEACN_BUS` is not `redis` (multi-instance fan-out would not work).",
            ]),
        ],
    },
)
