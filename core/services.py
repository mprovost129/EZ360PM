# core/services.py

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Iterable

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils import timezone

from .models import (
    Estimate,
    Invoice,
    InvoiceItem,
    RecurringPlan,
    Notification,
    CompanyMember,
    Expense,
    TimeEntry,
)
from .utils import advance_schedule, generate_invoice_number

User = get_user_model()


# ----------------------------
# Totals / (Re)calculations
# ----------------------------

def recalc_invoice(invoice: Invoice) -> Invoice:
    """
    Recalculate invoice subtotal/total/amount_paid and set PAID status if applicable.
    Assumes InvoiceItem has fields: description, qty, unit_price (no per-line total stored).
    """
    # Subtotal in Python to be safe with Decimals and nulls
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

    # Update status if fully paid
    new_status = invoice.status
    if total > 0 and paid >= total:
        new_status = getattr(Invoice, "PAID", "paid")

    invoice.subtotal = subtotal
    invoice.total = total
    invoice.amount_paid = paid
    invoice.status = new_status
    invoice.save(update_fields=["subtotal", "total", "amount_paid", "status"])
    return invoice


def recalc_estimate(est: Estimate) -> Estimate:
    """
    Recalculate estimate subtotal/total.
    """
    subtotal = Decimal("0.00")
    for it in est.items.all():  # type: ignore[attr-defined]
        q = Decimal(str(it.qty or 0))
        p = Decimal(str(it.unit_price or 0))
        subtotal += (q * p)

    tax = Decimal(str(est.tax or 0))
    total = (subtotal + tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    est.subtotal = subtotal
    est.total = total
    est.save(update_fields=["subtotal", "total"])
    return est


# ----------------------------
# Estimate -> Invoice
# ----------------------------

def convert_estimate_to_invoice(est: Estimate) -> Invoice:
    """
    Idempotently create an Invoice from an Estimate and copy line items.
    """
    if getattr(est, "converted_invoice_id", None):  # already converted
        return est.converted_invoice  # type: ignore[attr-defined]

    inv = Invoice.objects.create(
        company=est.company,
        client=est.client,
        project=est.project,
        number=None,  # will be assigned later via generate_invoice_number
        status=getattr(Invoice, "DRAFT", "draft"),
        issue_date=est.issue_date,
        due_date=None,
        notes=est.notes,
        tax=est.tax,
        currency=getattr(est, "currency", "usd"),
    )

    # Copy items (qty + unit_price)
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

    recalc_invoice(inv)

    # Mark estimate as accepted + link converted invoice
    est.converted_invoice = inv  # type: ignore[attr-defined]
    est.status = getattr(Estimate, "ACCEPTED", "accepted")
    est.save(update_fields=["converted_invoice", "status"])

    return inv


# ----------------------------
# Recurring Plans
# ----------------------------

def generate_invoice_from_plan(plan: RecurringPlan) -> Invoice:
    """
    Create an Invoice from a RecurringPlan (clone items from its template invoice if provided).
    """
    issue = plan.next_run_date
    due = (issue or timezone.now().date()) + timedelta(days=plan.due_days or 0)

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
    """
    Bump counters and compute next run date after creating/sending a plan's invoice.
    """
    plan.occurrences_sent = (plan.occurrences_sent or 0) + 1
    plan.last_run_at = timezone.now()
    plan.next_run_date = advance_schedule(plan.next_run_date, plan.frequency)
    plan.save(update_fields=["occurrences_sent", "last_run_at", "next_run_date"])


# ----------------------------
# Emailing Invoices (with PDF)
# ----------------------------

def email_invoice_default(inv: Invoice, request_base_url: Optional[str] = None) -> None:
    """
    Send invoice via email with attached PDF.
    Uses settings.SITE_URL for public link; base_url for PDF assets if provided.
    """
    to_email = getattr(inv.client, "email", None)
    if not to_email:
        return

    # Body
    body = render_to_string(
        "core/email/invoice_email.txt",
        {"inv": inv, "site_url": settings.SITE_URL},
    )

    # PDF
    from .views import _render_pdf_from_html  # lazy import to avoid heavy deps at import time
    html = render_to_string("core/pdf/invoice.html", {"inv": inv})
    base_url = request_base_url or f"{settings.SITE_URL}/"
    pdf_bytes = _render_pdf_from_html(html, base_url=base_url)

    # Email
    subject = f"Invoice {inv.number} from {inv.company.name}"
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    email.attach(f"invoice_{inv.number}.pdf", pdf_bytes, "application/pdf")
    email.send(fail_silently=False)


# ----------------------------
# Notifications
# ----------------------------

def _company_users(company, exclude: Optional[User] = None) -> list[User]: # type: ignore
    """
    Return all user accounts associated with a company (members + owner).
    Optionally exclude a specific user (e.g., the actor).
    """
    ids = set(CompanyMember.objects.filter(company=company).values_list("user_id", flat=True))
    if getattr(company, "owner_id", None):
        ids.add(company.owner_id)
    if exclude and exclude.id in ids:
        ids.remove(exclude.id)
    return list(User.objects.filter(id__in=ids))


def notify(
    company,
    recipient,
    text: str,
    *,
    actor=None,
    kind: str = Notification.GENERIC,
    url: str = "",
    target=None,
) -> Notification:
    """
    Create a single notification.
    If a target model instance is provided, it's linked via GenericForeignKey.
    """
    n = Notification(
        company=company,
        recipient=recipient,
        actor=actor,
        kind=kind,
        text=text[:280],  # hard cap
        url=(url or "")[:500],
    )
    if target is not None:
        from django.contrib.contenttypes.models import ContentType
        n.target_content_type = ContentType.objects.get_for_model(target.__class__)
        n.target_object_id = target.pk
    n.save()
    return n


def notify_company(
    company,
    actor: Optional[User], # type: ignore
    text: str,
    *,
    url: str = "",
    kind: str = Notification.GENERIC,
    exclude_actor: bool = True,
) -> int:
    """
    Broadcast a notification to all company users (optionally excluding the actor).
    Returns the number of notifications created.
    """
    recipients = _company_users(company, exclude=actor if exclude_actor else None)
    count = 0
    for user in recipients:
        notify(company, user, text, actor=actor, kind=kind, url=url)
        count += 1
    return count


def unread_count(company, user) -> int:
    return Notification.objects.for_company_user(company, user).unread().count()  # type: ignore[attr-defined]


def mark_all_read(company, user):
    Notification.objects.for_company_user(company, user).unread().update(read_at=timezone.now())  # type: ignore[attr-defined]


# ----------------------------
# Time → Invoice
# ----------------------------

def _round_hours(hours: Decimal, step: Decimal) -> Decimal:
    """
    Round hours to a given step (e.g., 0.25 for quarter-hour). Defaults to 0.01 if step <= 0.
    """
    if step <= 0:
        return hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    # round to integer number of steps, then back to hours
    return ((hours / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step).quantize(Decimal("0.01"))


def _parse_rounding(val: str) -> Decimal:
    try:
        f = Decimal(val)
        return f if f > 0 else Decimal("0")
    except Exception:
        return Decimal("0")


def group_time_entries(entries: Iterable[TimeEntry], group_by: str, rounding_step: Decimal):
    """
    Group time entries for invoicing.
    Returns list of dicts: {"label": str, "hours": Decimal, "entries": [TimeEntry]}
    """
    buckets: dict[object, list[TimeEntry]] = defaultdict(list)
    for t in entries:
        if group_by == "day":
            key = (t.started_at.date() if t.started_at else timezone.localdate())
        elif group_by == "user":
            key = getattr(t.user, "email", str(t.user_id)) # type: ignore
        elif group_by == "entry":
            key = t.pk
        elif group_by == "project":
            key = getattr(t.project, "name", "Project")
        else:
            key = "all"
        buckets[key].append(t)

    out = []
    for key, rows in buckets.items():
        total = sum((Decimal(str(r.hours or 0)) for r in rows), Decimal("0"))
        total = _round_hours(total, rounding_step)
        out.append({"label": str(key), "hours": total, "entries": rows})
    out.sort(key=lambda x: str(x["label"]))
    return out


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
    """
    rounding_step = _parse_rounding(rounding)
    base_rate = project.hourly_rate or Decimal("0.00")
    rate = (override_rate if override_rate and override_rate > 0 else base_rate)

    # Create invoice shell
    inv = Invoice.objects.create(
        company=company,
        client=project.client,
        project=project,
        issue_date=timezone.now().date(),
        status=getattr(Invoice, "DRAFT", "draft"),
    )

    # --- TIME ENTRIES ---
    time_qs = project.time_entries.filter(
        is_billable=True,
        invoice__isnull=True,
        started_at__date__gte=start,
        started_at__date__lte=end,
    )
    if only_approved:
        # Use approval fields (approved_at) rather than a status enum
        time_qs = time_qs.filter(approved_at__isnull=False)

    groups = group_time_entries(time_qs, group_by=group_by, rounding_step=rounding_step)

    line_items: list[InvoiceItem] = []
    for g in groups:
        if g["hours"] <= 0:
            continue
        qty = g["hours"]
        label: str
        # If grouping by entry and exactly one entry with notes, use that as label
        if group_by == "entry" and len(g["entries"]) == 1 and getattr(g["entries"][0], "notes", ""):
            label = g["entries"][0].notes  # type: ignore[index]
        else:
            if group_by in ("day", "user", "project"):
                label = f"Time — {g['label']}"
            else:
                label = "Time"
        if description_prefix:
            label = f"{description_prefix.strip()} — {label}"

        line_items.append(InvoiceItem(
            invoice=inv,
            description=label,
            qty=qty,
            unit_price=rate,
        ))

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
                line_items.append(InvoiceItem(
                    invoice=inv,
                    description=g["label"],
                    qty=Decimal("1"),
                    unit_price=g["total"],
                ))
            # Link expenses to prevent rebilling
            exp_qs.update(invoice=inv)

    # Persist items
    if line_items:
        InvoiceItem.objects.bulk_create(line_items)

    # Link the time entries even if rounded (common pattern)
    for g in groups:
        ids = [t.id for t in g["entries"]]
        if ids:
            project.time_entries.filter(id__in=ids).update(invoice=inv)

    # Final totals
    recalc_invoice(inv)
    return inv


# ----------------------------
# Expenses Helpers
# ----------------------------

def _expense_price(amount: Decimal, markup_pct: Optional[Decimal]) -> Decimal:
    """
    Apply percentage markup to an expense amount (e.g., 10 => +10%).
    """
    pct = (markup_pct or Decimal("0.00")) / Decimal("100.00")
    return (amount * (Decimal("1.00") + pct)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _group_expenses(
    qs,
    group_by: str,
    override_markup_pct: Optional[Decimal],
    label_prefix: str = "",
):
    """
    Returns list of dicts: {"label": str, "total": Decimal, "items": [Expense]}
    """
    buckets: dict[object, list[Expense]] = defaultdict(list)
    for e in qs:
        if group_by == "category":
            key = e.category or "Uncategorized"
        elif group_by == "vendor":
            key = e.vendor or "Unknown vendor"
        elif group_by == "expense":
            key = e.id
        else:
            key = "all"
        buckets[key].append(e)

    out = []
    for key, rows in buckets.items():
        total = Decimal("0.00")
        for r in rows:
            base = Decimal(str(r.amount or 0))
            price = _expense_price(
                base,
                override_markup_pct if override_markup_pct is not None else r.billable_markup_pct
            )
            total += price

        # Labels
        if group_by == "expense" and len(rows) == 1:
            e = rows[0]
            base_label = e.description or e.vendor or e.category or "Expense"
            label = f"{base_label}"
        elif group_by in ("category", "vendor"):
            label = f"Expenses — {key}"
        else:
            label = "Expenses"

        if label_prefix:
            label = f"{label_prefix.strip()} — {label}"

        out.append({"label": label, "total": total, "items": rows})

    out.sort(key=lambda x: str(x["label"]))
    return out
