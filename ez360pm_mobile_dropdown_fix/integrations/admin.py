from django.contrib import admin

from .models import (
    BankAccount,
    BankConnection,
    BankReconciliationPeriod,
    BankRule,
    BankTransaction,
    DropboxConnection,
    IntegrationConfig,
)


@admin.register(DropboxConnection)
class DropboxConnectionAdmin(admin.ModelAdmin):
    list_display = ("company", "is_active", "account_id", "expires_at", "updated_at")
    search_fields = ("company__name", "account_id")
    list_filter = ("is_active",)


@admin.register(IntegrationConfig)
class IntegrationConfigAdmin(admin.ModelAdmin):
    list_display = ("company", "use_dropbox_for_project_files", "updated_at")
    search_fields = ("company__name",)


@admin.register(BankConnection)
class BankConnectionAdmin(admin.ModelAdmin):
    list_display = ("company", "provider", "is_active", "last_sync_at", "last_sync_status")
    search_fields = ("company__name", "provider")
    list_filter = ("provider", "is_active", "last_sync_status")


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("connection", "name", "mask", "type", "subtype", "is_active", "updated_at")
    search_fields = ("name", "mask", "account_id", "connection__company__name")
    list_filter = ("type", "subtype", "is_active")


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ("account", "posted_date", "name", "amount_cents", "status", "is_pending")
    search_fields = ("name", "transaction_id", "account__name", "account__connection__company__name")
    list_filter = ("status", "is_pending")
    date_hierarchy = "posted_date"


@admin.register(BankRule)
class BankRuleAdmin(admin.ModelAdmin):
    list_display = ("company", "is_active", "priority", "match_field", "match_type", "match_text", "action")
    search_fields = ("match_text", "company__name")
    list_filter = ("is_active", "action", "match_field", "match_type")


@admin.register(BankReconciliationPeriod)
class BankReconciliationPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "start_date",
        "end_date",
        "status",
        "locked_at",
        "snapshot_bank_outflow_cents",
        "snapshot_expense_total_cents",
    )
    search_fields = ("company__name",)
    list_filter = ("status",)
    date_hierarchy = "start_date"
