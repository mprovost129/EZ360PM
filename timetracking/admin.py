from django.contrib import admin

from .models import TimeEntry, TimeEntryService, TimerState, TimeTrackingSettings


class TimeEntryServiceInline(admin.TabularInline):
    model = TimeEntryService
    extra = 0


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("company", "employee", "project", "started_at", "duration_minutes", "status", "billable")
    list_filter = ("company", "status", "billable")
    search_fields = ("note", "project__name", "project__project_number", "employee__username_public")
    inlines = [TimeEntryServiceInline]


@admin.register(TimerState)
class TimerStateAdmin(admin.ModelAdmin):
    list_display = ("company", "employee", "is_running", "started_at", "project")


@admin.register(TimeTrackingSettings)
class TimeTrackingSettingsAdmin(admin.ModelAdmin):
    list_display = ("company", "employee", "entry_mode", "clock_format", "rounding_minutes", "require_manager_approval")
