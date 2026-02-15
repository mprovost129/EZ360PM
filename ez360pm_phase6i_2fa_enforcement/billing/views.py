from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from companies.services import get_active_company

from .decorators import require_company_admin, require_staff
from .models import BillingWebhookEvent, PlanCode, BillingInterval, SubscriptionStatus
from .services import build_subscription_summary, ensure_company_subscription
from .stripe_service import (
    stripe_enabled,
    stripe_portal_enabled,
    create_subscription_checkout_session,
    create_billing_portal_session,
)


@require_company_admin
def billing_overview(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    sub = ensure_company_subscription(company)
    summary = build_subscription_summary(company)

    stripe_state = str(request.GET.get("stripe") or "").strip().lower()
    if stripe_state == "success":
        messages.success(request, "Payment complete. It may take a moment for Stripe to confirm your subscription.")
    elif stripe_state == "cancel":
        messages.info(request, "Checkout was canceled.")

    return render(
        request,
        "billing/overview.html",
        {
            "company": company,
            "sub": sub,
            "summary": summary,
            "PlanCode": PlanCode,
            "BillingInterval": BillingInterval,
            "SubscriptionStatus": SubscriptionStatus,
            "stripe_enabled": stripe_enabled(),
            "stripe_portal_enabled": stripe_portal_enabled(),
            "show_scaffold_controls": bool(settings.DEBUG) and (not stripe_enabled()),
            "show_webhook_history": bool(getattr(request.user, "is_staff", False) or getattr(request.user, "is_superuser", False)),
        },
    )


@require_company_admin
@require_POST
def set_plan(request: HttpRequest) -> HttpResponse:
    """Manual plan/interval changes (dev scaffold). Replace with Stripe later."""
    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    if stripe_enabled() or not settings.DEBUG:
        messages.error(request, "This dev helper is disabled.")
        return redirect("billing:overview")

    sub = ensure_company_subscription(company)
    plan = str(request.POST.get("plan") or "").strip()
    interval = str(request.POST.get("interval") or "").strip()

    changed_fields: list[str] = []
    if plan in {PlanCode.STARTER, PlanCode.PROFESSIONAL, PlanCode.PREMIUM} and plan != sub.plan:
        sub.plan = plan
        changed_fields.append("plan")
    if interval in {BillingInterval.MONTH, BillingInterval.YEAR} and interval != sub.billing_interval:
        sub.billing_interval = interval
        changed_fields.append("billing_interval")

    if changed_fields:
        sub.save(update_fields=changed_fields + ["updated_at"])
        messages.success(request, "Plan updated.")
    else:
        messages.info(request, "No changes.")

    return redirect("billing:overview")


@require_company_admin
@require_POST
def mark_active(request: HttpRequest) -> HttpResponse:
    """Dev/admin shortcut to toggle subscription active. Replace with webhook updates."""
    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    if stripe_enabled() or not settings.DEBUG:
        messages.error(request, "This dev helper is disabled.")
        return redirect("billing:overview")

    sub = ensure_company_subscription(company)
    sub.status = SubscriptionStatus.ACTIVE
    sub.current_period_start = sub.current_period_start or sub.trial_started_at
    sub.save(update_fields=["status", "current_period_start", "updated_at"])
    messages.success(request, "Subscription marked active (scaffold).")
    return redirect("billing:overview")


@require_company_admin
@require_POST
def start_checkout(request: HttpRequest) -> HttpResponse:
    """Start Stripe Checkout for subscription upgrades."""
    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    if not stripe_enabled():
        messages.error(request, "Stripe is not configured yet.")
        return redirect("billing:overview")

    plan = str(request.POST.get("plan") or "").strip()
    interval = str(request.POST.get("interval") or "").strip()

    try:
        session = create_subscription_checkout_session(request, company=company, plan=plan, interval=interval)
    except Exception as e:
        messages.error(request, f"Could not start checkout: {e}")
        return redirect("billing:overview")

    return redirect(session.url)


@require_company_admin
@require_POST
def portal(request: HttpRequest) -> HttpResponse:
    """Open Stripe Customer Portal."""
    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    if not stripe_portal_enabled():
        messages.error(request, "Stripe is not configured yet.")
        return redirect("billing:overview")

    try:
        session = create_billing_portal_session(request, company=company)
    except Exception as e:
        messages.error(request, f"Could not open Stripe portal: {e}")
        return redirect("billing:overview")

    return redirect(session.url)


@require_staff
def webhook_history(request: HttpRequest) -> HttpResponse:
    """Staff-only: view recent Stripe webhook events and processing results."""
    events = BillingWebhookEvent.objects.all()[:200]
    return render(request, "billing/webhook_history.html", {"events": events})


@require_staff
def webhook_event_detail(request: HttpRequest, pk: int) -> HttpResponse:
    obj = BillingWebhookEvent.objects.filter(pk=pk).first()
    if not obj:
        messages.error(request, "Webhook event not found.")
        return redirect("billing:webhook_history")

    return render(request, "billing/webhook_event_detail.html", {"event": obj})


def locked(request: HttpRequest) -> HttpResponse:
    """Shown when a company is locked (trial expired / inactive subscription)."""
    company = get_active_company(request)
    summary = build_subscription_summary(company) if company else None
    return render(request, "billing/locked.html", {"company": company, "summary": summary})
