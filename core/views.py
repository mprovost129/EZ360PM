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
    """Logged-in dashboard. Requires an active company context."""
    if not ensure_active_company_for_user(request):
        return redirect("companies:switch")

    company = get_active_company(request)

    sub = build_subscription_summary(company) if company else None
    plan = sub.plan if sub else PlanCode.STARTER
    is_professional = plan_meets(plan, min_plan=PlanCode.PROFESSIONAL)
    is_premium = plan_meets(plan, min_plan=PlanCode.PREMIUM)

    active_employee = getattr(request, "active_employee", None)
    employee_role = getattr(active_employee, "role", EmployeeRole.STAFF)

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

    # Expenses = approved/reimbursed expenses in current month (Professional+)
    expenses_cents = 0
    if is_professional:
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
    # Payables summary (Professional+)
    # ------------------------------------------------------------------
    outstanding_payables_cents = 0
    payables_due_soon_count = 0
    if is_professional:
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
    # Premium dashboard insights (Premium; role-gated in template)
    # ------------------------------------------------------------------
    premium_insights = None
    if is_premium:
        prev_month_end = month_start
        prev_month_start = (month_start - datetime.timedelta(days=1)).replace(day=1)

        prev_rev_cents = int(
            Payment.objects.filter(
                company=company,
                deleted_at__isnull=True,
                status=PaymentStatus.SUCCEEDED,
                payment_date__gte=prev_month_start,
                payment_date__lt=prev_month_end,
            ).aggregate(s=Sum("amount_cents"))["s"]
            or 0
        )

        prev_refunded_cents = int(
            Payment.objects.filter(
                company=company,
                deleted_at__isnull=True,
                status__in=[PaymentStatus.REFUNDED, PaymentStatus.SUCCEEDED],
                payment_date__gte=prev_month_start,
                payment_date__lt=prev_month_end,
            ).aggregate(s=Sum("refunded_cents"))["s"]
            or 0
        )
        prev_rev_net_cents = max(prev_rev_cents - prev_refunded_cents, 0)

        prev_expenses_cents = 0
        if is_professional:
            prev_expenses_cents = int(
                Expense.objects.filter(
                    company=company,
                    deleted_at__isnull=True,
                    status__in=[ExpenseStatus.APPROVED, ExpenseStatus.REIMBURSED],
                    date__gte=prev_month_start,
                    date__lt=prev_month_end,
                ).aggregate(s=Sum("total_cents"))["s"]
                or 0
            )

        def _pct_change(cur: int, prev: int) -> float | None:
            if prev <= 0:
                return None
            return round(((cur - prev) / float(prev)) * 100.0, 1)

        rev_change_pct = _pct_change(revenue_net_cents, prev_rev_net_cents)
        exp_change_pct = _pct_change(expenses_cents, prev_expenses_cents)

        overdue_qs = Document.objects.filter(
            company=company,
            deleted_at__isnull=True,
            doc_type=DocumentType.INVOICE,
            status__in=[DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID],
            due_date__isnull=False,
            due_date__lt=today,
            balance_due_cents__gt=0,
        )
        overdue_count = int(overdue_qs.count())
        overdue_cents = int(overdue_qs.aggregate(s=Sum("balance_due_cents"))["s"] or 0)

        dropbox = DropboxConnection.objects.filter(company=company).first()
        dropbox_connected = bool(dropbox and dropbox.is_active)

        premium_insights = {
            "rev_last_month_net_cents": prev_rev_net_cents,
            "rev_change_pct": rev_change_pct,
            "expenses_last_month_cents": prev_expenses_cents,
            "expenses_change_pct": exp_change_pct,
            "overdue_count": overdue_count,
            "overdue_cents": overdue_cents,
            "dropbox_connected": dropbox_connected,
        }

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
            "tier_flags": {
                "is_professional": is_professional,
                "is_premium": is_premium,
            },
            "premium_insights": premium_insights,
            "dashboard_layout": _build_dashboard_layout_json(
                company=company,
                plan=plan,
                employee_role=employee_role,
            ),
            "can_customize_dashboard": bool(
                is_premium and has_min_role(active_employee, EmployeeRole.MANAGER)
            ),
        },
    )


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
