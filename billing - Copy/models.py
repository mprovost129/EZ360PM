# billing/models.py
from __future__ import annotations

from django.db import models
from django.utils import timezone

from core.models import SyncModel
from companies.models import Company


class PlanCode(models.TextChoices):
    # Phase 3J+ (Stripe tiers)
    STARTER = "starter", "Starter"
    PROFESSIONAL = "professional", "Professional"
    PREMIUM = "premium", "Premium"


class BillingInterval(models.TextChoices):
    MONTH = "month", "Monthly"
    YEAR = "year", "Annual"


class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing", "Trialing"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past Due"
    CANCELED = "canceled", "Canceled"
    ENDED = "ended", "Ended"



class PlanCatalog(models.Model):
    """DB-backed catalog for plan pricing + Stripe identifiers.

    Stripe remains the billing authority. This model is the *display + routing* authority
    inside EZ360PM so pricing/IDs can be changed without redeploying code.

    Notes:
    - `code` must match `PlanCode` values.
    - Stripe price IDs are optional; if blank, we fall back to settings-based lookup.
    """

    code = models.CharField(max_length=20, choices=PlanCode.choices, unique=True)
    name = models.CharField(max_length=50)

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=10)

    monthly_price = models.DecimalField(max_digits=8, decimal_places=2)
    annual_price = models.DecimalField(max_digits=8, decimal_places=2)

    # Stripe price IDs for the base subscription plan.
    stripe_monthly_price_id = models.CharField(max_length=120, blank=True, default="")
    stripe_annual_price_id = models.CharField(max_length=120, blank=True, default="")

    included_seats = models.PositiveSmallIntegerField(default=1)
    trial_days = models.PositiveSmallIntegerField(default=14)

    class Meta:
        ordering = ["sort_order", "monthly_price"]
        verbose_name = "Plan (catalog)"
        verbose_name_plural = "Plans (catalog)"

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name} ({self.code})"


class SeatAddonConfig(models.Model):
    """Singleton configuration for extra seat pricing + Stripe identifiers."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    monthly_price = models.DecimalField(max_digits=8, decimal_places=2, default=9.99)
    annual_price = models.DecimalField(max_digits=8, decimal_places=2, default=99.99)

    stripe_monthly_price_id = models.CharField(max_length=120, blank=True, default="")
    stripe_annual_price_id = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        verbose_name = "Seat add-on config"
        verbose_name_plural = "Seat add-on config"

    def __str__(self) -> str:  # pragma: no cover
        return "Seat add-on config"



class CompanySubscription(SyncModel):
    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="subscription")

    # Base plan tier for the company (exactly one).
    plan = models.CharField(max_length=20, choices=PlanCode.choices, default=PlanCode.STARTER)

    # Billing interval for the base plan (informational + UI; Stripe is source of truth).
    billing_interval = models.CharField(
        max_length=10,
        choices=BillingInterval.choices,
        default=BillingInterval.MONTH,
    )

    # Extra seats purchased as a Stripe add-on subscription item quantity.
    # Seat limit = included_seats(plan) + extra_seats
    extra_seats = models.PositiveIntegerField(default=0)

    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices, default=SubscriptionStatus.TRIALING)

    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)

    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    stripe_customer_id = models.CharField(max_length=80, blank=True, default="")
    stripe_subscription_id = models.CharField(max_length=80, blank=True, default="")

    # Stripe cancellation tracking
    stripe_cancel_at_period_end = models.BooleanField(default=False)
    stripe_cancel_at = models.DateTimeField(null=True, blank=True)
    stripe_canceled_at = models.DateTimeField(null=True, blank=True)

    # Ops notification marker (platform owner)
    ops_notified_active_at = models.DateTimeField(null=True, blank=True)

    # license enforcement (desktop)
    last_license_check_at = models.DateTimeField(null=True, blank=True)

    # ------------------------------------------------------------------
    # Admin overrides (post-launch support)
    # ------------------------------------------------------------------
    # "Comped" = free instance granted by staff (e.g., friends/family, internal use).
    is_comped = models.BooleanField(default=False)
    comped_until = models.DateTimeField(null=True, blank=True)
    comped_reason = models.CharField(max_length=255, blank=True, default="")

    # Simple discount metadata (informational). Stripe promotion codes are supported
    # in Checkout, but we keep these fields so staff can track manual discounts.
    discount_percent = models.PositiveIntegerField(default=0)  # 0..100
    discount_note = models.CharField(max_length=255, blank=True, default="")
    discount_ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["plan", "billing_interval", "status"]),
            models.Index(fields=["trial_ends_at"]),
        ]

    def is_in_trial(self) -> bool:
        if self.status != SubscriptionStatus.TRIALING:
            return False
        if not self.trial_ends_at:
            return True
        return timezone.now() < self.trial_ends_at

    def is_comped_active(self) -> bool:
        if not self.is_comped:
            return False
        if not self.comped_until:
            return True
        return timezone.now() < self.comped_until

    def discount_is_active(self) -> bool:
        pct = int(self.discount_percent or 0)
        if pct <= 0:
            return False
        if not self.discount_ends_at:
            return True
        return timezone.now() < self.discount_ends_at

    def is_active_or_trial(self) -> bool:
        # Comped access always bypasses billing lock.
        if self.is_comped_active():
            return True
        return self.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING} and (
            self.status == SubscriptionStatus.ACTIVE or self.is_in_trial()
        )


class BillingWebhookEvent(models.Model):
    stripe_event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=200, blank=True, default="")
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    ok = models.BooleanField(default=False)
    error = models.TextField(blank=True, default="")
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["event_type"]),
            models.Index(fields=["received_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type or 'stripe.event'} ({self.stripe_event_id})"
