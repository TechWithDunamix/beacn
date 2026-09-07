"""CLI smoke tests — run as subprocesses with their own temp database."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _run(args, env_extra=None, input_text=None):
    import os

    env = dict(os.environ)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-m", "cli", *args],
        cwd=str(REPO), env=env, capture_output=True, text=True, input=input_text, timeout=60,
    )


@pytest.fixture
def db_env(tmp_path):
    return {
        "DATABASE_URL": f"sqlite://{tmp_path / 'cli.db'}",
        "DB_GENERATE_SCHEMAS": "true",
        "SECRET_KEY": "cli-test-secret-key",
        "APP_ENV": "local",
        "BEACN_HOME": str(tmp_path / "home"),
    }


def test_help_lists_command_groups():
    r = _run(["--help"])
    assert r.returncode == 0
    for expected in ("events publish", "key create", "producer create", "doctor", "serve"):
        assert expected in r.stdout


def test_doctor_reports_healthy(db_env):
    r = _run(["doctor"], db_env)
    assert r.returncode == 0
    assert "database: ok" in r.stdout
    assert "backend': 'memory'" in r.stdout or "'memory'" in r.stdout


def test_user_lifecycle_via_cli(db_env):
    assert _run(["migrate"], db_env).returncode == 0
    pw = {**db_env, "BEACN_PASSWORD": "Str0ng!password"}

    admin = _run(["user", "create", "boss@example.com", "--role", "Admin", "--admin"], pw)
    assert admin.returncode == 0, admin.stdout + admin.stderr
    assert "boss@example.com as Admin" in admin.stdout

    dev = _run(["user", "create", "dev@example.com", "--role", "Developer"], pw)
    assert dev.returncode == 0
    assert "as Developer" in dev.stdout

    listed = _run(["user", "list"], db_env)
    assert "boss@example.com" in listed.stdout and "dev@example.com" in listed.stdout
    assert "Admin" in listed.stdout and "Developer" in listed.stdout

    role = _run(["user", "role", "dev@example.com", "Operator"], db_env)
    assert role.returncode == 0
    assert "now Operator" in role.stdout

    dupe = _run(["user", "create", "boss@example.com", "--role", "ReadOnly"], pw)
    assert dupe.returncode == 1
    assert "already registered" in dupe.stdout


def test_user_create_without_password_env_refuses(db_env):
    assert _run(["migrate"], db_env).returncode == 0
    # No terminal (subprocess) and no BEACN_PASSWORD -> a clear refusal, not a hang.
    r = _run(["user", "create", "x@example.com", "--role", "ReadOnly"], db_env)
    assert r.returncode == 1
    assert "BEACN_PASSWORD" in (r.stdout + r.stderr)


def test_events_publish_needs_api_key(db_env):
    r = _run(["events", "publish", "a.b"], db_env)
    assert r.returncode == 1
    assert "BEACN_API_KEY" in r.stdout


def test_login_required_for_producer_list(db_env):
    r = _run(["producer", "list"], db_env)
    assert r.returncode == 1
    assert "beacn login" in r.stdout


def test_user_password_reset_via_cli(db_env):
    assert _run(["migrate"], db_env).returncode == 0
    pw = {**db_env, "BEACN_PASSWORD": "Str0ng!password"}
    assert _run(["user", "create", "boss@example.com", "--role", "Admin", "--admin"], pw).returncode == 0

    # --password: explicit, no prompt.
    r = _run(["user", "password", "boss@example.com", "--password", "An0ther!Secret"], db_env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Password changed" in r.stdout

    # --generate: prints a fresh password once.
    r = _run(["user", "password", "boss@example.com", "--generate"], db_env)
    assert r.returncode == 0
    assert "New password:" in r.stdout

    # too short is rejected.
    r = _run(["user", "password", "boss@example.com", "--password", "short"], db_env)
    assert r.returncode == 1
    assert "at least 10" in (r.stdout + r.stderr)

    # unknown account is a clean error.
    r = _run(["user", "password", "nobody@example.com", "--password", "An0ther!Secret"], db_env)
    assert r.returncode == 1
