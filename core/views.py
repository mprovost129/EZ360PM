# core/views.py
from __future__ import annotations

from datetime import timedelta, date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import uuid4
from core.decorators import subscription_or_landing

import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F, Value
from django.db.models.functions import Coalesce, Greatest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from django.template.loader import render_to_string

from django.contrib.postgres.search import (
    SearchVector,
    SearchQuery,
    SearchRank,
    TrigramSimilarity,
)

from core.decorators import require_subscription
from .emails import send_invoice_email, send_estimate_email
from .forms import (
    ClientForm,
    CompanyForm,
    ConvertEstimateToProjectForm,
    EstimateForm,
    EstimateItemFormSet,
    ExpenseForm,
    InviteForm,
    InvoiceForm,
    InvoiceItemFormSet,
    MemberForm,
    PaymentForm,
    ProjectForm,
    RecurringPlanForm,
    SendEmailForm,
    TimeEntryForm,
    TimeToInvoiceForm,
    TimesheetSubmitForm,
    TimesheetWeekForm,
    UserProfileForm,
    RefundForm,
)
from .models import (
    Client,
    Company,
    CompanyInvite,
    CompanyMember,
    Estimate,
    EstimateItem,
    Expense,
    Invoice,
    InvoiceItem,
    Notification,
    Payment,
    Project,
    RecurringPlan,
    TimeEntry,
)
from .services import (
    convert_estimate_to_invoice,
    create_invoice_from_time,
    email_invoice_default,
    generate_invoice_from_plan,
    mark_all_read,
    recalc_estimate,
    recalc_invoice,
)
from .utils import (
    combine_midday,
    default_range_last_30,
    generate_estimate_number,
    generate_invoice_number,
    generate_project_number,
    get_active_company,
    get_user_companies,
    get_user_membership,
    get_user_profile,
    parse_date,
    require_company_admin,
    set_active_company,
    week_range,
)
from .services import notify_company

# --- Plan helpers (features & limits) ---
try:
    from billing.utils import (  # type: ignore
        enforce_limit_or_upsell, # type: ignore
        require_feature, # type: ignore
        require_tier_at_least, # type: ignore
    )
except Exception:
    def enforce_limit_or_upsell(company, key: str, current_count: int):
        return True, None

    def require_feature(key: str):
        def _deco(fn):
            return fn

        return _deco

    def require_tier_at_least(slug: str):
        def _deco(fn):
            return fn

        return _deco


User = get_user_model()
stripe.api_key = settings.STRIPE_SECRET_KEY

@login_required
@subscription_or_landing(
    "core/landing_generic.html",
    context={"title": "Clients", "lead": "A simple CRM for people you work with.",
             "cta_primary_label": "See plans", "cta_secondary_label": "Learn more",
             "icon": "people"},
    context_cb=lambda r: {
        "cta_primary_url": reverse("billing:plans"),
        "cta_secondary_url": reverse("dashboard:home") + "#features",
    },
)


# ---------- Clients ----------
@login_required
def clients_list(request):
    company = get_active_company(request)
    q = (request.GET.get("q") or "").strip()
    qs = Client.objects.filter(company=company)
    if q:
        qs = qs.filter(
            Q(org__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(email__icontains=q)
        )

    paginator = Paginator(qs.order_by("-created_at"), 15)
    page = request.GET.get("page")
    clients = paginator.get_page(page)
    return render(request, "core/clients_list.html", {"clients": clients, "q": q})


@login_required
@require_subscription
def client_create(request):
    company = get_active_company(request)

    # Plan limit: max_clients
    count = Client.objects.filter(company=company).count()
    ok, limit = enforce_limit_or_upsell(company, "max_clients", count)
    if not ok:
        messages.warning(
            request, f"You've reached your plan’s limit of {limit} clients. Upgrade to add more."
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            messages.success(request, "Client created.")
            return redirect("core:clients")
    else:
        form = ClientForm()
    return render(request, "core/client_form.html", {"form": form, "mode": "create"})


@login_required
@require_subscription
def client_update(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Client, pk=pk, company=company)
    if request.method == "POST":
        form = ClientForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Client updated.")
            return redirect("core:clients")
    else:
        form = ClientForm(instance=obj)
    return render(request, "core/client_form.html", {"form": form, "mode": "edit", "obj": obj})


@login_required
@require_subscription
def client_delete(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Client, pk=pk, company=company)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Client deleted.")
        return redirect("core:clients")
    return render(request, "core/client_confirm_delete.html", {"obj": obj})


# ---------- Projects ----------

@login_required
@require_subscription
def projects_list(request):
    company = get_active_company(request)
    q = (request.GET.get("q") or "").strip()
    sort = (request.GET.get("sort") or "recent").lower()

    qs = (
        Project.objects.filter(company=company)
        .select_related("client")
        .prefetch_related("team")
        .annotate(logged_hours=Sum("time_entries__hours"))
    )

    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(number__icontains=q)
            | Q(client__org__icontains=q)
            | Q(client__first_name__icontains=q)
            | Q(client__last_name__icontains=q)
        )

    order_map = {
        "recent": "-created_at",
        "number": "number",
        "client": "client__org",
        "due": "due_date",
        "name": "name",
    }
    qs = qs.order_by(order_map.get(sort, "-created_at"))

    return render(request, "core/projects_list.html", {"projects": qs, "q": q, "sort": sort})


@login_required
@require_subscription
def project_create_hourly(request):
    return _project_create(request, default_type=Project.HOURLY)


@login_required
@require_subscription
def project_create_flat(request):
    return _project_create(request, default_type=Project.FLAT)


@login_required
@require_subscription
def _project_create(request, default_type: str):
    company = get_active_company(request)

    # Plan limit: max_projects
    count = Project.objects.filter(company=company).count()
    ok, limit = enforce_limit_or_upsell(company, "max_projects", count)
    if not ok:
        messages.warning(
            request, f"You've reached your plan’s limit of {limit} projects. Upgrade to add more."
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = ProjectForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.billing_type = form.cleaned_data.get("billing_type") or default_type
            obj.save()
            notify_company(
                company,
                request.user,
                f"Project {obj.number or ''} {obj.name} created",
                url=reverse("core:project_detail", args=[obj.pk]),
                kind=Notification.PROJECT_CREATED,
            )
            form.save_m2m()
            messages.success(request, "Project created.")
            return redirect("core:project_detail", pk=obj.pk)
    else:
        form = ProjectForm(initial={"billing_type": default_type})
    return render(
        request, "core/project_form.html", {"form": form, "mode": "create", "default_type": default_type}
    )


@login_required
@require_subscription
def project_update(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Project, pk=pk, company=company)
    if request.method == "POST":
        form = ProjectForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Project updated.")
            return redirect("core:project_detail", pk=obj.pk)
    else:
        form = ProjectForm(instance=obj)
    return render(request, "core/project_form.html", {"form": form, "mode": "edit", "obj": obj})


@login_required
@require_subscription
def project_delete(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Project, pk=pk, company=company)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Project deleted.")
        return redirect("core:projects")
    return render(request, "core/project_confirm_delete.html", {"obj": obj})


@login_required
@require_subscription
def project_detail(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Project.objects.select_related("client"), pk=pk, company=company)

    # Active timer for current user
    active = (
        TimeEntry.objects.filter(project=obj, user=request.user, ended_at__isnull=True)
        .order_by("-started_at")
        .first()
    )

    # Totals
    total_hours = TimeEntry.objects.filter(project=obj).aggregate(s=Sum("hours")).get("s") or 0
    unbilled_hours = (
        TimeEntry.objects.filter(project=obj, invoice__isnull=True).aggregate(s=Sum("hours")).get("s") or 0
    )
    unbilled_expenses_count = Expense.objects.filter(
        project=obj, is_billable=True, invoice__isnull=True
    ).count()

    # Sorted entries for the table
    time_entries = obj.time_entries.all().order_by("-started_at", "-id")  # type: ignore

    return render(
        request,
        "core/project_detail.html",
        {
            "obj": obj,
            "active": active,
            "total_hours": total_hours,
            "unbilled_hours": unbilled_hours,
            "unbilled_expenses_count": unbilled_expenses_count,
            "time_entries": time_entries,
        },
    )


# ---------- Invoices ----------

@login_required
def invoices_list(request):
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

    # Summary: total outstanding
    outstanding = sum((inv.total or 0) - (inv.amount_paid or 0) for inv in qs)

    return render(
        request,
        "core/invoices_list.html",
        {"invoices": qs, "q": q, "status": status, "outstanding": outstanding},
    )


@login_required
@require_subscription
def invoice_create(request):
    company = get_active_company(request)

    # Plan limit: max_invoices
    count = Invoice.objects.filter(company=company).count()
    ok, limit = enforce_limit_or_upsell(company, "max_invoices", count)
    if not ok:
        messages.warning(
            request, f"You've reached your plan’s limit of {limit} invoices. Upgrade to add more."
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = InvoiceForm(request.POST, company=company)
        formset = InvoiceItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            inv = form.save(commit=False)
            inv.company = company
            if not inv.number:
                inv.number = generate_invoice_number(company) # type: ignore
            inv.save()
            formset.instance = inv
            formset.save()
            notify_company(
                company,
                request.user,
                f"Invoice {inv.number} created for {inv.client}",
                url=reverse("core:invoice_detail", args=[inv.pk]),
                kind=Notification.INVOICE_CREATED,
            )
            recalc_invoice(inv)
            messages.success(request, "Invoice created.")
            return redirect("core:invoice_detail", pk=inv.pk)
    else:
        form = InvoiceForm(company=company, initial={"number": generate_invoice_number(company)}) # type: ignore
        formset = InvoiceItemFormSet()
    return render(request, "core/invoice_form.html", {"form": form, "formset": formset, "mode": "create"})


@login_required
@require_subscription
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
            return redirect("core:invoice_detail", pk=inv.pk)
    else:
        form = InvoiceForm(instance=inv, company=company)
        formset = InvoiceItemFormSet(instance=inv)
    return render(
        request, "core/invoice_form.html", {"form": form, "formset": formset, "mode": "edit", "inv": inv}
    )


@login_required
@require_subscription
def invoice_detail(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "project"),
        pk=pk,
        company=company,
    )
    recalc_invoice(inv)
    return render(request, "core/invoice_detail.html", {"inv": inv})


@login_required
@require_subscription
def invoice_delete(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(Invoice, pk=pk, company=company)
    if request.method == "POST":
        inv.delete()
        messages.success(request, "Invoice deleted.")
        return redirect("core:invoices")
    return render(request, "core/invoice_confirm_delete.html", {"inv": inv})


@login_required
@require_subscription
def invoice_mark_sent(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(Invoice, pk=pk, company=company)
    inv.status = Invoice.SENT
    inv.save(update_fields=["status"])
    messages.success(request, "Invoice marked as sent.")
    return redirect("core:invoice_detail", pk=pk)


@login_required
@require_subscription
def invoice_void(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(Invoice, pk=pk, company=company)
    inv.status = Invoice.VOID
    inv.save(update_fields=["status"])
    messages.success(request, "Invoice voided.")
    return redirect("core:invoice_detail", pk=pk)


# --- Public invoice view (no auth) ---

def _get_invoice_by_token(token):
    return get_object_or_404(
        Invoice.objects.select_related("client", "project"),
        public_token=token,
    )


def invoice_public(request, token):
    inv = _get_invoice_by_token(token)
    recalc_invoice(inv)
    return render(
        request,
        "core/invoice_public.html",
        {"inv": inv, "stripe_pk": settings.STRIPE_PUBLIC_KEY},
    )


def invoice_checkout(request, token):
    inv = _get_invoice_by_token(token)
    recalc_invoice(inv)
    if inv.balance <= 0:  # type: ignore[attr-defined]
        messages.info(request, "This invoice is already paid.")
        return redirect("core:invoice_public", token=token)

    # One-time payment for the outstanding balance
    balance = (inv.balance or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)  # type: ignore[attr-defined]
    amount_cents = int(balance * 100)
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[
            {
                "price_data": {
                    "currency": inv.currency or "usd",
                    "product_data": {"name": f"Invoice {inv.number}"},
                    "unit_amount": amount_cents,
                },
                "quantity": 1,
            }
        ],
        success_url=f"{settings.SITE_URL}{reverse('core:invoice_pay_success', kwargs={'token': str(inv.public_token)})}?sid={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.SITE_URL}{reverse('core:invoice_public', kwargs={'token': str(inv.public_token)})}",
        metadata={
            "invoice_id": str(inv.id),  # type: ignore
            "invoice_token": str(inv.public_token),
        },
    )
    return redirect(session.url)


def invoice_pay_success(request, token):
    inv = _get_invoice_by_token(token)
    recalc_invoice(inv)
    return render(request, "core/invoice_pay_success.html", {"inv": inv})


# ---------- Payments ----------

@login_required
def payments_list(request):
    return render(request, "core/payments_list.html")


@login_required
@require_subscription
def payment_create(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(Invoice, pk=pk, company=company)
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            p = form.save(commit=False)
            notify_company(
                company,
                request.user,
                f"Payment {p.amount} recorded for invoice {inv.number}",
                url=reverse("core:invoice_detail", args=[inv.pk]),
                kind=Notification.INVOICE_PAID,
            )
            p.company = company
            p.invoice = inv
            p.save()
            recalc_invoice(inv)
            messages.success(request, "Payment recorded.")
            return redirect("core:invoice_detail", pk=pk)
    else:
        form = PaymentForm()
    return render(request, "core/payment_form.html", {"form": form, "inv": inv})


# ---------- Time tracking ----------

@login_required
def time_list(request):
    return render(request, "core/time_list.html")


@login_required
@require_subscription
def project_timer_start(request, pk: int):
    company = get_active_company(request)
    project = get_object_or_404(Project, pk=pk, company=company)
    existing = TimeEntry.objects.filter(
        project=project, user=request.user, ended_at__isnull=True
    ).exists()
    if existing:
        messages.warning(request, "You already have a running timer on this project.")
        return redirect("core:project_detail", pk=pk)
    TimeEntry.objects.create(project=project, user=request.user, started_at=timezone.now())
    messages.success(request, "Timer started.")
    return redirect("core:project_detail", pk=pk)


@login_required
@require_subscription
def project_timer_stop(request, pk: int):
    company = get_active_company(request)
    project = get_object_or_404(Project, pk=pk, company=company)
    entry = (
        TimeEntry.objects.filter(project=project, user=request.user, ended_at__isnull=True)
        .order_by("-started_at")
        .first()
    )
    if not entry:
        messages.warning(request, "No active timer.")
        return redirect("core:project_detail", pk=pk)

    entry.ended_at = timezone.now()
    delta: timedelta = entry.ended_at - entry.started_at  # type: ignore
    entry.hours = round(delta.total_seconds() / 3600, 2) # type: ignore
    entry.save(update_fields=["ended_at", "hours"])
    messages.success(request, f"Timer stopped. Added {entry.hours}h.")
    return redirect("core:project_detail", pk=pk)


@login_required
@require_subscription
def timeentry_create(request, pk: int):
    company = get_active_company(request)
    project = get_object_or_404(Project, pk=pk, company=company)
    if request.method == "POST":
        form = TimeEntryForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.project = project
            t.user = request.user
            # If both started/ended provided but hours empty, compute hours
            if t.started_at and t.ended_at and not t.hours:
                delta = t.ended_at - t.started_at
                t.hours = round(delta.total_seconds() / 3600, 2)
            t.save()
            notify_company(
                company,
                request.user,
                f"Time entry added on {project.name}: {t.hours or 'timer'} h",
                url=reverse("core:project_detail", args=[project.pk]),
                kind=Notification.TIME_ADDED,
            )
            messages.success(request, "Time entry added.")
            return redirect("core:project_detail", pk=pk)
    else:
        form = TimeEntryForm()
    return render(request, "core/timeentry_form.html", {"form": form, "project": project})


# ---------- Expenses ----------

@login_required
def expenses_list(request):
    company = get_active_company(request)
    q = (request.GET.get("q") or "").strip()
    start = parse_date(request.GET.get("start"))
    end = parse_date(request.GET.get("end"))
    if not start or not end:
        start, end = default_range_last_30()

    qs = Expense.objects.filter(company=company, date__range=(start, end))
    if q:
        qs = qs.filter(
            Q(description__icontains=q)
            | Q(vendor__icontains=q)
            | Q(category__icontains=q)
            | Q(project__name__icontains=q)
            | Q(project__number__icontains=q)
        )
    qs = qs.select_related("project").order_by("-date", "-id")

    total = qs.aggregate(s=Sum("amount")).get("s") or Decimal("0")

    return render(
        request,
        "core/expenses_list.html",
        {"expenses": qs, "q": q, "start": start, "end": end, "total": total},
    )


@login_required
@require_subscription
def expense_create(request):
    company = get_active_company(request)

    # Plan limit: max_expenses
    count = Expense.objects.filter(company=company).count()
    ok, limit = enforce_limit_or_upsell(company, "max_expenses", count)
    if not ok:
        messages.warning(
            request, f"You've reached your plan’s limit of {limit} expenses. Upgrade to add more."
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = ExpenseForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()
            notify_company(
                company,
                request.user,
                f"Expense {obj.amount} • {obj.description or obj.vendor or 'Expense'}",
                url=reverse("core:expenses") + f"?q={obj.description or ''}",
                kind=Notification.EXPENSE_ADDED,
            )
            messages.success(request, "Expense created.")
            return redirect("core:expenses")
    else:
        form = ExpenseForm(initial={"date": timezone.now().date()})
    return render(request, "core/expense_form.html", {"form": form, "mode": "create"})


@login_required
@require_subscription
def expense_update(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Expense, pk=pk, company=company)
    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Expense updated.")
            return redirect("core:expenses")
    else:
        form = ExpenseForm(instance=obj)
    return render(request, "core/expense_form.html", {"form": form, "mode": "edit", "obj": obj})


@login_required
@require_subscription
def expense_delete(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Expense, pk=pk, company=company)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Expense deleted.")
        return redirect("core:expenses")
    return render(request, "core/expense_confirm_delete.html", {"obj": obj})


# ---------- Reports ----------

@login_required
@require_subscription
@require_tier_at_least("pro")  # Example: gate P&L to Pro and above
def reports_index(request):
    return render(request, "core/reports_index.html")


@login_required
@require_subscription
@require_tier_at_least("pro")  # Example: advanced report
def report_pnl(request):
    company = get_active_company(request)
    basis = (request.GET.get("basis") or "cash").lower()  # cash | accrual
    start = parse_date(request.GET.get("start"))
    end = parse_date(request.GET.get("end"))
    if not start or not end:
        start, end = default_range_last_30()

    # Income
    if basis == "accrual":
        income_qs = Invoice.objects.filter(company=company, issue_date__range=(start, end))
        income_total = income_qs.aggregate(s=Sum("total")).get("s") or Decimal("0")
    else:  # cash
        pay_qs = Payment.objects.filter(company=company, received_at__date__range=(start, end))
        income_total = pay_qs.aggregate(s=Sum("amount")).get("s") or Decimal("0")

    # Expenses
    exp_qs = Expense.objects.filter(company=company, date__range=(start, end))
    expenses_total = exp_qs.aggregate(s=Sum("amount")).get("s") or Decimal("0")

    profit = income_total - expenses_total

    # Category breakdown
    by_cat = exp_qs.values("category").annotate(total=Sum("amount")).order_by("category")

    context = {
        "basis": basis,
        "start": start,
        "end": end,
        "income_total": income_total,
        "expenses_total": expenses_total,
        "profit": profit,
        "by_cat": by_cat,
    }
    return render(request, "core/report_pnl.html", context)


@login_required
@require_subscription
@require_tier_at_least("pro")
def report_pnl_csv(request):
    company = get_active_company(request)
    basis = (request.GET.get("basis") or "cash").lower()
    start = parse_date(request.GET.get("start"))
    end = parse_date(request.GET.get("end"))
    if not start or not end:
        start, end = default_range_last_30()

    if basis == "accrual":
        income_qs = Invoice.objects.filter(company=company, issue_date__range=(start, end))
        income_total = income_qs.aggregate(s=Sum("total")).get("s") or Decimal("0")
    else:
        pay_qs = Payment.objects.filter(company=company, received_at__date__range=(start, end))
        income_total = pay_qs.aggregate(s=Sum("amount")).get("s") or Decimal("0")

    exp_qs = Expense.objects.filter(company=company, date__range=(start, end))
    expenses_total = exp_qs.aggregate(s=Sum("amount")).get("s") or Decimal("0")

    profit = income_total - expenses_total

    # CSV
    from csv import writer as csv_writer
    from io import StringIO

    buf = StringIO()
    w = csv_writer(buf)
    w.writerow(["Basis", basis])
    w.writerow(["Start", start.isoformat(), "End", end.isoformat()])
    w.writerow([])
    w.writerow(["Income", f"{income_total}"])
    w.writerow(["Expenses", f"{expenses_total}"])
    w.writerow(["Profit", f"{profit}"])
    w.writerow([])
    w.writerow(["Category", "Total"])
    for row in (
        exp_qs.values_list("category")
        .annotate(total=Sum("amount"))
        .order_by("category")
    ):
        w.writerow([row[0] or "(Uncategorized)", f"{row[1]}"])

    res = HttpResponse(buf.getvalue(), content_type="text/csv")
    res["Content-Disposition"] = f"attachment; filename=pnl_{start}_{end}_{basis}.csv"
    return res


# ---------- Company / Team ----------

@login_required
def company_profile(request):
    company = get_active_company(request)
    role = None
    if company:
        role = (
            CompanyMember.OWNER
            if company.owner_id == request.user.id # type: ignore
            else CompanyMember.objects.filter(company=company, user=request.user)
            .values_list("role", flat=True)
            .first()
        )
    invites = company.invites.filter(status=CompanyInvite.PENDING).order_by("-sent_at") if company else []  # type: ignore[attr-defined]
    members = (
        CompanyMember.objects.filter(company=company)
        .select_related("user")
        .order_by("-joined_at")
        if company
        else []
    )
    return render(
        request,
        "core/company_profile.html",
        {
            "company": company,
            "role": role,
            "members": members,
            "invites": invites,
            "companies": get_user_companies(request.user),
        },
    )


@login_required
def company_edit(request):
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")
    if not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to edit company settings.")
        return redirect("core:company_profile")

    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Company updated.")
            return redirect("core:company_profile")
    else:
        form = CompanyForm(instance=company)
    return render(request, "core/company_form.html", {"form": form, "company": company})


@login_required
def team_list(request):
    company = get_active_company(request)
    members = (
        CompanyMember.objects.filter(company=company)
        .select_related("user")
        .order_by("-joined_at")
        if company
        else []
    )
    invites = (
        CompanyInvite.objects.filter(company=company, status=CompanyInvite.PENDING).order_by("-sent_at")
        if company
        else []
    )
    can_manage = require_company_admin(request.user, company) if company else False
    return render(
        request,
        "core/team_list.html",
        {"company": company, "members": members, "invites": invites, "can_manage": can_manage},
    )


@login_required
def invite_create(request):
    company = get_active_company(request)
    if not company or not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to invite members.")
        return redirect("core:team_list")

    if request.method == "POST":
        form = InviteForm(request.POST)
        if form.is_valid():
            inv = form.save(commit=False)
            inv.company = company
            inv.invited_by = request.user
            inv.save()
            # Dev UX: show the invite link directly (and you can also email it)
            invite_url = request.build_absolute_uri(redirect("core:invite_accept", token=inv.token).url)
            messages.success(request, f"Invite sent to {inv.email}. Link: {invite_url}")
            print("Invite URL:", invite_url)
            return redirect("core:team_list")
    else:
        form = InviteForm()
    return render(request, "core/invite_form.html", {"form": form, "company": company})


@login_required
def invite_accept(request, token):
    inv = get_object_or_404(CompanyInvite, token=token)
    if inv.status != CompanyInvite.PENDING:
        messages.warning(request, "This invite is no longer valid.")
        return redirect("core:company_profile")

    # Attach current user as a member
    CompanyMember.objects.get_or_create(
        company=inv.company, user=request.user, defaults={"role": inv.role}
    )
    inv.status = CompanyInvite.ACCEPTED
    inv.accepted_at = timezone.now()
    inv.save(update_fields=["status", "accepted_at"])

    set_active_company(request, inv.company)
    messages.success(request, f"You've joined {inv.company.name} as {inv.role}.")
    return redirect("core:team_list")


@login_required
def member_remove(request, member_id: int):
    company = get_active_company(request)
    if not company or not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to remove members.")
        return redirect("core:team_list")
    m = get_object_or_404(CompanyMember, pk=member_id, company=company)
    if request.method == "POST":
        m.delete()
        messages.success(request, "Member removed.")
        return redirect("core:team_list")
    return render(request, "core/member_remove_confirm.html", {"member": m})


@login_required
def company_switch(request, company_id: int):
    # Basic session-based switcher
    c = get_object_or_404(Company, pk=company_id)
    set_active_company(request, c)
    messages.success(request, f"Switched to {c.name}.")
    return redirect("core:company_profile")


# ---------- Estimates ----------

try:
    _require_estimates = require_feature("estimates")  # type: ignore
except Exception:
    def _require_estimates(fn):
        return fn


@login_required
@_require_estimates
def estimates_list(request):
    company = get_active_company(request)
    q = (request.GET.get("q") or "").strip()
    show_templates = request.GET.get("templates") == "1"

    qs = Estimate.objects.filter(company=company)
    if not show_templates:
        qs = qs.filter(is_template=False)

    if q:
        qs = qs.filter(
            Q(number__icontains=q)
            | Q(client__org__icontains=q)
            | Q(client__first_name__icontains=q)
            | Q(client__last_name__icontains=q)
            | Q(project__name__icontains=q)
        )

    qs = qs.select_related("client", "project").order_by("-issue_date", "-id")
    return render(
        request, "core/estimates_list.html", {"estimates": qs, "q": q, "show_templates": show_templates}
    )


@login_required
@require_subscription
@_require_estimates
def estimate_create(request):
    company = get_active_company(request)

    # Plan limit: max_estimates (count non-templates)
    count = Estimate.objects.filter(company=company, is_template=False).count()
    ok, limit = enforce_limit_or_upsell(company, "max_estimates", count)
    if not ok:
        messages.warning(
            request, f"You've reached your plan’s limit of {limit} estimates. Upgrade to add more."
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = EstimateForm(request.POST, company=company)
        formset = EstimateItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            est = form.save(commit=False)
            est.company = company
            if not est.number:
                est.number = generate_estimate_number(company) # type: ignore
            est.save()
            notify_company(
                company,
                request.user,
                f"Estimate {est.number} created for {est.client}",
                url=reverse("core:estimate_detail", args=[est.pk]),
                kind=Notification.ESTIMATE_CREATED,
            )
            formset.instance = est
            formset.save()
            recalc_estimate(est)
            messages.success(request, "Estimate created.")
            return redirect("core:estimate_detail", pk=est.pk)
    else:
        form = EstimateForm(company=company, initial={"number": generate_estimate_number(company)}) # type: ignore
        formset = EstimateItemFormSet()
    return render(request, "core/estimate_form.html", {"form": form, "formset": formset, "mode": "create"})


@login_required
@require_subscription
@_require_estimates
def estimate_create_from(request, pk: int):
    company = get_active_company(request)
    src = get_object_or_404(Estimate, pk=pk, company=company)

    # Plan limit: max_estimates when creating from template as well
    count = Estimate.objects.filter(company=company, is_template=False).count()
    ok, limit = enforce_limit_or_upsell(company, "max_estimates", count)
    if not ok:
        messages.warning(
            request, f"You've reached your plan’s limit of {limit} estimates. Upgrade to add more."
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = EstimateForm(request.POST, company=company)
        formset = EstimateItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            est = form.save(commit=False)
            est.company = company
            if not est.number:
                est.number = generate_estimate_number(company) # type: ignore
            est.save()
            formset.instance = est
            formset.save()
            recalc_estimate(est)
            messages.success(request, "Estimate created from template.")
            return redirect("core:estimate_detail", pk=est.pk)
    else:
        form = EstimateForm(
            instance=None,
            company=company,
            initial={
                "client": src.client_id,  # type: ignore
                "project": src.project_id,  # type: ignore
                "number": generate_estimate_number(company), # type: ignore
                "status": Estimate.DRAFT,
                "issue_date": timezone.now().date(),
                "valid_until": src.valid_until,
                "tax": src.tax,
                "notes": src.notes,
            },
        )
        formset = EstimateItemFormSet(instance=None, queryset=EstimateItem.objects.none())
    return render(
        request,
        "core/estimate_form.html",
        {"form": form, "formset": formset, "mode": "create_from", "src": src},
    )


@login_required
@require_subscription
@_require_estimates
def estimate_detail(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(
        Estimate.objects.select_related("client", "project"), pk=pk, company=company
    )
    recalc_estimate(est)
    return render(request, "core/estimate_detail.html", {"est": est})


@login_required
@require_subscription
@_require_estimates
def estimate_update(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate, pk=pk, company=company)
    if request.method == "POST":
        form = EstimateForm(request.POST, instance=est, company=company)
        formset = EstimateItemFormSet(request.POST, instance=est)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            recalc_estimate(est)
            messages.success(request, "Estimate updated.")
            return redirect("core:estimate_detail", pk=est.pk)
    else:
        form = EstimateForm(instance=est, company=company)
        formset = EstimateItemFormSet(instance=est)
    return render(
        request, "core/estimate_form.html", {"form": form, "formset": formset, "mode": "edit", "est": est}
    )


@login_required
@require_subscription
@_require_estimates
def estimate_delete(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate, pk=pk, company=company)
    if request.method == "POST":
        est.delete()
        messages.success(request, "Estimate deleted.")
        return redirect("core:estimates")
    return render(request, "core/estimate_confirm_delete.html", {"est": est})


@login_required
@require_subscription
@_require_estimates
def estimate_mark_sent(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate, pk=pk, company=company)
    est.status = Estimate.SENT
    est.save(update_fields=["status"])
    messages.success(request, "Estimate marked as sent.")
    return redirect("core:estimate_detail", pk=pk)


@login_required
@require_subscription
@_require_estimates
def estimate_accept(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate, pk=pk, company=company)
    est.status = Estimate.ACCEPTED
    est.save(update_fields=["status"])
    notify_company(
        company,
        request.user,
        f"Estimate {est.number} accepted",
        url=reverse("core:estimate_detail", args=[est.pk]),
        kind=Notification.ESTIMATE_ACCEPTED,
    )
    messages.success(request, "Estimate accepted.")
    return redirect("core:estimate_detail", pk=pk)


@login_required
@require_subscription
@_require_estimates
def estimate_decline(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate, pk=pk, company=company)
    est.status = Estimate.DECLINED
    est.save(update_fields=["status"])
    messages.success(request, "Estimate declined.")
    return redirect("core:estimate_detail", pk=pk)


@login_required
@require_subscription
@_require_estimates
def estimate_convert(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(
        Estimate.objects.select_related("client", "project"), pk=pk, company=company
    )
    inv = convert_estimate_to_invoice(est)
    # assign invoice number now
    if not inv.number:
        inv.number = generate_invoice_number(company) # type: ignore
        inv.save(update_fields=["number"])
        notify_company(
            company,
            request.user,
            f"Estimate {est.number} converted to invoice {inv.number}",
            url=reverse("core:invoice_detail", args=[inv.pk]),
            kind=Notification.ESTIMATE_CONVERTED,
        )
        recalc_invoice(inv)
    messages.success(request, f"Converted to invoice {inv.number}.")
    return redirect("core:invoice_detail", pk=inv.pk)


# --- Public estimate views (no auth) ---

def _get_estimate_by_token(token):
    return get_object_or_404(Estimate.objects.select_related("client", "project"), public_token=token)


def estimate_public(request, token):
    est = _get_estimate_by_token(token)
    recalc_estimate(est)
    items = EstimateItem.objects.filter(estimate=est).order_by("id")

    # Allowed to accept/decline?
    can_act = est.status in (Estimate.DRAFT, Estimate.SENT)
    # Optional: enforce validity window
    if est.valid_until and est.valid_until < timezone.now().date():
        can_act = False

    return render(
        request,
        "core/estimate_public.html",
        {"est": est, "items": items, "can_act": can_act},
    )


@require_http_methods(["POST"])
def estimate_public_accept(request, token):
    est = get_object_or_404(Estimate.objects.select_related("company"), public_token=token)
    if est.status in (Estimate.ACCEPTED, Estimate.DECLINED):
        return redirect("core:estimate_public", token=token)

    signer = (request.POST.get("name") or "").strip()
    note = (request.POST.get("note") or "").strip()

    est.status = Estimate.ACCEPTED
    est.accepted_at = timezone.now()
    est.accepted_by = signer[:120]
    if note:
        est.client_note = (est.client_note + "\n" if est.client_note else "") + note
    est.save(update_fields=["status", "accepted_at", "accepted_by", "client_note"])

    try:
        notify_company(
            est.company,
            None,
            f"Estimate {est.number} accepted by {signer or 'client'}",
            url=reverse("core:estimate_detail", args=[est.pk]),
            kind=Notification.ESTIMATE_ACCEPTED,
            exclude_actor=False,
        )
    except Exception:
        pass

    messages.success(request, "Thanks! Your acceptance has been recorded.")
    return redirect("core:estimate_public", token=token)


@require_http_methods(["POST"])
def estimate_public_decline(request, token):
    est = get_object_or_404(Estimate.objects.select_related("company"), public_token=token)
    if est.status in (Estimate.ACCEPTED, Estimate.DECLINED):
        return redirect("core:estimate_public", token=token)

    signer = (request.POST.get("name") or "").strip()
    note = (request.POST.get("note") or "").strip()

    est.status = Estimate.DECLINED
    est.declined_at = timezone.now()
    est.declined_by = signer[:120]
    if note:
        est.client_note = (est.client_note + "\n" if est.client_note else "") + note
    est.save(update_fields=["status", "declined_at", "declined_by", "client_note"])

    try:
        notify_company(
            est.company,
            None,
            f"Estimate {est.number} declined by {signer or 'client'}",
            url=reverse("core:estimate_detail", args=[est.pk]),
            kind=Notification.ESTIMATE_CREATED,
            exclude_actor=False,
        )
    except Exception:
        pass

    messages.info(request, "Response recorded.")
    return redirect("core:estimate_public", token=token)


# ---------- PDF helpers ----------

def _render_pdf_from_html(html: str, base_url: str) -> bytes:
    """
    Try WeasyPrint first; show a clear error if its native deps aren't installed.
    """
    try:
        from weasyprint import HTML  # lazy import so runserver doesn’t crash
    except Exception as e:
        raise RuntimeError(
            "WeasyPrint isn’t available. Install the GTK/Pango runtime on Windows "
            "or configure an alternate PDF engine."
        ) from e

    return HTML(string=html, base_url=base_url).write_pdf() # type: ignore


@login_required
@require_subscription
def invoice_pdf(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "project"),
        pk=pk,
        company=company,
    )
    recalc_invoice(inv)
    html = render_to_string("core/pdf/invoice.html", {"inv": inv})
    pdf_bytes = _render_pdf_from_html(html, base_url=request.build_absolute_uri("/"))
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="invoice_{inv.number}.pdf"'
    return resp


@login_required
@require_subscription
def estimate_pdf(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(
        Estimate.objects.select_related("client", "project"),
        pk=pk,
        company=company,
    )
    recalc_estimate(est)
    html = render_to_string("core/pdf/estimate.html", {"est": est})
    pdf_bytes = _render_pdf_from_html(html, base_url=request.build_absolute_uri("/"))
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="estimate_{est.number}.pdf"'
    return resp


# ---------- Email (attach PDF + include public link) ----------

@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def invoice_email(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "project"),
        pk=pk,
        company=company,
    )
    recalc_invoice(inv)

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
            "core/email/invoice_email.txt",
            {"inv": inv, "site_url": settings.SITE_URL},
        )

        # PDF attachment
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
            request, f"Invoice emailed to {to[0]}{(' (cc: ' + ', '.join(cc) + ')' if cc else '')}."
        )
        return redirect("core:invoice_detail", pk=pk)

    return render(request, "core/email_send_form.html", {"form": form, "obj": inv, "kind": "invoice"})


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def estimate_email(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(
        Estimate.objects.select_related("client", "project"),
        pk=pk,
        company=company,
    )
    recalc_estimate(est)

    initial = {
        "to": getattr(est.client, "email", "") or "",
        "subject": f"Estimate {est.number} from {est.company.name}",
        "message": "",
    }

    form = SendEmailForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        to = [form.cleaned_data["to"]]
        cc_raw = form.cleaned_data.get("cc") or ""
        cc = [e.strip() for e in cc_raw.split(",") if e.strip()]
        subject = form.cleaned_data["subject"]
        body = form.cleaned_data["message"] or render_to_string(
            "core/email/estimate_email.txt",
            {"est": est, "site_url": settings.SITE_URL},
        )

        html = render_to_string("core/pdf/estimate.html", {"est": est})
        pdf_bytes = _render_pdf_from_html(html, base_url=request.build_absolute_uri("/"))
        filename = f"estimate_{est.number}.pdf"

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
            request, f"Estimate emailed to {to[0]}{(' (cc: ' + ', '.join(cc) + ')' if cc else '')}."
        )
        return redirect("core:estimate_detail", pk=pk)

    return render(request, "core/email_send_form.html", {"form": form, "obj": est, "kind": "estimate"})


@login_required
@require_subscription
def invoice_send_reminder(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "project"),
        pk=pk,
        company=company,
    )
    recalc_invoice(inv)

    # --- Eligibility checks
    if not getattr(inv, "allow_reminders", True):
        messages.info(request, "Reminders are disabled for this invoice.")
        return redirect("core:invoice_detail", pk=pk)

    # Compute balance if not available on the model
    balance = getattr(inv, "balance", None)
    if balance is None:
        balance = (inv.total or Decimal("0")) - (inv.amount_paid or Decimal("0"))

    if balance <= 0:
        messages.info(request, "This invoice is fully paid.")
        return redirect("core:invoice_detail", pk=pk)

    if inv.status in (Invoice.VOID, Invoice.DRAFT):
        messages.info(request, "This invoice is not eligible for reminders.")
        return redirect("core:invoice_detail", pk=pk)

    to_email = getattr(inv.client, "email", None)
    if not to_email:
        messages.error(request, "The client doesn’t have an email address.")
        return redirect("core:invoice_detail", pk=pk)

    # --- Subject
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

    # --- Body
    public_url = f"{settings.SITE_URL}{reverse('core:invoice_public', kwargs={'token': str(inv.public_token)})}"
    body = render_to_string(
        "core/email/invoice_reminder_email.txt",
        {
            "inv": inv,
            "site_url": settings.SITE_URL,
            "public_url": public_url,
            "days": days,
        },
    )

    # --- PDF (attempt helper, fall back to local)
    pdf_bytes = None
    try:
        from core.pdf import render_invoice_pdf  # type: ignore # optional helper
        try:
            pdf_bytes = render_invoice_pdf(inv, request=request)  # type: ignore[arg-type]
        except TypeError:
            pdf_bytes = render_invoice_pdf(inv)
    except Exception:
        try:
            html = render_to_string("core/pdf/invoice.html", {"inv": inv}) # type: ignore
            from core.pdf import _render_pdf_from_html as alt_render  # type: ignore
            pdf_bytes = alt_render(html, base_url=request.build_absolute_uri("/"))
        except Exception:
            pdf_bytes = None  # send without attachment

    # --- Send email
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    if pdf_bytes:
        email.attach(f"invoice_{inv.number}.pdf", pdf_bytes, "application/pdf")
    email.send(fail_silently=False)

    # --- Log
    inv.last_reminder_sent_at = timezone.now()
    log = inv.reminder_log.split(",") if getattr(inv, "reminder_log", "") else []
    log.append("manual")
    inv.reminder_log = ",".join(log)
    inv.save(update_fields=["last_reminder_sent_at", "reminder_log"])

    # --- Activity notification
    try:
        notify_company(
            company,
            request.user,
            f"Reminder sent for invoice {inv.number} to {to_email}",
            url=reverse("core:invoice_detail", args=[inv.pk]),
            kind=Notification.GENERIC,
        )
    except Exception:
        pass

    messages.success(request, f"Reminder sent to {to_email}.")
    return redirect("core:invoice_detail", pk=pk)


# ---------- Recurring Invoices ----------

@login_required
def recurring_list(request):
    company = get_active_company(request)
    plans = RecurringPlan.objects.filter(company=company).select_related(
        "client", "project", "template_invoice"
    )
    return render(request, "core/recurring_list.html", {"plans": plans})


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def recurring_create(request):
    company = get_active_company(request)
    if request.method == "POST":
        form = RecurringPlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.company = company
            if not plan.next_run_date:
                plan.next_run_date = plan.start_date
            plan.save()
            messages.success(request, "Recurring plan created.")
            return redirect("core:recurring_list")
    else:
        form = RecurringPlanForm(initial={})
    return render(request, "core/recurring_form.html", {"form": form, "mode": "create"})


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def recurring_update(request, pk: int):
    company = get_active_company(request)
    plan = get_object_or_404(RecurringPlan, pk=pk, company=company)
    if request.method == "POST":
        form = RecurringPlanForm(request.POST, instance=plan)
        if form.is_valid():
            form.save()
            messages.success(request, "Recurring plan updated.")
            return redirect("core:recurring_list")
    else:
        form = RecurringPlanForm(instance=plan)
    return render(
        request, "core/recurring_form.html", {"form": form, "mode": "edit", "plan": plan}
    )


@login_required
@require_subscription
def recurring_toggle_status(request, pk: int):
    company = get_active_company(request)
    plan = get_object_or_404(RecurringPlan, pk=pk, company=company)
    plan.status = RecurringPlan.PAUSED if plan.status == RecurringPlan.ACTIVE else RecurringPlan.ACTIVE
    plan.save(update_fields=["status"])
    messages.success(
        request, f"Plan {'paused' if plan.status == RecurringPlan.PAUSED else 'activated'}."
    )
    return redirect("core:recurring_list")


@login_required
@require_subscription
def recurring_run_now(request, pk: int):
    company = get_active_company(request)
    plan = get_object_or_404(RecurringPlan, pk=pk, company=company)
    if not plan.is_active():
        messages.error(request, "Plan is not active or has reached its end.")
        return redirect("core:recurring_list")

    inv = generate_invoice_from_plan(plan)
    # auto-email
    if plan.auto_email:
        try:
            email_invoice_default(inv, request_base_url=request.build_absolute_uri("/"))
            inv.status = Invoice.SENT
            inv.save(update_fields=["status"])
        except Exception as e:
            messages.warning(request, f"Invoice created but email failed: {e}")

    # advance schedule
    from .services import advance_plan_after_run

    advance_plan_after_run(plan)

    messages.success(request, f"Generated invoice {inv.number} from plan “{plan.title}”.")
    return redirect("core:invoice_detail", pk=inv.pk)


@login_required
@require_subscription
def recurring_delete(request, pk: int):
    company = get_active_company(request)
    plan = get_object_or_404(RecurringPlan, pk=pk, company=company)
    if request.method == "POST":
        plan.delete()
        messages.success(request, "Recurring plan deleted.")
        return redirect("core:recurring_list")
    return render(request, "core/recurring_confirm_delete.html", {"plan": plan})


# ---------- User Profile ----------

@login_required
def my_profile(request):
    company = get_active_company(request)
    profile = get_user_profile(request.user)
    membership = get_user_membership(request.user, company) if company else None
    companies = get_user_companies(request.user)
    return render(
        request,
        "core/profile.html",
        {
            "profile": profile,
            "company": company,
            "membership": membership,
            "companies": companies,
        },
    )


def _user_supports_name_fields() -> bool:
    U = get_user_model()
    return hasattr(U, "first_name") and hasattr(U, "last_name")


@login_required
def my_profile_edit(request):
    company = get_active_company(request)
    profile = get_user_profile(request.user)
    supports_names = _user_supports_name_fields()

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        # Hide name fields if the User model doesn't have them
        if not supports_names:
            form.fields.pop("first_name", None)
            form.fields.pop("last_name", None)

        if form.is_valid():
            form.save()

            # Persist User fields only if supported by your User model
            if supports_names:
                updates = []
                fn = form.cleaned_data.get("first_name")
                ln = form.cleaned_data.get("last_name")
                if fn is not None:
                    setattr(request.user, "first_name", fn)
                    updates.append("first_name")
                if ln is not None:
                    setattr(request.user, "last_name", ln)
                    updates.append("last_name")
                if updates:
                    request.user.save(update_fields=updates)

            messages.success(request, "Profile updated.")
            return redirect("core:my_profile")
    else:
        initial = {}
        if supports_names:
            initial = {
                "first_name": getattr(request.user, "first_name", "") or "",
                "last_name": getattr(request.user, "last_name", "") or "",
            }
        form = UserProfileForm(instance=profile, initial=initial)
        if not supports_names:
            form.fields.pop("first_name", None)
            form.fields.pop("last_name", None)

    return render(request, "core/profile_form.html", {"form": form, "company": company, "profile": profile})


@login_required
def member_edit(request, member_id: int):
    company = get_active_company(request)
    if not company or not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to edit team members.")
        return redirect("core:team_list")

    m = get_object_or_404(CompanyMember, pk=member_id, company=company)
    if request.method == "POST":
        form = MemberForm(request.POST, instance=m)
        if form.is_valid():
            form.save()
            messages.success(request, "Member updated.")
            return redirect("core:team_list")
    else:
        form = MemberForm(instance=m)

    return render(request, "core/member_form.html", {"form": form, "member": m, "company": company})


# ---------- Search ----------

@login_required
def search(request):
    company = get_active_company(request)
    q = (request.GET.get("q") or "").strip()

    if not q or not company:
        return render(
            request,
            "core/search.html",
            {
                "q": q,
                "has_query": bool(q),
                "clients": [],
                "clients_total": 0,
                "projects": [],
                "projects_total": 0,
                "invoices": [],
                "invoices_total": 0,
                "estimates": [],
                "estimates_total": 0,
                "expenses": [],
                "expenses_total": 0,
                "limit": 5,
            },
        )

    LIMIT = 5
    query = SearchQuery(q, search_type="websearch", config="english")

    # Clients
    c_vec = (
        SearchVector("org", weight="A", config="english")
        + SearchVector("first_name", weight="B", config="english")
        + SearchVector("last_name", weight="B", config="english")
        + SearchVector("email", weight="C", config="english")
    )
    clients_qs = (
        Client.objects.filter(company=company)
        .annotate(
            sv=c_vec,
            rank=SearchRank(c_vec, query),
            sim=Greatest(TrigramSimilarity("org", q), TrigramSimilarity("email", q)),
            score=Coalesce(F("rank"), Value(0.0)) + Coalesce(F("sim"), Value(0.0)),
        )
        .filter(Q(sv=query) | Q(sim__gt=0.25))
        .order_by("-score", "org", "last_name")
    )

    # Projects
    p_vec = SearchVector("name", weight="A", config="english") + SearchVector(
        "number", weight="B", config="english"
    )
    projects_qs = (
        Project.objects.filter(company=company)
        .select_related("client")
        .annotate(
            sv=p_vec,
            rank=SearchRank(p_vec, query),
            sim=Greatest(TrigramSimilarity("name", q), TrigramSimilarity("number", q)),
            score=Coalesce(F("rank"), Value(0.0)) + Coalesce(F("sim"), Value(0.0)),
        )
        .filter(Q(sv=query) | Q(sim__gt=0.25))
        .order_by("-score", "-created_at")
    )

    # Invoices
    i_vec = SearchVector("number", weight="A", config="english")
    invoices_qs = (
        Invoice.objects.filter(company=company)
        .select_related("client", "project")
        .annotate(
            sv=i_vec,
            rank=SearchRank(i_vec, query),
            sim=TrigramSimilarity("number", q),
            score=Coalesce(F("rank"), Value(0.0)) + Coalesce(F("sim"), Value(0.0)),
        )
        .filter(Q(sv=query) | Q(sim__gt=0.3))
        .order_by("-score", "-issue_date", "-id")
    )

    # Estimates
    e_vec = SearchVector("number", weight="A", config="english")
    estimates_qs = (
        Estimate.objects.filter(company=company)
        .select_related("client", "project")
        .annotate(
            sv=e_vec,
            rank=SearchRank(e_vec, query),
            sim=TrigramSimilarity("number", q),
            score=Coalesce(F("rank"), Value(0.0)) + Coalesce(F("sim"), Value(0.0)),
        )
        .filter(Q(sv=query) | Q(sim__gt=0.3))
        .order_by("-score", "-issue_date", "-id")
    )

    # Expenses
    x_vec = (
        SearchVector("description", weight="A", config="english")
        + SearchVector("vendor", weight="B", config="english")
        + SearchVector("category", weight="C", config="english")
    )
    expenses_qs = (
        Expense.objects.filter(company=company)
        .select_related("project")
        .annotate(
            sv=x_vec,
            rank=SearchRank(x_vec, query),
            sim=Greatest(TrigramSimilarity("description", q), TrigramSimilarity("vendor", q)),
            score=Coalesce(F("rank"), Value(0.0)) + Coalesce(F("sim"), Value(0.0)),
        )
        .filter(Q(sv=query) | Q(sim__gt=0.3))
        .order_by("-score", "-date", "-id")
    )

    def _lim(qs):
        return list(qs[:LIMIT])

    context = {
        "q": q,
        "has_query": True,
        "limit": LIMIT,
        "clients": _lim(clients_qs),
        "clients_total": clients_qs.count(),
        "projects": _lim(projects_qs),
        "projects_total": projects_qs.count(),
        "invoices": _lim(invoices_qs),
        "invoices_total": invoices_qs.count(),
        "estimates": _lim(estimates_qs),
        "estimates_total": estimates_qs.count(),
        "expenses": _lim(expenses_qs),
        "expenses_total": expenses_qs.count(),
    }
    return render(request, "core/search.html", context)


# --- Notifications ---

@login_required
def notifications(request):
    company = get_active_company(request)
    qs = Notification.objects.for_company_user(company, request.user).order_by("-created_at")  # type: ignore[attr-defined]
    return render(request, "core/notifications.html", {"items": qs})


@login_required
@require_POST
def notification_read(request, pk: int):
    company = get_active_company(request)
    n = get_object_or_404(Notification, pk=pk, company=company, recipient=request.user)
    n.mark_read()
    return redirect(request.META.get("HTTP_REFERER") or "core:notifications")


@login_required
@require_POST
def notifications_read_all(request):
    company = get_active_company(request)
    mark_all_read(company, request.user)
    return redirect(request.META.get("HTTP_REFERER") or "core:notifications")


@login_required
def notifications_list(request):
    company = get_active_company(request)
    qs = Notification.objects.filter(company=company, recipient=request.user).order_by("-created_at")[:300]
    return render(request, "core/notifications_list.html", {"notifications": qs})


@login_required
@require_http_methods(["POST"])
def notifications_mark_all_read(request):
    company = get_active_company(request)
    Notification.objects.filter(company=company, recipient=request.user, read_at__isnull=True).update(
        read_at=timezone.now()
    )
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("core:notifications")
    return redirect(next_url)


# Legacy convenience: direct send via util (kept for compatibility with any existing links)

@login_required
@require_subscription
def invoice_send_email(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(Invoice.objects.select_related("client"), pk=pk, company=company)

    default_to = (getattr(inv.client, "email", "") or getattr(request.user, "email", "") or "").strip()

    if request.method == "POST":
        to = (request.POST.get("to") or default_to).strip()
        note = (request.POST.get("note") or "").strip()
        if not to:
            messages.error(request, "Recipient email is required.")
        else:
            send_invoice_email(inv, to, note=note, mode="initial")
            try:
                inv.status = Invoice.SENT
                if hasattr(inv, "last_sent_at"):
                    inv.last_sent_at = timezone.now()  # type: ignore[attr-defined]
                inv.save(
                    update_fields=["status"]
                    + (["last_sent_at"] if hasattr(inv, "last_sent_at") else [])
                )
            except Exception:
                pass

            messages.success(request, f"Invoice {inv.number} emailed to {to}.")
            notify_company(
                company,
                request.user,
                f"Invoice {inv.number} emailed to {to}",
                url=reverse("core:invoice_detail", args=[inv.pk]),
                kind=Notification.INVOICE_CREATED,
            )
            return redirect("core:invoice_detail", pk=pk)

    return render(
        request, "core/invoice_send_email.html", {"inv": inv, "default_to": default_to, "mode": "initial"}
    )


@login_required
@require_subscription
def estimate_send_email(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate.objects.select_related("client", "project"), pk=pk, company=company)

    default_to = (getattr(est.client, "email", "") or getattr(request.user, "email", "") or "").strip()

    if request.method == "POST":
        to = (request.POST.get("to") or default_to).strip()
        note = (request.POST.get("note") or "").strip()
        if not to:
            messages.error(request, "Recipient email is required.")
        else:
            send_estimate_email(est, to, note=note, mode="initial")
            try:
                est.status = Estimate.SENT
                est.last_sent_at = timezone.now()
                est.save(update_fields=["status", "last_sent_at"])
            except Exception:
                pass

            messages.success(request, f"Estimate {est.number} emailed to {to}.")
            notify_company(
                company,
                request.user,
                f"Estimate {est.number} emailed to {to}",
                url=reverse("core:estimate_detail", args=[est.pk]),
                kind=Notification.ESTIMATE_CREATED,
            )
            return redirect("core:estimate_detail", pk=pk)

    return render(
        request, "core/estimate_send_email.html", {"est": est, "default_to": default_to, "mode": "initial"}
    )


# ---------- Estimate -> Project ----------

@login_required
@require_subscription
@_require_estimates
def estimate_convert_to_project(request, pk: int):
    company = get_active_company(request)
    est = get_object_or_404(Estimate.objects.select_related("client", "project"), pk=pk, company=company)

    initial_mode = (
        ConvertEstimateToProjectForm.MODE_ATTACH if est.project_id else ConvertEstimateToProjectForm.MODE_NEW  # type: ignore[attr-defined]
    )

    initial = {
        "mode": initial_mode,
        "new_name": (
            est.project.name  # type: ignore[union-attr]
            if est.project_id # type: ignore
            else (est.project.name if getattr(est, "project", None) else f"{est.client or 'Client'} — {est.number}") # type: ignore
        ),
        "new_number": generate_project_number(company), # type: ignore
    }

    form = ConvertEstimateToProjectForm(
        request.POST or None,
        company=company,
        client=getattr(est, "client", None),
        initial=initial,
    )

    if request.method == "POST" and form.is_valid():
        mode = form.cleaned_data["mode"]
        if mode == ConvertEstimateToProjectForm.MODE_ATTACH:
            proj = form.cleaned_data["existing_project"]
            if proj.company_id != company.id: # type: ignore
                messages.error(request, "Project must belong to your company.")
                return redirect("core:estimate_detail", pk=pk)
        else:
            proj = Project.objects.create(
                company=company,
                client=est.client,
                number=form.cleaned_data.get("new_number") or generate_project_number(company), # type: ignore
                name=form.cleaned_data.get("new_name") or f"Project from {est.number}",
                billing_type=form.cleaned_data.get("new_billing_type") or Project.HOURLY,
                estimated_hours=form.cleaned_data.get("new_estimated_hours") or 0,
                budget=form.cleaned_data.get("new_budget") or 0,
                start_date=form.cleaned_data.get("new_start_date"),
                due_date=form.cleaned_data.get("new_due_date"),
            )

        est.project = proj # type: ignore
        if est.status != Estimate.ACCEPTED:
            est.status = Estimate.ACCEPTED
        est.save(update_fields=["project", "status"])

        try:
            notify_company(
                company,
                request.user,
                f"Estimate {est.number} linked to project {proj.number} {proj.name}",
                url=reverse("core:project_detail", args=[proj.pk]),
                kind=Notification.GENERIC,
            )
        except Exception:
            pass

        messages.success(
            request, f"Estimate {est.number} is now linked to project {proj.number} — {proj.name}."
        )
        return redirect("core:project_detail", pk=proj.pk)

    return render(request, "core/estimate_convert_project.html", {"est": est, "form": form})


# ---------- Time → Invoice (wizard) ----------

@login_required
@require_subscription
def project_invoice_time(request, pk: int):
    company = get_active_company(request)
    project = get_object_or_404(Project, pk=pk, company=company)

    start_default, end_default = default_range_last_30()
    default_only_approved = bool(getattr(company, "require_time_approval", False))

    if request.method == "POST":
        form = TimeToInvoiceForm(request.POST)
        if form.is_valid():
            inv = create_invoice_from_time(
                project=project,
                company=company,
                start=form.cleaned_data["start"],
                end=form.cleaned_data["end"],
                group_by=form.cleaned_data["group_by"],
                rounding=form.cleaned_data["rounding"],
                override_rate=form.cleaned_data.get("override_rate"),
                description_prefix=form.cleaned_data.get("description") or "",
                include_expenses=form.cleaned_data.get("include_expenses") or False,
                expense_group_by=form.cleaned_data.get("expense_group_by") or "category",
                expense_markup_override=form.cleaned_data.get("expense_markup_override"),
                expense_label_prefix=form.cleaned_data.get("expense_label_prefix") or "",
                only_approved=form.cleaned_data.get("include_only_approved") or False,
            )
            if not inv.number:
                inv.number = generate_invoice_number(company) # type: ignore
                inv.save(update_fields=["number"])
            messages.success(request, f"Created invoice {inv.number} from unbilled items.")
            return redirect("core:invoice_detail", pk=inv.pk)
    else:
        form = TimeToInvoiceForm(
            initial={
                "start": start_default,
                "end": end_default,
                "include_expenses": True,
                "expense_group_by": "category",
                "include_only_approved": default_only_approved,
            }
        )

    # Preview
    start = form.initial.get("start", start_default)
    end = form.initial.get("end", end_default)
    only_approved = form.initial.get("include_only_approved", default_only_approved)

    time_qs = project.time_entries.filter( # type: ignore
        is_billable=True, invoice__isnull=True, started_at__date__gte=start, started_at__date__lte=end
    )
    if only_approved:
        time_qs = time_qs.filter(approved_at__isnull=False)

    preview_hours = time_qs.aggregate(s=Sum("hours")).get("s") or Decimal("0.00")

    exp_qs = Expense.objects.filter(
        project=project,
        company=company,
        invoice__isnull=True,
        is_billable=True,
        date__gte=start,
        date__lte=end,
    )
    preview_expenses = exp_qs.aggregate(s=Sum("amount")).get("s") or Decimal("0.00")

    return render(
        request,
        "core/project_invoice_time.html",
        {
            "project": project,
            "form": form,
            "preview_hours": preview_hours,
            "preview_expenses": preview_expenses,
            "project_rate": project.hourly_rate,
        },
    )


# ---------- Timesheets & Approvals ----------

@login_required
@require_subscription
def timesheet_week(request):
    company = get_active_company(request)
    today = timezone.now().date()
    default_week = today - timedelta(days=today.weekday())  # Monday
    if request.method == "POST":
        form = TimesheetWeekForm(request.POST, company=company, user=request.user)
        if form.is_valid():
            week = form.cleaned_data["week"]
            project = form.cleaned_data["project"]
            note = form.cleaned_data.get("note") or ""
            mon, sun = week_range(week)
            days = [mon + timedelta(days=i) for i in range(7)]
            values = [
                form.cleaned_data.get("mon"),
                form.cleaned_data.get("tue"),
                form.cleaned_data.get("wed"),
                form.cleaned_data.get("thu"),
                form.cleaned_data.get("fri"),
                form.cleaned_data.get("sat"),
                form.cleaned_data.get("sun"),
            ]

            created, updated = 0, 0
            for d, hours in zip(days, values):
                if hours and hours > 0:
                    te = (
                        TimeEntry.objects.filter(
                            project=project,
                            user=request.user,
                            invoice__isnull=True,
                            started_at__date=d,
                            notes__icontains="(Timesheet)",
                        )
                        .order_by("-id")
                        .first()
                    )
                    if te:
                        te.hours = hours
                        if not te.started_at:
                            te.started_at = combine_midday(d)
                        te.status = TimeEntry.DRAFT
                        te.notes = f"{note} (Timesheet)".strip()
                        te.save(update_fields=["hours", "started_at", "status", "notes"])
                        updated += 1
                    else:
                        TimeEntry.objects.create(
                            project=project,
                            user=request.user,
                            started_at=combine_midday(d),
                            hours=hours,
                            notes=f"{note} (Timesheet)".strip(),
                            is_billable=True,
                            status=TimeEntry.DRAFT,
                        )
                        created += 1
            messages.success(request, f"Timesheet saved. Created {created}, updated {updated}.")
            return redirect("core:timesheet_week")
    else:
        form = TimesheetWeekForm(company=company, user=request.user, initial={"week": default_week})

    mon, sun = week_range(form.initial.get("week") or default_week)
    entries = (
        TimeEntry.objects.filter(
            project__company=company,
            user=request.user,
            started_at__date__gte=mon,
            started_at__date__lte=sun,
        )
        .select_related("project")
        .order_by("project__name", "started_at")
    )
    return render(
        request, "core/timesheet_week.html", {"form": form, "entries": entries, "week_start": mon, "week_end": sun}
    )


@require_POST
@login_required
@require_subscription
def timesheet_submit_week(request):
    company = get_active_company(request)
    form = TimesheetSubmitForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid week.")
        return redirect("core:timesheet_week")

    week = form.cleaned_data["week"]
    mon, sun = week_range(week)
    qs = TimeEntry.objects.filter(
        project__company=company,
        user=request.user,
        invoice__isnull=True,
        started_at__date__gte=mon,
        started_at__date__lte=sun,
        status__in=[TimeEntry.DRAFT, TimeEntry.REJECTED],
    )
    now = timezone.now()
    updated = qs.update(status=TimeEntry.SUBMITTED, submitted_at=now)
    messages.success(request, f"Submitted {updated} entries for approval ({mon}–{sun}).")
    return redirect("core:timesheet_week")


@login_required
@require_subscription
def approvals_list(request):
    company = get_active_company(request)
    if not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to approve time.")
        return redirect("dashboard:home")

    pending = (
        TimeEntry.objects.filter(project__company=company, status=TimeEntry.SUBMITTED)
        .select_related("user", "project")
        .order_by("user__email", "started_at")
    )

    # Build groups: {(user_id, week_monday): {...}}
    groups = {}
    for t in pending:
        wk, _ = week_range(t.started_at.date())
        key = (t.user_id, wk) # type: ignore
        groups.setdefault(key, {"user": t.user, "week": wk, "entries": []})
        groups[key]["entries"].append(t)

    return render(request, "core/approvals_list.html", {"groups": groups})


@require_POST
@login_required
@require_subscription
def approvals_decide(request):
    company = get_active_company(request)
    if not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to approve time.")
        return redirect("core:approvals_list")

    action = request.POST.get("action")
    user_id = request.POST.get("user_id")
    week_str = request.POST.get("week")  # YYYY-MM-DD (monday)
    reason = (request.POST.get("reason") or "").strip()

    try:
        wk = date.fromisoformat(week_str)
    except Exception:
        messages.error(request, "Invalid week date.")
        return redirect("core:approvals_list")

    mon, sun = week_range(wk)
    qs = TimeEntry.objects.filter(
        project__company=company,
        user_id=user_id,
        status=TimeEntry.SUBMITTED,
        started_at__date__gte=mon,
        started_at__date__lte=sun,
    )

    now = timezone.now()
    if action == "approve":
        updated = qs.update(status=TimeEntry.APPROVED, approved_at=now, approved_by_id=request.user.id)
        messages.success(request, f"Approved {updated} entries for week starting {wk}.")
    elif action == "reject":
        updated = qs.update(status=TimeEntry.REJECTED, reject_reason=reason)
        messages.success(request, f"Rejected {updated} entries for week starting {wk}.")
    else:
        messages.error(request, "Unknown action.")
    return redirect("core:approvals_list")


@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def invoice_refund(request, pk: int):
    company = get_active_company(request)
    inv = get_object_or_404(
        Invoice.objects.select_related("client", "project"),
        pk=pk, company=company
    )
    recalc_invoice(inv)

    # Max refundable = net amount paid (can be reduced by prior refunds)
    refundable = (inv.amount_paid or Decimal("0.00"))

    if refundable <= 0:
        messages.info(request, "There are no funds to refund on this invoice.")
        return redirect("core:invoice_detail", pk=pk)

    form = RefundForm(request.POST or None, invoice=inv)

    if request.method == "POST" and form.is_valid():
        amt: Decimal = form.cleaned_data["amount"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if amt > refundable:
            messages.error(request, f"Amount exceeds refundable balance (${refundable}).")
            return render(request, "core/invoice_refund_form.html", {"form": form, "inv": inv, "refundable": refundable})

        # Stripe path if available/selected
        did_stripe = False
        pi_id = None
        refund_ext_id = ""
        try:
            use_stripe = form.cleaned_data.get("use_stripe", False)
        except Exception:
            use_stripe = False

        if use_stripe:
            pi_id = form.cleaned_data.get("payment_intent")
            if not pi_id:
                messages.error(request, "Select a Stripe payment to refund.")
                return render(request, "core/invoice_refund_form.html", {"form": form, "inv": inv, "refundable": refundable})

            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY
                re_ = stripe.Refund.create(payment_intent=pi_id, amount=int(amt * 100))
                refund_ext_id = f"{pi_id}:refund:{re_['id']}"
                did_stripe = True
            except Exception as e:
                messages.error(request, f"Stripe refund failed: {e}")
                return render(request, "core/invoice_refund_form.html", {"form": form, "inv": inv, "refundable": refundable})

        # Record negative Payment (idempotent for Stripe, unique token for manual)
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
                company, request.user,
                f"Refund recorded for invoice {inv.number} (${amt}).",
                url=reverse("core:invoice_detail", args=[inv.pk]),
                kind=Notification.GENERIC
            )
        except Exception:
            pass

        messages.success(
            request,
            f"Refund of ${amt} {'issued via Stripe and ' if did_stripe else ''}recorded."
        )
        return redirect("core:invoice_detail", pk=pk)

    return render(request, "core/invoice_refund_form.html", {
        "form": form, "inv": inv, "refundable": refundable
    })

@login_required
def company_create(request):
    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.save()
            CompanyMember.objects.get_or_create(company=obj, user=request.user, defaults={"role": CompanyMember.OWNER})
            set_active_company(request, obj)
            messages.success(request, "Company created. Welcome!")
            return redirect("core:company_profile")
    else:
        form = CompanyForm()
    return render(request, "core/company_form.html", {"form": form, "mode": "create"})