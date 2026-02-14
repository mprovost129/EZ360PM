from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST

from audit.services import log_event
from billing.models import BillingWebhookEvent, CompanySubscription, PlanCode, SubscriptionStatus
from companies.models import Company, EmployeeProfile
from companies.services import set_active_company_id
from companies.services import get_active_company
from core.support_mode import get_support_mode, set_support_mode
from billing.stripe_service import fetch_and_sync_subscription_from_stripe
from core.launch_checks import run_launch_checks
from core.retention import get_retention_days, run_prune_jobs

from .models import OpsAlertEvent, OpsAlertSource, OpsAlertLevel


def _is_staff(user) -> bool:
    return bool(user and user.is_authenticated and user.is_staff)


def _recent_webhooks_for_company(company: Company, limit: int = 50):
    """Best-effort: find recent Stripe webhook events tied to a company by matching stripe customer/subscription ids in payload."""
    try:
        sub = CompanySubscription.objects.filter(company=company).first()
    except Exception:
        sub = None

    if not sub:
        return []

    # Pull a small window and filter in Python; JSON querying differs across DBs.
    events = list(BillingWebhookEvent.objects.all()[:300])
    out = []
    for e in events:
        payload = e.payload_json or {}
        obj = (payload.get("data") or {}).get("object") or {}
        customer = str(obj.get("customer") or "")
        sid = str(obj.get("id") or obj.get("subscription") or "")
        if (sub.stripe_customer_id and customer == sub.stripe_customer_id) or (sub.stripe_subscription_id and sid == sub.stripe_subscription_id):
            out.append(e)
        if len(out) >= limit:
            break
    return out





@login_required
@user_passes_test(_is_staff)
def ops_dashboard(request: HttpRequest) -> HttpResponse:
    q = (request.GET.get("q") or "").strip()

    companies = Company.objects.all().annotate(
        employee_count=Count("employees", filter=Q(employees__deleted_at__isnull=True), distinct=True),
    ).order_by("-created_at")

    if q:
        companies = companies.filter(
            Q(name__icontains=q)
            | Q(owner__email__icontains=q)
            | Q(employees__user__email__icontains=q)
        ).distinct()

    # Prefetch subscription for display (best-effort)
    subs = {s.company_id: s for s in CompanySubscription.objects.select_related("company")}
    rows = []
    for c in companies[:200]:
        s = subs.get(c.id)
        rows.append(
            {
                "company": c,
                "subscription": s,
                "employee_count": getattr(c, "employee_count", 0) or 0,
                "seats_limit": (s.seats_limit if s else 1),
                "support_mode": get_support_mode(request),
            }
        )

    metrics = {
        "companies_total": Company.objects.count(),
        "companies_with_subscription": CompanySubscription.objects.count(),
        "active_subscriptions": CompanySubscription.objects.filter(
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE]
        ).count(),
        "open_alerts": OpsAlertEvent.objects.filter(is_resolved=False).count(),
    }

    return render(
        request,
        "ops/dashboard.html",
        {
            "q": q,
            "rows": rows,
            "metrics": metrics,
            "open_alerts": OpsAlertEvent.objects.filter(is_resolved=False).count(),
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_alerts(request: HttpRequest) -> HttpResponse:
    """Ops alerts (staff-only)."""
    status = (request.GET.get("status") or "open").strip().lower()
    source = (request.GET.get("source") or "").strip()
    level = (request.GET.get("level") or "").strip()
    q = (request.GET.get("q") or "").strip()

    qs = OpsAlertEvent.objects.all().select_related("company").order_by("-created_at")

    if status == "open":
        qs = qs.filter(is_resolved=False)
    elif status == "resolved":
        qs = qs.filter(is_resolved=True)

    if source:
        qs = qs.filter(source=source)
    if level:
        qs = qs.filter(level=level)
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(message__icontains=q)
            | Q(company__name__icontains=q)
        )

    items = list(qs[:200])

    summary = {
        "open_total": OpsAlertEvent.objects.filter(is_resolved=False).count(),
        "open_webhooks": OpsAlertEvent.objects.filter(is_resolved=False, source=OpsAlertSource.STRIPE_WEBHOOK).count(),
        "open_email": OpsAlertEvent.objects.filter(is_resolved=False, source=OpsAlertSource.EMAIL).count(),
        "open_slow": OpsAlertEvent.objects.filter(is_resolved=False, source=OpsAlertSource.SLOW_REQUEST).count(),
    }

    return render(
        request,
        "ops/alerts.html",
        {
            "items": items,
            "status": status,
            "source": source,
            "level": level,
            "q": q,
            "summary": summary,
            "sources": OpsAlertSource.choices,
            "levels": OpsAlertLevel.choices,
        },
    )


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_alert_resolve(request: HttpRequest, alert_id: int) -> HttpResponse:
    obj = get_object_or_404(OpsAlertEvent, pk=alert_id)
    try:
        obj.resolve(by_email=getattr(getattr(request, "user", None), "email", "") or "")
        messages.success(request, "Alert marked as resolved.")
    except Exception:
        messages.error(request, "Could not resolve alert.")
    return redirect("ops:alerts")


@login_required
@user_passes_test(_is_staff)
def ops_launch_checks(request: HttpRequest) -> HttpResponse:
    """Launch readiness checks (staff-only).

    These checks are intentionally simple and DB-agnostic, so they can run in
    dev/staging/prod without special privileges.
    """
    results = run_launch_checks()
    summary = {
        "total": len(results),
        "failed": sum(1 for r in results if not r["ok"] and r["level"] == "error"),
        "warn": sum(1 for r in results if not r["ok"] and r["level"] == "warn"),
        "ok": sum(1 for r in results if r["ok"]),
    }
    return render(
        request,
        "ops/launch_checks.html",
        {
            "results": results,
            "summary": summary,
            "support_mode": get_support_mode(request),
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_company_detail(request: HttpRequest, company_id: int) -> HttpResponse:
    company = get_object_or_404(Company, pk=company_id)
    subscription = getattr(company, "subscription", None)
    employees = (
        EmployeeProfile.objects.filter(company=company, deleted_at__isnull=True)
        .select_related("user")
        .order_by("role", "user__email")
    )

    # Support mode shortcut: staff can enter support mode for this company.
    if request.method == "POST":
        set_support_mode(request, company_id=str(company.id), reason="ops_console")
        set_active_company_id(request, str(company.id))
        log_event(request, "ops.support_mode_enabled", company=company)
        # NOTE: We intentionally keep the user in the normal app UI. Support mode affects permissions elsewhere.

    return render(
        request,
        "ops/company_detail.html",
        {
            "company": company,
            "subscription": subscription,
            "employees": employees,
            "seats_limit": subscription.seats_limit if subscription else 1,
            "support": get_support_mode(request),
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_company_timeline(request: HttpRequest, company_id: int) -> HttpResponse:
    company = get_object_or_404(Company, pk=company_id)
    # Audit events (company scoped)
    from audit.models import AuditEvent
    audit_events = AuditEvent.objects.filter(company=company).select_related("actor").order_by("-created_at")[:200]

    webhook_events = _recent_webhooks_for_company(company, limit=80)

    # Merge to a single timeline (normalize timestamp key)
    items = []
    for ev in audit_events:
        items.append({
            "kind": "audit",
            "ts": ev.created_at,
            "event": ev,
        })
    for wh in webhook_events:
        items.append({
            "kind": "stripe",
            "ts": wh.received_at,
            "event": wh,
        })
    items.sort(key=lambda x: x["ts"], reverse=True)

    return render(
        request,
        "ops/company_timeline.html",
        {
            "company": company,
            "items": items[:200],
            "support_mode": get_support_mode(request),
        },
    )


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_resync_subscription(request: HttpRequest, company_id: int) -> HttpResponse:
    company = get_object_or_404(Company, pk=company_id)

    try:
        fetch_and_sync_subscription_from_stripe(company=company)
        messages.success(request, "Subscription refreshed from Stripe.")
        log_event(
            company=company,
            actor=None,
            event_type="ops.subscription_resync",
            object_type="CompanySubscription",
            object_id=None,
            summary="Staff refreshed subscription from Stripe.",
            payload={"company_id": company.id},
            request=request,
        )
    except Exception as e:
        messages.error(request, f"Could not refresh from Stripe: {e}")

    return redirect("ops:company_detail", company_id=company.id)


@login_required
@user_passes_test(_is_staff)
def ops_retention(request: HttpRequest) -> HttpResponse:
    """Retention policy overview (staff-only)."""
    policy = get_retention_days()

    # Dry-run counts for display
    results = run_prune_jobs(dry_run=True)
    by_label = {r.label: r for r in results}

    return render(
        request,
        "ops/retention.html",
        {
            "policy": policy,
            "results": results,
            "by_label": by_label,
            "support_mode": get_support_mode(request),
        },
    )


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_retention_prune(request: HttpRequest) -> HttpResponse:
    """Run prune jobs now (staff-only)."""
    results = run_prune_jobs(dry_run=False)

    total_deleted = sum(r.deleted_count for r in results)
    messages.success(request, f"Prune complete. Deleted {total_deleted} rows.")
    # Audit events are per-company; best-effort log under current active/support company.
    company = get_active_company(request)
    if company is not None:
        log_event(
            request=request,
            company=company,
            actor=None,
            event_type="ops.retention_prune",
            object_type="Retention",
            object_id=None,
            summary=f"Staff ran retention prune: deleted {total_deleted} rows.",
            payload={
                "results": [
                    {
                        "label": r.label,
                        "retention_days": r.retention_days,
                        "eligible": r.eligible_count,
                        "deleted": r.deleted_count,
                    }
                    for r in results
                ]
            },
        )
    return redirect("ops:retention")


# --------------------------------------------------------------------------------------
# Health check endpoint (no auth) for uptime monitors / load balancers.
# GET /healthz/
# --------------------------------------------------------------------------------------
from django.http import JsonResponse
from django.db import connection
from django.core.cache import cache


def healthz(request):
    data = {"status": "ok"}
    # DB check
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        data["db"] = "ok"
    except Exception as e:
        data["status"] = "error"
        data["db"] = "error"
        data["db_error"] = str(e)[:200]

    # Cache check (best-effort)
    try:
        cache.set("healthz_ping", "1", timeout=5)
        v = cache.get("healthz_ping")
        data["cache"] = "ok" if v == "1" else "degraded"
    except Exception as e:
        data["cache"] = "error"
        data["cache_error"] = str(e)[:200]

    status_code = 200 if data["status"] == "ok" else 500
    return JsonResponse(data, status=status_code)
