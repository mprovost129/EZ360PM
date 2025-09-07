# clients/admin.py
from __future__ import annotations

from django.contrib import admin
from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "email",
        "phone",
        "company",
        "short_address",
        "created_at",
    )
    search_fields = (
        "org",
        "first_name",
        "last_name",
        "email",
        "phone",
        "city",
        "state",
        "zip_code",
    )
    search_help_text = "Search by client name, email, phone, or address"
    list_filter = ("company", "state", "city", "created_at")
    ordering = ("org", "last_name", "first_name")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
    list_select_related = ("company",)

    fieldsets = (
        (None, {
            "fields": ("company", "org", "first_name", "last_name", "email", "phone"),
        }),
        ("Address", {
            "fields": ("address_1", "address_2", "city", "state", "zip_code"),
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
        }),
    )
