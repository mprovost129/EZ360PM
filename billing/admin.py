# billing/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils.safestring import mark_safe
import json

from .models import SubscriptionTier, CompanySubscription, WebhookLog


@admin.register(SubscriptionTier)
class SubscriptionTierAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "stripe_price_id", "sort")
    ordering = ("sort",)
    search_fields = ("name", "slug", "stripe_price_id")
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "sort")}),
        ("Stripe", {"fields": ("stripe_price_id",)}),
        ("Capabilities", {"fields": ("features", "limits")}),
    )


@admin.register(CompanySubscription)
class CompanySubscriptionAdmin(admin.ModelAdmin):
    list_display = ("company", "tier", "status", "current_period_end", "cancel_at_period_end")
    list_filter = ("status", "cancel_at_period_end")
    search_fields = ("company__name", "stripe_customer_id", "stripe_subscription_id")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "current_period_end"


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "type",
        "processed_ok",
        "stripe_event_id",
        "invoice",
        "amount",
        "payment_external_id",
    )
    list_filter = ("processed_ok", "type")
    search_fields = ("stripe_event_id", "payment_external_id", "message")
    readonly_fields = ("created_at", "processed_at", "raw_pretty", "message")
    date_hierarchy = "created_at"

    def raw_pretty(self, obj: WebhookLog) -> str:
        """Pretty-print raw JSON payload with indentation for admin."""
        try:
            pretty = json.dumps(obj.raw, indent=2, sort_keys=True)
        except Exception:
            pretty = str(obj.raw)
        return mark_safe(f"<pre style='white-space: pre-wrap;'>{pretty}</pre>")

    raw_pretty.short_description = "Raw event" # type: ignore
