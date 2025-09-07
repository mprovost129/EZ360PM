# invoices/models.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

UserModelRef = settings.AUTH_USER_MODEL
TWOPLACES = Decimal("0.01")


class Invoice(models.Model):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    VOID = "void"
    STATUS_CHOICES = [(DRAFT, "Draft"), (SENT, "Sent"), (PAID, "Paid"), (VOID, "Void")]

    company = models.ForeignKey("company.company", on_delete=models.CASCADE, related_name="invoices")
    project = models.ForeignKey("projects.project", on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices")
    client  = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="invoices")

    number = models.CharField(max_length=30, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax      = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total    = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    public_token = models.UUIDField(default=uuid4, editable=False, unique=True)
    currency = models.CharField(max_length=3, default="usd")
    allow_reminders = models.BooleanField(default=True)
    reminder_log = models.CharField(max_length=120, blank=True, default="", help_text="CSV of offsets or 'manual'")
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-issue_date", "-id")
        indexes = [
            models.Index(fields=["company", "status", "issue_date"]),
            models.Index(fields=["company", "number"]),
            models.Index(fields=["company", "client"]),  # common reporting filter
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "number"], name="uniq_invoice_number_per_company"),
            models.CheckConstraint(
                check=models.Q(amount_paid__gte=Decimal("0.00")),
                name="invoice_amount_paid_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(total__gte=Decimal("0.00")),
                name="invoice_total_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"Invoice {self.number}"

    def get_absolute_url(self) -> str:
        return reverse("invoices:invoice_detail", args=[self.pk])

    @property
    def balance(self) -> Decimal:
        total = (self.total or Decimal("0.00"))
        paid = (self.amount_paid or Decimal("0.00"))
        out = total - paid
        return out if out > 0 else Decimal("0.00")

    @property
    def amount_due(self) -> Decimal:
        return self.balance

    @property
    def is_overdue(self) -> bool:
        return bool(self.due_date and self.balance > 0 and self.due_date < timezone.localdate())

    # Optional helper to (re)compute summary fields from items
    def recompute_totals(self) -> None:
        subtotal = Decimal("0.00")
        for it in self.items.all(): # type: ignore
            subtotal += (it.line_total or Decimal("0.00"))
        self.subtotal = subtotal.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        total = (self.subtotal or Decimal("0.00")) + (self.tax or Decimal("0.00"))
        self.total = total.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def clean(self):
        super().clean()
        # Friendly guards; DB constraints still apply
        if self.due_date and self.issue_date and self.due_date < self.issue_date:
            raise models.ValidationError({"due_date": "Due date cannot be before the issue date."}) # type: ignore
        if (self.amount_paid or Decimal("0")) < 0:
            raise models.ValidationError({"amount_paid": "Amount paid cannot be negative."}) # type: ignore


class InvoiceItem(models.Model):
    invoice = models.ForeignKey("invoices.Invoice", on_delete=models.CASCADE, related_name="items")  # fixed app label
    description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ("id",)

    @property
    def line_total(self) -> Decimal:
        q = self.qty or Decimal("0.00")
        p = self.unit_price or Decimal("0.00")
        return (q * p).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def __str__(self) -> str:
        return self.description


class RecurringPlan(models.Model):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    FREQ_CHOICES = [(WEEKLY, "Weekly"), (MONTHLY, "Monthly"), (QUARTERLY, "Quarterly"), (YEARLY, "Yearly")]

    ACTIVE = "active"
    PAUSED = "paused"
    STATUS_CHOICES = [(ACTIVE, "Active"), (PAUSED, "Paused")]

    company = models.ForeignKey("company.company", on_delete=models.CASCADE, related_name="recurring_plans")
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="recurring_plans")
    project = models.ForeignKey("projects.project", on_delete=models.SET_NULL, null=True, blank=True, related_name="recurring_plans")
    template_invoice = models.ForeignKey(
        "invoices.Invoice",  # fixed app label
        on_delete=models.SET_NULL, null=True, blank=True, related_name="used_as_template_for",
        help_text="Items/notes/tax copied each cycle.",
    )

    title = models.CharField(max_length=120)
    frequency = models.CharField(max_length=12, choices=FREQ_CHOICES, default=MONTHLY)
    start_date = models.DateField(help_text="First issue date.")
    next_run_date = models.DateField(help_text="Next scheduled generation date.")
    end_date = models.DateField(null=True, blank=True)
    due_days = models.PositiveIntegerField(default=14, help_text="Days after issue for due date.")

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=ACTIVE)
    auto_email = models.BooleanField(default=True, help_text="Email the invoice automatically on generation.")
    max_occurrences = models.PositiveIntegerField(null=True, blank=True, help_text="Stop after N issues (optional).")
    occurrences_sent = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["company", "status", "next_run_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} · {self.get_frequency_display()}" # type: ignore

    def is_active(self) -> bool:
        if self.status != self.ACTIVE:
            return False
        if self.end_date and self.next_run_date and self.next_run_date > self.end_date:
            return False
        if self.max_occurrences is not None and self.occurrences_sent >= self.max_occurrences:
            return False
        return True
