# dashboard/views.py
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import json
from typing import Dict, List, Tuple

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage, mail_admins
from django.db.models import F, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from clients.models import Client
from company.utils import get_active_company, get_onboarding_status
from core.forms import SuggestionForm
from core.models import Notification, Suggestion
from core.utils import default_range_last_30, parse_date
from expenses.models import Expense
from invoices.models import Invoice
from payments.models import Payment
from projects.models import Project
from timetracking.models import TimeEntry
from .utils import get_cookie_consent, set_consent_cookie

# Optional import; fall back gracefully if the helper isn't present.
try:
    from core.utils import user_has_active_subscription  # type: ignore
except Exception:  # pragma: no cover
    def user_has_active_subscription(company) -> bool:  # type: ignore
        return False


# ---- Constants ----
APP_NAME = getattr(settings, "APP_NAME", "EZ360PM")
COOKIE_NAME = getattr(settings, "COOKIE_CONSENT_NAME", "cookie_consent")
COOKIE_MAX_AGE = int(getattr(settings, "COOKIE_CONSENT_MAX_AGE", 31536000))  # 1 year


# ---- Public/Home ----
def home(request: HttpRequest) -> HttpResponse:
    """
    Public landing when logged out; full dashboard when logged in.
    Unsubscribed users still see the dashboard; subscription-gated actions
    elsewhere should enforce checks.
    """
    if not request.user.is_authenticated:
        return render(request, "dashboard/public_home.html", {"APP_NAME": APP_NAME})

    company = get_active_company(request)
    subscribed = user_has_active_subscription(company) if company else False
    today = timezone.localdate()

    # --- Last 30 days window
    start_30, end_30 = default_range_last_30()

    # Income (cash-basis) last 30
    income_30 = (
        Payment.objects.filter(company=company, received_at__date__range=(start_30, end_30))
        .aggregate(s=Sum("amount"))
        .get("s") or Decimal("0")
    )

    # Expenses last 30
    expenses_30 = (
        Expense.objects.filter(company=company, date__range=(start_30, end_30))
        .aggregate(s=Sum("amount"))
        .get("s") or Decimal("0")
    )
    profit_30 = Decimal(income_30) - Decimal(expenses_30)

    # --- Invoices & balances (exclude void)
    inv_qs = Invoice.objects.filter(company=company).exclude(status=Invoice.VOID)

    # NOTE: If you need to *force* recompute totals (e.g., after rate changes),
    # do it outside the request path (signal/management command), or gate it:
    # if settings.DEBUG:
    #     from invoices.services import recalc_invoice
    #     for inv in inv_qs.only("id", "total", "amount_paid", "status"):
    #         recalc_invoice(inv)

    # Outstanding = SUM( COALESCE(total,0) - COALESCE(amount_paid,0) ) where still > 0
    # We compute the sum of positive balances directly in SQL for speed.
    balances = (
        inv_qs.annotate(
            bal=Coalesce(F("total"), Value(Decimal("0"))) - Coalesce(F("amount_paid"), Value(Decimal("0")))
        )
        .filter(bal__gt=0)
        .aggregate(s=Sum("bal"))
        .get("s") or Decimal("0")
    )
    outstanding_total = Decimal(balances)

    # Overdue list (top 10)
    overdue: List[Tuple[Invoice, Decimal]] = []
    overdue_qs = (
        inv_qs.exclude(due_date__isnull=True)
        .filter(due_date__lt=today)
        .select_related("client")
        .annotate(
            bal=Coalesce(F("total"), Value(Decimal("0"))) - Coalesce(F("amount_paid"), Value(Decimal("0")))
        )
        .filter(bal__gt=0)
        .order_by("due_date")[:10]
    )
    for inv in overdue_qs:
        overdue.append((inv, inv.bal))  # type: ignore[attr-defined]

    # --- This week time (Mon–Sun)
    now = timezone.localtime()
    start_week = now.date() - timedelta(days=now.weekday())
    end_week = start_week + timedelta(days=6)

    hours_week_val = (
        TimeEntry.objects.filter(
            project__company=company, start_time__date__range=(start_week, end_week)
        )
        .aggregate(s=Sum("hours"))
        .get("s")
    )
    # Ensure Decimal for template consistency
    hours_week: Decimal = Decimal(str(hours_week_val or "0"))

    active_timers = TimeEntry.objects.filter(
        project__company=company, end_time__isnull=True
    ).count()

    # --- Activity & quick lists
    recent_notes = (
        Notification.objects.filter(company=company, recipient=request.user)
        .order_by("-created_at")[:10]
    )
    recent_projects = (
        Project.objects.filter(company=company)
        .select_related("client")
        .order_by("-created_at")[:5]
    )
    # Sum of payments per client; Coalesce to keep ordering stable when nulls
    top_clients = (
        Client.objects.filter(company=company)
        .annotate(total_paid=Coalesce(Sum("invoices__payments__amount"), Value(Decimal("0"))))
        .order_by("-total_paid", "org", "last_name")[:5]
    )

    context: Dict = {
        "income_30": income_30,
        "expenses_30": expenses_30,
        "profit_30": profit_30,
        "outstanding_total": outstanding_total,
        "overdue": overdue,
        "hours_week": hours_week,
        "active_timers": active_timers,
        "recent_notes": recent_notes,
        "recent_projects": recent_projects,
        "top_clients": top_clients,
        "start_30": start_30,
        "end_30": end_30,
        "start_week": start_week,
        "end_week": end_week,
        "subscribed": subscribed,
    }
    return render(request, "dashboard/home.html", context)


# ---- Contact / Suggestions ----
def contact_submit(request: HttpRequest) -> HttpResponse:
    """
    Simple contact endpoint for the public page.
    Open to logged-out users so the public landing can submit.
    """
    if request.method != "POST":
        return redirect("dashboard:home")

    name = (request.POST.get("name") or "").strip()
    email = (request.POST.get("email") or "").strip()
    message = (request.POST.get("message") or "").strip()

    if not message or not email:
        messages.error(request, "Please include your email and a short message.")
        return redirect("dashboard:home")

    subject = f"[{APP_NAME}] Contact — {name or 'Visitor'}"
    body = f"From: {name or 'Visitor'} <{email}>\n\n{message}"

    support_email = getattr(settings, "SUPPORT_EMAIL", "")
    if support_email:
        EmailMessage(
            subject=subject,
            body=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            to=[support_email],
            reply_to=[email],
        ).send(fail_silently=True)
    else:
        # Fallback to ADMINS if SUPPORT_EMAIL isn't configured
        mail_admins(subject=subject, message=body, fail_silently=True)

    messages.success(request, "Thanks! We’ve received your message.")
    return redirect("dashboard:home")


def contact(request: HttpRequest) -> HttpResponse:
    """
    “Suggest an improvement” / contact form.
    Saves Suggestion and emails admins; open to public but pre-fills for logged-in.
    """
    initial: Dict[str, str] = {}
    if request.user.is_authenticated:
        initial["name"] = getattr(request.user, "name", "") or ""
        initial["email"] = getattr(request.user, "email", "") or ""

    # Capture the page they came from
    ref = request.META.get("HTTP_REFERER", "")
    if ref and "page_url" not in request.POST:
        initial["page_url"] = ref

    form = SuggestionForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        s: Suggestion = form.save(commit=False)
        if request.user.is_authenticated:
            s.user = request.user  # type: ignore[attr-defined]
            s.company = get_active_company(request)  # type: ignore
        s.save()

        # Lightweight email to site admins (configure ADMINS in settings for delivery)
        try:
            body = render_to_string("dashboard/email/suggestion.txt", {"s": s})
            mail_admins(
                subject=f"[{APP_NAME}] New suggestion — {s.subject}",
                message=body,
                fail_silently=True,
            )
        except Exception:
            # Intentionally swallow to avoid UX regression if email is misconfigured
            pass

        messages.success(request, "Thanks! Your suggestion has been sent.")
        return redirect("dashboard:contact_thanks")

    return render(request, "dashboard/contact.html", {"form": form})


def contact_thanks(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/contact_thanks.html")


# ---- Help Center ----
HELP_ARTICLES = {
    "getting-started": "dashboard/help/getting_started.html",
    "invoices": "dashboard/help/invoices.html",
    "time-tracking": "dashboard/help/time_tracking.html",
    "estimates": "dashboard/help/estimates.html",
    "projects": "dashboard/help/projects.html",
    "expenses": "dashboard/help/expenses.html",
    "payments": "dashboard/help/payments.html",
    "reports": "dashboard/help/reports.html",
    "billing": "dashboard/help/billing.html",
    "team": "dashboard/help/team.html",
    "data": "dashboard/help/data.html",
    "security": "dashboard/help/security.html",
}

def help_index(request: HttpRequest) -> HttpResponse:
    articles = [
        {"slug": "getting-started", "title": "Getting Started", "desc": "Set up your company, clients, and first project."},
        {"slug": "invoices", "title": "Invoices", "desc": "Create, send, and track invoices; use templates and reminders."},
        {"slug": "time-tracking", "title": "Time Tracking", "desc": "Use timers and manual logs; convert time to invoices."},
        {"slug": "estimates", "title": "Estimates & Proposals", "desc": "Create estimates for approval and convert to projects/invoices."},
        {"slug": "projects", "title": "Projects", "desc": "Hourly vs flat-rate, budgets, phases, and status."},
        {"slug": "expenses", "title": "Expenses", "desc": "Record, categorize, rebill, and attach receipts."},
        {"slug": "payments", "title": "Payments", "desc": "Record payments and reconcile; enable online payments."},
        {"slug": "reports", "title": "Reports", "desc": "Profit & loss, cash flow, time, and project performance."},
        {"slug": "billing", "title": "Billing & Subscription", "desc": "Choose a plan, manage the subscription, and receipts."},
        {"slug": "team", "title": "Team & Roles", "desc": "Invite teammates, roles, and approvals."},
        {"slug": "data", "title": "Data Export & Import", "desc": "Export your data and import clients/projects."},
        {"slug": "security", "title": "Privacy & Security", "desc": "Security practices, backups, and data retention."},
    ]
    return render(request, "dashboard/help/index.html", {"articles": articles})


def help_article(request: HttpRequest, slug: str) -> HttpResponse:
    tpl = HELP_ARTICLES.get(slug)
    if not tpl:
        messages.info(request, "That article isn’t available yet.")
        return redirect("dashboard:help_index")
    return render(request, tpl, {"slug": slug})


# ---- Suggestions (admin) ----
@staff_member_required
def suggestions_admin_list(request: HttpRequest) -> HttpResponse:
    qs = Suggestion.objects.select_related("user", "company").order_by("-created_at")[:200]
    return render(request, "dashboard/suggestions_admin_list.html", {"items": qs})


# ---- Legal / Cookies ----
def _legal_ctx() -> Dict[str, object]:
    return {
        "company_name": getattr(settings, "COMPANY_NAME", "Your Company, LLC"),
        "company_address": getattr(settings, "COMPANY_ADDRESS", "123 Main St, City, State, Country"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", "support@example.com"),
        "site_url": getattr(settings, "SITE_URL", "https://example.com"),
        "effective_date": getattr(settings, "LEGAL_EFFECTIVE_DATE", timezone.now().date()),
        "governing_law": getattr(settings, "GOVERNING_LAW", "Delaware, USA"),
        "do_not_sell_url": getattr(settings, "DO_NOT_SELL_URL", ""),
        "subprocessors_url": getattr(settings, "SUBPROCESSORS_URL", ""),
    }


def subprocessors(request):
    items = getattr(settings, "SUBPROCESSORS", [])
    effective_str = getattr(settings, "LEGAL_EFFECTIVE_DATE", "")
    effective_date = parse_date(effective_str) if effective_str else None

    return render(
        request,
        "dashboard/legal/subprocessors.html",
        {
            "items": items,
            "effective_date": effective_date,
            "company_name": getattr(settings, "COMPANY_NAME", "EZ360PM"),
            "site_url": getattr(settings, "SITE_URL", ""),
        },
    )


def _consent_cookie_value(analytics: bool, marketing: bool) -> str:
    # compact, readable format the frontend can parse easily
    return f"v=1&ana={'1' if analytics else '0'}&mkt={'1' if marketing else '0'}"


def _safe_next(request: HttpRequest, fallback: str = "/") -> str:
    """Prevent open redirects by verifying the host/scheme."""
    candidate = request.POST.get("next") or request.META.get("HTTP_REFERER") or fallback
    return candidate if url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}) else fallback


def cookies(request):
    """
    Public Cookie Policy page.
    """
    ctx = {
        "effective_date": getattr(settings, "LEGAL_EFFECTIVE_DATE", ""),
        "governing_law": getattr(settings, "GOVERNING_LAW", ""),
        "company_name": getattr(settings, "COMPANY_NAME", getattr(settings, "APP_NAME", "EZ360PM")),
        "support_email": getattr(settings, "SUPPORT_EMAIL", "support@example.com"),
    }
    return render(request, "dashboard/legal/cookies.html", ctx)


def terms(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/legal/terms.html", _legal_ctx())


def privacy(request: HttpRequest) -> HttpResponse:
    return render(request, "dashboard/legal/privacy.html", _legal_ctx())


# ---- Onboarding ----
@login_required
def onboarding(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    status = get_onboarding_status(request.user, company)
    return render(
        request,
        "onboarding/onboarding.html",
        {
            "status": status,
            "company": company,
        },
    )


@require_POST
@login_required
def onboarding_dismiss(request: HttpRequest) -> HttpResponse:
    request.session["onboarding_dismissed"] = True
    messages.info(request, "Onboarding hidden. You can return to it anytime from the Help menu.")
    return redirect("dashboard:home")


@login_required
def refer(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    code = f"{request.user.pk}-{(company.pk if company else '0')}"
    link = f"{getattr(settings,'SITE_URL','').rstrip('/')}/?ref={code}"
    return render(request, "dashboard/refer.html", {"link": link})


def _read_consent(request) -> Dict[str, bool]:
    """Best-effort parse of the consent cookie into flags."""
    name = getattr(settings, "COOKIE_CONSENT_NAME", "cookie_consent")
    raw = request.COOKIES.get(name, "")
    default = {"analytics": False, "marketing": False}
    if not raw:
        return default
    try:
        if raw in ("all", "accept"):
            return {"analytics": True, "marketing": True}
        if raw in ("essential", "reject"):
            return default
        if raw.startswith("custom:"):
            body = raw.split("custom:", 1)[1]
            parts = dict(p.split("=", 1) for p in body.split(",") if "=" in p)
            return {
                "analytics": parts.get("analytics") in ("1", "true", "True"),
                "marketing": parts.get("marketing") in ("1", "true", "True"),
            }
        # Allow JSON format too
        data = json.loads(raw)
        return {"analytics": bool(data.get("analytics")), "marketing": bool(data.get("marketing"))}
    except Exception:
        return default

def _effective_date():
    eff = getattr(settings, "LEGAL_EFFECTIVE_DATE", "")
    try:
        return date.fromisoformat(eff) if eff else None
    except Exception:
        return None

def cookie_preferences(request):
    flags = _read_consent(request)
    ctx = {
        "analytics": flags["analytics"],
        "marketing": flags["marketing"],
        "effective_date": _effective_date(),
    }
    return render(request, "dashboard/legal/cookie_preferences.html", ctx)

@require_POST
def cookie_consent_set(request):
    """
    Persist cookie consent.
      - choice=accept|all       → full consent
      - choice=reject|essential → essentials only
      - choice=custom           → use checkboxes 'analytics' and/or 'marketing'
    """
    choice = (request.POST.get("choice") or "").lower()
    analytics = bool(request.POST.get("analytics"))
    marketing = bool(request.POST.get("marketing"))

    name = getattr(settings, "COOKIE_CONSENT_NAME", "cookie_consent")
    max_age = int(getattr(settings, "COOKIE_CONSENT_MAX_AGE", 60 * 60 * 24 * 365))

    if choice in ("accept", "all"):
        value = "all"
    elif choice in ("reject", "essential"):
        value = "essential"
    else:
        value = f"custom:analytics={'1' if analytics else '0'},marketing={'1' if marketing else '0'}"

    resp = redirect(request.META.get("HTTP_REFERER") or reverse("dashboard:cookie_preferences"))
    resp.set_cookie(
        name,
        value,
        max_age=max_age,
        samesite="Lax",
        secure=not settings.DEBUG,
        httponly=False,  # front-end JS can read to hide the banner
    )
    return resp