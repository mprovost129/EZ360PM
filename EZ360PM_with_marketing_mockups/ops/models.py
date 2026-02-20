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
    OPS_DASHBOARD = "ops_dashboard", "Ops dashboard"
    PROBE = "probe", "Probe"


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


class OpsAlertSnooze(models.Model):
    """Suppress creation of new alerts for a source (and optionally a company) until a time."""

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by_email = models.EmailField(blank=True, default="")

    source = models.CharField(max_length=32, choices=OpsAlertSource.choices, db_index=True)
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="ops_alert_snoozes")

    snoozed_until = models.DateTimeField(db_index=True)
    reason = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ["-snoozed_until"]
        indexes = [
            models.Index(fields=["source", "snoozed_until"], name="ops_snooze_source_until_idx"),
            models.Index(fields=["company", "source", "snoozed_until"], name="ops_snooze_co_source_until_idx"),
        ]

    def __str__(self) -> str:
        co = self.company.name if self.company else "Platform"
        return f"Snooze {self.source} for {co} until {self.snoozed_until:%Y-%m-%d %H:%M}"


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


class QAIssueSeverity(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class QAIssueStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_PROGRESS = "in_progress", "In progress"
    RESOLVED = "resolved", "Resolved"
    WONT_FIX = "wont_fix", "Won't fix"


class QAIssue(models.Model):
    """Staff QA punchlist issue tracking (V1 launch hardening).

    Goals:
    - Central place to log dead ends / bugs / UX gaps found during end-to-end QA.
    - Lightweight; does not replace a full issue tracker, but is available in-prod.
    - Optional company scoping for tenant-specific issues.
    """

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now, db_index=True)

    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="qa_issues")

    status = models.CharField(max_length=24, choices=QAIssueStatus.choices, default=QAIssueStatus.OPEN, db_index=True)
    severity = models.CharField(max_length=16, choices=QAIssueSeverity.choices, default=QAIssueSeverity.MEDIUM, db_index=True)

    area = models.CharField(max_length=64, blank=True, default="", db_index=True, help_text="Module/area (e.g., Invoices, Banking, Time).")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    discovered_by_email = models.EmailField(blank=True, default="")
    assigned_to_email = models.EmailField(blank=True, default="")

    related_url = models.URLField(blank=True, default="")
    steps_to_reproduce = models.TextField(blank=True, default="")
    expected_behavior = models.TextField(blank=True, default="")
    actual_behavior = models.TextField(blank=True, default="")

    resolution_notes = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Keep index names <= 30 chars for maximum cross-DB compatibility.
            models.Index(fields=["status", "severity", "created_at"], name="ops_qai_st_sev_cr_idx"),
            models.Index(fields=["company", "status", "created_at"], name="ops_qai_co_st_cr_idx"),
            models.Index(fields=["area", "status", "created_at"], name="ops_qai_ar_st_cr_idx"),
        ]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.title}"

    def touch(self, *, save: bool = True) -> None:
        self.updated_at = timezone.now()
        if save:
            self.save(update_fields=["updated_at"])

    def mark_resolved(self, *, notes: str = "", by_email: str | None = None, save: bool = True) -> None:
        self.status = QAIssueStatus.RESOLVED
        self.resolved_at = timezone.now()
        if notes:
            self.resolution_notes = notes
        if by_email:
            self.assigned_to_email = (by_email or "").strip()[:254]
        self.updated_at = timezone.now()
        if save:
            self.save(update_fields=["status", "resolved_at", "resolution_notes", "assigned_to_email", "updated_at"])




class OpsCheckKind(models.TextChoices):
    SMOKE = "smoke", "Smoke Test"
    INVARIANTS = "invariants", "Invariants"
    IDEMPOTENCY = "idempotency", "Idempotency Scan"
    READINESS = "readiness", "Readiness Check"
    TEMPLATE_SANITY = "template_sanity", "Template sanity"
    URL_SANITY = "url_sanity", "URL sanity"


class OpsCheckRun(models.Model):
    """Historical record of staff-run ops checks.

    Used for launch evidence and for spotting regressions between builds.
    """

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_by_email = models.EmailField(blank=True, default="")

    # Company is optional (readiness is global).
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.SET_NULL, related_name="ops_check_runs")

    kind = models.CharField(max_length=32, choices=OpsCheckKind.choices, db_index=True)
    args = models.JSONField(default=dict, blank=True)

    is_ok = models.BooleanField(default=False, db_index=True)
    duration_ms = models.IntegerField(default=0)
    output_text = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["kind", "created_at"]),
            models.Index(fields=["company", "created_at"]),
            models.Index(fields=["is_ok", "created_at"]),
        ]

    def __str__(self) -> str:
        company = self.company_id or "-"
        return f"{self.kind} ({company}) @ {self.created_at:%Y-%m-%d %H:%M}"


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


class OpsProbeKind(models.TextChoices):
    SENTRY_TEST_ERROR = "sentry_test_error", "Sentry test error"
    ALERT_TEST = "alert_test", "Alert test"


class OpsProbeStatus(models.TextChoices):
    TRIGGERED = "triggered", "Triggered"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class OpsProbeEvent(models.Model):
    """Staff-triggered probes used to validate monitoring and alerts."""

    id = models.BigAutoField(primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    kind = models.CharField(max_length=32, choices=OpsProbeKind.choices, db_index=True)
    status = models.CharField(max_length=16, choices=OpsProbeStatus.choices, default=OpsProbeStatus.TRIGGERED, db_index=True)

    initiated_by_email = models.EmailField(max_length=254, blank=True, default="")
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["kind", "status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.kind} ({self.status})"

class SiteConfig(models.Model):
    """Singleton settings for Ops alert routing.

    Purpose: make alert routing (email/webhook) configurable from the Ops UI without
    requiring environment variable changes.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    # Webhook routing (Slack/Discord/custom)
    ops_alert_webhook_enabled = models.BooleanField(default=False)
    ops_alert_webhook_url = models.URLField(blank=True, default="")
    ops_alert_webhook_timeout_seconds = models.DecimalField(max_digits=5, decimal_places=2, default=2.50)

    # Email routing (admin alert emails)
    ops_alert_email_enabled = models.BooleanField(default=False)
    ops_alert_email_recipients = models.TextField(
        blank=True,
        default="",
        help_text="Comma-separated list of recipient email addresses.",
    )
    ops_alert_email_min_level = models.CharField(
        max_length=16,
        choices=OpsAlertLevel.choices,
        default=OpsAlertLevel.ERROR,
        help_text="Minimum alert level to email (inclusive).",
    )

    # Noise filters (best-effort): skip creating alerts that match these patterns.
    ops_alert_noise_path_prefixes = models.TextField(
        blank=True,
        default="",
        help_text="One per line. If details.path starts with any prefix, the alert will be ignored.",
    )
    ops_alert_noise_user_agents = models.TextField(
        blank=True,
        default="",
        help_text="One per line. If details.user_agent contains any token (case-insensitive), the alert will be ignored.",
    )

    # Deduplication: if an identical alert (source+title+company) is created within this
    # window and the prior alert is still open, we increment a counter instead of creating
    # a new row.
    ops_alert_dedup_minutes = models.PositiveSmallIntegerField(
        default=10,
        help_text="Deduplicate identical open alerts within this many minutes (0 disables).",
    )

    # Retention helpers (used by management command).
    ops_alert_prune_resolved_after_days = models.PositiveSmallIntegerField(
        default=30,
        help_text="Resolved alerts older than this many days may be pruned.",
    )

    ops_snooze_prune_after_days = models.PositiveSmallIntegerField(
        default=30,
        help_text="Expired snoozes older than this many days may be pruned (for audit cleanliness).",
    )


    # Maintenance mode (launch/ops): when enabled, non-staff users see a maintenance page.
    maintenance_mode_enabled = models.BooleanField(
        default=False,
        help_text="When enabled, the site shows a maintenance notice to non-staff users.",
    )
    maintenance_message = models.TextField(
        blank=True,
        default="",
        help_text="Optional message displayed on the maintenance page.",
    )
    maintenance_allow_staff = models.BooleanField(
        default=True,
        help_text="If enabled, staff users may continue to use the app during maintenance.",
    )

    # ------------------------------------------------------------------
    # Billing & onboarding controls (platform-wide)
    # ------------------------------------------------------------------
    billing_trial_days = models.PositiveSmallIntegerField(
        default=14,
        help_text="Number of free-trial days for new subscriptions created via Stripe Checkout.",
    )

    # ------------------------------------------------------------------
    # Ops notification emails (high-signal events, not alerts)
    # ------------------------------------------------------------------
    ops_notify_email_enabled = models.BooleanField(
        default=False,
        help_text="When enabled, EZ360PM sends owner notifications for key lifecycle events (signups, conversions).",
    )
    ops_notify_email_recipients = models.TextField(
        blank=True,
        default="",
        help_text="Comma-separated list of recipient email addresses for ops notifications (separate from alerts).",
    )
    ops_notify_on_company_signup = models.BooleanField(
        default=True,
        help_text="Notify when a new company is created (trial started).",
    )
    ops_notify_on_subscription_active = models.BooleanField(
        default=True,
        help_text="Notify when a subscription becomes active (first successful renewal/payment).",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ops Site Config"
        verbose_name_plural = "Ops Site Config"

    def __str__(self) -> str:
        return "Ops Site Config"

    @classmethod
    def get_solo(cls) -> "SiteConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def email_recipients_list(self) -> list[str]:
        raw = self.ops_alert_email_recipients or ""
        parts = [p.strip() for p in raw.split(",")]
        return [p for p in parts if p]

    def notify_recipients_list(self) -> list[str]:
        raw = self.ops_notify_email_recipients or ""
        parts = [p.strip() for p in raw.split(",")]
        return [p for p in parts if p]

