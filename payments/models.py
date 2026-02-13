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
