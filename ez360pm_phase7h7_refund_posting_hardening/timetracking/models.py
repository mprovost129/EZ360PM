# timetracking/models.py
from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import SyncModel
from companies.models import Company, EmployeeProfile
from crm.models import Client
from projects.models import Project
from catalog.models import CatalogItem


class TimeStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    BILLED = "billed", "Billed"
    VOID = "void", "Void"


class TimeEntry(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="time_entries")
    employee = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="time_entries")

    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL)
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL)

    # time
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.BigIntegerField(default=0)

    billable = models.BooleanField(default=True)
    note = models.TextField(blank=True, default="")

    status = models.CharField(max_length=20, choices=TimeStatus.choices, default=TimeStatus.DRAFT)

    approved_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="approved_time_entries")
    approved_at = models.DateTimeField(null=True, blank=True)

    billed_document = models.ForeignKey(
        "documents.Document",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="billed_time_entries",
    )
    billed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "employee", "started_at"]),
            models.Index(fields=["company", "status"]),
            # Phase 3W: the list view filters by company, deleted_at is null,
            # optionally employee (staff), status/billable, and date range on started_at.
            models.Index(
                fields=["company", "status", "started_at"],
                name="co_status_start_live_idx",
                condition=Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["company", "employee", "status", "started_at"],
                name="co_emp_status_start_live_idx",
                condition=Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["company", "billable", "started_at"],
                name="co_billable_start_live_idx",
                condition=Q(deleted_at__isnull=True),
            ),
        ]

    def clean(self):
        """Enforce project-driven client linkage.

        Policy:
        - If project is set, client must match project.client.
        - If client is set without project, we allow it for legacy/manual entries.
        """
        super().clean()
        if self.project_id:
            proj_client_id = getattr(self.project, "client_id", None)
            if proj_client_id:
                if self.client_id and self.client_id != proj_client_id:
                    from django.core.exceptions import ValidationError
                    raise ValidationError({"project": "Project client does not match selected client."})
                self.client_id = proj_client_id

    def save(self, *args, **kwargs):
        # Keep client aligned to project.
        if self.project_id:
            try:
                proj_client_id = getattr(self.project, "client_id", None)
                if proj_client_id:
                    self.client_id = proj_client_id
            except Exception:
                pass
        return super().save(*args, **kwargs)


class TimeEntryService(SyncModel):
    """
    Multiple services linked to one time entry.
    """
    time_entry = models.ForeignKey(TimeEntry, on_delete=models.CASCADE, related_name="services")
    catalog_item = models.ForeignKey(CatalogItem, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=200)
    minutes = models.BigIntegerField(default=0)


class TimerState(SyncModel):
    """
    One global timer per user per company.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="timer_states")
    employee = models.OneToOneField(EmployeeProfile, on_delete=models.CASCADE, related_name="timer_state")

    is_running = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)

    # Pause/resume support
    is_paused = models.BooleanField(default=False)
    paused_at = models.DateTimeField(null=True, blank=True)
    elapsed_seconds = models.BigIntegerField(default=0)

    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL)
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL)

    service_catalog_item = models.ForeignKey(CatalogItem, null=True, blank=True, on_delete=models.SET_NULL)
    service_name = models.CharField(max_length=200, blank=True, default="")

    note = models.TextField(blank=True, default="")

    def clean(self):
        super().clean()
        if self.project_id:
            proj_client_id = getattr(self.project, "client_id", None)
            if proj_client_id:
                if self.client_id and self.client_id != proj_client_id:
                    from django.core.exceptions import ValidationError
                    raise ValidationError({"project": "Project client does not match selected client."})
                self.client_id = proj_client_id

    def save(self, *args, **kwargs):
        if self.project_id:
            try:
                proj_client_id = getattr(self.project, "client_id", None)
                if proj_client_id:
                    self.client_id = proj_client_id
            except Exception:
                pass
        return super().save(*args, **kwargs)


class TimeEntryMode(models.TextChoices):
    DURATION = "duration", "Duration only"
    RANGE = "range", "Start/End time"


class ClockFormat(models.TextChoices):
    H12 = "12h", "12-hour"
    H24 = "24h", "24-hour"


class TimeTrackingSettings(SyncModel):
    """Per-employee settings that sync to desktop."""
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="time_settings")
    employee = models.OneToOneField(EmployeeProfile, on_delete=models.CASCADE, related_name="time_settings")

    entry_mode = models.CharField(max_length=20, choices=TimeEntryMode.choices, default=TimeEntryMode.DURATION)
    clock_format = models.CharField(max_length=10, choices=ClockFormat.choices, default=ClockFormat.H12)

    rounding_minutes = models.PositiveIntegerField(default=15, help_text="0 disables rounding; otherwise round to N minutes.")
    require_manager_approval = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "employee"], name="uniq_time_settings_company_employee"),
        ]
