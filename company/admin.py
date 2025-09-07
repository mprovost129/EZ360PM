# company/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import QuerySet

from .models import Company, CompanyMember, CompanyInvite

__all__ = ["CompanyAdmin", "CompanyMemberAdmin", "CompanyInviteAdmin"]


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Admin interface for Company records."""

    list_display = (
        "name",
        "owner",
        "admin_first_name",
        "admin_last_name",
        "admin_phone",
        "created_at",
    )
    search_fields = (
        "name",
        "owner__email",
        "owner__username",
        "admin_first_name",
        "admin_last_name",
    )
    list_filter = ("created_at",)
    ordering = ("-created_at", "id")

    autocomplete_fields = ("owner",)
    readonly_fields = ("created_at", "updated_at", "logo_preview")

    fieldsets = (
        (None, {"fields": ("name", "owner", "company_logo", "logo_preview")}),
        ("Admin contact", {"fields": ("admin_first_name", "admin_last_name", "admin_phone")}),
        ("Address", {"fields": ("address_1", "address_2", "city", "state", "zip_code")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request) -> QuerySet[Company]:
        """Optimize queries by prefetching related owner."""
        return super().get_queryset(request).select_related("owner")

    def logo_preview(self, obj: Company) -> str:
        """Render company logo thumbnail in admin."""
        if obj.company_logo:
            return format_html(
                '<img src="{}" style="max-height:60px; border-radius:6px;" />',
                obj.company_logo.url,
            )
        return "—"

    logo_preview.short_description = "Logo"  # type: ignore[attr-defined]


@admin.register(CompanyMember)
class CompanyMemberAdmin(admin.ModelAdmin):
    """Admin for managing company members."""

    list_display = ("company", "user", "role", "job_title", "hourly_rate", "joined_at")
    list_filter = ("role", "company")
    search_fields = ("user__email", "company__name")
    ordering = ("-joined_at",)


@admin.register(CompanyInvite)
class CompanyInviteAdmin(admin.ModelAdmin):
    """Admin for managing invitations sent to join companies."""

    list_display = ("company", "email", "role", "status", "sent_at", "accepted_at")
    list_filter = ("status", "role", "company")
    search_fields = ("email", "company__name")
    ordering = ("-sent_at",)
