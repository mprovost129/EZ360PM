# invoices/views.py
from __future__ import annotations

# --- Stdlib ---
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import uuid4

# --- Third-party / Django ---
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Value, DecimalField, F, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from expenses.models import Expense
from payments.models import Payment

# --- Local apps ---
try:
    from billing.utils import enforce_limit_or_upsell  # type: ignore
except Exception:  # pragma: no cover
    def enforce_limit_or_upsell(company, key: str, current_count: int):
        return True, None

from company.utils import get_active_company
from core.decorators import require_subscription
from core.utils import default_range_last_30
from company.services import notify_company
from core.models import Notification

from projects.models import Project
from core.views import _render_pdf_from_html  # TODO: move to core.pdf

from .forms import InvoiceForm, InvoiceItemFormSet, RecurringPlanForm, TimeToInvoiceForm
from .models import Invoice, RecurringPlan
from .services import (
    create_invoice_from_time,
    email_invoice_default,
    generate_invoice_from_plan,
    recalc_invoice,
)
from .utils import generate_invoice_number

# Stripe config
stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")


# =============================================================================
# List / CRUD
# =============================================================================

@login_required
def invoices(request):
    company = get_active_company(request)
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Invoice.objects.filter(company=company).select_related("client", "project")

    if q:
        qs = qs.filter(
            Q(number__icontains=q)
            | Q(client__org__icontains=q)
            | Q(client__first_name__icontains=q)
            | Q(client__last_name__icontains=q)
            | Q(project__name__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)

    qs = qs.order_by("-issue_date", "-id")

    # DB-side outstanding across the *filtered* set
    zero = Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2))
    balance_expr = ExpressionWrapper(
        Coalesce(F("total"), zero) - Coalesce(F("amount_paid"), zero),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    outstanding = qs.aggregate(s=Coalesce(Sum(balance_expr), zero))["s"] or Decimal("0.00")

    # Pagination (matches your template’s optional block)
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "invoices/invoices.html",
        {
            "invoices": page_obj.object_list,
            "page_obj": page_obj,
            "q": q,
            "status": status,
            "outstanding": outstanding,
        },
    )


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def invoice_create(request):
    company = get_active_company(request)

    count = Invoice.objects.filter(company=company).count()
    ok, limit = enforce_limit_or_upsell(company, "max_invoices", count)
    if not ok:
        messages.warning(
            request,
            f"You've reached your plan’s limit of {limit} invoices. Upgrade to add more.",
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = InvoiceForm(request.POST, company=company)
        formset = InvoiceItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            inv = form.save(commit=False)
            inv.company = company
            if not inv.number:
                inv.number = generate_invoice_number(company)  # type: ignore
            inv.save()
            formset.instance = inv
            formset.save()
            recalc_invoice(inv)

            notify_company(
                company,
                request.user,
                f"Invoice {inv.number} created for {inv.client}",
                url=reverse("invoices:invoice_detail", args=[inv.pk]),
                kind=Notification.INVOICE_CREATED,
            )
            messages.success(request, "Invoice created.")
            return redirect("invoices:invoice_detail", pk=inv.pk)
    else:
        form = InvoiceForm(
            company=company, initial={"number": generate_invoice_number(company)}  # type: ignore
        )
        formset = InvoiceItemFormSet()

    return render(
        request,
        "invoices/invoice_form.html",
        {"form": form, "formset": formset, "mode": "create"},
    )


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def invoice_update(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(Invoice, pk=pk, company=company)

    if request.method == "POST":
        form = InvoiceForm(request.POST, instance=inv, company=company)
        formset = InvoiceItemFormSet(request.POST, instance=inv)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            recalc_invoice(inv)
            messages.success(request, "Invoice updated.")
            return redirect("invoices:invoice_detail", pk=inv.pk)
    else:
        form = InvoiceForm(instance=inv, company=company)
        formset = InvoiceItemFormSet(instance=inv)

    return render(
        request,
        "invoices/invoice_form.html",
        {"form": form, "formset": formset, "mode": "edit", "inv": inv},
    )


@login_required
@require_subscription
@require_http_methods(["GET"])
def invoice_detail(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "project"), pk=pk, company=company
    )
    recalc_invoice(inv)
    return render(request, "invoices/invoice_detail.html", {"inv": inv})


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def invoice_delete(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(Invoice, pk=pk, company=company)
    if request.method == "POST":
        inv.delete()
        messages.success(request, "Invoice deleted.")
        # Ensure this matches your urls.py name for the list route
        return redirect("invoices:invoices")
    return render(request, "invoices/invoice_confirm_delete.html", {"inv": inv})


@login_required
@require_subscription
def invoice_mark_sent(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(Invoice, pk=pk, company=company)
    inv.status = Invoice.SENT
    inv.save(update_fields=["status"])
    messages.success(request, "Invoice marked as sent.")
    return redirect("invoices:invoice_detail", pk=pk)


# =============================================================================
# Public / Stripe checkout
# =============================================================================

def _get_invoice_by_token(token):
    return get_object_or_404(
        Invoice.objects.select_related("client", "project"), public_token=token
    )


def invoice_public(request, token):
    inv = _get_invoice_by_token(token)
    recalc_invoice(inv)
    return render(
        request,
        "invoices/invoice_public.html",
        {"inv": inv, "stripe_pk": settings.STRIPE_PUBLIC_KEY},
    )


def invoice_checkout(request, token):
    inv = _get_invoice_by_token(token)
    recalc_invoice(inv)

    if getattr(inv, "balance", None) is not None and inv.balance <= 0:  # type: ignore[attr-defined]
        messages.info(request, "This invoice is already paid.")
        return redirect("invoices:invoice_public", token=token)

    balance = (getattr(inv, "balance", None) or (inv.total or 0) - (inv.amount_paid or 0))
    balance = Decimal(balance).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    amount_cents = int(balance * 100)

    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": inv.currency or "usd",
                "product_data": {"name": f"Invoice {inv.number}"},
                "unit_amount": amount_cents,
            },
            "quantity": 1,
        }],
        success_url=f"{settings.SITE_URL}{reverse('invoices:invoice_pay_success', kwargs={'token': str(inv.public_token)})}?sid={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.SITE_URL}{reverse('invoices:invoice_public', kwargs={'token': str(inv.public_token)})}",
        metadata={"invoice_id": str(inv.id), "invoice_token": str(inv.public_token)},  # type: ignore
    )
    return redirect(session.url)


def invoice_pay_success(request, token):
    inv = _get_invoice_by_token(token)
    recalc_invoice(inv)
    return render(request, "invoices/invoice_pay_success.html", {"inv": inv})


# =============================================================================
# PDF / Email
# =============================================================================

@login_required
@require_subscription
def invoice_pdf(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "project"), pk=pk, company=company
    )
    recalc_invoice(inv)
    html = render_to_string("core/pdf/invoice.html", {"inv": inv})
    pdf_bytes = _render_pdf_from_html(html, base_url=request.build_absolute_uri("/"))
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="invoice_{inv.number}.pdf"'
    return resp


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def invoice_email(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "project"), pk=pk, company=company
    )
    recalc_invoice(inv)

    from core.forms import SendEmailForm  # local import to avoid cross-app init issues

    initial = {
        "to": getattr(inv.client, "email", "") or "",
        "subject": f"Invoice {inv.number} from {inv.company.name}",
        "message": "",
    }

    form = SendEmailForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        to = [form.cleaned_data["to"]]
        cc_raw = form.cleaned_data.get("cc") or ""
        cc = [e.strip() for e in cc_raw.split(",") if e.strip()]
        subject = form.cleaned_data["subject"]
        body = form.cleaned_data["message"] or render_to_string(
            "core/email/invoice_email.txt", {"inv": inv, "site_url": settings.SITE_URL}
        )

        html = render_to_string("core/pdf/invoice.html", {"inv": inv})
        pdf_bytes = _render_pdf_from_html(html, base_url=request.build_absolute_uri("/"))
        filename = f"invoice_{inv.number}.pdf"

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=to,
            cc=cc or None,
        )
        email.attach(filename, pdf_bytes, "application/pdf")
        email.send(fail_silently=False)
        messages.success(
            request,
            f"Invoice emailed to {to[0]}{(' (cc: ' + ', '.join(cc) + ')' if cc else '')}.",
        )
        return redirect("invoices:invoice_detail", pk=pk)

    return render(request, "core/email_send_form.html", {"form": form, "obj": inv, "kind": "invoice"})


# =============================================================================
# Reminders / Refunds
# =============================================================================

@login_required
@require_subscription
def invoice_send_reminder(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "project"), pk=pk, company=company
    )
    recalc_invoice(inv)

    if not getattr(inv, "allow_reminders", True):
        messages.info(request, "Reminders are disabled for this invoice.")
        return redirect("invoices:invoice_detail", pk=pk)

    balance = getattr(inv, "balance", None)
    if balance is None:
        balance = (inv.total or Decimal("0")) - (inv.amount_paid or Decimal("0"))

    if balance <= 0:
        messages.info(request, "This invoice is fully paid.")
        return redirect("invoices:invoice_detail", pk=pk)

    if inv.status in (Invoice.VOID, Invoice.DRAFT):
        messages.info(request, "This invoice is not eligible for reminders.")
        return redirect("invoices:invoice_detail", pk=pk)

    to_email = getattr(inv.client, "email", None)
    if not to_email:
        messages.error(request, "The client doesn’t have an email address.")
        return redirect("invoices:invoice_detail", pk=pk)

    days: Optional[int] = None
    if inv.due_date:
        days = (timezone.now().date() - inv.due_date).days

    if days is not None and days > 0:
        base_subject = f"Overdue: Invoice {inv.number} ({days} day{'s' if days != 1 else ''} past due)"
    elif days == 0:
        base_subject = f"Due today: Invoice {inv.number}"
    elif inv.due_date:
        base_subject = f"Reminder: Invoice {inv.number} due {inv.due_date}"
    else:
        base_subject = f"Reminder: Invoice {inv.number}"

    subject = f"{getattr(settings, 'EMAIL_SUBJECT_PREFIX', '[EZ360PM] ')}{base_subject}"

    public_url = f"{settings.SITE_URL}{reverse('invoices:invoice_public', kwargs={'token': str(inv.public_token)})}"
    body = render_to_string(
        "core/email/invoice_reminder_email.txt",
        {"inv": inv, "site_url": settings.SITE_URL, "public_url": public_url, "days": days},
    )

    pdf_bytes = None
    try:
        from invoices.pdf import render_invoice_pdf  # type: ignore
        try:
            pdf_bytes = render_invoice_pdf(inv, request=request)  # type: ignore[arg-type]
        except TypeError:
            pdf_bytes = render_invoice_pdf(inv)
    except Exception:
        try:
            html = render_to_string("core/pdf/invoice.html", {"inv": inv})
            from core.pdf import _render_pdf_from_html as alt_render  # type: ignore
            pdf_bytes = alt_render(html, base_url=request.build_absolute_uri("/"))
        except Exception:
            pdf_bytes = None

    email = EmailMessage(
        subject=subject, body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    if pdf_bytes:
        email.attach(f"invoice_{inv.number}.pdf", pdf_bytes, "application/pdf")
    email.send(fail_silently=False)

    inv.last_reminder_sent_at = timezone.now()
    log = inv.reminder_log.split(",") if getattr(inv, "reminder_log", "") else []
    log.append("manual")
    inv.reminder_log = ",".join(log)
    inv.save(update_fields=["last_reminder_sent_at", "reminder_log"])

    try:
        notify_company(
            company,
            request.user,
            f"Reminder sent for invoice {inv.number} to {to_email}",
            url=reverse("invoices:invoice_detail", args=[inv.pk]),
            kind=Notification.GENERIC,
        )
    except Exception:
        pass

    messages.success(request, f"Reminder sent to {to_email}.")
    return redirect("invoices:invoice_detail", pk=pk)


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def invoice_refund(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "project"), pk=pk, company=company
    )
    recalc_invoice(inv)

    refundable = inv.amount_paid or Decimal("0.00")
    if refundable <= 0:
        messages.info(request, "There are no funds to refund on this invoice.")
        return redirect("invoices:invoice_detail", pk=pk)

    from payments.forms import RefundForm  # local import to avoid init issues
    form = RefundForm(request.POST or None, invoice=inv)

    if request.method == "POST" and form.is_valid():
        amt: Decimal = form.cleaned_data["amount"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if amt > refundable:
            messages.error(request, f"Amount exceeds refundable balance (${refundable}).")
            return render(
                request, "invoices/invoice_refund_form.html",
                {"form": form, "inv": inv, "refundable": refundable},
            )

        did_stripe = False
        refund_ext_id = ""
        use_stripe = form.cleaned_data.get("use_stripe", False) if "use_stripe" in form.fields else False
        pi_id = form.cleaned_data.get("payment_intent") if use_stripe else None

        if use_stripe:
            if not pi_id:
                messages.error(request, "Select a Stripe payment to refund.")
                return render(
                    request, "invoices/invoice_refund_form.html",
                    {"form": form, "inv": inv, "refundable": refundable},
                )
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                re_ = stripe.Refund.create(payment_intent=pi_id, amount=int(amt * 100))
                refund_ext_id = f"{pi_id}:refund:{re_['id']}"
                did_stripe = True
            except Exception as e:
                messages.error(request, f"Stripe refund failed: {e}")
                return render(
                    request, "invoices/invoice_refund_form.html",
                    {"form": form, "inv": inv, "refundable": refundable},
                )

        external_id = refund_ext_id or f"manual-refund-{uuid4()}"
        Payment.objects.get_or_create(
            company=inv.company,
            invoice=inv,
            external_id=external_id,
            defaults={
                "amount": -amt,
                "received_at": timezone.now(),
                "method": "Stripe Refund" if did_stripe else "Manual Refund",
            },
        )

        recalc_invoice(inv)
        try:
            notify_company(
                company,
                request.user,
                f"Refund recorded for invoice {inv.number} (${amt}).",
                url=reverse("invoices:invoice_detail", args=[inv.pk]),
                kind=Notification.GENERIC,
            )
        except Exception:
            pass

        messages.success(request, f"Refund of ${amt} {'issued via Stripe and ' if did_stripe else ''}recorded.")
        return redirect("invoices:invoice_detail", pk=pk)

    return render(request, "invoices/invoice_refund_form.html", {"form": form, "inv": inv, "refundable": refundable})


# =============================================================================
# Time → Invoice (wizard)
# =============================================================================

@login_required
@require_http_methods(["GET", "POST"])
def project_invoice_time(request, pk: int):
    company = get_active_company(request)
    if not company:
        return redirect("core:onboarding_company")

    project = get_object_or_404(Project.objects.select_related("client"), pk=pk, company=company)
    start_default, end_default = default_range_last_30()

    if request.method == "POST":
        form = TimeToInvoiceForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            inv = create_invoice_from_time(
                project=project,
                company=company,
                start=cd["start"],
                end=cd["end"],
                group_by=cd["group_by"],
                rounding=cd["rounding"],
                override_rate=cd.get("override_rate"),
                description_prefix=cd.get("description") or "",
                include_expenses=cd.get("include_expenses", True),
                expense_group_by=cd.get("expense_group_by") or "category",
                expense_markup_override=cd.get("expense_markup_override"),
                expense_label_prefix=cd.get("expense_label_prefix") or "",
                only_approved=cd.get("include_only_approved", True),
            )
            messages.success(request, f"Draft invoice {inv.number} created.")
            return redirect("invoices:invoice_detail", inv.pk)
    else:
        form = TimeToInvoiceForm(initial={
            "start": start_default,
            "end": end_default,
            "rounding": "0.25",
            "group_by": "day",
            "include_expenses": True,
            "include_only_approved": True,
        })

    if form.is_bound and form.is_valid():
        cd = form.cleaned_data
        start = cd["start"]; end = cd["end"]
        include_only_approved = cd.get("include_only_approved", True)
        include_expenses = cd.get("include_expenses", True)
        markup_override = cd.get("expense_markup_override")
    else:
        start, end = start_default, end_default
        include_only_approved = True
        include_expenses = True
        markup_override = None

    time_qs = project.time_entries.filter(  # type: ignore[attr-defined]
        is_billable=True,
        invoice__isnull=True,
        start_time__date__gte=start,
        start_time__date__lte=end,
    )
    if include_only_approved:
        time_qs = time_qs.filter(approved_at__isnull=False)

    preview_hours = (
        time_qs.aggregate(s=Coalesce(Sum("hours"), Value(Decimal("0.00")), output_field=DecimalField()))
        .get("s") or Decimal("0.00")
    )

    preview_expenses = Decimal("0.00")
    if include_expenses:
        exp_qs = Expense.objects.filter(
            project=project,
            company=company,
            invoice__isnull=True,
            is_billable=True,
            date__gte=start,
            date__lte=end,
        ).only("amount", "billable_markup_pct")

        for e in exp_qs.iterator():
            base = Decimal(str(e.amount or 0))
            pct = Decimal(str(markup_override if markup_override is not None else e.billable_markup_pct or 0))
            price = (base * (Decimal("1.00") + (pct / Decimal("100.00")))).quantize(Decimal("0.01"))
            preview_expenses += price

    context = {
        "project": project,
        "form": form,
        "project_rate": project.hourly_rate or Decimal("0.00"),
        "preview_hours": preview_hours.quantize(Decimal("0.01")),
        "preview_expenses": preview_expenses.quantize(Decimal("0.01")) if include_expenses else None,
    }
    return render(request, "projects/project_invoice_time.html", context)


# =============================================================================
# Recurring Invoices
# =============================================================================

@login_required
def recurring_list(request):
    company = get_active_company(request)

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    frequency = (request.GET.get("frequency") or "").strip()

    qs = RecurringPlan.objects.filter(company=company).select_related(
        "client", "project", "template_invoice"
    )

    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(client__org__icontains=q)
            | Q(client__first_name__icontains=q)
            | Q(client__last_name__icontains=q)
        )

    if status in (RecurringPlan.ACTIVE, RecurringPlan.PAUSED):
        qs = qs.filter(status=status)

    if frequency in (RecurringPlan.WEEKLY, RecurringPlan.MONTHLY, RecurringPlan.QUARTERLY, RecurringPlan.YEARLY):
        qs = qs.filter(frequency=frequency)

    qs = qs.order_by("next_run_date", "id")

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "plans": page_obj.object_list,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "q": q,
        "status": status,
        "frequency": frequency,
    }
    return render(request, "invoices/recurring_list.html", context)


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def recurring_create(request):
    company = get_active_company(request)
    if request.method == "POST":
        form = RecurringPlanForm(request.POST, company=company)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.company = company
            if not plan.next_run_date:
                plan.next_run_date = plan.start_date
            plan.save()
            messages.success(request, "Recurring plan created.")
            return redirect("invoices:recurring_list")
    else:
        form = RecurringPlanForm(initial={}, company=company)
    return render(request, "invoices/recurring_form.html", {"form": form, "mode": "create"})


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def recurring_update(request, pk: int):
    company = get_active_company(request)
    plan = get_object_or_404(RecurringPlan, pk=pk, company=company)
    if request.method == "POST":
        form = RecurringPlanForm(request.POST, instance=plan, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Recurring plan updated.")
            return redirect("invoices:recurring_list")
    else:
        form = RecurringPlanForm(instance=plan, company=company)
    return render(
        request, "invoices/recurring_form.html", {"form": form, "mode": "edit", "plan": plan}
    )


@login_required
@require_subscription
@require_http_methods(["POST"])
def recurring_toggle_status(request, pk: int):
    company = get_active_company(request)
    plan = get_object_or_404(RecurringPlan, pk=pk, company=company)
    plan.status = RecurringPlan.PAUSED if plan.status == RecurringPlan.ACTIVE else RecurringPlan.ACTIVE
    plan.save(update_fields=["status"])
    messages.success(
        request, f"Plan {'paused' if plan.status == RecurringPlan.PAUSED else 'activated'}."
    )
    return redirect("invoices:recurring_list")


@login_required
@require_subscription
@require_http_methods(["POST"])
def recurring_run_now(request, pk: int):
    company = get_active_company(request)
    plan = get_object_or_404(RecurringPlan, pk=pk, company=company)
    if not plan.is_active():
        messages.error(request, "Plan is not active or has reached its end.")
        return redirect("invoices:recurring_list")

    inv = generate_invoice_from_plan(plan)
    if plan.auto_email:
        try:
            email_invoice_default(inv, request_base_url=request.build_absolute_uri("/"))
            inv.status = Invoice.SENT
            inv.save(update_fields=["status"])
        except Exception as e:
            messages.warning(request, f"Invoice created but email failed: {e}")

    from invoices.services import advance_plan_after_run
    advance_plan_after_run(plan)

    messages.success(request, f"Generated invoice {inv.number} from plan “{plan.title}”.")
    return redirect("invoices:invoice_detail", pk=inv.pk)


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def recurring_delete(request, pk: int):
    company = get_active_company(request)
    plan = get_object_or_404(RecurringPlan, pk=pk, company=company)
    if request.method == "POST":
        plan.delete()
        messages.success(request, "Recurring plan deleted.")
        return redirect("invoices:recurring_list")
    return render(request, "invoices/recurring_confirm_delete.html", {"plan": plan})
