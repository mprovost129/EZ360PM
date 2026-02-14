from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Custom user model.

    - Public usernames are required and unique.
    - Email is also unique.
    - Authentication uses email as the username field.
    """

    email = models.EmailField(unique=True)

    # Email verification (Pack P)
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]  # username remains the public handle

    def mark_email_verified(self):
        if not self.email_verified:
            self.email_verified = True
            self.email_verified_at = timezone.now()
            self.save(update_fields=["email_verified", "email_verified_at"])

    def __str__(self) -> str:  # pragma: no cover
        return self.username or self.email


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
