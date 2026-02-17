from __future__ import annotations

from django.contrib import admin

from .models import (
    OpsCheckRun,
    OpsCheckKind,
    OpsAlertEvent,
    OpsAlertSnooze,
    LaunchGateItem,
    BackupRun,
    BackupRestoreTest,
    ReleaseNote,
    UserPresence,
    OpsEmailTest,
    OpsProbeEvent,
    SiteConfig,
)


@admin.register(OpsAlertEvent)
class OpsAlertEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "level", "source", "company", "title", "is_resolved")
    list_filter = ("level", "source", "is_resolved", "created_at")
    search_fields = ("title", "message", "company__name", "company__id", "resolved_by_email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(OpsAlertSnooze)
class OpsAlertSnoozeAdmin(admin.ModelAdmin):
    list_display = ("source", "company", "snoozed_until", "created_by_email", "created_at")
    list_filter = ("source", "company")
    search_fields = ("created_by_email", "reason", "company__name")
    ordering = ("-snoozed_until",)


@admin.register(LaunchGateItem)
class LaunchGateItemAdmin(admin.ModelAdmin):
    list_display = ("key", "title", "is_complete", "completed_at", "completed_by")
    list_filter = ("is_complete",)
    search_fields = ("key", "title", "description", "notes")
    readonly_fields = ("created_at", "updated_at", "completed_at")


@admin.register(BackupRun)
class BackupRunAdmin(admin.ModelAdmin):
    list_display = ("created_at", "status", "storage", "size_bytes", "initiated_by_email")
    list_filter = ("status", "storage")
    search_fields = ("initiated_by_email", "notes")
    readonly_fields = ("created_at",)


@admin.register(BackupRestoreTest)
class BackupRestoreTestAdmin(admin.ModelAdmin):
    list_display = ("tested_at", "outcome", "tested_by_email")
    list_filter = ("outcome",)
    search_fields = ("tested_by_email", "notes")
    readonly_fields = ("tested_at",)


@admin.register(ReleaseNote)
class ReleaseNoteAdmin(admin.ModelAdmin):
    list_display = ("created_at", "environment", "build_version", "build_sha", "title", "is_published", "created_by_email")
    list_filter = ("environment", "is_published", "created_at")
    search_fields = ("title", "notes", "build_version", "build_sha", "created_by_email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(UserPresence)
class UserPresenceAdmin(admin.ModelAdmin):
    list_display = ("last_seen", "company", "user")
    list_filter = ("company",)
    search_fields = ("user__email", "company__name")
    readonly_fields = ("last_seen", "company", "user")
    ordering = ("-last_seen",)


@admin.register(OpsEmailTest)
class OpsEmailTestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "status", "to_email", "subject", "backend", "latency_ms")
    list_filter = ("status", "created_at")
    search_fields = ("to_email", "subject", "error", "initiated_by_email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(OpsProbeEvent)
class OpsProbeEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "status", "initiated_by_email")
    list_filter = ("kind", "status", "created_at")
    search_fields = ("initiated_by_email",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(OpsCheckRun)
class OpsCheckRunAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "company", "is_ok", "duration_ms", "created_by_email")
    list_filter = ("kind", "is_ok")
    search_fields = ("created_by_email", "output_text", "company__name", "company__owner__email")
    readonly_fields = ("created_at", "output_text", "args", "duration_ms", "created_by_email")
    ordering = ("-created_at",)

@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    list_display = ("id", "updated_at", "ops_alert_webhook_enabled", "ops_alert_email_enabled", "ops_alert_email_min_level")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        # Singleton: prevent multiple rows
        if SiteConfig.objects.exists():
            return False
        return super().has_add_permission(request)
