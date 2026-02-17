from __future__ import annotations

import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from companies.services import ensure_active_company_for_user, get_active_company
from core.onboarding import build_onboarding_checklist, onboarding_progress
from documents.models import Document, DocumentStatus, DocumentType
from expenses.models import Expense, ExpenseStatus
from payments.models import Payment, PaymentStatus
from payables.models import Bill, BillStatus
from projects.models import Project
from timetracking.models import TimeEntry, TimeStatus


def home(request: HttpRequest):
    """Logged-out marketing page (root path)."""
    if request.user.is_authenticated:
        return redirect("core:app_dashboard")
    return render(request, "core/home.html")


@login_required
def app_dashboard(request: HttpRequest):
    """Logged-in dashboard. Requires an active company context."""
    if not ensure_active_company_for_user(request):
        return redirect("companies:switch")

    company = get_active_company(request)

    # ------------------------------------------------------------------
    # Onboarding
    # ------------------------------------------------------------------
    steps = build_onboarding_checklist(company) if company else []
    progress = onboarding_progress(steps) if company else None

    # ------------------------------------------------------------------
    # KPI window
    # ------------------------------------------------------------------
    today = timezone.localdate()
    month_start = today.replace(day=1)
    month_end = (month_start + datetime.timedelta(days=32)).replace(day=1)

    # Revenue = succeeded payments in current month (net of refunds)
    revenue_cents = int(
        Payment.objects.filter(
            company=company,
            deleted_at__isnull=True,
            status=PaymentStatus.SUCCEEDED,
            payment_date__gte=month_start,
            payment_date__lt=month_end,
        ).aggregate(s=Sum("amount_cents"))["s"]
        or 0
    )

    refunded_cents = int(
        Payment.objects.filter(
            company=company,
            deleted_at__isnull=True,
            status__in=[PaymentStatus.REFUNDED, PaymentStatus.SUCCEEDED],
            payment_date__gte=month_start,
            payment_date__lt=month_end,
        ).aggregate(s=Sum("refunded_cents"))["s"]
        or 0
    )
    revenue_net_cents = max(revenue_cents - refunded_cents, 0)

    # Expenses = approved/reimbursed expenses in current month
    expenses_cents = int(
        Expense.objects.filter(
            company=company,
            deleted_at__isnull=True,
            status__in=[ExpenseStatus.APPROVED, ExpenseStatus.REIMBURSED],
            date__gte=month_start,
            date__lt=month_end,
        ).aggregate(s=Sum("total_cents"))["s"]
        or 0
    )

    # A/R = balance due on sent/partially-paid invoices
    ar_cents = int(
        Document.objects.filter(
            company=company,
            deleted_at__isnull=True,
            doc_type=DocumentType.INVOICE,
            status__in=[DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID],
        ).aggregate(s=Sum("balance_due_cents"))["s"]
        or 0
    )

    # Unbilled (billable, approved) time
    unbilled_minutes = int(
        TimeEntry.objects.filter(
            company=company,
            deleted_at__isnull=True,
            billable=True,
            status=TimeStatus.APPROVED,
            billed_document__isnull=True,
        ).aggregate(s=Sum("duration_minutes"))["s"]
        or 0
    )
    unbilled_hours = round(unbilled_minutes / 60.0, 1)

    # ------------------------------------------------------------------
    # Payables summary
    # ------------------------------------------------------------------
    outstanding_payables_cents = int(
        Bill.objects.filter(
            company=company,
            deleted_at__isnull=True,
            status__in=[BillStatus.POSTED, BillStatus.PARTIALLY_PAID],
        ).aggregate(s=Sum("balance_cents"))["s"]
        or 0
    )

    due_soon_to = today + datetime.timedelta(days=7)
    payables_due_soon_count = int(
        Bill.objects.filter(
            company=company,
            deleted_at__isnull=True,
            status__in=[BillStatus.POSTED, BillStatus.PARTIALLY_PAID],
            due_date__isnull=False,
            due_date__gte=today,
            due_date__lte=due_soon_to,
            balance_cents__gt=0,
        ).count()
    )

    # ------------------------------------------------------------------
    # Recent activity panels
    # ------------------------------------------------------------------
    recent_invoices = (
        Document.objects.filter(
            company=company,
            deleted_at__isnull=True,
            doc_type=DocumentType.INVOICE,
        )
        .select_related("client", "project")
        .order_by("-created_at")[:6]
    )

    recent_payments = (
        Payment.objects.filter(company=company, deleted_at__isnull=True)
        .select_related("client", "invoice")
        .order_by("-created_at")[:6]
    )

    recent_time = (
        TimeEntry.objects.filter(company=company, deleted_at__isnull=True)
        .select_related("project", "client", "employee")
        .order_by("-started_at", "-created_at")[:6]
    )

    due_soon_projects = (
        Project.objects.filter(company=company, deleted_at__isnull=True, due_date__isnull=False)
        .select_related("client")
        .order_by("due_date")[:6]
    )

    return render(
        request,
        "core/app_dashboard.html",
        {
            "onboarding_steps": steps,
            "onboarding_progress": progress,
            "kpi": {
                "revenue_net_cents": revenue_net_cents,
                "expenses_cents": expenses_cents,
                "ar_cents": ar_cents,
                "unbilled_hours": unbilled_hours,
                "month_label": month_start.strftime("%b %Y"),
            },
            "outstanding_payables_cents": outstanding_payables_cents,
            "payables_due_soon_count": payables_due_soon_count,
            "recent_invoices": recent_invoices,
            "recent_payments": recent_payments,
            "recent_time": recent_time,
            "due_soon_projects": due_soon_projects,
        },
    )


@login_required
def getting_started(request: HttpRequest):
    """A guided onboarding checklist page."""

    if not ensure_active_company_for_user(request):
        return redirect("companies:switch")

    company = get_active_company(request)
    steps = build_onboarding_checklist(company) if company else []
    progress = onboarding_progress(steps) if company else None

    return render(
        request,
        "core/getting_started.html",
        {
            "onboarding_steps": steps,
            "onboarding_progress": progress,
        },
    )


def health(request: HttpRequest) -> JsonResponse:
    """Legacy health endpoint. Prefer /healthz for DB-verified checks."""
    from core.middleware import health_payload

    return JsonResponse(health_payload(), status=200)
