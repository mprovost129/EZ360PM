# companies/models.py
from __future__ import annotations

from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import SyncModel


class Company(SyncModel):
    name = models.CharField(max_length=160)
    logo = models.ImageField(upload_to="company_logos/", blank=True, null=True)

    # branding
    email_from_name = models.CharField(max_length=160, blank=True, default="")
    email_from_address = models.EmailField(blank=True, default="")

    # address
    address1 = models.CharField(max_length=200, blank=True, default="")
    address2 = models.CharField(max_length=200, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    state = models.CharField(max_length=2, blank=True, default="")
    zip_code = models.CharField(max_length=12, blank=True, default="")

    # -------------------------
    # Financial defaults (Phase 5B)
    # -------------------------
    default_invoice_due_days = models.PositiveIntegerField(
        default=30,
        help_text="Default number of days until invoice due date (used when creating new invoices).",
    )
    default_estimate_valid_days = models.PositiveIntegerField(
        default=30,
        help_text="Default number of days an estimate/proposal remains valid (used when creating new documents).",
    )
    default_sales_tax_percent = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.000"),
        help_text="Default sales tax percentage for guidance (does not automatically apply tax to line items).",
    )
    default_line_items_taxable = models.BooleanField(
        default=False,
        help_text="Default 'Taxable' checkbox for new document line items.",
    )


    is_active = models.BooleanField(default=True)

    # Security policy
    require_2fa_for_admins_managers = models.BooleanField(default=False)
    require_2fa_for_all = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["updated_at"]),
            models.Index(fields=["deleted_at"]),
        ]

    def __str__(self) -> str:
        return self.name


class EmployeeRole(models.TextChoices):
    STAFF = "staff", "Staff"
    MANAGER = "manager", "Manager"
    ADMIN = "admin", "Admin"
    OWNER = "owner", "Owner"


class EmployeeProfile(SyncModel):
    """
    Per-company employee profile. A user can have multiple EmployeeProfiles
    across different companies.
    """

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="employees")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee_profiles")

    # public identity
    display_name = models.CharField(max_length=160, blank=True, default="")
    username_public = models.CharField(max_length=40)  # public "username used interchangeably"

    role = models.CharField(max_length=20, choices=EmployeeRole.choices, default=EmployeeRole.STAFF)

    # Optional per-user override: require 2FA for this employee regardless of role
    force_2fa = models.BooleanField(default=False)

    # employment details
    is_active = models.BooleanField(default=True)

    # Security policy
    require_2fa_for_admins_managers = models.BooleanField(default=False)
    require_2fa_for_all = models.BooleanField(default=False)
    hired_at = models.DateField(null=True, blank=True)
    terminated_at = models.DateField(null=True, blank=True)

    # rates (hidden from staff)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cost_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # optional later

    # permissions overrides (optional)
    can_view_company_financials = models.BooleanField(default=False)  # managers/admins set automatically too
    can_approve_time = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "username_public"], name="uniq_company_username_public"),
            models.UniqueConstraint(fields=["company", "user"], name="uniq_company_user_profile"),
        ]
        indexes = [
            models.Index(fields=["company", "role"]),
            models.Index(fields=["company", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.username_public} @ {self.company.name}"


class CompanyInvite(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="invites")
    email = models.EmailField()
    username_public = models.CharField(max_length=40)
    role = models.CharField(max_length=20, choices=EmployeeRole.choices, default=EmployeeRole.STAFF)

    # Optional per-user override: require 2FA for this employee regardless of role
    force_2fa = models.BooleanField(default=False)

    token = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL)

    accepted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "email"]),
            models.Index(fields=["token"]),
        ]
