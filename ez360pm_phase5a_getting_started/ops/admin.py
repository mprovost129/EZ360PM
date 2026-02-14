from __future__ import annotations

from django.contrib import admin

from .models import OpsAlertEvent


@admin.register(OpsAlertEvent)
class OpsAlertEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "level", "source", "company", "title", "is_resolved")
    list_filter = ("level", "source", "is_resolved", "created_at")
    search_fields = ("title", "message", "company__name", "company__id", "resolved_by_email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
