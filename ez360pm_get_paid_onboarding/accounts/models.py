from __future__ import annotations

import re

from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models
from django.utils import timezone


def _suggest_username(email: str) -> str:
    """Generate a stable, DB-safe username from an email.

    EZ360PM is email-first. We keep the underlying AbstractUser.username field
    only for compatibility (admin, contrib assumptions), but we never prompt
    for it in the UI.
    """

    email = (email or "").strip().lower()
    local = email.split("@", 1)[0] if "@" in email else email
    local = re.sub(r"[^a-z0-9_\.-]+", "_", local)
    local = local.strip("._-") or "user"
    return local[:140]


class UserManager(DjangoUserManager):
    """User manager that does not require a username input."""

    def _ensure_username(self, email: str, username: str | None = None) -> str:
        base = (username or "").strip() or _suggest_username(email)
        candidate = base
        i = 0
        while self.model.objects.filter(username__iexact=candidate).exists():
            i += 1
            suffix = f"_{i}"
            candidate = f"{base[: (150 - len(suffix))]}{suffix}"
        return candidate

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        username = extra_fields.pop("username", None)
        extra_fields["username"] = self._ensure_username(email, username)
        return super().create_user(email=email, password=password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email=email, password=password, **extra_fields)


class User(AbstractUser):
    """Custom user model.

    - Authentication uses email as the username field.
    - We do NOT prompt for a username anywhere in the app UI.
      The underlying `username` field exists for compatibility with
      AbstractUser/admin and is auto-populated from email.
    """

    email = models.EmailField(unique=True)

    objects = UserManager()

    # Email verification (Pack P)
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    def mark_email_verified(self):
        if not self.email_verified:
            self.email_verified = True
            self.email_verified_at = timezone.now()
            self.save(update_fields=["email_verified", "email_verified_at"])

    def __str__(self) -> str:  # pragma: no cover
        return self.email


class TwoFactorSettings(models.Model):
    """Per-user 2FA (TOTP) settings.

    We implement RFC6238-compatible TOTP without external deps.
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="two_factor")
    secret = models.CharField(max_length=64, blank=True, default="")  # base32, no padding
    is_enabled = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_used(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])

    def __str__(self) -> str:  # pragma: no cover
        return f"2FA for {self.user_id} ({'enabled' if self.is_enabled else 'disabled'})"


class LoginEvent(models.Model):
    """Simple login success audit trail for a user.

    Stores successful authentication events for user-visible security history.
    """

    METHOD_PASSWORD = "password"
    METHOD_2FA = "2fa"
    METHOD_CHOICES = (
        (METHOD_PASSWORD, "Password"),
        (METHOD_2FA, "2FA"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_events")
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=METHOD_PASSWORD)

    ip_address = models.CharField(max_length=64, blank=True, default="")
    user_agent = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Login {self.user_id} via {self.method} at {self.created_at:%Y-%m-%d %H:%M}"



class AccountLockout(models.Model):
    """Account-based login failure tracker + lockout.

    Identifier is a normalized string (typically email).
    """

    identifier = models.CharField(max_length=254, unique=True)
    failed_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_failed_at = models.DateTimeField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def is_locked(self) -> bool:
        if not self.locked_until:
            return False
        return timezone.now() < self.locked_until

    def clear(self):
        self.failed_count = 0
        self.locked_until = None
        self.last_failed_at = None
        self.save(update_fields=["failed_count", "locked_until", "last_failed_at", "updated_at"])

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.identifier} ({self.failed_count})"
