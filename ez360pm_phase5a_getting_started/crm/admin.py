from django.contrib import admin

from .models import Client, ClientPhone, Vendor, ClientImportBatch, ClientImportMapping


class ClientPhoneInline(admin.TabularInline):
    model = ClientPhone
    extra = 0


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("display_label", "company", "email", "credit_cents", "outstanding_cents", "deleted_at")
    list_filter = ("company", "state")
    search_fields = ("company_name", "first_name", "last_name", "email")
    inlines = [ClientPhoneInline]


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "email", "phone", "deleted_at")
    list_filter = ("company",)
    search_fields = ("name", "email", "phone")


@admin.register(ClientImportBatch)
class ClientImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "original_filename", "created_at", "imported_at", "uploaded_by")
    list_filter = ("company",)
    search_fields = ("original_filename", "id")


@admin.register(ClientImportMapping)
class ClientImportMappingAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "is_default", "updated_at", "updated_by")
    list_filter = ("company", "is_default")
    search_fields = ("name",)
