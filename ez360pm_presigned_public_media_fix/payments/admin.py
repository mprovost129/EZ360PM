from django.contrib import admin

from core.money import format_money_cents

from core.admin_mixins import IncludeSoftDeletedAdminMixin

from .models import ClientCreditApplication, ClientCreditLedgerEntry, Payment, PaymentRefund, Refund, StripeConnectAccount


@admin.register(Payment)
class PaymentAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    def amount_display(self, obj):
        return format_money_cents(obj.amount_display)
    amount_display.short_description = "Amount"

    list_display = ("id", "company", "client", "invoice", "amount_display", "status", "payment_date", "created_at")
    list_filter = ("status", "method", "company")
    search_fields = ("id", "invoice__number", "client__first_name", "client__last_name", "client__company_name")


@admin.register(ClientCreditLedgerEntry)
class ClientCreditLedgerEntryAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    def cents_delta_display(self, obj):
        return format_money_cents(obj.cents_delta)
    cents_delta_display.short_description = "Delta"

    list_display = ("id", "company", "client", "invoice", "cents_delta_display", "reason", "created_at")
    list_filter = ("company",)
    search_fields = ("client__first_name", "client__last_name", "client__company_name", "invoice__number", "reason")


@admin.register(ClientCreditApplication)
class ClientCreditApplicationAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    def cents_display(self, obj):
        return format_money_cents(obj.cents)
    cents_display.short_description = "Applied"

    list_display = ("id", "company", "client", "invoice", "cents_display", "applied_at", "created_at")
    list_filter = ("company",)
    search_fields = ("client__first_name", "client__last_name", "client__company_name", "invoice__number", "memo")


@admin.register(Refund)
class RefundAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    def cents_display(self, obj):
        return format_money_cents(obj.cents)
    cents_display.short_description = "Amount"

    list_display = ("id", "company", "payment", "cents_display", "status", "created_at")
    list_filter = ("company", "status")


@admin.register(PaymentRefund)
class PaymentRefundAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    def cents_display(self, obj):
        return format_money_cents(obj.cents)
    cents_display.short_description = "Amount"

    list_display = ("id", "company", "payment", "cents_display", "status", "stripe_refund_id", "created_at")
    list_filter = ("status", "company")
    search_fields = ("stripe_refund_id", "payment__stripe_payment_intent_id", "payment__stripe_charge_id")


@admin.register(StripeConnectAccount)
class StripeConnectAccountAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "company",
        "status",
        "stripe_account_id",
        "charges_enabled",
        "payouts_enabled",
        "details_submitted",
        "last_sync_at",
        "updated_at",
    )
    list_filter = ("status", "charges_enabled", "payouts_enabled")
    search_fields = ("stripe_account_id", "company__name")
