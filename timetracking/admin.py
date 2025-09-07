# timetracking/admin.py
from __future__ import annotations

from django.contrib import admin, messages
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import TimeEntry


class HasInvoiceFilter(admin.SimpleListFilter):
    title = "Invoiced?"
    parameter_name = "has_invoice"

    def lookups(self, request, model_admin):  # type: ignore
        return (("yes", "Yes"), ("no", "No"))

    def queryset(self, request, qs):  # type: ignore
        if self.value() == "yes":
            return qs.filter(invoice__isnull=False)
        if self.value() == "no":
            return qs.filter(invoice__isnull=True)
        return qs


class RunningFilter(admin.SimpleListFilter):
    title = "Running?"
    parameter_name = "running"

    def lookups(self, request, model_admin):  # type: ignore
        return (("yes", "Yes"), ("no", "No"))

    def queryset(self, request, qs):  # type: ignore
        if self.value() == "yes":
            return qs.filter(end_time__isnull=True)
        if self.value() == "no":
            return qs.filter(end_time__isnull=False)
        return qs


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    # ——— List ———
    list_display = (
        "short_id",
        "project",
        "user",
        "company",
        "status",
        "is_billable",
        "hours",
        "duration_display",
        "started",
        "ended",
        "invoice_link",
    )
    list_select_related = ("project", "user", "company", "invoice")
    ordering = ("-start_time", "-id")
    date_hierarchy = "start_time"
    list_per_page = 50

    search_fields = (
        "id",
        "project__name",
        "user__email",
        "user__first_name",
        "user__last_name",
        "notes",
    )
    list_filter = (
        "status",
        "is_billable",
        "project",
        "company",
        HasInvoiceFilter,
        RunningFilter,
        ("start_time", admin.DateFieldListFilter),
    )

    readonly_fields = ("duration_display",)
    fields = (
        "project",
        "user",
        "company",
        "start_time",
        "end_time",
        "duration_display",
        "hours",
        "is_billable",
        "status",
        "submitted_at",
        "approved_at",
        "approved_by",
        "reject_reason",
        "invoice",
        "notes",
    )

    # Performance/UX on large datasets
    raw_id_fields = ("project", "user", "company", "invoice")
    autocomplete_fields = ()  # keep explicit; raw_id is usually nicer for big tables

    # ——— Helpful row methods ———
    @admin.display(description="ID", ordering="id")
    def short_id(self, obj: TimeEntry):
        sid = str(obj.id)
        return sid[:8] if len(sid) > 8 else sid

    @admin.display(description="Started", ordering="start_time")
    def started(self, obj: TimeEntry):
        return obj.start_time

    @admin.display(description="Ended", ordering="end_time")
    def ended(self, obj: TimeEntry):
        return obj.end_time or format_html('<span style="color:#0a7">Running…</span>')

    @admin.display(description="Duration")
    def duration_display(self, obj: TimeEntry):
        secs = obj.duration_seconds
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    @admin.display(description="Invoice", ordering="invoice")
    def invoice_link(self, obj: TimeEntry):
        if not obj.invoice_id:  # type: ignore
            return "—"
        # Build the correct admin change URL for the related invoice dynamically
        inv = obj.invoice  # type: ignore
        app_label = inv._meta.app_label # type: ignore
        model_name = inv._meta.model_name # type: ignore
        url = reverse(f"admin:{app_label}_{model_name}_change", args=[obj.invoice_id])  # type: ignore
        label = getattr(inv, "number", None) or str(obj.invoice_id)  # type: ignore # human number fallback
        return format_html('<a href="{}">{}</a>', url, label)

    # ——— Actions ———
    actions = [
        "action_stop_running",
        "action_recompute_hours",
        "action_mark_billable",
        "action_mark_nonbillable",
        "action_submit",
        "action_approve",
        "action_reject",
    ]

    @admin.action(description="Stop running timers now")
    def action_stop_running(self, request, queryset):
        qs = queryset.filter(end_time__isnull=True)
        count = 0
        now = timezone.now()
        for te in qs:
            te.end_time = now
            te.save(update_fields=["end_time", "hours"])
            count += 1
        self.message_user(
            request,
            f"Stopped {count} running entr{'y' if count == 1 else 'ies'}.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Recompute hours from timestamps")
    def action_recompute_hours(self, request, queryset):
        updated = 0
        for te in queryset.filter(end_time__isnull=False, start_time__isnull=False):
            prev = te.hours
            te.hours = te._compute_hours_from_times()
            if te.hours != prev:
                te.save(update_fields=["hours"])
                updated += 1
        self.message_user(
            request,
            f"Recomputed hours on {updated} entr{'y' if updated == 1 else 'ies'}.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Mark as billable")
    def action_mark_billable(self, request, queryset):
        updated = queryset.update(is_billable=True)
        self.message_user(request, f"Marked {updated} as billable.", level=messages.SUCCESS)

    @admin.action(description="Mark as non-billable")
    def action_mark_nonbillable(self, request, queryset):
        updated = queryset.update(is_billable=False)
        self.message_user(request, f"Marked {updated} as non-billable.", level=messages.SUCCESS)

    @admin.action(description="Submit for approval")
    def action_submit(self, request, queryset):
        qs = queryset.filter(end_time__isnull=False)
        updated = qs.update(status=TimeEntry.SUBMITTED, submitted_at=timezone.now())
        self.message_user(request, f"Submitted {updated} for approval.", level=messages.SUCCESS)

    @admin.action(description="Approve")
    def action_approve(self, request, queryset):
        qs = queryset.filter(end_time__isnull=False)
        updated = qs.update(
            status=TimeEntry.APPROVED,
            approved_at=timezone.now(),
            approved_by=request.user,
            reject_reason="",
        )
        self.message_user(
            request,
            f"Approved {updated} entr{'y' if updated == 1 else 'ies'}.",
            level=messages.SUCCESS,
        )

    @admin.action(description="Reject (clears reason to fill manually)")
    def action_reject(self, request, queryset):
        updated = queryset.update(status=TimeEntry.REJECTED, reject_reason="")
        self.message_user(
            request,
            f"Rejected {updated} entr{'y' if updated == 1 else 'ies'}.",
            level=messages.WARNING,
        )
