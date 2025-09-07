# expenses/models.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


UserModelRef = settings.AUTH_USER_MODEL  # e.g. "accounts.User"


class ExpenseQuerySet(models.QuerySet):
    def for_company(self, company_id: int | str):
        return self.filter(company_id=company_id)

    def for_project(self, project_id: int | None):
        return self.filter(project_id=project_id) if project_id else self.none()

    def billable(self):
        return self.filter(is_billable=True)

    def unbillable(self):
        return self.filter(is_billable=False)

    def unbilled(self):
        # Billable and not yet attached to an invoice
        return self.filter(is_billable=True, invoice__isnull=True)

    def billed(self):
        return self.filter(is_billable=True, invoice__isnull=False)

    def in_date_range(self, start: Optional[timezone.datetime], end: Optional[timezone.datetime]):
        qs = self
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        return qs


class Expense(models.Model):
    """
    A single company expense. Optionally linked to a project and (if rebilled) to an invoice.
    """
    company = models.ForeignKey(
        "company.Company",  # was "company.company"
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    project = models.ForeignKey(
        "projects.Project",  # was "projects.project"
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )
    vendor = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Entered in your company currency; non-negative.",
    )
    date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=100, blank=True)
    is_billable = models.BooleanField(default=False)
    invoice = models.ForeignKey(
        "invoices.Invoice",  # was "core.Invoice"
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="expenses",
        help_text="If rebilled to a client, the invoice this expense was added to.",
    )
    billable_markup_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("999.99"))],
        help_text="Percentage markup to apply when rebilling, e.g. 10.00 for 10%.",
    )
    billable_note = models.CharField(max_length=200, blank=True, default="")

    # Optional audit fields (easy to enable later if you wire them up)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # created_by = models.ForeignKey(UserModelRef, null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses_created")
    # updated_by = models.ForeignKey(UserModelRef, null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses_updated")

    objects = ExpenseQuerySet.as_manager()

    class Meta:
        ordering = ("-date", "-id")
        indexes = [
            models.Index(fields=["company", "project", "date"]),
            models.Index(fields=["company", "date"]),
            models.Index(fields=["company", "category"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=Decimal("0.00")),
                name="expense_amount_non_negative",
            ),
            models.CheckConstraint(
                check=models.Q(billable_markup_pct__gte=Decimal("0.00")),
                name="expense_markup_non_negative",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        # Include amount for quick admin identification
        return f"{self.description} — {self.amount:.2f}"

    # ---- Computed helpers -------------------------------------------------

    @staticmethod
    def _round_cents(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def markup_multiplier(self) -> Decimal:
        """
        10.00% -> 1.10  ;  0.00% -> 1.00
        """
        return Decimal("1.00") + (self.billable_markup_pct or Decimal("0")) / Decimal("100")

    @property
    def rebill_amount(self) -> Decimal:
        """
        Amount including markup (if billable). Always rounded to cents.
        """
        base = self.amount or Decimal("0.00")
        if not self.is_billable:
            return self._round_cents(base)
        return self._round_cents(base * self.markup_multiplier)

    @property
    def markup_amount(self) -> Decimal:
        """
        The markup portion only (rebill_amount - amount). Never negative.
        """
        total = self.rebill_amount
        base = self.amount or Decimal("0.00")
        out = total - base
        return self._round_cents(out if out >= 0 else Decimal("0.00"))

    # ---- State helpers ----------------------------------------------------

    def can_attach_to_invoice(self) -> bool:
        """
        True if this expense is billable and not already attached to an invoice.
        """
        return self.is_billable and self.invoice_id is None # type: ignore

    def mark_billed(self, invoice: "invoices.Invoice") -> None: # type: ignore
        """
        Convenience helper to associate this expense to an invoice.
        (Caller should handle saving within a transaction.)
        """
        self.invoice = invoice

    # ---- Validation -------------------------------------------------------

    def clean(self):
        """
        Guardrails:
        - If not billable, ignore invoice / markup logically (invoice may be kept for history if you prefer).
        - Prevent negative numbers (enforced by validator/constraint, but keep friendly check).
        """
        super().clean()

        if self.amount is not None and self.amount < 0:
            raise models.ValidationError({"amount": "Amount must be non-negative."}) # type: ignore

        if self.billable_markup_pct is not None and self.billable_markup_pct < 0:
            raise models.ValidationError({"billable_markup_pct": "Markup must be non-negative."}) # type: ignore

        # Optional: disallow invoice assignment when not billable
        # if not self.is_billable and self.invoice_id:
        #     raise models.ValidationError({"invoice": "Cannot attach a non-billable expense to an invoice."})

    # ---- Query sugar ------------------------------------------------------

    @classmethod
    def totals_for_company_month(
        cls,
        company_id: int | str,
        year: int,
        month: int,
    ) -> dict[str, Decimal]:
        """
        Returns a dict of totals for the month (base spend and rebill totals).
        Useful for dashboards.
        """
        qs = cls.objects.for_company(company_id).filter(date__year=year, date__month=month) # type: ignore

        base_total = qs.aggregate(n=models.Sum("amount"))["n"] or Decimal("0.00")

        # Compute rebill totals in Python to respect markup rules
        rebill_total = Decimal("0.00")
        for e in qs.billable():
            rebill_total += e.rebill_amount

        return {
            "expense_total": base_total.quantize(Decimal("0.01")),
            "rebill_total": rebill_total.quantize(Decimal("0.01")),
        }
