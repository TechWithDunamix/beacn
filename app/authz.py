"""Control-plane RBAC.

Roles are `sillo.permissions.Group` rows; permissions are
`sillo.permissions.Permission` rows. `ensure_roles()` (called from a startup
hook) creates the catalogue and the four default roles idempotently.

`is_superuser` is the Owner escape hatch and is checked first, so the account
that bootstrapped the installation can never lock itself out.
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = ["CATALOGUE", "ROLES", "PermissionDenied", "ensure_roles", "require", "permissions_of"]


class PermissionDenied(Exception):
    def __init__(self, permission: str) -> None:
        super().__init__(f"missing permission: {permission}")
        self.permission = permission


#: permission -> human description
CATALOGUE: dict[str, str] = {
    "events.read": "View the event store and event detail",
    "events.publish": "Publish events through the control plane",
    "events.replay": "Replay events to consumers",
    "topics.read": "View topics and their configuration",
    "topics.write": "Create and reconfigure topics and their access policy",
    "producers.read": "View the producer registry",
    "producers.write": "Register and disable producers",
    "apikeys.read": "View API keys (never their secrets)",
    "apikeys.write": "Issue, rotate and revoke API keys",
    "connections.read": "View realtime connections",
    "connections.write": "Terminate realtime connections",
    "tasks.read": "View observed tasks",
    "notifications.read": "View notification activity",
    "subscriptions.read": "View durable subscriptions",
    "subscriptions.write": "Create and remove durable subscriptions",
    "audit.read": "View the audit log",
    "users.read": "View operators and roles",
    "users.write": "Manage operators and role assignments",
    "settings.read": "View system configuration and health",
}

_READ_ONLY = [p for p in CATALOGUE if p.endswith(".read")]
_DEVELOPER = _READ_ONLY + ["events.publish", "events.replay", "subscriptions.write"]
_OPERATOR = _DEVELOPER + [
    "topics.write",
    "producers.write",
    "apikeys.write",
    "connections.write",
]

ROLES: dict[str, tuple[str, list[str]]] = {
    "Admin": ("Full control of BEACN, including operators and roles.", list(CATALOGUE)),
    "Operator": ("Runs the platform: topics, producers, keys, connections.", _OPERATOR),
    "Developer": ("Publishes and replays events; reads everything.", _DEVELOPER),
    "ReadOnly": ("Read-only access to every screen.", _READ_ONLY),
}


async def ensure_roles() -> None:
    """Create the catalogue and the default roles. Idempotent; run on every boot.

    Adds permissions to a role but never removes them, so an installation that
    deliberately narrowed a role keeps that across upgrades — except Admin,
    which always converges on the full catalogue so no permission is unreachable.
    """
    from sillo.permissions import Group, Permission

    for name, description in CATALOGUE.items():
        await Permission.define(name, description)

    for role_name, (description, perms) in ROLES.items():
        role = await Group.get_or_create(role_name, description)
        held = set(await role.get_permissions())
        missing = [p for p in perms if p not in held]
        if missing and (role_name == "Admin" or not held):
            await role.add_permissions(*missing)


async def permissions_of(user) -> set[str]:
    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    if getattr(user, "is_superuser", False):
        return set(CATALOGUE)
    try:
        return set(await user.load_permissions())
    except Exception:  # noqa: BLE001
        return set()


async def role_names_of(user) -> list[str]:
    try:
        return sorted(await user.get_groups())
    except Exception:  # noqa: BLE001
        return []


async def require(user, *permissions: str) -> None:
    if user is None:
        raise PermissionDenied(permissions[0] if permissions else "authenticated")
    if getattr(user, "is_superuser", False):
        return
    held = await permissions_of(user)
    for permission in permissions:
        if permission not in held:
            raise PermissionDenied(permission)


def any_of(held: Iterable[str], *permissions: str) -> bool:
    held = set(held)
    return any(p in held for p in permissions)
