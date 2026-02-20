from django.contrib import admin

from core.admin_mixins import IncludeSoftDeletedAdminMixin
from core.money import format_money_cents

from .models import Client, ClientPhone, ClientImportBatch, ClientImportMapping


class ClientPhoneInline(admin.TabularInline):
    model = ClientPhone
    extra = 0


@admin.register(Client)
class ClientAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    def credit_display(self, obj):
        return format_money_cents(obj.credit_cents)
    credit_display.short_description = "Credit"

    def outstanding_display(self, obj):
        return format_money_cents(obj.outstanding_cents)
    outstanding_display.short_description = "Outstanding"

    list_display = ("display_label", "company", "email", "credit_display", "outstanding_display", "deleted_at")
    list_filter = ("company", "state")
    search_fields = ("company_name", "first_name", "last_name", "email")
    inlines = [ClientPhoneInline]



@admin.register(ClientImportBatch)
class ClientImportBatchAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = ("id", "company", "original_filename", "created_at", "imported_at", "uploaded_by")
    list_filter = ("company",)
    search_fields = ("original_filename", "id")


@admin.register(ClientImportMapping)
class ClientImportMappingAdmin(IncludeSoftDeletedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "company", "is_default", "updated_at", "updated_by")
    list_filter = ("company", "is_default")
    search_fields = ("name",)
