# core/admin.py
from __future__ import annotations

from django.contrib import admin

from .models import (
    Company,
    Client,
    Project,
    Invoice,
    InvoiceItem,
    Payment,
    Expense,
    TimeEntry,
    CompanyMember,
    CompanyInvite,
)


# -----------------------------
# Basic Registrations
# -----------------------------

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "phone", "created_at")
    search_fields = ("name", "owner__email")
    ordering = ("name",)
    readonly_fields = ("created_at",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("org", "last_name", "first_name", "email", "phone")
    search_fields = ("org", "last_name", "first_name", "email")
    list_filter = ("company",)
    ordering = ("org", "last_name")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "client", "company", "billing_type", "budget", "due_date")
    search_fields = ("number", "name", "client__org", "client__last_name")
    list_filter = ("company", "billing_type")
    ordering = ("-created_at",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "company", "client", "status", "issue_date", "due_date", "total", "amount_paid")
    search_fields = ("number", "client__org", "client__last_name", "client__email")
    list_filter = ("company", "status", "issue_date")
    date_hierarchy = "issue_date"
    ordering = ("-issue_date",)
    readonly_fields = ("subtotal", "total", "amount_paid")


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ("invoice", "description", "qty", "unit_price", "line_total")
    search_fields = ("invoice__number", "description")
    ordering = ("invoice",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "company", "amount", "method", "received_at")
    search_fields = ("invoice__number", "company__name", "method")
    list_filter = ("company", "method")
    date_hierarchy = "received_at"
    ordering = ("-received_at",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "company", "project", "amount", "date", "category", "is_billable")
    search_fields = ("description", "vendor", "category", "company__name")
    list_filter = ("company", "category", "is_billable")
    date_hierarchy = "date"
    ordering = ("-date",)


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ("project", "user", "hours", "status", "started_at", "ended_at")
    search_fields = ("project__name", "user__email", "notes")
    list_filter = ("project", "status", "is_billable")
    date_hierarchy = "started_at"
    ordering = ("-started_at",)


# -----------------------------
# Company Membership / Invites
# -----------------------------

@admin.register(CompanyMember)
class CompanyMemberAdmin(admin.ModelAdmin):
    list_display = ("company", "user", "role", "job_title", "hourly_rate", "joined_at")
    list_filter = ("role", "company")
    search_fields = ("user__email", "company__name")
    ordering = ("-joined_at",)


@admin.register(CompanyInvite)
class CompanyInviteAdmin(admin.ModelAdmin):
    list_display = ("company", "email", "role", "status", "sent_at", "accepted_at")
    list_filter = ("status", "role", "company")
    search_fields = ("email", "company__name")
    ordering = ("-sent_at",)
