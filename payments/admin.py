# payments/admin.py
from __future__ import annotations

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from .models import Payment

# Optional: only imported when used to avoid circulars at import time
def _recalc_invoice_safe(inv):
    try:
        from invoices.services import recalc_invoice  # lazy import
        recalc_invoice(inv)
    except Exception:
        # Don't crash admin if invoices app or function changes
        pass


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "received_at",
        "invoice_number",
        "client_name",
        "company",
        "amount",
        "method",
        "external_id_short",
    )
    search_fields = (
        "invoice__number",
        "invoice__client__org",
        "invoice__client__first_name",
        "invoice__client__last_name",
        "company__name",
        "method",
        "external_id",
    )
    list_filter = ("company", "method")
    date_hierarchy = "received_at"
    ordering = ("-received_at",)
    list_select_related = ("invoice", "invoice__client", "company")
    raw_id_fields = ("invoice", "company")
    actions = ("recalc_invoices",)

    # ----- Display helpers -----
    def invoice_number(self, obj: Payment) -> str:
        return getattr(getattr(obj, "invoice", None), "number", "—")
    invoice_number.short_description = _("Invoice #") # type: ignore
    invoice_number.admin_order_field = "invoice__number" # type: ignore

    def client_name(self, obj: Payment) -> str:
        inv = getattr(obj, "invoice", None)
        return str(getattr(inv, "client", "—")) if inv else "—"
    client_name.short_description = _("Client") # type: ignore
    client_name.admin_order_field = "invoice__client__org" # type: ignore

    def external_id_short(self, obj: Payment) -> str:
        eid = obj.external_id or ""
        return eid if len(eid) <= 18 else f"{eid[:18]}…"
    external_id_short.short_description = _("External ID") # type: ignore

    # ----- Actions -----
    def recalc_invoices(self, request, queryset):
        invoices = set()
        for p in queryset.select_related("invoice"):
            if p.invoice_id:
                invoices.add(p.invoice)
        count = 0
        for inv in invoices:
            _recalc_invoice_safe(inv)
            count += 1
        self.message_user(
            request,
            _(f"Recalculated totals for {count} related invoice(s)."),
            level=messages.SUCCESS,
        )
    recalc_invoices.short_description = _("Recalculate related invoices") # type: ignore

    # ----- Keep invoice totals in sync on save/delete -----
    def save_model(self, request, obj: Payment, form, change):
        super().save_model(request, obj, form, change)
        if obj.invoice_id: # type: ignore
            _recalc_invoice_safe(obj.invoice)

    def delete_model(self, request, obj: Payment):
        inv = obj.invoice if obj.invoice_id else None # type: ignore
        super().delete_model(request, obj)
        if inv:
            _recalc_invoice_safe(inv)

    def delete_queryset(self, request, queryset):
        # Recalc for each affected invoice once after bulk delete
        invoices = {p.invoice for p in queryset if p.invoice_id}
        super().delete_queryset(request, queryset)
        for inv in invoices:
            _recalc_invoice_safe(inv)
