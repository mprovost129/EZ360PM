from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from core.models import SyncModel
from companies.models import Company, EmployeeProfile
from accounting.models import Account


class Vendor(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="payables_vendors")

    # Override SyncModel updated_by_user related_name to avoid clashes with other apps' Vendor models.
    updated_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_payables_vendor_set",
    )

    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")

    address1 = models.CharField(max_length=200, blank=True, default="")
    address2 = models.CharField(max_length=200, blank=True, default="")
    city = models.CharField(max_length=120, blank=True, default="")
    state = models.CharField(max_length=32, blank=True, default="")
    postal_code = models.CharField(max_length=20, blank=True, default="")
    country = models.CharField(max_length=60, blank=True, default="US")

    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("company", "name")]

    def __str__(self) -> str:
        return self.name


class BillStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    POSTED = "posted", "Posted"
    PARTIALLY_PAID = "partially_paid", "Partially paid"
    PAID = "paid", "Paid"


class Bill(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="bills")
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="bills")

    bill_number = models.CharField(max_length=60, blank=True, default="")
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=24, choices=BillStatus.choices, default=BillStatus.DRAFT)

    subtotal_cents = models.IntegerField(default=0)
    tax_cents = models.IntegerField(default=0)
    total_cents = models.IntegerField(default=0)

    amount_paid_cents = models.IntegerField(default=0)
    balance_cents = models.IntegerField(default=0)

    posted_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="bills_created")

    class Meta:
        ordering = ["-issue_date", "-created_at"]
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "vendor"]),
            models.Index(fields=["company", "due_date"]),
        ]

    def __str__(self) -> str:
        num = self.bill_number or str(self.id)[:8]
        return f"Bill {num}"

    @property
    def is_posted(self) -> bool:
        return self.status in {BillStatus.POSTED, BillStatus.PARTIALLY_PAID, BillStatus.PAID}

    def clean(self):
        if self.total_cents < 0 or self.subtotal_cents < 0 or self.tax_cents < 0:
            raise ValidationError("Amounts cannot be negative.")
        if self.amount_paid_cents < 0 or self.balance_cents < 0:
            raise ValidationError("Paid/balance cannot be negative.")

    def recalc_totals(self):
        subtotal = int(self.lines.aggregate(s=Sum("line_total_cents"))["s"] or 0)
        tax = int(self.tax_cents or 0)
        total = subtotal + tax
        paid = int(self.payments.filter(deleted_at__isnull=True).aggregate(s=Sum("amount_cents"))["s"] or 0)
        balance = max(total - paid, 0)

        self.subtotal_cents = subtotal
        self.total_cents = total
        self.amount_paid_cents = paid
        self.balance_cents = balance

        # update status based on payment
        if self.is_posted:
            if total > 0 and paid <= 0:
                self.status = BillStatus.POSTED
            elif 0 < paid < total:
                self.status = BillStatus.PARTIALLY_PAID
            elif paid >= total and total > 0:
                self.status = BillStatus.PAID

    def save(self, *args, **kwargs):
        # Prevent editing posted bills except safe recalculations.
        if self.pk:
            old = Bill.all_objects.filter(pk=self.pk).first()
            if old and old.is_posted:
                # allow status/amount fields updates via services only; block editing vendor/number/dates
                protected = ["company_id", "vendor_id", "bill_number", "issue_date", "due_date"]
                for f in protected:
                    if getattr(self, f) != getattr(old, f):
                        raise ValidationError("Posted bills cannot be edited.")
        return super().save(*args, **kwargs)

    @transaction.atomic
    def post(self, *, actor: EmployeeProfile | None = None):
        if self.deleted_at:
            raise ValidationError("Cannot post a deleted bill.")
        if self.is_posted:
            return
        # must have at least one line
        if not self.lines.exists():
            raise ValidationError("Add at least one line item before posting.")
        self.status = BillStatus.POSTED
        self.posted_at = timezone.now()
        self.recalc_totals()
        self.updated_by_user = getattr(actor, "user", None)
        self.save(update_fields=["status", "posted_at", "subtotal_cents", "total_cents", "amount_paid_cents", "balance_cents", "tax_cents", "updated_at", "revision", "updated_by_user"])


class BillLineItem(SyncModel):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="lines")

    description = models.CharField(max_length=240)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price_cents = models.IntegerField(default=0)

    expense_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="bill_line_items")

    line_total_cents = models.IntegerField(default=0)

    class Meta:
        ordering = ["id"]

    def clean(self):
        if self.unit_price_cents < 0:
            raise ValidationError("Unit price cannot be negative.")
        if self.quantity is None or self.quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")

    def save(self, *args, **kwargs):
        # immutable if bill posted
        if self.bill_id:
            bill = self.bill
            if bill and bill.is_posted:
                if self.pk:
                    raise ValidationError("Cannot edit lines on a posted bill.")
        qty = float(self.quantity or 0)
        self.line_total_cents = int(round(qty * int(self.unit_price_cents or 0)))
        return super().save(*args, **kwargs)


class BillPayment(SyncModel):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="payments")

    payment_date = models.DateField(default=timezone.localdate)
    amount_cents = models.IntegerField(default=0)

    payment_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="bill_payments")
    reference = models.CharField(max_length=120, blank=True, default="")

    created_by = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="bill_payments_created")

    class Meta:
        ordering = ["-payment_date", "-created_at"]

    def clean(self):
        if self.amount_cents <= 0:
            raise ValidationError("Payment amount must be greater than zero.")

    def save(self, *args, **kwargs):
        # Can only add payments to posted bills
        if self.bill_id and self.bill and not self.bill.is_posted:
            raise ValidationError("You can only record payments for a posted bill.")
        return super().save(*args, **kwargs)
