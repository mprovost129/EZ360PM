from django.contrib import admin

from core.money import format_money_cents

from .models import Account, JournalEntry, JournalLine


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0

    def debit_display(self, obj):
        return format_money_cents(obj.debit_cents)
    debit_display.short_description = "Debit"

    def credit_display(self, obj):
        return format_money_cents(obj.credit_cents)
    credit_display.short_description = "Credit"

    readonly_fields = ("debit_display", "credit_display")
    fields = ("account", "description", "debit_display", "credit_display", "client", "project")


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("company", "code", "name", "type", "normal_balance", "is_active")
    list_filter = ("company", "type", "is_active")
    search_fields = ("code", "name")


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("company", "entry_date", "memo", "source_type", "source_id")
    list_filter = ("company", "source_type", "entry_date")
    search_fields = ("memo", "source_type", "source_id")
    inlines = [JournalLineInline]
