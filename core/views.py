# core/views.py
from __future__ import annotations

# --- Stdlib ---
from datetime import date, timedelta
from decimal import Decimal
from csv import writer as csv_writer
from io import StringIO

# --- Third-party / Django ---
import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import (
    SearchQuery,
    SearchRank,
    SearchVector,
    TrigramSimilarity,
)
from django.db.models import F, Q, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

# --- Local apps ---
from clients.models import Client
from company.utils import get_active_company, get_user_companies
from estimates.models import Estimate
from expenses.models import Expense
from invoices.models import Invoice
from payments.models import Payment
from projects.models import Project

from core.decorators import require_subscription
from core.models import Notification
from core.services import mark_all_read
from core.utils import default_range_last_30, parse_date

# --- Plan helpers (features & limits) ---
try:
    from billing.utils import require_tier_at_least  # type: ignore
except Exception:
    # No billing app loaded → no-op decorators & helpers
    def require_tier_at_least(slug: str):
        def _deco(fn):
            return fn
        return _deco


# --- Stripe (used elsewhere in core; keep key set here for convenience) ---
User = get_user_model()
stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")


# =============================================================================
# Helpers
# =============================================================================

def _csv_response(name_parts: list[str], content: str) -> HttpResponse:
    """
    Build a CSV HttpResponse with a safe filename like name_parts joined by '_'.
    """
    safe = "_".join(p.replace(" ", "-") for p in name_parts if p)
    res = HttpResponse(content, content_type="text/csv")
    res["Content-Disposition"] = f'attachment; filename="{safe}.csv"'
    return res


def _limit(qs, n: int):
    """Return list(qs[:n]) — tiny helper to slice & realize limited results."""
    return list(qs[:n])


# =============================================================================
# Reports
# =============================================================================

def reports(request):
    """
    Simple totals for income, expenses, and profit within a date range.
    """
    company = get_active_company(request)
    try:
        start = date.fromisoformat(request.GET.get("start") or "")
    except Exception:
        start = timezone.localdate() - timedelta(days=29)
    try:
        end = date.fromisoformat(request.GET.get("end") or "")
    except Exception:
        end = timezone.localdate()

    income = (
        Payment.objects.filter(company=company, received_at__date__range=(start, end))
        .aggregate(s=Sum("amount"))["s"]
        or Decimal("0.00")
    )
    expenses = (
        Expense.objects.filter(company=company, date__range=(start, end))
        .aggregate(s=Sum("amount"))["s"]
        or Decimal("0.00")
    )
    profit = income - expenses

    return render(
        request,
        "core/reports.html",
        {"start": start, "end": end, "income": income, "expenses": expenses, "profit": profit},
    )


@login_required
@require_subscription
@require_tier_at_least("pro")
def report_pnl(request):
    """
    Profit & Loss (cash or accrual) with category breakdown.
    """
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
    by_cat = exp_qs.values("category").annotate(total=Sum("amount")).order_by("category")

    return render(
        request,
        "core/report_pnl.html",
        {
            "basis": basis,
            "start": start,
            "end": end,
            "income_total": income_total,
            "expenses_total": expenses_total,
            "profit": profit,
            "by_cat": by_cat,
        },
    )


@login_required
@require_subscription
@require_tier_at_least("pro")
def report_pnl_csv(request):
    """
    CSV download for Profit & Loss (cash or accrual).
    """
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
    for row in exp_qs.values_list("category").annotate(total=Sum("amount")).order_by("category"):
        w.writerow([row[0] or "(Uncategorized)", f"{row[1]}"])

    return _csv_response(
        ["pnl", start.isoformat(), end.isoformat(), basis],
        buf.getvalue(),
    )


# =============================================================================
# PDF helpers
# =============================================================================

def _render_pdf_from_html(html: str, base_url: str) -> bytes:
    """
    Render a PDF from HTML using WeasyPrint.
    Windows requires GTK/Pango runtime; otherwise raise a helpful error.
    """
    try:
        from weasyprint import HTML  # lazy import
    except Exception as e:
        raise RuntimeError(
            "WeasyPrint isn’t available. Install the GTK/Pango runtime on Windows "
            "or configure an alternate PDF engine."
        ) from e

    return HTML(string=html, base_url=base_url).write_pdf()  # type: ignore


# =============================================================================
# Search
# =============================================================================

@login_required
def search(request):
    """
    Global search across Clients, Projects, Invoices, Estimates, and Expenses.
    Uses Postgres full-text (SearchVector/Rank) and pg_trgm similarity (TrigramSimilarity).
    """
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

    # Clients (scoped to active company)
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

    context = {
        "q": q,
        "has_query": True,
        "limit": LIMIT,
        "clients": _limit(clients_qs, LIMIT),
        "clients_total": clients_qs.count(),
        "projects": _limit(projects_qs, LIMIT),
        "projects_total": projects_qs.count(),
        "invoices": _limit(invoices_qs, LIMIT),
        "invoices_total": invoices_qs.count(),
        "estimates": _limit(estimates_qs, LIMIT),
        "estimates_total": estimates_qs.count(),
        "expenses": _limit(expenses_qs, LIMIT),
        "expenses_total": expenses_qs.count(),
    }
    return render(request, "core/search.html", context)


# =============================================================================
# Notifications
# =============================================================================

@login_required
def notifications(request):
    company = get_active_company(request)
    qs = Notification.objects.for_company_user(  # type: ignore[attr-defined]
        company, request.user
    ).order_by("-created_at")
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
    if not company:
        return render(request, "core/notifications_list.html", {"notifications": []})
    qs = (
        Notification.objects.filter(company=company, recipient=request.user)
        .order_by("-created_at")[:300]
    )
    return render(request, "core/notifications_list.html", {"notifications": qs})


@login_required
@require_http_methods(["POST"])
def notifications_mark_all_read(request):
    company = get_active_company(request)
    Notification.objects.filter(
        company=company,
        recipient=request.user,
        read_at__isnull=True,
    ).update(read_at=timezone.now())
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or reverse("core:notifications")
    return redirect(next_url)

