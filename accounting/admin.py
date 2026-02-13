from django.contrib import admin

from .models import Account, JournalEntry, JournalLine


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    readonly_fields = ("debit_cents", "credit_cents")
    fields = ("account", "description", "debit_cents", "credit_cents", "client", "project")


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
