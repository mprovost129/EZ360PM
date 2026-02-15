from django.contrib import admin

from core.admin_mixins import IncludeSoftDeletedAdminMixin

from .models import ClientCreditApplication, ClientCreditLedgerEntry, Payment, PaymentRefund, Refund


@admin.register(Payment)
class PaymentAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = ("id", "company", "client", "invoice", "amount_cents", "status", "payment_date", "created_at")
    list_filter = ("status", "method", "company")
    search_fields = ("id", "invoice__number", "client__first_name", "client__last_name", "client__company_name")


@admin.register(ClientCreditLedgerEntry)
class ClientCreditLedgerEntryAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = ("id", "company", "client", "invoice", "cents_delta", "reason", "created_at")
    list_filter = ("company",)
    search_fields = ("client__first_name", "client__last_name", "client__company_name", "invoice__number", "reason")


@admin.register(ClientCreditApplication)
class ClientCreditApplicationAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = ("id", "company", "client", "invoice", "cents", "applied_at", "created_at")
    list_filter = ("company",)
    search_fields = ("client__first_name", "client__last_name", "client__company_name", "invoice__number", "memo")


@admin.register(Refund)
class RefundAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = ("id", "company", "payment", "cents", "status", "created_at")
    list_filter = ("company", "status")


@admin.register(PaymentRefund)
class PaymentRefundAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = ("id", "company", "payment", "cents", "status", "stripe_refund_id", "created_at")
    list_filter = ("status", "company")
    search_fields = ("stripe_refund_id", "payment__stripe_payment_intent_id", "payment__stripe_charge_id")
