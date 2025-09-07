# invoices/admin.py
from __future__ import annotations

from decimal import Decimal

from django.contrib import admin, messages
from django.db.models import F, Value, DecimalField, ExpressionWrapper

from .models import Invoice, InvoiceItem
from .services import recalc_invoice


# -----------------------------
# Inlines
# -----------------------------
class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    fields = ("description", "qty", "unit_price", "line_total")
    readonly_fields = ("line_total",)

    def line_total(self, obj: InvoiceItem) -> str:
        try:
            return f"${obj.line_total:.2f}"
        except Exception:
            return "—"
    line_total.short_description = "Line total"  # type: ignore[attr-defined]


# -----------------------------
# List filters
# -----------------------------
class OutstandingFilter(admin.SimpleListFilter):
    title = "Balance"
    parameter_name = "balance_state"

    def lookups(self, request, model_admin): # type: ignore
        return (
            ("outstanding", "Outstanding (> $0)"),
            ("clear", "Zero balance"),
        )

    def queryset(self, request, queryset):
        balance_expr = ExpressionWrapper(
            F("total") - F("amount_paid"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        if self.value() == "outstanding":
            return queryset.annotate(_balance=balance_expr).filter(_balance__gt=Decimal("0.00"))
        if self.value() == "clear":
            return queryset.annotate(_balance=balance_expr).filter(_balance__lte=Decimal("0.00"))
        return queryset


# -----------------------------
# Admin registrations
# -----------------------------
@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    inlines = (InvoiceItemInline,)

    list_display = (
        "number",
        "company",
        "client",
        "status",
        "issue_date",
        "due_date",
        "total_display",
        "amount_paid_display",
        "balance_display",
    )
    search_fields = ("number", "client__org", "client__last_name", "client__email")
    list_filter = ("company", "status", "issue_date", "client", OutstandingFilter)
    date_hierarchy = "issue_date"
    ordering = ("-issue_date", "-id")
    readonly_fields = ("subtotal", "total", "amount_paid")
    autocomplete_fields = ("client", "project")
    list_select_related = ("company", "client", "project")
    list_per_page = 50

    actions = ("mark_as_sent", "mark_as_paid", "recalc_totals")

    # ---------- Queryset enrichment ----------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        balance_expr = ExpressionWrapper(
            F("total") - F("amount_paid"),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )
        return qs.annotate(_balance=balance_expr)

    # ---------- Display helpers ----------
    def total_display(self, obj: Invoice) -> str:
        return f"${(obj.total or Decimal('0')).quantize(Decimal('0.01'))}"
    total_display.short_description = "Total"  # type: ignore[attr-defined]
    total_display.admin_order_field = "total"   # type: ignore[attr-defined]

    def amount_paid_display(self, obj: Invoice) -> str:
        return f"${(obj.amount_paid or Decimal('0')).quantize(Decimal('0.01'))}"
    amount_paid_display.short_description = "Paid"  # type: ignore[attr-defined]
    amount_paid_display.admin_order_field = "amount_paid"  # type: ignore[attr-defined]

    def balance_display(self, obj: Invoice) -> str:
        # uses annotated _balance from get_queryset
        bal = getattr(obj, "_balance", (obj.total or Decimal("0")) - (obj.amount_paid or Decimal("0")))
        return f"${(bal or Decimal('0')).quantize(Decimal('0.01'))}"
    balance_display.short_description = "Balance"  # type: ignore[attr-defined]
    balance_display.admin_order_field = "_balance"  # type: ignore[attr-defined]

    # ---------- Actions ----------
    @admin.action(description="Mark selected invoices as Sent")
    def mark_as_sent(self, request, queryset):
        updated = queryset.update(status=Invoice.SENT)
        self.message_user(request, f"Marked {updated} invoice(s) as Sent.", level=messages.SUCCESS)

    @admin.action(description="Mark selected invoices as Paid")
    def mark_as_paid(self, request, queryset):
        updated = queryset.update(status=Invoice.PAID)
        self.message_user(request, f"Marked {updated} invoice(s) as Paid.", level=messages.SUCCESS)

    @admin.action(description="Recalculate totals for selected invoices")
    def recalc_totals(self, request, queryset):
        n = 0
        for inv in queryset.iterator():
            recalc_invoice(inv)
            n += 1
        self.message_user(request, f"Recalculated {n} invoice(s).", level=messages.SUCCESS)

    # Recalculate after inline edits
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        try:
            recalc_invoice(form.instance)  # keep totals in sync after item edits
        except Exception:
            pass


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ("invoice", "description", "qty", "unit_price", "line_total_display")
    search_fields = ("invoice__number", "description")
    ordering = ("invoice", "id")
    autocomplete_fields = ("invoice",)

    def line_total_display(self, obj: InvoiceItem) -> str:
        try:
            return f"${obj.line_total:.2f}"
        except Exception:
            return "—"
    line_total_display.short_description = "Line total"  # type: ignore[attr-defined]
