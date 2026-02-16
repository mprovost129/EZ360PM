# crm/models.py
from __future__ import annotations

from django.db import models
from django.utils import timezone

from core.models import SyncModel
from companies.models import Company

import uuid


class ContactPhoneType(models.TextChoices):
    MOBILE = "mobile", "Mobile"
    WORK = "work", "Work"
    HOME = "home", "Home"
    OTHER = "other", "Other"


class Client(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="clients")

    first_name = models.CharField(max_length=80, blank=True, default="")
    last_name = models.CharField(max_length=80, blank=True, default="")
    company_name = models.CharField(max_length=160, blank=True, default="")

    email = models.EmailField(blank=True, default="")
    internal_note = models.TextField(blank=True, default="")

    address1 = models.CharField(max_length=200, blank=True, default="")
    address2 = models.CharField(max_length=200, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    state = models.CharField(max_length=2, blank=True, default="")
    zip_code = models.CharField(max_length=12, blank=True, default="")

    # financials
    credit_cents = models.BigIntegerField(default=0)  # overpayment credit
    outstanding_cents = models.BigIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["company", "company_name", "last_name", "first_name"]),
            models.Index(fields=["company", "updated_at"]),
            models.Index(fields=["company", "email"]),
        ]

    def display_label(self) -> str:
        if self.company_name.strip():
            return self.company_name.strip()
        return " ".join([x for x in [self.first_name.strip(), self.last_name.strip()] if x])

    def __str__(self) -> str:
        return f"{self.display_label()} ({self.company.name})"


class ClientPhone(SyncModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="phones")
    phone_type = models.CharField(max_length=20, choices=ContactPhoneType.choices, default=ContactPhoneType.MOBILE)
    number = models.CharField(max_length=40)

    class Meta:
        indexes = [models.Index(fields=["client"])]



class ClientImportBatch(models.Model):
    """Temporary storage for client CSV imports.

    We store the raw CSV content so we can support a 2-step wizard:
    1) Upload + preview
    2) Map columns + import
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="client_import_batches")
    created_at = models.DateTimeField(default=timezone.now)
    uploaded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_import_batches",
    )
    original_filename = models.CharField(max_length=260, blank=True, default="")
    csv_content = models.TextField(blank=True, default="")

    # Import results (stored after running the import so the user can download a report)
    imported_at = models.DateTimeField(null=True, blank=True)
    last_summary = models.JSONField(blank=True, default=dict)
    last_report_csv = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"ClientImportBatch {self.id} ({self.company.name})"


class ClientImportMapping(models.Model):
    """Saved client CSV mapping per company.

    Lets customers import repeatedly without remapping each time.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="client_import_mappings")
    name = models.CharField(max_length=120)
    mapping = models.JSONField(blank=True, default=dict)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_import_mappings_created",
    )
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_import_mappings_updated",
    )

    class Meta:
        indexes = [models.Index(fields=["company", "name"]), models.Index(fields=["company", "is_default"])]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_client_import_mapping_name_per_company")
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.company.name})"
