# invoices/services.py
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, List

from django.conf import settings
from django.utils import timezone
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.db.models import Sum

from expenses.models import Expense
from core.services import _parse_rounding, group_time_entries
from core.utils import advance_schedule
from expenses.services import _group_expenses
from .utils import generate_invoice_number

from .models import (
    Invoice,
    InvoiceItem,
    RecurringPlan,
)


def create_invoice_from_time(
    *,
    project,
    company,
    start,
    end,
    group_by: str,
    rounding: str,
    override_rate: Optional[Decimal],
    description_prefix: str = "",
    include_expenses: bool = True,
    expense_group_by: str = "category",
    expense_markup_override: Optional[Decimal] = None,
    expense_label_prefix: str = "",
    only_approved: bool = False,
) -> Invoice:
    """
    Build a draft invoice from unbilled project time (and optional billable expenses).
    Links included time/expenses to the created invoice to prevent double-billing.
    Ensures a non-null, unique invoice number at creation.
    """
    rounding_step = _parse_rounding(rounding)
    base_rate = project.hourly_rate or Decimal("0.00")
    rate = (override_rate if override_rate and override_rate > 0 else base_rate)

    # Create invoice shell with a valid number immediately
    issue = timezone.localdate()
    inv = Invoice.objects.create(
        company=company,
        client=project.client,
        project=project,
        number=generate_invoice_number(company),
        issue_date=issue,
        status=getattr(Invoice, "DRAFT", "draft"),
    )

    # --- TIME ENTRIES ---
    time_qs = project.time_entries.filter(  # type: ignore[attr-defined]
        is_billable=True,
        invoice__isnull=True,
        start_time__date__gte=start,
        start_time__date__lte=end,
    )
    if only_approved:
        time_qs = time_qs.filter(approved_at__isnull=False)

    groups = group_time_entries(time_qs, group_by=group_by, rounding_step=rounding_step)

    line_items: List[InvoiceItem] = []
    for g in groups:
        if g["hours"] <= 0:
            continue
        qty = g["hours"]
        # Prefer single-entry notes as description if grouping by entry
        if group_by == "entry" and len(g["entries"]) == 1 and getattr(g["entries"][0], "notes", ""):
            label = g["entries"][0].notes  # type: ignore[index]
        else:
            if group_by in ("day", "user", "project"):
                label = f"Time — {g['label']}"
            else:
                label = "Time"
        if description_prefix:
            label = f"{description_prefix.strip()} — {label}"

        line_items.append(InvoiceItem(invoice=inv, description=label, qty=qty, unit_price=rate))

    # --- EXPENSES (optional) ---
    if include_expenses:
        exp_qs = Expense.objects.filter(
            project=project,
            company=company,
            invoice__isnull=True,
            is_billable=True,
            date__gte=start,
            date__lte=end,
        ).order_by("date", "id")

        if exp_qs.exists():
            groups_e = _group_expenses(
                exp_qs,
                expense_group_by,
                expense_markup_override,
                expense_label_prefix,
            )
            for g in groups_e:
                # Each expense group becomes a single line with qty=1 and unit_price=total
                line_items.append(
                    InvoiceItem(invoice=inv, description=g["label"], qty=Decimal("1"), unit_price=g["total"])
                )
            # Link expenses to prevent rebilling
            exp_qs.update(invoice=inv)

    # Persist items
    if line_items:
        InvoiceItem.objects.bulk_create(line_items)

    # Link the time entries to the invoice (even when rounding was applied)
    for g in groups:
        ids = [t.id for t in g["entries"]]
        if ids:
            project.time_entries.filter(id__in=ids).update(invoice=inv)

    # Final totals
    recalc_invoice(inv)
    return inv


def recalc_invoice(invoice: Invoice) -> Invoice:
    """
    Recalculate invoice subtotal/total/amount_paid and set PAID status if applicable.
    """
    subtotal = Decimal("0.00")
    for it in invoice.items.all():  # type: ignore[attr-defined]
        q = Decimal(str(it.qty or 0))
        p = Decimal(str(it.unit_price or 0))
        subtotal += (q * p)

    tax = Decimal(str(invoice.tax or 0))
    total = (subtotal + tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    paid = (
        invoice.payments.aggregate(s=Sum("amount")).get("s")  # type: ignore[attr-defined]
        or Decimal("0.00")
    )
    paid = Decimal(str(paid)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    new_status = invoice.status
    if total > 0 and paid >= total:
        new_status = getattr(Invoice, "PAID", "paid")

    invoice.subtotal = subtotal
    invoice.total = total
    invoice.amount_paid = paid
    invoice.status = new_status
    invoice.save(update_fields=["subtotal", "total", "amount_paid", "status"])
    return invoice


def email_invoice_default(inv: Invoice, request_base_url: Optional[str] = None) -> None:
    """
    Send invoice via email with attached PDF.
    Uses settings.SITE_URL for public link; base_url for PDF assets if provided.
    """
    to_email = getattr(inv.client, "email", None)
    if not to_email:
        return

    body = render_to_string("core/email/invoice_email.txt", {"inv": inv, "site_url": settings.SITE_URL})

    # Lazy import heavy PDF deps via views helper
    from .views import _render_pdf_from_html  # noqa: WPS433
    html = render_to_string("core/pdf/invoice.html", {"inv": inv})
    base_url = request_base_url or f"{settings.SITE_URL}/"
    pdf_bytes = _render_pdf_from_html(html, base_url=base_url)

    subject = f"Invoice {inv.number} from {inv.company.name}"
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    email.attach(f"invoice_{inv.number}.pdf", pdf_bytes, "application/pdf")
    email.send(fail_silently=False)


# ============================
# Recurring Plans
# ============================

def generate_invoice_from_plan(plan: RecurringPlan) -> Invoice:
    """
    Create an Invoice from a RecurringPlan (clone items from its template invoice if provided).
    """
    issue = plan.next_run_date
    due = (issue or timezone.localdate()) + timedelta(days=plan.due_days or 0)

    inv = Invoice.objects.create(
        company=plan.company,
        client=plan.client,
        project=plan.project,
        number=generate_invoice_number(plan.company),
        issue_date=issue,
        due_date=due,
        status=getattr(Invoice, "DRAFT", "draft"),
        currency=getattr(getattr(plan, "template_invoice", None), "currency", "usd"),
        tax=getattr(getattr(plan, "template_invoice", None), "tax", Decimal("0.00")),
        notes=getattr(getattr(plan, "template_invoice", None), "notes", ""),
    )

    tpl = getattr(plan, "template_invoice", None)
    if tpl:
        clones = [
            InvoiceItem(
                invoice=inv,
                description=it.description,
                qty=getattr(it, "qty", None) or getattr(it, "quantity", None) or Decimal("1"),
                unit_price=it.unit_price,
            )
            for it in tpl.items.all()  # type: ignore[attr-defined]
        ]
        if clones:
            InvoiceItem.objects.bulk_create(clones)

    recalc_invoice(inv)
    return inv


def advance_plan_after_run(plan: RecurringPlan) -> None:
    """Bump counters and compute next run date after creating/sending a plan's invoice."""
    plan.occurrences_sent = (plan.occurrences_sent or 0) + 1
    plan.last_run_at = timezone.now()
    plan.next_run_date = advance_schedule(plan.next_run_date, plan.frequency)
    plan.save(update_fields=["occurrences_sent", "last_run_at", "next_run_date"])
