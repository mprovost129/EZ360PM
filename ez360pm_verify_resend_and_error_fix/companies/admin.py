from django.contrib import admin

from .models import Company, CompanyInvite, EmployeeProfile


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "require_2fa_for_admins_managers", "require_2fa_for_all", "created_at")
    list_filter = ("is_active", "require_2fa_for_admins_managers", "require_2fa_for_all")
    search_fields = ("name",)
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("name", "logo", "is_active")}),
        ("Branding", {"fields": ("email_from_name", "email_from_address")}),
        ("Address", {"fields": ("address1", "address2", "city", "state", "zip_code")}),
        ("Financial Defaults", {"fields": ("default_invoice_due_days", "default_estimate_valid_days", "default_sales_tax_percent", "default_line_items_taxable")}),
        ("Security Policy", {"fields": ("require_2fa_for_admins_managers", "require_2fa_for_all")}),
        ("System", {"fields": ("id", "created_at", "updated_at")}),
    )


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = ("username_public", "company", "role", "force_2fa", "is_active")
    list_filter = ("company", "role", "force_2fa", "is_active")
    search_fields = ("username_public", "display_name", "user__email")
    readonly_fields = ("id", "created_at", "updated_at")

    fieldsets = (
        (None, {"fields": ("company", "user", "display_name", "username_public", "role", "is_active")}),
        ("Security", {"fields": ("force_2fa",)}),
        ("System", {"fields": ("id", "created_at", "updated_at")}),
    )


@admin.register(CompanyInvite)
class CompanyInviteAdmin(admin.ModelAdmin):
    list_display = ("email", "company", "role", "accepted_at", "created_at")
    list_filter = ("company", "role")
    search_fields = ("email",)
    readonly_fields = ("id", "created_at", "updated_at")
