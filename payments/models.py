# payments/models.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


UserModelRef = settings.AUTH_USER_MODEL  # e.g. "accounts.User"


class Payment(models.Model):
    company = models.ForeignKey("company.Company", on_delete=models.CASCADE, related_name="payments")
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    received_at = models.DateTimeField(default=timezone.now)
    method = models.CharField(max_length=50, blank=True)  # Stripe, Cash, Check, etc.
    external_id = models.CharField(max_length=200, blank=True, db_index=True)

    class Meta:
        ordering = ("-received_at", "-id")
        indexes = [
            models.Index(fields=["company", "invoice", "received_at"]),
        ]
        constraints = [
            # Prevent duplicate ingestion when an external reference (e.g., Stripe PI)
            # is provided; allow multiple rows when external_id is blank.
            models.UniqueConstraint(
                fields=["company", "external_id"],
                name="uniq_payment_external_per_company",
                condition=~Q(external_id=""),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.amount} on {self.invoice}"
