from __future__ import annotations

from django.contrib import admin

from .models import CompanySubscription, BillingWebhookEvent


@admin.register(CompanySubscription)
class CompanySubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "plan",
        "billing_interval",
        "is_comped",
        "comped_until",
        "discount_percent",
        "extra_seats",
        "status",
        "trial_ends_at",
        "current_period_end",
        "stripe_customer_id",
    )
    list_filter = ("plan", "billing_interval", "status")
    search_fields = ("company__name", "stripe_customer_id", "stripe_subscription_id")
    readonly_fields = ("created_at", "updated_at", "deleted_at")


@admin.register(BillingWebhookEvent)
class BillingWebhookEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "stripe_event_id", "ok", "received_at", "processed_at")
    list_filter = ("ok", "event_type")
    search_fields = ("stripe_event_id", "event_type")
    readonly_fields = ("stripe_event_id", "event_type", "received_at", "processed_at", "payload_json", "ok", "error")
