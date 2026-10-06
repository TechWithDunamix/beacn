# Every task this project needs, discoverable with `make` on its own.
#
# Assumes an ACTIVE virtual environment (python -m venv .venv && source
# .venv/bin/activate): every target runs against that environment's python,
# pip and console scripts — never the system interpreter. The commands are
# plain pip/uvicorn/beacn invocations rather than anything bespoke, so you can
# always read what a target does and run it by hand when you need to vary it.

.DEFAULT_GOAL := help
.PHONY: help check-venv env install build setup deploy migrate work doctor \
        admin login cli dev frontend-dev serve test lint format check clean

# uv-managed venvs (what deploy/install.sh and `uv venv` create) have no pip
# inside them — prefer uv when it is on PATH, fall back to python -m pip.
PY  := python
PIP := $(shell command -v uv >/dev/null 2>&1 && echo "uv pip install --python python" || echo "python -m pip install")
CLI     := beacn
APP     := app.main:app
HOST    ?= 127.0.0.1
PORT    ?= 8000
WORKERS ?= 1
# bun when present (what deploy/install.sh uses), npm otherwise.
NODE    := $(shell command -v bun 2>/dev/null || command -v npm 2>/dev/null)

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# -- guard ----------------------------------------------------------------

check-venv:  ## Fail unless a virtual environment is active
	@test -n "$$VIRTUAL_ENV" || { \
	  echo "  no active virtual environment."; \
	  echo "  run: python -m venv .venv && source .venv/bin/activate"; \
	  exit 1; }

# -- setup ----------------------------------------------------------------

env: check-venv  ## Create .env from .env.example, filling in a fresh SECRET_KEY
	@test -f .env || cp .env.example .env
	@$(PY) -c "import pathlib,re,secrets; p=pathlib.Path('.env'); t=p.read_text(); p.write_text(re.sub(r'^SECRET_KEY=$$|^SECRET_KEY=change-me.*$$', 'SECRET_KEY='+secrets.token_hex(32), t, flags=re.M))" \
	  && echo "  .env ready (SECRET_KEY filled in only if it was still empty or a placeholder)"

# `.[server,redis,postgres]` is what deploy/install.sh and the docs install;
# [dev] adds the test and lint tools. The runtime packages are also core deps,
# so a bare install still boots.
install: check-venv  ## Install Python packages and front-end dependencies
	$(PIP) -e '.[server,redis,postgres,dev]'
	@test -n "$(NODE)" || { echo "  need bun or npm on PATH for the front end"; exit 1; }
	$(NODE) install

build:  ## Build the front end into static/build
	@test -n "$(NODE)" || { echo "  need bun or npm on PATH for the front end"; exit 1; }
	$(NODE) run build

setup: env install build migrate  ## Everything except running: .env, packages, front end, database

deploy: check-venv setup  ## Install everything, build, migrate — then deploy the app
	# The foreground command is inlined rather than `$(MAKE) serve` because make
	# executes $(MAKE) lines even under `-n` — a dry run would really restart
	# systemd on a production host.
	@if command -v systemctl >/dev/null 2>&1 \
	   && systemctl list-unit-files 2>/dev/null | grep -q '^beacn-web\.service'; then \
	  echo "==> restarting the beacn systemd units"; \
	  sudo systemctl restart beacn.target; \
	  echo "==> deployed. health: curl -s http://127.0.0.1:$(PORT)/health"; \
	else \
	  echo "==> no beacn systemd units installed — running in the foreground"; \
	  echo "==> maintenance jobs: run 'make work' every few minutes (deploy/install.sh installs them as a timer)"; \
	  uvicorn $(APP) --host $(HOST) --port $(PORT) --workers $(WORKERS); \
	fi

# -- database & operations -----------------------------------------------

migrate:  ## Create tables and seed the RBAC catalogue
	$(CLI) migrate

work:  ## One round of maintenance jobs (retention, counters, reaping)
	$(CLI) work

doctor:  ## Check configuration, database and bus
	$(CLI) doctor

admin:  ## Create the first operator. make admin e=you@example.com
	@test -n "$(e)" || (echo "  usage: make admin e=you@example.com"; exit 1)
	$(CLI) user create $(e) --role Admin --admin

login:  ## Log the CLI in against a running server
	$(CLI) login

cli:  ## Any CLI command: make cli ARGS="key list"
	$(CLI) $(ARGS)

# -- running -------------------------------------------------------------

dev:  ## Reloadable server; run `npm run dev` alongside it (Vite, VITE_DEV=true)
	$(CLI) serve --reload --host 127.0.0.1 --port $(PORT)

frontend-dev:  ## Vite dev server with hot reload
	$(NODE) run dev

serve:  ## Run in the foreground as production would (HOST/PORT/WORKERS overridable)
	uvicorn $(APP) --host $(HOST) --port $(PORT) --workers $(WORKERS)

# -- quality -------------------------------------------------------------

test:  ## Run the test suite
	pytest -q

lint:  ## Check style and lint rules
	ruff check .

format:  ## Apply formatting and fixable lint rules
	ruff format .
	ruff check --fix .

check: lint test  ## Everything CI runs

clean:  ## Remove caches and build artefacts (static/build is kept — it is what production serves)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache dist build *.egg-info
