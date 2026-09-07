"""The Inertia adapter, configured once.

Route modules call the module-level `render` from `sillo_inertia`, which finds
this adapter through the middleware handling the request — so `routes/` never
imports back into `app/`.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sillo.core.http import HttpContext
from sillo_inertia import Inertia, always, vite_react

from app.authz import permissions_of, role_names_of
from app.config import BASE_DIR, ENVIRONMENTS, config

BUILD_DIR = BASE_DIR / "static" / "build"
MANIFEST = BUILD_DIR / ".vite" / "manifest.json"
ENTRY = "js/main.tsx"
ROOT_VIEW = BASE_DIR / "resources" / "views" / "app.html"


def asset_version() -> str | None:
    if config.vite_dev or not MANIFEST.is_file():
        return None
    return hashlib.sha256(MANIFEST.read_bytes()).hexdigest()[:12]


def build_inertia() -> Inertia:
    return Inertia(
        root_view=ROOT_VIEW,
        base_dir=BASE_DIR,
        version=asset_version,
        root_id="app",
        vite=vite_react(
            entry=ENTRY,
            dev=config.vite_dev,
            dev_server=config.vite_dev_server,
            manifest_path=MANIFEST,
            asset_prefix="/assets/",
        ),
    )


def _safe_user(ctx: HttpContext) -> Any | None:
    try:
        user = ctx.user
    except Exception:  # noqa: BLE001
        return None
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return user


async def _auth_prop(ctx: HttpContext) -> dict[str, Any]:
    user = _safe_user(ctx)
    if user is None:
        return {"user": None, "permissions": [], "roles": []}
    return {
        "user": {
            "id": user.pk,
            "name": user.name,
            "email": user.email,
            "title": getattr(user, "title", None),
            "is_superuser": bool(getattr(user, "is_superuser", False)),
        },
        "permissions": sorted(await permissions_of(user)),
        "roles": await role_names_of(user),
    }


def share_globals(inertia: Inertia) -> None:
    inertia.view_data["title"] = config.app_name
    inertia.share(
        auth=always(_auth_prop),
        app=always(
            lambda _: {
                "name": config.app_name,
                "env": config.app_env,
                "environments": list(ENVIRONMENTS),
                "bus": config.bus_backend,
            }
        ),
    )
