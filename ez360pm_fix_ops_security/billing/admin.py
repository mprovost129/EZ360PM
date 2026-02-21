from __future__ import annotations

from django.contrib import admin

from .models import CompanySubscription, BillingWebhookEvent, PlanCatalog, SeatAddonConfig


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


@admin.register(PlanCatalog)
class PlanCatalogAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "is_active",
        "monthly_price",
        "annual_price",
        "included_seats",
        "trial_days",
        "stripe_monthly_price_id",
        "stripe_annual_price_id",
    )
    list_filter = ("is_active", "code")
    search_fields = ("code", "name")
    ordering = ("sort_order",)


@admin.register(SeatAddonConfig)
class SeatAddonConfigAdmin(admin.ModelAdmin):
    list_display = ("monthly_price", "annual_price", "stripe_monthly_price_id", "stripe_annual_price_id")
