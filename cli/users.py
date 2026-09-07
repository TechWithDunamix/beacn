"""BEACN operator accounts, on the framework's own command design.

`sillo.users.commands` ships the account operations as plain async functions —
`create_user`, `create_admin`, `find_user`, `set_password`, `set_active`,
`list_users` — written, in the framework's words, "so that a project's own
tooling can call them without going through a process boundary". BEACN does
exactly that: these commands reuse those functions against BEACN's own `User`
model and add the one thing the framework has no opinion about — assigning a
control-plane **role** (a `sillo.permissions` group).

Namespaced `beacn user <verb>` to match the rest of the CLI (`producer create`,
`key create`), rather than the framework's `user:create` colon form.
"""

from __future__ import annotations

from sillo.console import Argument, Flag, Option
from sillo.users import commands as accounts

from app.authz import ROLES
from cli.client import CliError
from cli.commands import LocalCommand

__all__ = ["USER_COMMANDS"]

ROLE_NAMES = list(ROLES)  # Admin, Operator, Developer, ReadOnly


def _norm_email(raw: str) -> str:
    email = (raw or "").strip().lower()
    if "@" not in email:
        raise CliError("A valid email address is required.")
    return email


async def _assign_role(user, role: str) -> None:
    from sillo.permissions import Group

    group = await Group.get_or_none(name=role)
    if group is None:
        raise CliError(f"No such role {role!r}. One of: {', '.join(ROLE_NAMES)}")
    for existing in await Group.of_user(user):
        await existing.remove_user(user)
    await group.add_user(user)


class UserCreate(LocalCommand):
    name = "user create"
    help = "Create an operator account and assign it a role."
    arguments = [
        Argument("email", help="Email address (also used as the username)."),
        Option("role", default="ReadOnly", choices=ROLE_NAMES, help="Control-plane role."),
        Flag("admin", help="Also mark the account a superuser (the Owner escape hatch)."),
        Flag("json"),
    ]

    async def run_async(self) -> int:
        from app.authz import ensure_roles

        await ensure_roles()
        email = _norm_email(self.argument("email"))
        role = self.option("role")
        if role not in ROLE_NAMES:
            raise CliError(f"role must be one of: {', '.join(ROLE_NAMES)}")

        password = self.read_password()
        # `create_admin` runs the framework password policy; `create_user` is
        # lenient by design (invite/SSO flows). A control-plane login is neither,
        # so hold the ordinary path to a floor too.
        if not self.flag("admin") and len(password) < 10:
            raise CliError("Password must be at least 10 characters.")
        create = accounts.create_admin if self.flag("admin") else accounts.create_user
        try:
            from database.models import User

            user = await create(email, email, password, model=User)
        except ValueError as error:
            # The framework names the rule that failed — a taken address, or
            # which part of the password policy. Its wording beats a guess.
            raise CliError(str(error)) from error

        await _assign_role(user, role)

        if self.json_out:
            self.emit({"id": user.pk, "email": user.email, "role": role,
                       "superuser": bool(getattr(user, "is_superuser", False))})
        else:
            self.success(f"Created {user.email} as {role}"
                         + (" (superuser)" if self.flag("admin") else "") + ".")
            self.muted("  Sign in at /login")
        return 0


class UserList(LocalCommand):
    name = "user list"
    help = "List operator accounts, newest first."
    arguments = [
        Option("limit", type=int, default=50, short="l", help="Maximum rows."),
        Flag("json"),
    ]

    async def run_async(self) -> int:
        from database.models import User

        users = await accounts.list_users(model=User, limit=self.option("limit"))
        rows = []
        for user in users:
            roles = sorted(await user.get_groups())
            rows.append({
                "id": user.pk, "email": user.email,
                "roles": roles,
                "superuser": bool(getattr(user, "is_superuser", False)),
                "active": bool(getattr(user, "is_active", True)),
            })
        if self.json_out:
            self.emit(rows)
            return 0
        if not rows:
            self.muted("No operators yet. Create one with: beacn user create <email> --role Admin")
            return 0
        self.table(
            ["id", "email", "roles", "superuser", "active"],
            [[r["id"], r["email"], ", ".join(r["roles"]) or "—",
              "yes" if r["superuser"] else "", "yes" if r["active"] else "no"] for r in rows],
            align=["right", "left", "left", "center", "center"],
        )
        return 0


class UserShow(LocalCommand):
    name = "user show"
    help = "Show one operator's roles and permissions."
    arguments = [Argument("identifier", help="Email address."), Flag("json")]

    async def run_async(self) -> int:
        from app.authz import permissions_of
        from database.models import User

        user = await accounts.find_user(self.argument("identifier"), model=User)
        if user is None:
            raise CliError(f"No user matches {self.argument('identifier')!r}.")
        roles = sorted(await user.get_groups())
        perms = sorted(await permissions_of(user))
        if self.json_out:
            self.emit({"id": user.pk, "email": user.email, "active": user.is_active,
                       "superuser": user.is_superuser, "roles": roles, "permissions": perms})
            return 0
        self.pairs([
            ("id", user.pk), ("email", user.email),
            ("active", "yes" if user.is_active else "no"),
            ("superuser", "yes" if user.is_superuser else "no"),
            ("roles", ", ".join(roles) or "—"),
        ])
        self.blank()
        self.muted(f"  {len(perms)} permission(s): {', '.join(perms) or '—'}")
        return 0


class UserPassword(LocalCommand):
    name = "user password"
    help = "Change an operator's password."
    arguments = [Argument("identifier", help="Email address."), Flag("json")]

    async def run_async(self) -> int:
        from database.models import User

        password = self.read_password("New password")
        try:
            await accounts.set_password(self.argument("identifier"), password, model=User)
        except (LookupError, ValueError) as error:
            raise CliError(str(error)) from error
        self.success("Password changed.")
        return 0


class _SetActive(LocalCommand):
    _active = True

    async def run_async(self) -> int:
        from database.models import User

        try:
            user = await accounts.set_active(self.argument("identifier"), self._active, model=User)
        except LookupError as error:
            raise CliError(str(error)) from error
        self.success(f"{user.email} is now {'active' if self._active else 'disabled'}.")
        return 0


class UserDisable(_SetActive):
    name = "user disable"
    help = "Disable an operator account (reversible; credentials stop working)."
    _active = False
    arguments = [Argument("identifier", help="Email address."), Flag("json")]


class UserEnable(_SetActive):
    name = "user enable"
    help = "Re-enable a disabled operator account."
    _active = True
    arguments = [Argument("identifier", help="Email address."), Flag("json")]


class UserRole(LocalCommand):
    name = "user role"
    help = "Set an operator's control-plane role (replaces any existing role)."
    arguments = [
        Argument("identifier", help="Email address."),
        Argument("role", help=f"One of: {', '.join(ROLE_NAMES)}"),
        Flag("json"),
    ]

    async def run_async(self) -> int:
        from app.authz import ensure_roles
        from database.models import User

        await ensure_roles()
        user = await accounts.find_user(self.argument("identifier"), model=User)
        if user is None:
            raise CliError(f"No user matches {self.argument('identifier')!r}.")
        role = self.argument("role")
        await _assign_role(user, role)
        if self.json_out:
            self.emit({"email": user.email, "role": role})
        else:
            self.success(f"{user.email} is now {role}.")
        return 0


USER_COMMANDS = (
    UserCreate, UserList, UserShow, UserPassword, UserDisable, UserEnable, UserRole,
)
