# payments/models.py
from __future__ import annotations

from django.db import models
from django.utils import timezone

from core.models import SyncModel
from companies.models import Company, EmployeeProfile
from crm.models import Client
from documents.models import Document


class PaymentMethod(models.TextChoices):
    STRIPE = "stripe", "Stripe"
    CASH = "cash", "Cash"
    CHECK = "check", "Check"
    ACH = "ach", "ACH"
    CARD = "card", "Card"
    OTHER = "other", "Other"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"
    VOID = "void", "Void"


class Payment(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="payments")
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL)
    invoice = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")

    payment_date = models.DateField(null=True, blank=True)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.OTHER)
    amount_cents = models.BigIntegerField(default=0)
    refunded_cents = models.BigIntegerField(default=0)
    notes = models.TextField(blank=True, default="")

    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)

    # Stripe fields
    stripe_payment_intent_id = models.CharField(max_length=80, blank=True, default="")
    stripe_checkout_session_id = models.CharField(max_length=80, blank=True, default="")
    stripe_charge_id = models.CharField(max_length=80, blank=True, default="")

    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=["company", "status", "payment_date"]),
            models.Index(fields=["company", "invoice"]),
            models.Index(fields=["company", "client"]),
            models.Index(fields=["company", "stripe_payment_intent_id"]),
        ]



class PaymentRefundStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class PaymentRefund(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="payment_refunds")
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="payment_refunds")

    cents = models.BigIntegerField(default=0)
    status = models.CharField(max_length=20, choices=PaymentRefundStatus.choices, default=PaymentRefundStatus.PENDING)

    # Stripe fields
    stripe_refund_id = models.CharField(max_length=80, blank=True, default="")
    stripe_charge_id = models.CharField(max_length=80, blank=True, default="")
    stripe_payment_intent_id = models.CharField(max_length=80, blank=True, default="")

    memo = models.CharField(max_length=240, blank=True, default="")
    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "payment", "created_at"]),
            models.Index(fields=["company", "stripe_refund_id"]),
        ]


class ClientCreditLedgerEntry(SyncModel):
    """
    Tracks credit creation/use (overpayment, adjustment, applied to invoice, etc.)
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="credit_ledger")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="credit_entries")
    invoice = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL)

    cents_delta = models.BigIntegerField()  # + credit, - credit used
    reason = models.CharField(max_length=120, blank=True, default="")
    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=["company", "client", "created_at"]),
            models.Index(fields=["company", "invoice"]),
        ]




class ClientCreditApplication(SyncModel):
    """Represents applying existing client credit to an invoice (no cash movement)."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="credit_applications")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="credit_applications")
    invoice = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="credit_applications")

    cents = models.BigIntegerField()
    memo = models.CharField(max_length=240, blank=True, default="")

    applied_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL)

    journal_entry = models.ForeignKey(
        "accounting.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credit_applications",
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "client", "applied_at"]),
            models.Index(fields=["company", "invoice"]),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} · {self.client.id} · {self.cents}c → {self.invoice.id}"


class Refund(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="refunds")
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refunds")
    invoice = models.ForeignKey(Document, null=True, blank=True, on_delete=models.SET_NULL)

    cents = models.BigIntegerField(default=0)
    reason = models.CharField(max_length=120, blank=True, default="")
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)

    stripe_refund_id = models.CharField(max_length=80, blank=True, default="")
    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL)


class Retainer(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="retainers")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="retainers")

    cents_balance = models.BigIntegerField(default=0)
    notes = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL)


class StripeConnectStatus(models.TextChoices):
    NOT_CONNECTED = "not_connected", "Not connected"
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    RESTRICTED = "restricted", "Restricted"


class StripeConnectAccount(SyncModel):
    """Stores a company's Stripe Connect account (for invoice payouts).

    This is separate from EZ360PM subscription billing. When a company's customer pays an invoice,
    the PaymentIntent can be created with transfer_data.destination to route funds to this connected
    account.
    """

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="stripe_connect")

    stripe_account_id = models.CharField(max_length=80, blank=True, default="")

    charges_enabled = models.BooleanField(default=False)
    payouts_enabled = models.BooleanField(default=False)
    details_submitted = models.BooleanField(default=False)

    status = models.CharField(max_length=20, choices=StripeConnectStatus.choices, default=StripeConnectStatus.NOT_CONNECTED)
    disabled_reason = models.CharField(max_length=200, blank=True, default="")
    requirements_json = models.JSONField(default=dict, blank=True)

    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["stripe_account_id"]),
        ]

    @property
    def is_ready(self) -> bool:
        return bool(self.stripe_account_id) and self.charges_enabled and self.payouts_enabled
