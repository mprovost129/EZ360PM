from django.db import models
from django.utils import timezone
from django.conf import settings

class SubscriptionTier(models.Model):
    slug = models.SlugField(unique=True)      # e.g., "starter", "pro"
    name = models.CharField(max_length=100)
    stripe_price_id = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    sort = models.PositiveIntegerField(default=0)  # higher means higher tier

    # NEW
    features = models.JSONField(default=dict, blank=True)  # {"estimates": true, "client_portal": false}
    limits   = models.JSONField(default=dict, blank=True)  # {"max_clients": 50, "max_projects": 50}

    def __str__(self):
        return self.name

class CompanySubscription(models.Model):
    STATUS_CHOICES = [
        ("incomplete", "Incomplete"),
        ("trialing", "Trialing"),
        ("active", "Active"),
        ("past_due", "Past due"),
        ("canceled", "Canceled"),
        ("unpaid", "Unpaid"),
    ]

    company = models.OneToOneField("core.Company", on_delete=models.CASCADE, related_name="subscription")
    tier = models.ForeignKey(SubscriptionTier, null=True, blank=True, on_delete=models.SET_NULL)

    stripe_customer_id = models.CharField(max_length=100, blank=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="incomplete")
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def is_active(self) -> bool:
        return self.status in {"trialing", "active"} and (self.current_period_end is None or self.current_period_end > timezone.now())

    def __str__(self):
        return f"{self.company} — {self.tier or 'No Tier'} ({self.status})"
    
    
class WebhookLog(models.Model):
    stripe_event_id = models.CharField(max_length=120, unique=True, db_index=True)
    type = models.CharField(max_length=120, db_index=True)
    raw = models.JSONField(default=dict, blank=True)

    # outcome
    processed_ok = models.BooleanField(default=False, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    message = models.TextField(blank=True, default="")

    # helpful joins (optional)
    invoice = models.ForeignKey(
        "core.Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="webhook_logs"
    )
    payment_external_id = models.CharField(max_length=200, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.type} · {self.stripe_event_id}"