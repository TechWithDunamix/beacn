"""Control-plane accounts: who operates this BEACN installation.

Single-tenant control plane — one installation, one team, authorization is
global rather than org-scoped. Roles are `sillo.permissions.Group` rows and
permissions are `sillo.permissions.Permission` rows; the catalogue and the
bootstrap live in `app/authz.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sillo.permissions import PermissionMixin
from sillo.record import Model
from sillo.record.fields import PasswordField
from sillo.users import UserBaseModel, UserManager
from tortoise import fields

__all__ = ["LoginEvent", "User", "UserSession"]


class User(UserBaseModel, PermissionMixin):
    """An operator. `is_superuser` is the Owner escape hatch, checked first."""

    objects = UserManager()

    password = PasswordField()
    full_name = fields.CharField(max_length=150, null=True)
    title = fields.CharField(max_length=120, null=True)
    timezone_name = fields.CharField(max_length=64, default="UTC")

    disabled_at = fields.DatetimeField(null=True, default=None)
    disabled_reason = fields.CharField(max_length=255, null=True)

    class Meta:
        table = "users"

    def __str__(self) -> str:
        return self.email

    @property
    def name(self) -> str:
        return self.full_name or self.email.split("@")[0]

    async def disable(self, reason: str = "") -> None:
        self.is_active = False
        self.disabled_at = datetime.now(UTC)
        self.disabled_reason = reason or None
        await self.save()
        await UserSession.filter(user_id=self.pk, revoked_at=None).update(
            revoked_at=datetime.now(UTC), revoked_reason="account disabled"
        )

    async def enable(self) -> None:
        self.is_active = True
        self.disabled_at = None
        self.disabled_reason = None
        await self.save()


# Tortoise does not run `UserManager.contribute_to_class` for a plain manager
# attribute the way Django does, so `User.objects.model` stays `None` and every
# `objects.*` call falls back to the framework's own unregistered `User`. Bind
# it by hand — this is what lets `sillo.users.commands` operate on BEACN's model.
User.objects.model = User


class UserSession(Model):
    """A signed-in browser or CLI token. The session key is stored SHA-256 hashed."""

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="sessions", on_delete=fields.CASCADE)
    key_hash = fields.CharField(max_length=64, unique=True, index=True)
    kind = fields.CharField(max_length=16, default="web")  # web | cli
    ip = fields.CharField(max_length=64, null=True)
    user_agent = fields.CharField(max_length=400, null=True)
    label = fields.CharField(max_length=120, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_seen_at = fields.DatetimeField(null=True)
    expires_at = fields.DatetimeField(null=True)
    revoked_at = fields.DatetimeField(null=True, default=None)
    revoked_reason = fields.CharField(max_length=120, null=True)

    class Meta:
        table = "user_sessions"
        indexes = (("user_id", "revoked_at"),)

    @property
    def is_live(self) -> bool:
        if self.revoked_at is not None:
            return False
        if self.expires_at is not None and self.expires_at <= datetime.now(UTC):
            return False
        return True


class LoginEvent(Model):
    """Every sign-in attempt, successful or not."""

    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="login_events", null=True, on_delete=fields.SET_NULL
    )
    email = fields.CharField(max_length=255, index=True)
    successful = fields.BooleanField(default=False)
    reason = fields.CharField(max_length=40, default="ok")
    kind = fields.CharField(max_length=16, default="web")
    ip = fields.CharField(max_length=64, null=True)
    user_agent = fields.CharField(max_length=400, null=True)
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "login_events"
        indexes = (("successful", "created_at"),)
