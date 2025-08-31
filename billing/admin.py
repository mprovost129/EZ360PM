from django.contrib import admin
from .models import SubscriptionTier, CompanySubscription
from .models import WebhookLog


@admin.register(SubscriptionTier)
class TierAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "stripe_price_id", "sort")
    ordering = ("sort",)
    search_fields = ("name", "slug", "stripe_price_id")
    fieldsets = (
        (None, {"fields": ("name", "slug", "description", "sort")}),
        ("Stripe", {"fields": ("stripe_price_id",)}),
        ("Capabilities", {"fields": ("features", "limits")}),
    )

@admin.register(CompanySubscription)
class CompanySubAdmin(admin.ModelAdmin):
    list_display = ("company", "tier", "status", "current_period_end")
    search_fields = ("company__name", "stripe_customer_id", "stripe_subscription_id")
    

@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "type", "processed_ok", "stripe_event_id", "invoice", "amount", "payment_external_id")
    list_filter = ("processed_ok", "type",)
    search_fields = ("stripe_event_id", "payment_external_id", "message")
    readonly_fields = ("created_at", "processed_at", "raw", "message")
