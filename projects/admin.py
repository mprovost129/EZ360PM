# projects/admin.py
from __future__ import annotations

from django.contrib import admin

from projects.models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "name",
        "client",
        "company",
        "billing_type",
        "budget",
        "due_date",
        "created_at",
    )
    list_display_links = ("number", "name")
    search_fields = ("number", "name", "client__org", "client__last_name", "client__first_name")
    list_filter = ("company", "billing_type", "due_date")
    ordering = ("-created_at", "-id")
    date_hierarchy = "created_at"
    list_per_page = 50
    list_select_related = ("client", "company")
    readonly_fields = ("created_at",)
    filter_horizontal = ("team",)
