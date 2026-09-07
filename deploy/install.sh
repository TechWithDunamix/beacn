#!/usr/bin/env bash
#
# BEACN — one-shot installer / upgrader for a systemd host (Debian/Ubuntu or
# RHEL/Fedora). Run as root from a checkout:
#
#     sudo deploy/install.sh --all
#
# What it does, idempotently (safe to re-run for an upgrade):
#   * installs prerequisites: python venv + build tools, and — when asked —
#     Redis and PostgreSQL (skipped if already present)
#   * creates the `beacn` system user, /opt/beacn and /etc/beacn
#   * syncs this checkout into /opt/beacn and builds the venv
#   * builds the front end if Node is available
#   * writes /etc/beacn/beacn.env on first run (generates SECRET_KEY); never
#     overwrites an existing one
#   * installs the systemd units, runs migrations, starts the web tier and the
#     maintenance timer
#
# Flags:
#   --redis            install + enable a local Redis
#   --postgres         install + enable a local PostgreSQL, create the beacn DB
#   --caddy            install Caddy (reverse proxy; config left to you)
#   --all              --redis --postgres --caddy
#   --no-build         skip the front-end build even if Node is present
#   --app-dir DIR      install location (default /opt/beacn)
#   --user NAME        service account (default beacn)
#   --domain HOST      write APP_URL / CORS_ORIGINS for this host on first run
#
set -euo pipefail

APP=beacn
APP_DIR=/opt/beacn
APP_USER=beacn
DO_REDIS=0 DO_PG=0 DO_CADDY=0 DO_BUILD=1 DOMAIN=""
PY_EXTRAS="server,redis,postgres"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m  %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m  %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root (sudo deploy/install.sh ...)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --redis) DO_REDIS=1;;
    --postgres) DO_PG=1;;
    --caddy) DO_CADDY=1;;
    --all) DO_REDIS=1; DO_PG=1; DO_CADDY=1;;
    --no-build) DO_BUILD=0;;
    --app-dir) APP_DIR="$2"; shift;;
    --user) APP_USER="$2"; shift;;
    --domain) DOMAIN="$2"; shift;;
    -h|--help) sed -n '2,40p' "$0"; exit 0;;
    *) die "unknown flag: $1";;
  esac
  shift
done

SRC="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
[[ -f "$SRC/pyproject.toml" && -d "$SRC/app" ]] || die "run this from the beacn checkout ($SRC looks wrong)"

# --------------------------------------------------------------------------
# package manager
# --------------------------------------------------------------------------
if   command -v apt-get >/dev/null; then PM=apt
elif command -v dnf     >/dev/null; then PM=dnf
else die "need apt-get or dnf"; fi

# A fresh Ubuntu box runs unattended-upgrades on boot and holds the dpkg lock
# for a few minutes. Wait it out rather than failing the install half way.
apt_wait() {
  [[ $PM == apt ]] || return 0
  local waited=0
  while fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock \
              /var/lib/apt/lists/lock /var/cache/apt/archives/lock >/dev/null 2>&1; do
    (( waited == 0 )) && log "Waiting for another apt/dpkg process (unattended-upgrades?) to release the lock…"
    waited=1; sleep 5
  done
}

pm_install() {
  case $PM in
    apt) apt_wait; DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@";;
    dnf) dnf install -y "$@";;
  esac
}

log "Installing base prerequisites"
if [[ $PM == apt ]]; then
  apt_wait; apt-get update -qq
  pm_install python3 python3-venv python3-dev build-essential git curl ca-certificates rsync openssl
else
  pm_install python3 python3-devel gcc gcc-c++ make git curl ca-certificates rsync openssl
fi
PYTHON="$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3)"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "Python >= 3.11 required, found $($PYTHON -V)"
log "Using $($PYTHON -V) at $PYTHON"

# uv builds the venv and installs the project — the same tool the sillo release
# workflows use. Installed system-wide so every account can reach it.
if command -v uv >/dev/null; then
  log "uv already installed ($(uv --version))"
else
  log "Installing uv into /usr/local/bin"
  curl -LsSf https://astral.sh/uv/install.sh \
    | env UV_INSTALL_DIR=/usr/local/bin INSTALLER_NO_MODIFY_PATH=1 sh
fi
UV="$(command -v uv || echo /usr/local/bin/uv)"
[[ -x "$UV" ]] || die "uv install failed"

# --------------------------------------------------------------------------
# Redis
# --------------------------------------------------------------------------
if [[ $DO_REDIS == 1 ]]; then
  if command -v redis-server >/dev/null; then
    log "Redis already installed"
  else
    log "Installing Redis"
    [[ $PM == apt ]] && pm_install redis-server || pm_install redis
  fi
  systemctl enable --now "$([[ $PM == apt ]] && echo redis-server || echo redis)"
fi

# --------------------------------------------------------------------------
# PostgreSQL
# --------------------------------------------------------------------------
if [[ $DO_PG == 1 ]]; then
  if command -v psql >/dev/null && systemctl list-unit-files | grep -q '^postgresql'; then
    log "PostgreSQL already installed"
  else
    log "Installing PostgreSQL"
    if [[ $PM == apt ]]; then
      pm_install postgresql
    else
      pm_install postgresql-server postgresql-contrib
      [[ -d /var/lib/pgsql/data/base ]] || postgresql-setup --initdb
    fi
  fi
  systemctl enable --now postgresql
  log "Ensuring the beacn role and database exist"
  # Set the password every run (CREATE if missing, else ALTER) so the URL this
  # script writes always matches the role — a re-run after a failed first run
  # must not leave them out of sync.
  DB_PASS="$(openssl rand -hex 16)"
  sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'beacn') THEN
    ALTER ROLE beacn LOGIN PASSWORD '${DB_PASS}';
  ELSE
    CREATE ROLE beacn LOGIN PASSWORD '${DB_PASS}';
  END IF;
END \$\$;
SQL
  sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='beacn'" | grep -q 1 \
    || sudo -u postgres createdb -O beacn beacn
  NEW_DATABASE_URL="postgres://beacn:${DB_PASS}@127.0.0.1:5432/beacn"
fi

# --------------------------------------------------------------------------
# Caddy (optional)
# --------------------------------------------------------------------------
if [[ $DO_CADDY == 1 ]]; then
  if command -v caddy >/dev/null; then
    log "Caddy already installed"
  else
    log "Installing Caddy"
    if [[ $PM == apt ]]; then
      pm_install debian-keyring debian-archive-keyring apt-transport-https
      curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
      curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' > /etc/apt/sources.list.d/caddy-stable.list
      apt_wait; apt-get update -qq && pm_install caddy
    else
      dnf install -y 'dnf-command(copr)' && dnf copr enable -y @caddy/caddy && pm_install caddy
    fi
  fi
  systemctl enable --now caddy
  log "A reverse-proxy template is at deploy/Caddyfile.example"
fi

# --------------------------------------------------------------------------
# service user + directories
# --------------------------------------------------------------------------
if ! id "$APP_USER" >/dev/null 2>&1; then
  log "Creating system user $APP_USER"
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
mkdir -p "$APP_DIR" "/etc/$APP" "$APP_DIR/storage"

# --------------------------------------------------------------------------
# sync code
# --------------------------------------------------------------------------
log "Syncing $SRC -> $APP_DIR"
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '.cache' --exclude 'node_modules' \
  --exclude 'storage/*.db*' --exclude 'examples/keys.json' --exclude '__pycache__' \
  "$SRC"/ "$APP_DIR"/
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR/.cache"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# --------------------------------------------------------------------------
# venv (uv)
# --------------------------------------------------------------------------
log "Building the virtualenv with uv and installing beacn[$PY_EXTRAS]"
# Run uv *from inside $APP_DIR*. sudo inherits the caller's cwd, which is the
# invoking user's checkout (e.g. /home/ubuntu/beacn) — a directory the service
# account cannot read, so uv's config walk-up fails with
# "Permission denied opening uv.toml". Changing into /opt/beacn (owned by the
# service account) avoids it entirely.
run_uv() {
  sudo -u "$APP_USER" env HOME="$APP_DIR" UV_CACHE_DIR="$APP_DIR/.cache/uv" \
    sh -c 'cd "$1" && shift && exec "$@"' _ "$APP_DIR" "$UV" "$@"
}
run_uv venv --python "$PYTHON" "$APP_DIR/.venv"
run_uv pip install --python "$APP_DIR/.venv/bin/python" --prerelease=allow -e ".[$PY_EXTRAS]"

# --------------------------------------------------------------------------
# front end
# --------------------------------------------------------------------------
if [[ $DO_BUILD == 1 ]] && command -v npm >/dev/null; then
  log "Building the front end (npm ci && npm run build)"
  ( cd "$APP_DIR" && sudo -u "$APP_USER" npm ci --silent && sudo -u "$APP_USER" npm run build --silent )
elif [[ ! -f "$APP_DIR/static/build/.vite/manifest.json" ]]; then
  warn "No front-end build present and Node is unavailable."
  warn "Install Node and re-run, or build static/build/ on another host and copy it in."
  warn "Until then the dashboard HTML loads but has no JavaScript."
fi

# --------------------------------------------------------------------------
# env file
# --------------------------------------------------------------------------
ENV_FILE="/etc/$APP/$APP.env"
if [[ -f "$ENV_FILE" ]]; then
  log "Keeping existing $ENV_FILE"
  # ...but if --postgres just rotated the local DB password, keep the URL in sync.
  [[ -n "${NEW_DATABASE_URL:-}" ]] && sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${NEW_DATABASE_URL}|" "$ENV_FILE"
else
  log "Writing $ENV_FILE (first run)"
  install -m 0640 -o root -g "$APP_USER" "$APP_DIR/deploy/$APP.env.example" "$ENV_FILE"
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -hex 32)|" "$ENV_FILE"
  [[ -n "${NEW_DATABASE_URL:-}" ]] && sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${NEW_DATABASE_URL}|" "$ENV_FILE"
  [[ $DO_REDIS == 0 ]] && sed -i "s|^BEACN_BUS=redis|BEACN_BUS=memory|;s|^QUEUE_BACKEND=redis|QUEUE_BACKEND=memory|" "$ENV_FILE"
  if [[ -n "$DOMAIN" ]]; then
    sed -i "s|^APP_URL=.*|APP_URL=https://$DOMAIN|;s|^CORS_ORIGINS=.*|CORS_ORIGINS=https://$DOMAIN|" "$ENV_FILE"
  fi
fi
chmod 0640 "$ENV_FILE"; chown root:"$APP_USER" "$ENV_FILE"

# --------------------------------------------------------------------------
# systemd
# --------------------------------------------------------------------------
log "Installing systemd units"
for u in "$APP_DIR"/deploy/systemd/*; do
  install -m 0644 "$u" "/etc/systemd/system/$(basename "$u")"
done
# rewrite the hard-coded paths/user if this install is non-default
if [[ "$APP_DIR" != /opt/beacn || "$APP_USER" != beacn ]]; then
  sed -i "s|/opt/beacn|$APP_DIR|g; s|^User=beacn|User=$APP_USER|; s|^Group=beacn|Group=$APP_USER|; s|beacn:beacn|$APP_USER:$APP_USER|" \
    /etc/systemd/system/beacn-*.service
fi
systemctl daemon-reload

log "Running database migrations"
systemctl restart beacn-migrate.service

log "Starting the web tier and the maintenance timer"
systemctl enable --now beacn-web.service beacn-work.timer
systemctl restart beacn-web.service

# --------------------------------------------------------------------------
# done
# --------------------------------------------------------------------------
cat <<DONE

$(printf '\033[1;32m✔  BEACN is installed.\033[0m')

  status   : systemctl status beacn-web
  logs     : journalctl -u beacn-web -f
  config   : $ENV_FILE
  health   : curl -s http://127.0.0.1:$(grep -oP '^BEACN_PORT=\K.*' "$ENV_FILE")/health

Next:

  1. Create the first operator:
       sudo -u $APP_USER $APP_DIR/.venv/bin/beacn user create you@example.com --role Admin --admin

  2. Put it behind TLS — see $APP_DIR/deploy/Caddyfile.example (or your proxy).

  3. Register a producer + issue an API key in the dashboard, then publish:
       curl -XPOST https://<host>/api/v1/events -H "Authorization: Bearer bk_..." \\
            -d '{"event":"deployment.completed","topic":"deployments","data":{}}'

To upgrade later: git pull in this checkout, then re-run this script.
DONE
