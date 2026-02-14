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
    AUTH = "auth", "Auth"
    THROTTLE = "throttle", "Throttle"
    SLOW_REQUEST = "slow_request", "Slow request"


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
