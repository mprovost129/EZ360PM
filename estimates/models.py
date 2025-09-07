# estimates/models.py
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class Estimate(models.Model):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SENT, "Sent"),
        (ACCEPTED, "Accepted"),
        (DECLINED, "Declined"),
        (EXPIRED, "Expired"),
    ]

    company = models.ForeignKey(
        "company.Company", on_delete=models.CASCADE, related_name="estimates"
    )
    client = models.ForeignKey(
        "clients.Client", on_delete=models.PROTECT, related_name="estimates"
    )
    project = models.ForeignKey(
        "projects.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="estimates"
    )

    number = models.CharField(max_length=32, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=DRAFT)
    issue_date = models.DateField(default=timezone.now)
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    tax = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    is_template = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    public_token = models.UUIDField(default=uuid4, unique=True, editable=False)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.CharField(max_length=120, blank=True, default="")
    declined_at = models.DateTimeField(null=True, blank=True)
    declined_by = models.CharField(max_length=120, blank=True, default="")
    client_note = models.TextField(blank=True, default="")

    converted_invoice = models.OneToOneField(
        "invoices.Invoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="from_estimate",
    )

    class Meta:
        unique_together = ("company", "number")
        ordering = ("-issue_date", "-id")
        indexes = [
            models.Index(fields=["company", "status", "issue_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.number} — {self.client}"

    def get_absolute_url(self) -> str:
        return reverse("estimates:estimate_detail", args=[self.pk])

    def get_public_url(self) -> str:
        base = getattr(settings, "SITE_URL", "")
        return f"{base}{reverse('estimates:estimate_public', kwargs={'token': str(self.public_token)})}"

    # --- Helpers -------------------------------------------------------------

    def recalc_totals(self) -> None:
        """
        Recalculate subtotal, tax, and total from related items.
        (Business rules: `tax` field represents absolute tax amount.)
        """
        subtotal = sum((it.line_total for it in self.items.all()), Decimal("0.00")) # type: ignore
        # Keep existing tax value unless you want to recompute from a rate elsewhere.
        self.subtotal = subtotal.quantize(Decimal("0.01"))
        self.total = (self.subtotal + (self.tax or Decimal("0.00"))).quantize(Decimal("0.01"))

    @property
    def is_expired(self) -> bool:
        return bool(self.valid_until and self.valid_until < timezone.localdate())


class EstimateItem(models.Model):
    estimate = models.ForeignKey(
        "estimates.Estimate", on_delete=models.CASCADE, related_name="items"
    )
    description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ("id",)

    @property
    def line_total(self) -> Decimal:
        q = self.qty or Decimal("0.00")
        p = self.unit_price or Decimal("0.00")
        return (q * p).quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return self.description
