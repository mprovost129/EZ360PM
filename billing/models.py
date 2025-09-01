# billing/models.py
from __future__ import annotations

from typing import Any

from django.db import models
from django.utils import timezone


class SubscriptionTier(models.Model):
    """
    A purchasable subscription tier (mapped to a Stripe Price).
    """
    slug = models.SlugField(unique=True, help_text="URL-safe key, e.g. 'starter', 'pro'.")
    name = models.CharField(max_length=100)
    stripe_price_id = models.CharField(max_length=200, help_text="Stripe Price ID (price_...).")
    description = models.TextField(blank=True)
    sort = models.PositiveIntegerField(default=0, help_text="Higher values show higher in plan lists.")

    # Feature flags / soft limits (kept flexible via JSON)
    features = models.JSONField(default=dict, blank=True)  # e.g. {"estimates": true, "client_portal": false}
    limits = models.JSONField(default=dict, blank=True)    # e.g. {"max_clients": 50, "max_projects": 50}

    class Meta:
        ordering = ("-sort", "name")
        indexes = [
            models.Index(fields=("slug",)),
        ]

    def __str__(self) -> str:
        return self.name

    # Convenience helpers
    def has_feature(self, key: str, default: bool = False) -> bool:
        v = self.features.get(key, default) if isinstance(self.features, dict) else default
        return bool(v)

    def limit_for(self, key: str, default: int | None = None) -> int | None:
        v = self.limits.get(key, default) if isinstance(self.limits, dict) else default
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return default


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
        "core.Company",
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

    def __str__(self) -> str:
        return f"{self.company} — {self.tier or 'No Tier'} ({self.status})"

    def is_active(self) -> bool:
        """
        Active if status is trialing/active and not expired (or no period end set).
        """
        now = timezone.now()
        if self.status not in {self.STATUS_TRIALING, self.STATUS_ACTIVE}:
            return False
        return self.current_period_end is None or self.current_period_end > now


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
        "core.Invoice",
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
        ]

    def __str__(self) -> str:
        return f"{self.type} · {self.stripe_event_id}"
