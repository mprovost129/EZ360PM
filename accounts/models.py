# accounts/models.py
from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.mail import send_mail
from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------
# User Manager
# ---------------------------------------------------------------------
class UserManager(BaseUserManager):
    """
    Custom manager for User model with email as the unique identifier.
    """

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra: Any) -> "User":
        if not email:
            raise ValueError("The Email field is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)

        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra)


# ---------------------------------------------------------------------
# User Model
# ---------------------------------------------------------------------
class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model using email as the username field.
    """

    email = models.EmailField(_("email address"), unique=True)
    name = models.CharField(_("full name"), max_length=150, blank=True)

    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("staff status"), default=False)
    is_verified = models.BooleanField(_("email verified"), default=False)

    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    accepted_tos_at = models.DateTimeField(_("accepted terms at"), null=True, blank=True)
    accepted_privacy_at = models.DateTimeField(_("accepted privacy at"), null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        constraints = [
            # Enforce case-insensitive uniqueness on email (especially useful on Postgres)
            UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]
        indexes = [
            models.Index(Lower("email"), name="accounts_user_email_ci_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.email

    # --- Helpful accessors -------------------------------------------------
    @property
    def first_name(self) -> str:
        return (self.name or "").split(" ", 1)[0] if self.name else ""

    @property
    def last_name(self) -> str:
        if not self.name or " " not in self.name:
            return ""
        return self.name.split(" ", 1)[1]

    def get_full_name(self) -> str:
        return self.name or self.email

    def get_short_name(self) -> str:
        return self.first_name or self.email

    def email_user(self, subject: str, message: str, from_email: str | None = None, **kwargs: Any) -> None:
        send_mail(subject, message, from_email, [self.email], **kwargs)

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Keep email normalized and lowercase
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email).lower() # type: ignore
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------
def _avatar_upload_to(instance: "UserProfile", filename: str) -> str:
    # Store avatars under a stable per-user directory
    return f"avatars/user_{instance.user_id}/{filename}" # type: ignore


class UserProfile(models.Model):
    """
    Lightweight profile attached to the User.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    avatar = models.ImageField(upload_to=_avatar_upload_to, blank=True, null=True) # type: ignore
    phone = models.CharField(max_length=40, blank=True)
    title = models.CharField(max_length=120, blank=True)
    timezone = models.CharField(max_length=64, blank=True, default="")
    locale = models.CharField(max_length=16, blank=True, default="")
    bio = models.TextField(blank=True)
    dark_mode = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user",)

    def __str__(self) -> str:  # pragma: no cover
        return self.user.get_full_name() or str(self.user)


# ---------------------------------------------------------------------
# Signals: keep a profile in sync with the User
# ---------------------------------------------------------------------
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=User)
def _create_or_update_user_profile(sender, instance: User, created: bool, **kwargs: Any) -> None:
    # Create on first save; ensure it exists afterwards
    if created:
        UserProfile.objects.create(user=instance)
    else:
        # Touch updated_at if profile exists (no-op if not)
        UserProfile.objects.filter(user=instance).update(updated_at=timezone.now())
