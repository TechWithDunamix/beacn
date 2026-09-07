# Deploying BEACN

A systemd deployment for a single Debian/Ubuntu or RHEL/Fedora host. For
multiple hosts, run this on each and set `BEACN_BUS=redis` with a shared Redis
(see [`docs/SCALING.md`](../docs/SCALING.md)).

```bash
git clone https://github.com/TechWithDunamix/beacn && cd beacn
sudo deploy/install.sh --all --domain beacn.example.com
```

`--all` installs and enables a local Redis, PostgreSQL and Caddy. Drop flags you
don't want (`--redis`, `--postgres`, `--caddy`); without `--redis` the installer
switches the env file to the single-process in-memory bus.

The script is **idempotent** — to upgrade, `git pull` and run it again.

## What gets installed

| Path | What |
|---|---|
| `/opt/beacn` | the app + its virtualenv (`.venv`) |
| `/etc/beacn/beacn.env` | configuration, read by every unit; `SECRET_KEY` generated on first run |
| `beacn` (system user) | runs every service; no login shell |

### systemd units

| Unit | Role |
|---|---|
| `beacn-migrate.service` | `oneshot` — `beacn migrate`. `beacn-web` requires it. The only process allowed to create schema. |
| `beacn-web.service` | the web tier: `uvicorn app.main:app --workers ${BEACN_WEB_WORKERS}`. Graceful `SIGTERM` (close 1001 to sockets, drain the bus). |
| `beacn-work.service` + `.timer` | maintenance jobs (`beacn work`) every 2 minutes — retention prune, counter refresh, connection reaping, idempotency sweep. |
| `beacn-web@.service` | *optional* template: one process per port for running behind a load balancer instead of `uvicorn --workers`. `systemctl enable --now beacn-web@8000 beacn-web@8001`. |
| `beacn.target` | convenience: `systemctl restart beacn.target`. |

## Common operations

```bash
systemctl status beacn-web
journalctl -u beacn-web -f
systemctl restart beacn-web.service          # after editing /etc/beacn/beacn.env
systemctl list-timers beacn-work.timer

sudo -u beacn /opt/beacn/.venv/bin/beacn doctor        # config + db + bus check
sudo -u beacn /opt/beacn/.venv/bin/beacn user create you@example.com --role Admin --admin
```

## Reverse proxy

`deploy/Caddyfile.example` proxies `beacn.example.com` to `127.0.0.1:8000` with
automatic HTTPS, `flush_interval -1` (SSE), and a 24 h upstream read timeout
(WebSockets). Any proxy works as long as it passes `Upgrade` and does not buffer
`text/event-stream`.

## Front end

The built assets (`static/build/`) are **not** committed. `install.sh` builds
them with `npm ci && npm run build` if Node is on the host; otherwise build on
another machine and `rsync` `static/build/` into `/opt/beacn/`, or run a CI job
that does it. With `VITE_DEV=false` (the production default) the app serves those
files; without them the dashboard HTML loads but has no JavaScript.

## Uninstall

```bash
systemctl disable --now beacn-web beacn-work.timer beacn-migrate
rm /etc/systemd/system/beacn-*.service /etc/systemd/system/beacn.target
systemctl daemon-reload
rm -rf /opt/beacn /etc/beacn
userdel beacn
# then drop the beacn postgres db/role and the redis instance if they were dedicated
```
