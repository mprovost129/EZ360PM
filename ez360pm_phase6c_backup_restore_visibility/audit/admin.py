from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "company", "event_type", "object_type", "object_id", "actor")
    list_filter = ("company", "event_type", "object_type")
    search_fields = ("event_type", "object_type", "summary", "actor__username_public", "company__name")
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "revision",
        "company",
        "actor",
        "event_type",
        "object_type",
        "object_id",
        "summary",
        "payload_json",
        "ip_address",
        "user_agent",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
