# billing/models.py
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, Optional

from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------
# Plan / Tier
# ---------------------------------------------------------------------
class SubscriptionTier(models.Model):
    """
    A purchasable subscription tier (mapped to a Stripe Price).
    """
    slug = models.SlugField(unique=True, help_text="URL-safe key, e.g. 'starter', 'pro'.")
    name = models.CharField(max_length=100)
    stripe_price_id = models.CharField(max_length=200, help_text="Stripe Price ID (price_...).")
    description = models.TextField(blank=True)

    # Sorting & visibility
    sort = models.PositiveIntegerField(default=0, help_text="Higher values show higher in plan lists.")
    active = models.BooleanField(default=True)
    trial_days = models.PositiveIntegerField(null=True, blank=True, help_text="Optional trial period (days).")

    # Feature flags / soft limits (kept flexible via JSON)
    features = models.JSONField(default=dict, blank=True)
    limits = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-sort", "name")
        indexes = [
            models.Index(fields=("slug",)),
            models.Index(fields=("active", "sort")),
        ]

    def __str__(self) -> str:
        return self.name

    # --- helpers ---------------------------------------------------------
    def has_feature(self, key: str, default: bool = False) -> bool:
        data = self.features if isinstance(self.features, dict) else {}
        return bool(data.get(key, default))

    def limit_for(self, key: str, default: Optional[int] = None) -> Optional[int]:
        data = self.limits if isinstance(self.limits, dict) else {}
        val = data.get(key, default)
        try:
            return int(val) if val is not None else None
        except (TypeError, ValueError):
            return default


# ---------------------------------------------------------------------
# Company Subscription (synced from Stripe)
# ---------------------------------------------------------------------
class CompanySubscription(models.Model):
    """
    One subscription record per Company; synced from Stripe events.
    """
    STATUS_INCOMPLETE = "incomplete"
    STATUS_TRIALING = "trialing"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_CANCELED = "canceled"
    STATUS_UNPAID = "unpaid"

    STATUS_CHOICES = [
        (STATUS_INCOMPLETE, "Incomplete"),
        (STATUS_TRIALING, "Trialing"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAST_DUE, "Past due"),
        (STATUS_CANCELED, "Canceled"),
        (STATUS_UNPAID, "Unpaid"),
    ]

    company = models.OneToOneField(
        "company.Company",               # <-- updated app label
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    tier = models.ForeignKey(
        SubscriptionTier,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="subscriptions",
    )

    stripe_customer_id = models.CharField(max_length=100, blank=True, db_index=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True, db_index=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INCOMPLETE, db_index=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company subscription"
        verbose_name_plural = "Company subscriptions"
        indexes = [
            models.Index(fields=("status", "current_period_end")),
            models.Index(fields=("stripe_customer_id",)),
            models.Index(fields=("stripe_subscription_id",)),
        ]

    def __str__(self) -> str:
        return f"{self.company} — {self.tier or 'No Tier'} ({self.status})"

    # --- helpers ---------------------------------------------------------
    def is_active(self) -> bool:
        """
        True if status is trialing/active and not expired (or no period end set).
        """
        if self.status not in {self.STATUS_TRIALING, self.STATUS_ACTIVE}:
            return False
        return self.current_period_end is None or self.current_period_end > timezone.now()

    def days_left(self) -> Optional[int]:
        """
        Days left in current period (rounded down), or None if no end.
        """
        if not self.current_period_end:
            return None
        delta = self.current_period_end - timezone.now()
        return max(delta.days, 0)


# ---------------------------------------------------------------------
# Webhook Logs (Stripe)
# ---------------------------------------------------------------------
class WebhookLog(models.Model):
    """
    Raw Stripe webhook event logs, plus resolution outcome and joins for debugging.
    """
    stripe_event_id = models.CharField(max_length=120, unique=True, db_index=True)
    type = models.CharField(max_length=120, db_index=True)
    raw = models.JSONField(default=dict, blank=True)

    # Processing outcome
    processed_ok = models.BooleanField(default=False, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    message = models.TextField(blank=True, default="")

    # Helpful joins (optional)
    invoice = models.ForeignKey(
        "invoices.Invoice",              # <-- updated app label
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="webhook_logs",
    )
    payment_external_id = models.CharField(max_length=200, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("type", "processed_ok")),
            models.Index(fields=("created_at",)),
        ]

    def __str__(self) -> str:
        return f"{self.type} · {self.stripe_event_id}"

    # --- helpers ---------------------------------------------------------
    def mark_processed(self, ok: bool = True, message: str = "") -> None:
        self.processed_ok = ok
        self.processed_at = timezone.now()
        if message:
            self.message = (self.message + "\n" + message).strip() if self.message else message
        self.save(update_fields=["processed_ok", "processed_at", "message"])

    def mark_failed(self, message: str = "") -> None:
        self.mark_processed(ok=False, message=message or "Failed")

