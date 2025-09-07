# timetracking/models.py
from __future__ import annotations

from uuid import uuid4
from datetime import timedelta, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

UserModelRef = settings.AUTH_USER_MODEL


class TimeEntry(models.Model):
    # ---- Workflow/status ----
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SUBMITTED, "Submitted"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    # ---- Core fields ----
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)

    # Correct app labels (model moved out of core)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="time_entries")
    user = models.ForeignKey(UserModelRef, on_delete=models.CASCADE, related_name="time_entries")
    company = models.ForeignKey("company.Company", on_delete=models.CASCADE, related_name="time_entries")

    start_time = models.DateTimeField()
    end_time = models.DateTimeField(null=True, blank=True)  # null => running

    notes = models.TextField(blank=True, default="")
    # Stored decimal hours; computed on stop if still 0.00
    hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))

    is_billable = models.BooleanField(default=True)
    invoice = models.ForeignKey(
        "invoices.Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="time_entries"
    )

    # ---- Approvals ----
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_timeentries",
    )
    reject_reason = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        # Keep using the original table to avoid migration churn / data moves
        db_table = "core_timeentry"
        ordering = ("-start_time", "-id")
        indexes = [
            models.Index(fields=["project", "user", "start_time"]),
            models.Index(fields=["project", "status", "start_time"]),
            models.Index(fields=["user", "status", "start_time"]),
            models.Index(fields=["company", "start_time"]),
            models.Index(fields=["invoice"]),
        ]
        constraints = [
            # Enforce one running entry per (user, company)
            models.UniqueConstraint(
                fields=["user", "company"],
                condition=Q(end_time__isnull=True),
                name="uniq_running_timeentry_per_user_company",
            )
        ]

    # ---------- Convenience / timer helpers ----------
    def __str__(self) -> str:
        return f"{self.project} — {self.user} — {self.hours}h ({self.status})"

    @property
    def is_running(self) -> bool:
        return self.end_time is None

    @property
    def duration(self) -> timedelta:
        end = self.end_time or timezone.now()
        delta = end - self.start_time
        return delta if delta.total_seconds() >= 0 else timedelta(0)

    @property
    def duration_seconds(self) -> int:
        return int(self.duration.total_seconds())

    @property
    def billed(self) -> bool:
        return self.invoice_id is not None  # type: ignore

    @staticmethod
    def active_for(user, company=None) -> Optional["TimeEntry"]:
        qs = TimeEntry.objects.filter(user=user, end_time__isnull=True).select_related("project", "company")
        if company is not None:
            qs = qs.filter(company=company)
        return qs.first()

    # ---------- Validation & persistence ----------
    def clean(self):
        # Temporal sanity
        if self.end_time and self.end_time < self.start_time:
            raise ValidationError({"end_time": "End time cannot be earlier than start time."})

        # Company/project coherence
        if self.project_id and self.company_id: # type: ignore
            try:
                proj_company_id = self.project.company_id  # may hit DB if not cached
                if proj_company_id and self.company_id != proj_company_id: # type: ignore
                    raise ValidationError({"company": "Company must match the project's company."})
            except Exception:
                # If project isn't resolvable, let DB layer raise later
                pass

    def _compute_hours_from_times(self) -> Decimal:
        secs = self.duration_seconds
        hours = Decimal(secs) / Decimal(3600)
        return hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def stop(self, when: Optional[datetime] = None, *, keep_manual_hours: bool = False) -> None:
        if not self.is_running:
            return
        self.end_time = when or timezone.now()
        if not keep_manual_hours or (self.hours or Decimal("0.00")) == Decimal("0.00"):
            self.hours = self._compute_hours_from_times()

    def save(self, *args, **kwargs):
        # Auto-align company to project's company when possible
        try:
            if self.project_id and (not self.company_id or self.company_id != self.project.company_id): # type: ignore
                self.company = self.project.company  # keep in sync
        except Exception:
            # Non-fatal; consistency still enforced by clean() and app logic
            pass

        # If end_time present but hours are zero, compute from timestamps
        if self.end_time and (self.hours or Decimal("0.00")) == Decimal("0.00"):
            try:
                self.hours = self._compute_hours_from_times()
            except Exception:
                pass

        super().save(*args, **kwargs)
