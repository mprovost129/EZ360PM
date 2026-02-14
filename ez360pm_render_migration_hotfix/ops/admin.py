from __future__ import annotations

from django.contrib import admin

from .models import OpsAlertEvent, LaunchGateItem, BackupRun, BackupRestoreTest, ReleaseNote, UserPresence


@admin.register(OpsAlertEvent)
class OpsAlertEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "level", "source", "company", "title", "is_resolved")
    list_filter = ("level", "source", "is_resolved", "created_at")
    search_fields = ("title", "message", "company__name", "company__id", "resolved_by_email")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


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
