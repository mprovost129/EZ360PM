from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    Document,
    DocumentLineItem,
    DocumentStatus,
    DocumentType,
    RecurringFrequency,
    RecurringPlan,
    RecurringPlanLineItem,
)
from .services import allocate_document_number, recalc_document_totals
from .services_email import send_document_to_client


def _add_months(d: date, months: int, day_of_month: int | None = None) -> date:
    """Add months to a date with safe day clamping.

    - If day_of_month is provided, we try to set that day (clamped to month length).
    - Otherwise, we preserve the existing day as much as possible.
    """

    if months <= 0:
        return d
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    target_day = day_of_month if day_of_month is not None else d.day
    target_day = max(1, min(int(target_day), int(last_day)))
    return date(y, m, target_day)


def compute_next_run_date(plan: RecurringPlan, from_date: date | None = None) -> date:
    base = from_date or plan.next_run_date
    if plan.frequency == RecurringFrequency.WEEKLY:
        return base + timedelta(weeks=int(plan.interval or 1))
    # monthly
    return _add_months(base, int(plan.interval or 1), day_of_month=int(plan.day_of_month or 1))


@dataclass
class RecurringRunResult:
    created_invoice: Document | None
    skipped: bool
    message: str


@transaction.atomic
def generate_invoice_from_plan(plan: RecurringPlan, *, run_date: date | None = None) -> RecurringRunResult:
    """Generate a single invoice from a plan and advance the schedule.

    This function is transaction-safe and intended to be used by both:
    - the UI "Run now" action
    - the scheduled management command
    """

    if not plan.is_active:
        return RecurringRunResult(created_invoice=None, skipped=True, message="Plan is inactive")

    today = run_date or timezone.localdate()

    # Guard: do not run early.
    if plan.next_run_date and plan.next_run_date > today:
        return RecurringRunResult(created_invoice=None, skipped=True, message="Not due yet")

    # Create the invoice document.
    doc = Document.objects.create(
        company=plan.company,
        doc_type=DocumentType.INVOICE,
        client=plan.client,
        project=plan.project,
        created_by=plan.created_by,
        title=f"{plan.name}",
        issue_date=today,
        due_date=today + timedelta(days=int(plan.due_days or 0)),
        status=DocumentStatus.SENT if plan.auto_mark_sent else DocumentStatus.DRAFT,
        notes=plan.notes or "",
    )

    # Allocate a number immediately for recurring invoices.
    doc.number = allocate_document_number(plan.company, DocumentType.INVOICE)
    doc.save(update_fields=["number", "updated_at"])

    # Copy line items
    items = list(plan.line_items.filter(deleted_at__isnull=True).order_by("sort_order", "created_at"))
    if not items:
        # Still advance schedule; keep invoice as $0 draft/sent with a warning.
        recalc_document_totals(doc)
        plan.last_run_date = today
        plan.next_run_date = compute_next_run_date(plan, from_date=today)
        plan.save(update_fields=["last_run_date", "next_run_date", "updated_at"])
        return RecurringRunResult(created_invoice=doc, skipped=False, message="Invoice created (no line items)")

    for idx, li in enumerate(items):
        unit = int(li.unit_price_cents or 0)
        qty = li.qty
        # subtotal is qty * unit_price
        try:
            line_subtotal = int(round(float(qty) * unit))
        except Exception:
            line_subtotal = unit

        DocumentLineItem.objects.create(
            document=doc,
            sort_order=idx,
            name=li.name,
            description=li.description or "",
            qty=li.qty,
            unit_price_cents=unit,
            line_subtotal_cents=line_subtotal,
            tax_cents=0,
            line_total_cents=line_subtotal,
            is_taxable=bool(li.is_taxable),
        )

    recalc_document_totals(doc)

    # Advance schedule.
    plan.last_run_date = today
    plan.next_run_date = compute_next_run_date(plan, from_date=today)
    plan.save(update_fields=["last_run_date", "next_run_date", "updated_at"])

    # Optional: auto-email invoice to client. Use on_commit so email isn't sent if tx rolls back.
    if plan.auto_email:
        to_override = (plan.email_to_override or "").strip() or None
        transaction.on_commit(lambda: send_document_to_client(doc, actor=plan.created_by, to_email=to_override))

    return RecurringRunResult(created_invoice=doc, skipped=False, message="Invoice created")


def generate_due_invoices_for_company(company, *, run_date: date | None = None) -> list[RecurringRunResult]:
    today = run_date or timezone.localdate()
    results: list[RecurringRunResult] = []
    plans = (
        RecurringPlan.objects
        .filter(company=company, deleted_at__isnull=True, is_active=True, next_run_date__lte=today)
        .select_related("company", "client", "project")
        .order_by("next_run_date", "created_at")
    )
    for plan in plans:
        results.append(generate_invoice_from_plan(plan, run_date=today))
    return results
