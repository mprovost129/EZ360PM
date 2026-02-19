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

from billing.models import PlanCode
from billing.services import build_subscription_summary, plan_meets
from integrations.models import DropboxConnection

from companies.permissions import has_min_role
from core.dashboard_registry import default_dashboard_layout, get_dashboard_widgets
from core.forms.dashboard import DashboardLayoutForm
from core.models import DashboardLayout
from billing.decorators import tier_required
from companies.decorators import require_min_role
from companies.models import EmployeeRole


def home(request: HttpRequest):
    """Logged-out marketing page (root path)."""
    if request.user.is_authenticated:
        return redirect("core:app_dashboard")
    return render(request, "core/home.html")




@login_required
def app_dashboard(request: HttpRequest):
    # Ensure an active company is selected (auto-select if possible).
    if not ensure_active_company_for_user(request):
        return redirect("companies:switch")

    company = get_active_company(request)
    user = request.user

    subscription = build_subscription_summary(company)
    plan_key = subscription.plan

    active_employee = getattr(request, "active_employee", None)
    employee_role = getattr(active_employee, "role", "staff")

    # ------------------------------------------------------------------
    # Dashboard period filter (Revenue/Expenses KPIs)
    # ------------------------------------------------------------------
    # Values: month | last30 | last90 | ytd
    today = timezone.localdate()
    range_key = (request.GET.get("range") or "month").strip().lower()
    if range_key not in {"month", "last30", "last90", "ytd"}:
        range_key = "month"

    if range_key == "month":
        start_date = today.replace(day=1)
        if start_date.month == 12:
            next_month = start_date.replace(year=start_date.year + 1, month=1, day=1)
        else:
            next_month = start_date.replace(month=start_date.month + 1, day=1)
        end_date = next_month - datetime.timedelta(days=1)
        kpi_period_label = start_date.strftime("%b %Y")
    elif range_key == "last30":
        start_date = today - datetime.timedelta(days=29)
        end_date = today
        kpi_period_label = "Last 30 days"
    elif range_key == "last90":
        start_date = today - datetime.timedelta(days=89)
        end_date = today
        kpi_period_label = "Last 90 days"
    else:  # ytd
        start_date = today.replace(month=1, day=1)
        end_date = today
        kpi_period_label = "Year to date"

    start_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
    end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))

    # ------------------------------------------------------------------
    # KPIs + lists
    # ------------------------------------------------------------------
    from payments.models import Payment
    from expenses.models import Expense
    from timetracking.models import TimeEntry
    from documents.models import Document
    from projects.models import Project

    revenue_cents = (
        Payment.objects.filter(
            company=company,
            status=PaymentStatus.SUCCEEDED,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ).aggregate(total=Sum("amount_cents"))["total"]
        or 0
    )

    expenses_cents = (
        Expense.objects.filter(
            company=company,
            date__gte=start_date,
            date__lte=end_date,
        ).aggregate(total=Sum("amount_cents"))["total"]
        or 0
    )

    ar_cents = (
        Document.objects.filter(
            company=company,
            doc_type=DocumentType.INVOICE,
            status__in=[DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID],
        ).aggregate(total=Sum("balance_due_cents"))["total"]
        or 0
    )

    unbilled_minutes = (
        TimeEntry.objects.filter(
            company=company,
            billable=True,
            billed_document__isnull=True,
            status__in=[TimeStatus.APPROVED, TimeStatus.SUBMITTED],
        ).aggregate(total=Sum("duration_minutes"))["total"]
        or 0
    )
    unbilled_hours = float(unbilled_minutes) / 60.0

    # Outstanding invoices: earliest due first. Include undated at bottom.
    outstanding_base = (
        Document.objects.filter(
            company=company,
            doc_type=DocumentType.INVOICE,
            status__in=[DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID],
        )
        .select_related("client")
        .order_by("due_date", "created_at")
    )
    outstanding_invoices = list(outstanding_base.filter(due_date__isnull=False)[:8])
    if len(outstanding_invoices) < 8:
        outstanding_invoices += list(outstanding_base.filter(due_date__isnull=True)[: (8 - len(outstanding_invoices))])

    recent_open_projects = (
        Project.objects.filter(company=company, is_active=True)
        .select_related("client")
        .order_by("-updated_at")[:8]
    )

    recent_expenses = (
        Expense.objects.filter(company=company)
        .select_related("vendor")
        .order_by("-date", "-created_at")[:8]
    )

    # Onboarding / getting started (right sidebar widget)
    onboarding_steps = build_onboarding_checklist(company)
    onboarding_progress_data = onboarding_progress(onboarding_steps)

    dashboard_layout = _build_dashboard_layout_json(
        company=company,
        plan=plan_key,
        employee_role=employee_role,
    )

    ctx = {
        "company": company,
        "user": user,
        "subscription": subscription,
        "dashboard_layout": dashboard_layout,
        "onboarding_steps": onboarding_steps,
        "onboarding_progress": onboarding_progress_data,
        "kpi_period_key": range_key,
        "kpi_period_label": kpi_period_label,
        "kpis": {
            "revenue_cents": revenue_cents,
            "expenses_cents": expenses_cents,
            "ar_cents": ar_cents,
            "unbilled_hours": unbilled_hours,
            "ar_as_of": today,
            "unbilled_as_of": today,
        },
        # widget datasets
        "outstanding_invoices": outstanding_invoices,
        "recent_open_projects": recent_open_projects,
        "recent_expenses": recent_expenses,
    }

    return render(request, "core/app_dashboard.html", ctx)


def _build_dashboard_layout_json(*, company, plan: str, employee_role: str) -> dict[str, list[str]]:
    """Return a sanitized layout for the current user."""

    widgets = get_dashboard_widgets()

    # Allowed widgets for this user
    allowed: set[str] = set()
    for key, w in widgets.items():
        if not plan_meets(plan, min_plan=w.min_plan):
            continue
        # has_min_role expects an employee-like object with .role
        if not has_min_role(type("E", (), {"role": employee_role})(), w.min_role):
            continue
        allowed.add(key)

    layout = default_dashboard_layout()

    if plan_meets(plan, min_plan=PlanCode.PREMIUM):
        try:
            obj = DashboardLayout.objects.filter(company=company, role=employee_role).first()
            if obj and isinstance(obj.layout_json, dict):
                layout = {
                    "left": list(obj.layout_json.get("left", []) or []),
                    "right": list(obj.layout_json.get("right", []) or []),
                }
        except Exception:
            # Never break dashboard due to layout issues.
            layout = default_dashboard_layout()

    # Sanitize: remove unknown/disallowed; keep order.
    left = [k for k in layout.get("left", []) if k in allowed]
    right = [k for k in layout.get("right", []) if k in allowed]

    used = set(left + right)
    # Add missing allowed widgets into their default columns.
    for k in [x for x in widgets.keys() if x in allowed and x not in used]:
        if widgets[k].default_column == "left":
            left.append(k)
        else:
            right.append(k)

    # Ensure basics are always present.
    for required in ["kpis", "quick_actions"]:
        if required in allowed and required not in left and required not in right:
            if widgets.get(required) and widgets[required].default_column == "right":
                right.insert(0, required)
            else:
                left.insert(0, required)

    return {"left": left, "right": right}


@tier_required(PlanCode.PREMIUM)
@require_min_role(EmployeeRole.MANAGER)
def dashboard_customize(request: HttpRequest):
    """Premium-only dashboard customization (per-company, per-role)."""

    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    sub = build_subscription_summary(company)
    plan = sub.plan

    active_employee = getattr(request, "active_employee", None)
    employee_role = getattr(active_employee, "role", EmployeeRole.MANAGER)

    existing = DashboardLayout.objects.filter(company=company, role=employee_role).first()
    initial_layout = None
    if existing and isinstance(existing.layout_json, dict):
        initial_layout = {
            "left": list(existing.layout_json.get("left", []) or []),
            "right": list(existing.layout_json.get("right", []) or []),
        }

    if request.method == "POST":
        form = DashboardLayoutForm(
            data=request.POST,
            plan=plan,
            employee_role=employee_role,
            initial_layout=initial_layout or default_dashboard_layout(),
        )
        if form.is_valid():
            layout_json = form.build_layout_json()
            if not existing:
                existing = DashboardLayout(company=company, role=employee_role)
            existing.layout_json = layout_json
            existing.updated_at = timezone.now()
            existing.updated_by_user = getattr(request, "user", None)
            existing.save()
            return redirect("core:app_dashboard")
    else:
        form = DashboardLayoutForm(
            plan=plan,
            employee_role=employee_role,
            initial_layout=initial_layout or default_dashboard_layout(),
        )

    widgets = get_dashboard_widgets()
    keys = getattr(form, "allowed_widget_keys", [])
    rows = []
    for key in keys:
        rows.append(
            {
                "key": key,
                "label": widgets[key].label,
                "enabled": form[f"{key}__enabled"],
                "column": form[f"{key}__column"],
                "order": form[f"{key}__order"],
            }
        )

    return render(
        request,
        "core/dashboard_customize.html",
        {
            "form": form,
            "rows": rows,
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
