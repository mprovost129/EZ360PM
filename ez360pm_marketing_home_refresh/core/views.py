from __future__ import annotations

import datetime

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.db.models.functions import TruncMonth
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

    # Display helpers
    user_display_name = (
        (getattr(user, "get_full_name", lambda: "")() or "").strip() or getattr(user, "username", "") or getattr(user, "email", "")
    )
    user_role_label = str(employee_role).replace("_", " ").title() if employee_role else "Staff"

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

    recent_invoices = (
        Document.objects.filter(company=company, doc_type=DocumentType.INVOICE)
        .select_related("client")
        .order_by("-updated_at", "-created_at")[:8]
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

    # Quick Notes (right rail)
    try:
        from notes.forms import UserNoteForm

        quick_note_form = UserNoteForm()
    except Exception:
        quick_note_form = None

    ctx = {
        "company": company,
        "user": user,
        "user_display_name": user_display_name,
        "user_role_label": user_role_label,
        "subscription": subscription,
        "dashboard_layout": dashboard_layout,
        "onboarding_steps": onboarding_steps,
        "onboarding_progress": onboarding_progress_data,
        "quick_note_form": quick_note_form,
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
        "recent_invoices": recent_invoices,
        "recent_open_projects": recent_open_projects,
        "recent_expenses": recent_expenses,
    }

    return render(request, "core/app_dashboard.html", ctx)


@login_required
def dashboard_revenue_trend_api(request: HttpRequest) -> JsonResponse:
    """Return a 6-month revenue time series (cash-in) for the active company."""

    if not ensure_active_company_for_user(request):
        return JsonResponse({"labels": [], "series": []})

    company = get_active_company(request)
    if not company:
        return JsonResponse({"labels": [], "series": []})

    today = timezone.localdate()

    # Build the 6 months window (including current month).
    months: list[tuple[int, int]] = []
    y, m = today.year, today.month
    for i in range(5, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        months.append((yy, mm))

    start_date = datetime.date(months[0][0], months[0][1], 1)
    if months[-1][1] == 12:
        next_month = datetime.date(months[-1][0] + 1, 1, 1)
    else:
        next_month = datetime.date(months[-1][0], months[-1][1] + 1, 1)
    end_date = next_month - datetime.timedelta(days=1)

    start_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
    end_dt = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))

    rows = (
        Payment.objects.filter(
            company=company,
            status=PaymentStatus.SUCCEEDED,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        )
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("amount_cents"))
        .order_by("month")
    )

    by_month: dict[tuple[int, int], int] = {}
    for r in rows:
        dt = r.get("month")
        if not dt:
            continue
        by_month[(dt.year, dt.month)] = int(r.get("total") or 0)

    labels: list[str] = []
    series: list[int] = []
    for yy, mm in months:
        labels.append(datetime.date(yy, mm, 1).strftime("%b %Y"))
        series.append(by_month.get((yy, mm), 0))

    return JsonResponse({"labels": labels, "series": series})


@login_required
def dashboard_ar_aging_api(request: HttpRequest) -> JsonResponse:
    """Return A/R aging buckets for open invoices (balance due)."""

    if not ensure_active_company_for_user(request):
        return JsonResponse({"labels": [], "series": []})

    company = get_active_company(request)
    if not company:
        return JsonResponse({"labels": [], "series": []})

    today = timezone.localdate()

    invoices = Document.objects.filter(
        company=company,
        doc_type=DocumentType.INVOICE,
        status__in=[DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID],
        balance_due_cents__gt=0,
    ).only("due_date", "created_at", "balance_due_cents")

    buckets = {
        "Current": 0,
        "1–30": 0,
        "31–60": 0,
        "61–90": 0,
        "90+": 0,
    }

    for inv in invoices:
        ref_date = inv.due_date or timezone.localdate(inv.created_at)
        age_days = (today - ref_date).days
        amt = int(inv.balance_due_cents or 0)

        if age_days <= 0:
            buckets["Current"] += amt
        elif age_days <= 30:
            buckets["1–30"] += amt
        elif age_days <= 60:
            buckets["31–60"] += amt
        elif age_days <= 90:
            buckets["61–90"] += amt
        else:
            buckets["90+"] += amt

    labels = list(buckets.keys())
    series = [buckets[k] for k in labels]
    return JsonResponse({"labels": labels, "series": series})


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

    # ------------------------------------------------------------------
    # Forced layout removals
    #
    # These widgets were migrated out of the dashboard rail and into
    # other surfaces (sidebar/header/billing). We remove them even if
    # an older saved layout still includes them.
    # ------------------------------------------------------------------
    forced_remove: set[str] = {
        "outstanding_invoices",
        "active_company",
        "your_role",
        "subscription",
    }

    # Sanitize: remove unknown/disallowed; keep order.
    left = [k for k in layout.get("left", []) if k in allowed and k not in forced_remove]
    right = [k for k in layout.get("right", []) if k in allowed and k not in forced_remove]

    # Ensure quick notes is above getting started (when onboarding is incomplete).
    if "quick_notes" in right and "getting_started" in right:
        base = [k for k in right if k not in {"quick_notes", "getting_started"}]
        pair = ["quick_notes", "getting_started"]
        if "quick_actions" in base:
            i = base.index("quick_actions") + 1
            right = base[:i] + pair + base[i:]
        else:
            right = pair + base

    used = set(left + right)
    # Add missing allowed widgets into their default columns.
    for k in [x for x in widgets.keys() if x in allowed and x not in used and x not in forced_remove]:
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


@login_required
def global_search(request: HttpRequest):
    """Global search across the active company.

    This is intentionally lightweight (v1): it provides a single place to search and jump
    to the right record, without overbuilding a full-text system.
    """
    if not ensure_active_company_for_user(request):
        return redirect("companies:switch")

    company = get_active_company(request)
    q = (request.GET.get("q") or "").strip()
    if not q:
        return redirect("core:app_dashboard")

    # Helpers
    def _safe(filter_fn, default):
        try:
            return filter_fn()
        except Exception:
            return default

    # Clients
    clients = _safe(
        lambda: list(
            __import__("crm.models", fromlist=["Client"]).Client.objects.filter(company=company).filter(
                # name/email/phone-ish fields
                # (phone stored in related model; keep it simple for now)
                # fall back to name/email
                name__icontains=q
            ).order_by("name")[:10]
        ),
        [],
    )
    if not clients:
        clients = _safe(
            lambda: list(
                __import__("crm.models", fromlist=["Client"]).Client.objects.filter(company=company).filter(
                    email__icontains=q
                ).order_by("name")[:10]
            ),
            [],
        )

    # Projects
    projects = _safe(
        lambda: list(
            Project.objects.filter(company=company).filter(
                # project_number often used by contractors
                # name/title varies; Project has name in this codebase
                name__icontains=q
            ).order_by("-updated_at")[:10]
        ),
        [],
    )
    if not projects:
        projects = _safe(
            lambda: list(
                Project.objects.filter(company=company).filter(project_number__icontains=q).order_by("-updated_at")[:10]
            ),
            [],
        )

    # Documents (Invoices/Estimates/Proposals)
    documents = _safe(
        lambda: list(
            Document.objects.filter(company=company).filter(
                number__icontains=q
            ).select_related("client").order_by("-updated_at")[:10]
        ),
        [],
    )
    if not documents:
        documents = _safe(
            lambda: list(
                Document.objects.filter(company=company).filter(title__icontains=q).select_related("client").order_by("-updated_at")[:10]
            ),
            [],
        )

    # Expenses
    expenses = _safe(
        lambda: list(
            Expense.objects.filter(company=company).select_related("vendor").filter(
                description__icontains=q
            ).order_by("-date", "-created_at")[:10]
        ),
        [],
    )

    # Payments
    payments = _safe(
        lambda: list(
            Payment.objects.filter(company=company).select_related("client").filter(
                notes__icontains=q
            ).order_by("-created_at")[:10]
        ),
        [],
    )

    ctx = {
        "company": company,
        "q": q,
        "clients": clients,
        "projects": projects,
        "documents": documents,
        "expenses": expenses,
        "payments": payments,
    }
    return render(request, "core/search_results.html", ctx)
