# expenses/admin.py
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from .models import Expense


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "description",
        "vendor",
        "company",
        "project",
        "amount_display",
        "date",
        "category",
        "is_billable",
    )
    list_filter = ("company", "category", "is_billable", "date")
    search_fields = (
        "description",
        "vendor",
        "category",
        "company__name",
        "project__name",
        "project__number",
    )
    date_hierarchy = "date"
    ordering = ("-date", "-id")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": (
                "company",
                "project",
                "vendor",
                "category",
                "description",
                "amount",
                "date",
            )
        }),
        ("Billing", {
            "fields": (
                "is_billable",
                "billable_markup_pct",
                "billable_note",
                "invoice",
            ),
            "classes": ("collapse",),
        }),
        ("Audit", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def amount_display(self, obj: Expense) -> str:
        """Show amount as currency with optional markup indicator."""
        amt = f"${obj.amount:.2f}"
        if obj.is_billable and obj.billable_markup_pct:
            return format_html(
                "{} <span style='color:#666;'>(+{}%)</span>",
                amt,
                obj.billable_markup_pct,
            )
        return amt

    amount_display.short_description = "Amount" # type: ignore
