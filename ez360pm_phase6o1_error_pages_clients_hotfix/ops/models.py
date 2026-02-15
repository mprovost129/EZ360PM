from __future__ import annotations

from django.db import models
from django.utils import timezone

from companies.models import Company


class OpsAlertLevel(models.TextChoices):
    INFO = "info", "Info"
    WARN = "warn", "Warning"
    ERROR = "error", "Error"


class OpsAlertSource(models.TextChoices):
    STRIPE_WEBHOOK = "stripe_webhook", "Stripe webhook"
    EMAIL = "email", "Email"
    SLOW_REQUEST = "slow_request", "Slow request"
    AUTH = "auth", "Auth"
    THROTTLE = "throttle", "Throttle"
    LAUNCH_GATE = "launch_gate", "Launch gate"
    BACKUP = "backup", "Backup"
    RESTORE_TEST = "restore_test", "Restore test"


class OpsAlertEvent(models.Model):
    """Lightweight staff-visible ops alerts.

    Goals:
    - Capture *actionable* failures and key degradations.
    - Safe for prod; never blocks request paths.
    - Supports acknowledgement (resolved) workflow.
    """

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    level = models.CharField(max_length=16, choices=OpsAlertLevel.choices, default=OpsAlertLevel.ERROR, db_index=True)
    source = models.CharField(max_length=32, choices=OpsAlertSource.choices, default=OpsAlertSource.EMAIL, db_index=True)

    # Company is optional because some alerts are platform-wide.
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="ops_alerts")

    title = models.CharField(max_length=200)
    message = models.TextField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)

    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by_email = models.EmailField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source", "level", "created_at"]),
            models.Index(fields=["company", "is_resolved", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.level}] {self.source}: {self.title}"

    def resolve(self, *, by_email: str | None = None, save: bool = True) -> None:
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolved_by_email = (by_email or "").strip()[:254]
        if save:
            self.save(update_fields=["is_resolved", "resolved_at", "resolved_by_email"])


class LaunchGateItem(models.Model):
    """Staff-managed launch readiness gate checklist.

    This is a *process* artifact that complements the automated checks in
    `core.launch_checks.run_launch_checks()`.
    """

    key = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    is_complete = models.BooleanField(default=False, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    completed_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_launch_gate_items",
    )

    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["key"]

    def mark_complete(self, *, user=None):
        self.is_complete = True
        self.completed_at = timezone.now()
        if user is not None:
            self.completed_by = user
        self.updated_at = timezone.now()

    def mark_incomplete(self):
        self.is_complete = False
        self.completed_at = None
        self.completed_by = None
        self.updated_at = timezone.now()

    def __str__(self) -> str:
        return f"{self.key}: {self.title}"


class BackupRunStatus(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILED = "failed", "Failed"


class BackupRun(models.Model):
    """Optional audit trail of backups.

    EZ360PM does not (yet) run backups itself. This model exists so staff can:
    - record manual/scheduled backup runs performed by the platform/host
    - capture failures in a structured way
    - confirm retention + restore process before launch
    """

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    status = models.CharField(max_length=16, choices=BackupRunStatus.choices, default=BackupRunStatus.SUCCESS, db_index=True)

    storage = models.CharField(max_length=64, blank=True, default="")
    size_bytes = models.BigIntegerField(default=0)
    notes = models.TextField(blank=True, default="")
    initiated_by_email = models.EmailField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Backup {self.created_at:%Y-%m-%d %H:%M} ({self.status})"


class RestoreTestOutcome(models.TextChoices):
    PASS = "pass", "Pass"
    FAIL = "fail", "Fail"


class BackupRestoreTest(models.Model):
    """Record of a restore test (required for Launch Readiness Gate)."""

    tested_at = models.DateTimeField(default=timezone.now, db_index=True)
    outcome = models.CharField(max_length=8, choices=RestoreTestOutcome.choices, default=RestoreTestOutcome.PASS, db_index=True)
    notes = models.TextField(blank=True, default="")
    tested_by_email = models.EmailField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-tested_at"]
        indexes = [
            models.Index(fields=["outcome", "tested_at"]),
        ]

    def __str__(self) -> str:
        return f"Restore test {self.tested_at:%Y-%m-%d} ({self.outcome})"


class ReleaseNote(models.Model):
    """Staff-maintained release notes.

    Purpose:
    - Provide human-readable context for a deployment (what changed, what to verify).
    - Show current build metadata in Ops without relying on external tooling.
    - Keep a lightweight audit trail for promotions.

    This is not a changelog generator; it's intentionally manual.
    """

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    environment = models.CharField(
        max_length=24,
        blank=True,
        default="",
        help_text="Deployment environment (dev/staging/prod). Optional, but recommended.",
        db_index=True,
    )
    build_version = models.CharField(max_length=64, blank=True, default="", db_index=True)
    build_sha = models.CharField(max_length=64, blank=True, default="", db_index=True)

    title = models.CharField(max_length=200)
    notes = models.TextField(blank=True, default="")

    is_published = models.BooleanField(
        default=True,
        help_text="If disabled, note remains visible to staff but excluded from summaries.",
        db_index=True,
    )

    created_by_email = models.EmailField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["environment", "created_at"]),
            models.Index(fields=["build_version", "created_at"]),
            models.Index(fields=["build_sha", "created_at"]),
        ]

    def __str__(self) -> str:
        env = self.environment or "unknown"
        v = self.build_version or "?"
        return f"{env} {v}: {self.title}"


class UserPresence(models.Model):
    """Lightweight presence row per (user, company).

    Used for staff-facing SLO dashboards (active users in the last N minutes).
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="presence_rows",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name="presence_rows",
    )

    last_seen = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        unique_together = [("user", "company")]
        indexes = [
            models.Index(fields=["company", "last_seen"]),
            models.Index(fields=["last_seen"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} @ {self.company.name} ({self.last_seen:%Y-%m-%d %H:%M})"

    @classmethod
    def touch(cls, *, user, company, when=None) -> None:
        """Best-effort upsert."""

        when = when or timezone.now()
        try:
            updated = cls.objects.filter(user=user, company=company).update(last_seen=when)
            if not updated:
                cls.objects.create(user=user, company=company, last_seen=when)
        except Exception:
            # If create races with another request, fall back to update.
            try:
                cls.objects.filter(user=user, company=company).update(last_seen=when)
            except Exception:
                return


class OpsEmailTestStatus(models.TextChoices):
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


class OpsEmailTest(models.Model):
    """Audit log for Ops-triggered email test sends.

    Goal: provide an in-app, staff-only way to validate email configuration
    (SMTP/transactional provider) without shell access.
    """

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    to_email = models.EmailField(max_length=254)
    subject = models.CharField(max_length=200)
    backend = models.CharField(max_length=255, blank=True, default="")
    from_email = models.CharField(max_length=254, blank=True, default="")

    status = models.CharField(max_length=20, choices=OpsEmailTestStatus.choices, default=OpsEmailTestStatus.SENT)
    latency_ms = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")
    initiated_by_email = models.EmailField(max_length=254, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.status} → {self.to_email}"
