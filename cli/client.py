"""The CLI's HTTP client and credential store.

Administrative commands go over HTTP through `/api/control` and `/api/v1`, not
the database directly: authorization is enforced once, server-side, and a CLI
with its own DB connection would be a second unguarded path to every operation.
The exceptions — `serve`, `migrate`, `doctor`, `admin create` — are local by
necessity and cannot be done through any authenticated route.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import httpx

__all__ = ["ApiClient", "CliError", "clear_token", "load_token", "save_token"]


class CliError(Exception):
    """A failure with a message already fit to print."""


def _home() -> Path:
    override = os.getenv("BEACN_HOME")
    return Path(override) if override else Path(os.path.expanduser("~")) / ".config" / "beacn"


def _token_path() -> Path:
    return _home() / "credentials.json"


def save_token(url: str, token: str, email: str) -> Path:
    path = _token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, stat.S_IRWXU)
    path.write_text(json.dumps({"url": url.rstrip("/"), "token": token, "email": email}, indent=2))
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def load_token() -> dict[str, str] | None:
    path = _token_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    return data if data.get("token") else None


def clear_token() -> bool:
    path = _token_path()
    if path.is_file():
        path.unlink()
        return True
    return False


class ApiClient:
    def __init__(self, *, require_auth: bool = True) -> None:
        self.base_url = os.getenv("BEACN_URL", "http://localhost:8000").rstrip("/")
        creds = load_token()
        self.token = None
        if creds:
            self.base_url = creds.get("url", self.base_url)
            self.token = creds.get("token")
        env_token = os.getenv("BEACN_TOKEN")
        if env_token:
            self.token = env_token
        if require_auth and not self.token:
            raise CliError("Authentication required.\nRun: beacn login")

    def _headers(self) -> dict:
        h = {"X-BEACN-Control": "1"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def request(self, method: str, path: str, *, json_body: Any = None, params: dict | None = None) -> Any:
        url = self.base_url + path
        try:
            resp = httpx.request(
                method, url, json=json_body, params=params, headers=self._headers(), timeout=30.0
            )
        except httpx.HTTPError as exc:
            raise CliError(f"cannot reach BEACN at {self.base_url}: {exc}") from exc
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", {})
            except ValueError:
                err = {}
            raise CliError(err.get("message") or f"HTTP {resp.status_code}: {resp.text[:200]}")
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)
