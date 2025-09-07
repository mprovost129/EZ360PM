# company/models.py
from __future__ import annotations

from uuid import uuid4
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone

UserModelRef = settings.AUTH_USER_MODEL


class Company(models.Model):
    owner = models.ForeignKey(
        UserModelRef,
        on_delete=models.CASCADE,
        related_name="companies",
    )
    name = models.CharField(max_length=160, blank=True, null=True)

    company_logo = models.ImageField(upload_to="company_logos/", blank=True, null=True)

    admin_first_name = models.CharField(max_length=100, blank=True, null=True)
    admin_last_name  = models.CharField(max_length=100, blank=True, null=True)
    admin_phone      = models.CharField(max_length=50, blank=True)

    address_1 = models.CharField("Address line 1", max_length=200, blank=True, null=True)
    address_2 = models.CharField("Address line 2", max_length=200, blank=True, null=True)
    city      = models.CharField(max_length=100, blank=True, null=True)
    state     = models.CharField("State / Province", max_length=100, blank=True, null=True)
    zip_code  = models.CharField("ZIP / Postal code", max_length=20, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "company"
        verbose_name_plural = "companies"
        ordering = ("-created_at", "id")
        indexes = [
            models.Index(fields=["owner", "name"]),
        ]
        constraints = [
            # Multiple NULL names are allowed by SQL semantics; unique among non-NULL names per owner.
            models.UniqueConstraint(fields=["owner", "name"], name="uniq_owner_company_name"),
        ]

    def __str__(self) -> str:
        name = (self.name or "").strip()
        if name:
            return name
        owner_hint = ""
        try:
            owner_hint = getattr(self.owner, "email", None) or getattr(self.owner, "username", "") or ""
        except Exception:
            pass
        return f"{owner_hint}'s company" if owner_hint else f"Company #{self.pk or '?'}"

    @property
    def admin_full_name(self) -> str:
        first = (self.admin_first_name or "").strip()
        last  = (self.admin_last_name or "").strip()
        return f"{first} {last}".strip()


class CompanyMember(models.Model):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    ROLE_CHOICES = [(OWNER, "Owner"), (ADMIN, "Admin"), (MEMBER, "Member")]

    company = models.ForeignKey("company.Company", on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(UserModelRef, on_delete=models.CASCADE, related_name="company_memberships")
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default=MEMBER)
    joined_at = models.DateTimeField(default=timezone.now)
    job_title = models.CharField(max_length=120, blank=True)
    hourly_rate = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = "company member"
        verbose_name_plural = "company members"
        ordering = ("-joined_at",)
        constraints = [
            models.UniqueConstraint(fields=["company", "user"], name="uniq_company_member"),
        ]
        indexes = [
            models.Index(fields=["company", "role"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self) -> str:
        return f"{self.company} — {self.user} ({self.role})"

    # helpers
    def is_owner(self) -> bool:
        return self.role == self.OWNER

    def is_admin(self) -> bool:
        return self.role in {self.OWNER, self.ADMIN}


class CompanyInvite(models.Model):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CANCELED = "canceled"
    STATUS_CHOICES = [(PENDING, "Pending"), (ACCEPTED, "Accepted"), (CANCELED, "Canceled")]

    company = models.ForeignKey("company.Company", on_delete=models.CASCADE, related_name="invites")
    email = models.EmailField()
    role = models.CharField(max_length=12, choices=CompanyMember.ROLE_CHOICES, default=CompanyMember.MEMBER)
    token = models.UUIDField(default=uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(
        UserModelRef, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_company_invites"
    )
    sent_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)

    class Meta:
        verbose_name = "company invite"
        verbose_name_plural = "company invites"
        ordering = ("-sent_at",)
        indexes = [
            models.Index(fields=["company", "email"]),
            models.Index(fields=["token"]),
            models.Index(fields=["status", "sent_at"]),
        ]

    def __str__(self) -> str:
        return f"Invite {self.email} → {self.company} ({self.role})"
