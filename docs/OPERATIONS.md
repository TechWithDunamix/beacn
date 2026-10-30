# Operations and recovery

Use the [deployment reference](DEPLOYMENT.md) for settings and
[Linux installer guide](../deploy/README.md) for systemd setup.

## Deployment choices

| Setup | Intended use | Important constraint |
| --- | --- | --- |
| SQLite + memory bus | Local development, one web process | Live fan-out is process-local |
| PostgreSQL + Redis + systemd | Linux production deployment | All instances share DB, Redis namespace and signing secret |
| Bundled Compose | Local integration with PostgreSQL and Redis | Development credentials and settings; review ports and replicas |

The checked-in Compose file specifies two web replicas with a fixed host port
8000. A single Docker host cannot bind both replicas to the same port. The committed Compose
configuration also combines `APP_ENV=production` with `COOKIE_SECURE=false`,
which the production guard rejects. For local use, set the shared `APP_ENV` to
`development` in a local Compose copy/override and explicitly select one web replica:

```sh
docker compose up --build --scale web=1
```

For multiple replicas, configure a proxy and remove fixed per-replica host port
bindings. Do not use the bundled development credentials in production.

## Verify after deployment

```sh
curl --fail http://127.0.0.1:8000/health
sudo -u beacn /opt/beacn/.venv/bin/beacn doctor
sudo systemctl status beacn-migrate.service beacn-web.service
sudo systemctl list-timers beacn-work.timer
sudo journalctl -u beacn-web.service -u beacn-work.service --since '15 minutes ago'
```

Also publish and subscribe with credentials in the intended environment. A
successful HTTP health check does not prove cross-instance Redis delivery.
When using multiple instances, publish through one and consume through another.
The database controls health status; a degraded bus can still return HTTP 200.
Inspect `/metrics`, `doctor`, and logs for bus state and dropped deliveries.

The reverse proxy must support WebSocket upgrades and unbuffered SSE. Keep the
web listener private behind it. Realtime credentials appear in query strings;
redact `token` from proxy/access logs and prefer short-lived JWTs for browsers.

## Updates and schema

Back up the database and configuration before deployment. Deploy a known
revision, install its dependencies, and rebuild `static/build/`. Apply migrations
from one process before the new web tier accepts traffic. Set
`DB_GENERATE_SCHEMAS=false` in serving processes. The systemd migration service
is a oneshot with `RemainAfterExit=yes`; restarting only the web service does
not rerun it. Restarting `beacn.target` also restarts its migration service.

The optional `beacn-web@<port>` template units are not part of `beacn.target`;
stop/restart each enabled instance explicitly when updating them. Coordinate
migrations across hosts yourself; each host's migration unit is not a fleet lock.
A code rollback does not roll back the database. Check schema compatibility
before deploying an older revision or restore a tested backup.

## Delivery and replay

Live WebSocket/SSE delivery uses bounded queues and can lose messages when
consumers fall behind or Redis is unavailable. Persistence succeeds independently
of cross-instance fan-out. Redis recovery does not automatically replay all
missed events to connected consumers.

For recovery, retain the last successfully processed BEACN envelope id per topic
and environment, then call `POST /api/v1/events/replay` with `topic`, `since`
and `limit`, using a key with `events:replay`. Process results in order and
follow `replay.next_since` until it is null. Replayed events can overlap live
traffic; deduplicate by event id and checkpoint only after processing succeeds.
Arrange overlap between your live subscription and replay so events published
during catch-up are not lost.

`truncated=true` has two meanings in the current implementation: the requested
cursor predates retained history, or the replay exceeded the page limit. Use
`earliest_available` to assess a retention gap and `next_since` to continue
pagination. It is not by itself proof that data was deleted.

The SSE route does not process `Last-Event-ID`; reconnecting is not sufficient
for recovery. Use explicit REST or WebSocket replay. Never advertise exactly-once
delivery or unlimited history to consumers.

## Backups and retention

Back up PostgreSQL using your database platform's supported backup/restore
process, and test restores to an isolated instance. SQLite development backups
must be consistent with active writes; stop the local app or use SQLite's backup
API. Keep configuration and `SECRET_KEY` in secured backups separately from Git.

`beacn work` runs retention, counter refresh, idempotency cleanup and connection
reaping once. The installed timer runs it every two minutes. Monitor the timer;
starting the web server alone does not schedule those jobs. Set retention to
cover your maximum expected outage and recovery period. Topic-specific retention
can override the default. Retention is not an archival backup.

## Troubleshooting

| Symptom | Check / action |
| --- | --- |
| Production refuses startup | `APP_DEBUG=false`, non-default secret, secure cookies, PostgreSQL, Redis bus; read the boot error |
| Blank dashboard / missing JS | Build `static/build/`, set `VITE_DEV=false`, check asset requests |
| Publish returns 401 or 403 | Active key, expiry, `events:publish`, correct producer environment |
| History works but another instance receives nothing | Redis connectivity/namespace, bus logs, consumer topic grants |
| SSE connects but receives nothing | Publish after connecting; inspect welcome's allowed topics; disable proxy buffering |
| Duplicate consumer side effects | Deduplicate by envelope id and checkpoint after successful work |
| Missing older events | Retention, explicit replay pagination and consumer checkpoints |
| Storage keeps growing | Maintenance timer, retention settings and database indexes/backups |
| Host port 8000 already allocated in Compose | Use `--scale web=1` locally or configure a shared reverse proxy |
