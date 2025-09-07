# estimates/services.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.db import transaction

from invoices.models import Invoice, InvoiceItem
from invoices.services import recalc_invoice
from invoices.utils import generate_invoice_number

from .models import Estimate

User = get_user_model()


# ============================
# Totals / (Re)calculations
# ============================

def _q2(x: Decimal) -> Decimal:
    """Quantize to 2 decimal places with HALF_UP."""
    return (x or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def recalc_estimate(est: Estimate) -> Estimate:
    """
    Recalculate estimate subtotal/total from its items.

    Assumes `est.tax` is an absolute amount (not a rate).
    Writes `subtotal` and `total` rounded to 2 decimals.
    """
    # If caller didn't prefetch items, this will still work.
    subtotal = Decimal("0.00")
    for it in est.items.all():  # type: ignore[attr-defined]
        q = Decimal(str(it.qty or 0))
        p = Decimal(str(it.unit_price or 0))
        subtotal += (q * p)

    tax = Decimal(str(est.tax or 0))
    est.subtotal = _q2(subtotal)
    est.total = _q2(est.subtotal + tax)
    est.save(update_fields=["subtotal", "total"])
    return est


# ============================
# Estimate -> Invoice
# ============================

@transaction.atomic
def convert_estimate_to_invoice(est: Estimate) -> Invoice:
    """
    Idempotently create an Invoice from an Estimate and copy line items.

    Concurrency-safe:
      - Locks the Estimate row to prevent duplicate invoices on race.
      - Re-checks linkage after acquiring the lock.

    Ensures an invoice number is assigned immediately.
    """
    # Lock the estimate row for update within the transaction
    est = (
        Estimate.objects.select_for_update()
        .select_related("company", "client", "project")
        .prefetch_related("items")
        .get(pk=est.pk)
    )

    # Idempotent early return if already converted
    if getattr(est, "converted_invoice_id", None):
        return est.converted_invoice  # type: ignore[attr-defined]

    inv = Invoice.objects.create(
        company=est.company,
        client=est.client,
        project=est.project,
        number=generate_invoice_number(est.company),
        status=getattr(Invoice, "DRAFT", "draft"),
        issue_date=est.issue_date,
        due_date=None,
        notes=est.notes,
        tax=est.tax,
        currency=getattr(est, "currency", "usd"),
    )

    # Copy items (bulk)
    items = [
        InvoiceItem(
            invoice=inv,
            description=it.description,
            qty=it.qty,
            unit_price=it.unit_price,
        )
        for it in est.items.all()  # type: ignore[attr-defined]
    ]
    if items:
        InvoiceItem.objects.bulk_create(items)

    # Recalculate invoice totals after items & tax
    recalc_invoice(inv)

    # Link estimate -> invoice and mark accepted (set timestamp if missing)
    est.converted_invoice = inv  # type: ignore[attr-defined]
    est.status = getattr(Estimate, "ACCEPTED", "accepted")
    if not getattr(est, "accepted_at", None):
        from django.utils import timezone
        est.accepted_at = timezone.now()
    est.save(update_fields=["converted_invoice", "status", "accepted_at"])

    return inv
