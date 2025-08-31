# dashboard/views.py
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Dict, List, Tuple
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import EmailMessage, mail_admins
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from core.forms import SuggestionForm
from core.models import (
    Client,
    Expense,
    Invoice,
    Notification,
    Payment,
    Project,
    Suggestion,
    TimeEntry,
)
from core.services import recalc_invoice
from core.utils import default_range_last_30, get_active_company, get_onboarding_status

# Optional import; fall back gracefully if the helper isn't present.
try:
    from core.utils import user_has_active_subscription  # type: ignore
except Exception:
    def user_has_active_subscription(company) -> bool:  # type: ignore
        return False


def home(request):
    """
    Public landing when logged out; full dashboard when logged in.
    Unsubscribed users still see the dashboard, but subscription-gated
    actions elsewhere should block as needed.
    """
    if not request.user.is_authenticated:
        return render(request, "dashboard/public_home.html", {"APP_NAME": getattr(settings, "APP_NAME", "EZ360PM")})

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
    profit_30 = income_30 - expenses_30

    # --- Invoices & balances (exclude void) and keep totals fresh
    inv_qs = Invoice.objects.filter(company=company).exclude(status=Invoice.VOID)
    for inv in inv_qs.only("id", "total", "amount_paid", "status"):
        recalc_invoice(inv)

    outstanding_total = sum((inv.total or Decimal("0")) - (inv.amount_paid or Decimal("0")) for inv in inv_qs)

    # Overdue list
    overdue: List[Tuple[Invoice, Decimal]] = []
    overdue_qs = (
        inv_qs.exclude(due_date__isnull=True)
        .filter(due_date__lt=today)
        .select_related("client")
        .order_by("due_date")[:10]
    )
    for inv in overdue_qs:
        bal = (inv.total or Decimal("0")) - (inv.amount_paid or Decimal("0"))
        if bal > 0:
            overdue.append((inv, bal))

    # --- This week time (Mon–Sun)
    now = timezone.localtime()
    start_week = now.date() - timedelta(days=now.weekday())
    end_week = start_week + timedelta(days=6)

    hours_week = (
        TimeEntry.objects.filter(project__company=company, started_at__date__range=(start_week, end_week))
        .aggregate(s=Sum("hours"))
        .get("s") or 0
    )
    active_timers = TimeEntry.objects.filter(project__company=company, ended_at__isnull=True).count()

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
    top_clients = (
        Client.objects.filter(company=company)
        .annotate(total_paid=Sum("invoices__payments__amount"))
        .order_by("-total_paid")[:5]
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


def contact_submit(request):
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

    subject = f"[{getattr(settings, 'APP_NAME', 'EZ360PM')}] Contact — {name or 'Visitor'}"
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


def contact(request):
    """
    “Suggest an improvement” / contact form.
    Saves Suggestion and emails admins; open to public but pre-fills for logged-in.
    """
    initial = {}
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
            s.company = get_active_company(request) # type: ignore
        s.save()

        # Lightweight email to site admins (configure ADMINS in settings for delivery)
        try:
            body = render_to_string("dashboard/email/suggestion.txt", {"s": s})
            mail_admins(subject=f"[{getattr(settings, 'APP_NAME', 'EZ360PM')}] New suggestion — {s.subject}", message=body, fail_silently=True)
        except Exception:
            pass

        messages.success(request, "Thanks! Your suggestion has been sent.")
        return redirect("dashboard:contact_thanks")

    return render(request, "dashboard/contact.html", {"form": form})


def contact_thanks(request):
    return render(request, "dashboard/contact_thanks.html")


# ---------- Help Center ----------

HELP_ARTICLES = {
    "getting-started": "dashboard/help/getting_started.html",
    "invoices": "dashboard/help/invoices.html",
    "time-tracking": "dashboard/help/time_tracking.html",
}

def help_index(request):
    articles = [
        {"slug": k, "title": t}
        for k, t in {
            "getting-started": "Getting started",
            "invoices": "Invoices & payments",
            "time-tracking": "Time tracking & approvals",
        }.items()
    ]
    return render(request, "dashboard/help/index.html", {"articles": articles})


def help_article(request, slug: str):
    tpl = HELP_ARTICLES.get(slug)
    if not tpl:
        messages.info(request, "That article isn’t available yet.")
        return redirect("dashboard:help_index")
    return render(request, tpl, {"slug": slug})


# ---------- Suggestions (admin) ----------

@staff_member_required
def suggestions_admin_list(request):
    qs = Suggestion.objects.select_related("user", "company").order_by("-created_at")[:200]
    return render(request, "dashboard/suggestions_admin_list.html", {"items": qs})

def _legal_ctx():
    from django.utils import timezone
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
    ctx = _legal_ctx() | {"items": getattr(settings, "SUBPROCESSORS", [])}
    return render(request, "dashboard/legal/subprocessors.html", ctx)

def cookies(request):
    ctx = _legal_ctx()
    return render(request, "dashboard/legal/cookies.html", ctx)

def _consent_cookie_value(analytics: bool, marketing: bool) -> str:
    # compact, readable format the frontend can parse easily
    return f"v=1&ana={'1' if analytics else '0'}&mkt={'1' if marketing else '0'}"

def cookie_preferences(request):
    # pre-fill toggles from existing cookie (if any)
    raw = request.COOKIES.get(getattr(settings, "COOKIE_CONSENT_NAME", "cookie_consent"), "")
    defaults = {"analytics": False, "marketing": False}
    try:
        parts = dict(p.split("=", 1) for p in raw.split("&") if "=" in p)
        defaults["analytics"] = parts.get("ana") == "1"
        defaults["marketing"] = parts.get("mkt") == "1"
    except Exception:
        pass
    ctx = _legal_ctx() | defaults
    return render(request, "dashboard/legal/cookie_preferences.html", ctx)

@require_POST
def cookie_consent_set(request):
    choice = (request.POST.get("choice") or "").lower()
    ref = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    name = getattr(settings, "COOKIE_CONSENT_NAME", "cookie_consent")
    max_age = int(getattr(settings, "COOKIE_CONSENT_MAX_AGE", 31536000))

    if choice == "accept_all":
        value = _consent_cookie_value(analytics=True, marketing=True)
    elif choice == "reject_all":
        value = _consent_cookie_value(analytics=False, marketing=False)
    else:
        # custom
        analytics = request.POST.get("analytics") == "on"
        marketing = request.POST.get("marketing") == "on"
        value = _consent_cookie_value(analytics=analytics, marketing=marketing)

    resp = redirect(ref)
    # non-HttpOnly so JS can check before loading analytics
    resp.set_cookie(
        name,
        value,
        max_age=max_age,
        secure=request.is_secure(),
        samesite="Lax",
        httponly=False,
    )
    messages.success(request, "Your cookie preferences have been saved.")
    return resp

def terms(request):
    return render(request, "dashboard/legal/terms.html", _legal_ctx())

def privacy(request):
    return render(request, "dashboard/legal/privacy.html", _legal_ctx())

@login_required
def onboarding(request):
    company = get_active_company(request)
    status = get_onboarding_status(request.user, company)
    return render(request, "dashboard/onboarding.html", {
        "status": status,
        "company": company,
    })

@require_POST
@login_required
def onboarding_dismiss(request):
    request.session["onboarding_dismissed"] = True
    messages.info(request, "Onboarding hidden. You can return to it anytime from the Help menu.")
    return redirect("dashboard:home")