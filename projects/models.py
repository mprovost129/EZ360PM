# projects/models.py
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

UserModelRef = settings.AUTH_USER_MODEL


class Project(models.Model):
    HOURLY = "hourly"
    FLAT = "flat"
    BILLING_TYPE_CHOICES = [(HOURLY, "Hourly"), (FLAT, "Flat Rate")]

    company = models.ForeignKey("company.company", on_delete=models.CASCADE, related_name="projects")
    client = models.ForeignKey("clients.Client", on_delete=models.PROTECT, related_name="projects")

    # Make optional so it can be auto-generated
    number = models.CharField(max_length=20, blank=True)
    name = models.CharField(max_length=200)
    details = models.TextField(blank=True)
    billing_type = models.CharField(max_length=10, choices=BILLING_TYPE_CHOICES, default=HOURLY)

    # Monetary / time fields
    budget = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Optional monetary budget (in company currency).",
    )
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(
        max_digits=8, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Optional estimate of hours.",
    )
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Used for hourly billing calculations.",
    )

    team = models.ManyToManyField(UserModelRef, blank=True, related_name="team_projects")

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["company", "number"]),
            models.Index(fields=["company", "client", "due_date"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "number"], name="uniq_project_number_per_company"),
        ]

    def __str__(self) -> str:
        return f"{self.number or '(unassigned)'} — {self.name}"

    def get_absolute_url(self) -> str:
        return reverse("projects:project_detail", args=[self.pk])

    # -----------------------------
    # Auto-numbering
    # -----------------------------
    def _generate_number(self) -> str:
        """
        Generate the next unique project number for this company.
        Default pattern: YYYY-### (e.g., 2025-001). Skips any malformed rows.
        """
        year = timezone.localdate().year
        prefix = f"{year}-"

        existing = (
            Project.objects
            .filter(company=self.company, number__startswith=prefix)
            .values_list("number", flat=True)
        )

        max_seq = 0
        for n in existing:
            try:
                # Accept '2025-001', '2025-1', even '2025-001A' (digits only)
                suffix = str(n).split("-", 1)[1]
                digits = "".join(ch for ch in suffix if ch.isdigit())
                if digits:
                    max_seq = max(max_seq, int(digits))
            except Exception:
                continue

        seq = max_seq + 1
        candidate = f"{prefix}{seq:03d}"
        # Ensure uniqueness in case of races / odd data
        while Project.objects.filter(company=self.company, number=candidate).exists():
            seq += 1
            candidate = f"{prefix}{seq:03d}"
        return candidate

    def save(self, *args, **kwargs):
        # Assign a number if not provided
        if (not self.number) and self.company_id: # type: ignore
            self.number = self._generate_number()
        super().save(*args, **kwargs)

    # -----------------------------
    # Validation
    # -----------------------------
    def clean(self):
        super().clean()
        if self.start_date and self.due_date and self.due_date < self.start_date:
            from django.core.exceptions import ValidationError
            raise ValidationError({"due_date": "Due date cannot be before start date."})

    # -----------------------------
    # Helpful computed properties
    # -----------------------------
    @property
    def is_overdue(self) -> bool:
        """True if the project has a due date in the past (based on local date)."""
        try:
            return bool(self.due_date and self.due_date < timezone.localdate())
        except Exception:
            return False

    @property
    def hours_logged(self) -> Decimal:
        """
        Sum of related time entry hours (expects a related_name='time_entries' with Decimal hours field).
        Returns Decimal('0.00') if none.
        """
        agg = getattr(self, "time_entries", None)
        if not agg:
            return Decimal("0.00")
        total = agg.aggregate(s=Sum("hours")).get("s") or Decimal("0.00")
        return Decimal(str(total)).quantize(Decimal("0.01"))

    @property
    def amount_spent(self) -> Decimal:
        """
        Simple spend estimate for hourly projects: hours_logged * hourly_rate.
        For flat projects, returns Decimal('0.00') (spend tracking is invoice/expense driven).
        """
        if self.billing_type != self.HOURLY:
            return Decimal("0.00")
        amt = (self.hours_logged or Decimal("0.00")) * (self.hourly_rate or Decimal("0.00"))
        return Decimal(amt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def budget_remaining(self) -> Decimal | None:
        """
        If a monetary budget is set (> 0), returns budget - amount_spent (not below zero).
        Otherwise returns None.
        """
        if not self.budget or self.budget <= 0:
            return None
        remaining = (self.budget or Decimal("0.00")) - (self.amount_spent or Decimal("0.00"))
        if remaining < 0:
            remaining = Decimal("0.00")
        return remaining.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)