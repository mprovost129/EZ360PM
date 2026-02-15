from __future__ import annotations

import os
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from django.utils import timezone

from audit.services import log_event
from billing.models import BillingWebhookEvent, CompanySubscription, PlanCode, SubscriptionStatus
from companies.models import Company, EmployeeProfile
from accounts.models import AccountLockout
from companies.services import set_active_company_id
from companies.services import get_active_company
from core.support_mode import get_support_mode, set_support_mode
from billing.stripe_service import fetch_and_sync_subscription_from_stripe
from core.launch_checks import run_launch_checks
from core.retention import get_retention_days, run_prune_jobs

from .forms import ReleaseNoteForm

from .models import OpsAlertEvent, OpsAlertSource, OpsAlertLevel, LaunchGateItem, BackupRun, BackupRestoreTest, BackupRunStatus, RestoreTestOutcome, ReleaseNote, UserPresence


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


def version(request: HttpRequest) -> HttpResponse:
    """Public build/version info.

    Safe by design: returns environment + build identifiers only.
    Do not include secrets.
    """
    payload = {
        "app": "EZ360PM",
        "environment": getattr(settings, "APP_ENVIRONMENT", ""),
        "build": {
            "version": getattr(settings, "BUILD_VERSION", ""),
            "sha": getattr(settings, "BUILD_SHA", ""),
            "date": getattr(settings, "BUILD_DATE", ""),
        },
    }
    return JsonResponse(payload)





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
    subs = {s.company.id: s for s in CompanySubscription.objects.select_related("company")}
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

    system_status = {
        "app_environment": getattr(settings, "APP_ENVIRONMENT", ""),
        "build_version": getattr(settings, "BUILD_VERSION", ""),
        "build_sha": getattr(settings, "BUILD_SHA", ""),
        "build_date": getattr(settings, "BUILD_DATE", ""),
        "settings_module": os.environ.get("DJANGO_SETTINGS_MODULE", ""),
        "debug": bool(getattr(settings, "DEBUG", False)),
        "secure_ssl_redirect": bool(getattr(settings, "SECURE_SSL_REDIRECT", False)),
        "session_cookie_secure": bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
        "csrf_cookie_secure": bool(getattr(settings, "CSRF_COOKIE_SECURE", False)),
        "allowed_hosts": getattr(settings, "ALLOWED_HOSTS", []),
        "email_backend": getattr(settings, "EMAIL_BACKEND", ""),
        "cache_backend": (getattr(settings, "CACHES", {}).get("default", {}) or {}).get("BACKEND", ""),
        "sentry_enabled": bool(os.environ.get("SENTRY_DSN")),
    }

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
            "system_status": system_status,
            "open_alerts": OpsAlertEvent.objects.filter(is_resolved=False).count(),
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_slo_dashboard(request: HttpRequest) -> HttpResponse:
    """SLO-style dashboard (staff-only).

    Focus: active users + key failure signals (webhooks/email/auth).
    """

    now = timezone.now()
    window_5m = now - timedelta(minutes=5)
    window_30m = now - timedelta(minutes=30)
    window_24h = now - timedelta(hours=24)

    active_5m = UserPresence.objects.filter(last_seen__gte=window_5m).count()
    active_30m = UserPresence.objects.filter(last_seen__gte=window_30m).count()

    webhook_open = OpsAlertEvent.objects.filter(source=OpsAlertSource.STRIPE_WEBHOOK, is_resolved=False).count()
    email_open = OpsAlertEvent.objects.filter(source=OpsAlertSource.EMAIL, is_resolved=False).count()
    auth_open = OpsAlertEvent.objects.filter(source=OpsAlertSource.AUTH, is_resolved=False).count()

    webhook_24h = OpsAlertEvent.objects.filter(source=OpsAlertSource.STRIPE_WEBHOOK, created_at__gte=window_24h).count()
    email_24h = OpsAlertEvent.objects.filter(source=OpsAlertSource.EMAIL, created_at__gte=window_24h).count()

    # Stripe webhook freshness (best-effort global signal)
    last_webhook = BillingWebhookEvent.objects.order_by("-received_at").first()
    webhook_last_received_at = getattr(last_webhook, "received_at", None)
    last_webhook_ok = BillingWebhookEvent.objects.filter(ok=True).order_by("-received_at").first()
    webhook_last_ok_at = getattr(last_webhook_ok, "received_at", None)
    webhook_fail_24h = BillingWebhookEvent.objects.filter(ok=False, received_at__gte=window_24h).count()

    recent_alerts = OpsAlertEvent.objects.filter(created_at__gte=window_24h).select_related("company").order_by("-created_at")[:50]

    active_by_company = (
        UserPresence.objects.filter(last_seen__gte=window_30m)
        .values("company__id", "company__name")
        .annotate(active_users=Count("user", distinct=True))
        .order_by("-active_users", "company__name")[:30]
    )

    return render(
        request,
        "ops/slo_dashboard.html",
        {
            "active_5m": active_5m,
            "active_30m": active_30m,
            "webhook_open": webhook_open,
            "email_open": email_open,
            "auth_open": auth_open,
            "webhook_24h": webhook_24h,
            "email_24h": email_24h,
            "webhook_last_received_at": webhook_last_received_at,
            "webhook_last_ok_at": webhook_last_ok_at,
            "webhook_fail_24h": webhook_fail_24h,
            "recent_alerts": recent_alerts,
            "active_by_company": active_by_company,
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
@login_required
@user_passes_test(_is_staff)
def ops_security(request: HttpRequest) -> HttpResponse:
    """Security-focused ops view: lockouts + auth/throttle alerts."""
    lockouts = AccountLockout.objects.all().order_by("-updated_at")[:200]
    auth_alerts = OpsAlertEvent.objects.filter(source=OpsAlertSource.AUTH).order_by("-created_at")[:100]
    throttle_alerts = OpsAlertEvent.objects.filter(source=OpsAlertSource.THROTTLE).order_by("-created_at")[:100]

    counts = {
        "open_auth": OpsAlertEvent.objects.filter(source=OpsAlertSource.AUTH, is_resolved=False).count(),
        "open_throttle": OpsAlertEvent.objects.filter(source=OpsAlertSource.THROTTLE, is_resolved=False).count(),
    }

    return render(
        request,
        "ops/security.html",
        {
            "lockouts": lockouts,
            "auth_alerts": auth_alerts,
            "throttle_alerts": throttle_alerts,
            "counts": counts,
            "support_mode": get_support_mode(request),
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_launch_gate(request: HttpRequest) -> HttpResponse:
    items = LaunchGateItem.objects.all()
    total = items.count()
    complete = items.filter(is_complete=True).count()
    return render(
        request,
        "ops/launch_gate.html",
        {
            "items": items,
            "summary": {"total": total, "complete": complete, "remaining": max(0, total - complete)},
            "support_mode": get_support_mode(request),
        },
    )


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_launch_gate_toggle(request: HttpRequest, item_id: int) -> HttpResponse:
    item = get_object_or_404(LaunchGateItem, pk=item_id)
    action = (request.POST.get("action") or "").strip().lower()
    if action == "complete":
        item.mark_complete(user=request.user)
        item.save(update_fields=["is_complete", "completed_at", "completed_by", "updated_at"])
        messages.success(request, f"Marked complete: {item.title}")
    elif action == "reopen":
        item.mark_incomplete()
        item.save(update_fields=["is_complete", "completed_at", "completed_by", "updated_at"])
        messages.info(request, f"Reopened: {item.title}")
    else:
        messages.error(request, "Invalid action.")
    return redirect("ops:launch_gate")


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



@login_required
@user_passes_test(_is_staff)
def ops_reconciliation(request: HttpRequest) -> HttpResponse:
    """Accounting reconciliation sanity checks (staff-only)."""
    from ops.services_reconciliation import reconcile_company

    company_id = (request.GET.get("company") or "").strip()
    company = None
    if company_id:
        try:
            company = Company.objects.filter(id=int(company_id)).first()
        except Exception:
            company = None

    # Default to current active/support company if any
    if company is None:
        try:
            company = get_active_company(request)
        except Exception:
            company = None

    companies = Company.objects.all().order_by("name")[:200]

    snapshot = None
    if company is not None:
        try:
            snapshot = reconcile_company(company)
        except Exception as e:
            messages.error(request, f"Could not run reconciliation: {e}")

    return render(
        request,
        "ops/reconciliation.html",
        {
            "companies": companies,
            "company": company,
            "snapshot": snapshot,
            "support_mode": get_support_mode(request),
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_drift_tools(request: HttpRequest) -> HttpResponse:
    """Staff-only tools to fix common reconciliation drift cases."""
    from payments.models import Payment, PaymentStatus
    from documents.models import Document, DocumentType, DocumentStatus
    from .forms import DriftCompanyActionForm, DriftLinkPaymentForm

    company_id = (request.GET.get("company") or "").strip()
    company = None
    if company_id:
        try:
            company = Company.objects.filter(id=int(company_id)).first()
        except Exception:
            company = None
    if company is None:
        try:
            company = get_active_company(request)
        except Exception:
            company = None

    companies = Company.objects.all().order_by("name")[:200]

    orphan_payments = []
    invoice_candidates = []
    if company is not None:
        orphan_payments = list(
            Payment.objects.filter(
                company=company,
                status__in=[PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED],
                invoice__isnull=True,
                deleted_at__isnull=True,
            )
            .order_by("-created_at")[:50]
        )
        # Candidates where stored rollups are likely stale
        invoice_candidates = list(
            Document.objects.filter(
                company=company,
                doc_type=DocumentType.INVOICE,
                deleted_at__isnull=True,
            )
            .exclude(status=DocumentStatus.VOID)
            .filter(models.Q(amount_paid_cents__gt=0) | models.Q(balance_due_cents__lt=models.F("total_cents")))
            .order_by("-updated_at")[:50]
        )

    action_form = DriftCompanyActionForm(initial={"company_id": company.id if company else ""})
    link_form = DriftLinkPaymentForm(initial={"company_id": company.id if company else ""})

    return render(
        request,
        "ops/drift_tools.html",
        {
            "companies": companies,
            "company": company,
            "orphan_payments": orphan_payments,
            "invoice_candidates": invoice_candidates,
            "action_form": action_form,
            "link_form": link_form,
            "support_mode": get_support_mode(request),
        },
    )


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_drift_recalc(request: HttpRequest) -> HttpResponse:
    from documents.models import Document, DocumentType, DocumentStatus
    from payments.services import recalc_invoice_financials
    from .forms import DriftCompanyActionForm

    form = DriftCompanyActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid request.")
        return redirect("ops:drift_tools")

    company = get_object_or_404(Company, id=form.cleaned_data["company_id"])

    count = 0
    qs = (
        Document.objects.filter(company=company, doc_type=DocumentType.INVOICE, deleted_at__isnull=True)
        .exclude(status=DocumentStatus.VOID)
        .order_by("created_at")
    )
    for inv in qs.iterator(chunk_size=200):
        recalc_invoice_financials(inv, actor=getattr(request, "employee_profile", None))
        count += 1

    messages.success(request, f"Recalculated {count} invoices for {company.name}.")
    return redirect(f"{request.path_info.rsplit('/', 2)[0]}/?company={company.id}")


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_drift_post_missing(request: HttpRequest) -> HttpResponse:
    from documents.models import Document, DocumentType, DocumentStatus
    from payments.models import Payment, PaymentStatus
    from expenses.models import Expense, ExpenseStatus
    from accounting.services import post_invoice_if_needed, post_payment_if_needed, post_expense_if_needed
    from .forms import DriftCompanyActionForm

    form = DriftCompanyActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid request.")
        return redirect("ops:drift_tools")

    company = get_object_or_404(Company, id=form.cleaned_data["company_id"])

    posted = {"invoices": 0, "payments": 0, "expenses": 0}

    invoices = (
        Document.objects.filter(company=company, doc_type=DocumentType.INVOICE, deleted_at__isnull=True)
        .exclude(status__in=[DocumentStatus.DRAFT, DocumentStatus.VOID])
        .order_by("created_at")
    )
    for inv in invoices.iterator(chunk_size=200):
        if post_invoice_if_needed(inv):
            posted["invoices"] += 1

    payments = (
        Payment.objects.filter(company=company, status=PaymentStatus.SUCCEEDED, deleted_at__isnull=True)
        .order_by("created_at")
    )
    for p in payments.iterator(chunk_size=200):
        if post_payment_if_needed(p):
            posted["payments"] += 1

    expenses = (
        Expense.objects.filter(company=company, status__in=[ExpenseStatus.SUBMITTED, ExpenseStatus.APPROVED], deleted_at__isnull=True)
        .order_by("created_at")
    )
    for e in expenses.iterator(chunk_size=200):
        if post_expense_if_needed(e):
            posted["expenses"] += 1

    messages.success(
        request,
        f"Posted missing entries for {company.name}: invoices {posted['invoices']}, payments {posted['payments']}, expenses {posted['expenses']}.",
    )
    return redirect(f"{request.path_info.rsplit('/', 2)[0]}/?company={company.id}")


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_drift_link_payment(request: HttpRequest) -> HttpResponse:
    from payments.models import Payment
    from documents.models import Document, DocumentType
    from payments.services import recalc_invoice_financials
    from accounting.services import post_payment_if_needed
    from .forms import DriftLinkPaymentForm

    form = DriftLinkPaymentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid request.")
        return redirect("ops:drift_tools")

    company = get_object_or_404(Company, id=form.cleaned_data["company_id"])

    payment = get_object_or_404(Payment, id=form.cleaned_data["payment_id"], company=company)
    invoice = get_object_or_404(Document, id=form.cleaned_data["invoice_id"], company=company, doc_type=DocumentType.INVOICE)

    payment.invoice = invoice
    if invoice.client_id and not payment.client_id:
        payment.client = invoice.client
    payment.save(update_fields=["invoice", "client", "updated_at"])

    recalc_invoice_financials(invoice, actor=getattr(request, "employee_profile", None))
    post_payment_if_needed(payment)

    messages.success(request, f"Linked payment {str(payment.id)[:8]} to invoice {invoice.number or str(invoice.id)[:8]}.")
    return redirect(f"/ops/drift/?company={company.id}")



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


@login_required
@user_passes_test(_is_staff)
def ops_backups(request: HttpRequest) -> HttpResponse:
    """Backups/restore status page.

    Note: EZ360PM does not execute backups. This page provides configuration visibility
    and a place to record backup runs / restore tests.
    """
    cfg = {
        "backup_enabled": bool(getattr(settings, "BACKUP_ENABLED", False)),
        "backup_retention_days": int(getattr(settings, "BACKUP_RETENTION_DAYS", 14)),
        "backup_storage": str(getattr(settings, "BACKUP_STORAGE", "host_managed")),
        "backup_notify_emails": list(getattr(settings, "BACKUP_NOTIFY_EMAILS", [])),
    }

    backup_runs = BackupRun.objects.all()[:25]
    restore_tests = BackupRestoreTest.objects.all()[:10]
    latest_restore = restore_tests[0] if restore_tests else None

    return render(
        request,
        "ops/backups.html",
        {
            "cfg": cfg,
            "backup_runs": backup_runs,
            "restore_tests": restore_tests,
            "latest_restore": latest_restore,
        },
    )


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_backup_record_run(request: HttpRequest) -> HttpResponse:
    status = request.POST.get("status") or BackupRunStatus.SUCCESS
    storage = (request.POST.get("storage") or "").strip()[:64]
    notes = (request.POST.get("notes") or "").strip()

    BackupRun.objects.create(
        status=status if status in {BackupRunStatus.SUCCESS, BackupRunStatus.FAILED} else BackupRunStatus.SUCCESS,
        storage=storage,
        notes=notes[:2000],
        initiated_by_email=(getattr(request.user, "email", "") or "")[:254],
        details={"ua": request.META.get("HTTP_USER_AGENT", "")[:200], "path": request.path},
    )
    messages.success(request, "Backup run recorded.")
    return redirect("ops:backups")


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_backup_record_restore_test(request: HttpRequest) -> HttpResponse:
    outcome = request.POST.get("outcome") or RestoreTestOutcome.PASS
    notes = (request.POST.get("notes") or "").strip()

    BackupRestoreTest.objects.create(
        outcome=outcome if outcome in {RestoreTestOutcome.PASS, RestoreTestOutcome.FAIL} else RestoreTestOutcome.PASS,
        notes=notes[:4000],
        tested_by_email=(getattr(request.user, "email", "") or "")[:254],
        details={"ua": request.META.get("HTTP_USER_AGENT", "")[:200]},
    )
    messages.success(request, "Restore test recorded.")
    return redirect("ops:backups")


@login_required
@user_passes_test(_is_staff)
def ops_releases(request: HttpRequest) -> HttpResponse:
    """Staff release notes + current build metadata."""

    q = (request.GET.get("q") or "").strip()
    env = (request.GET.get("env") or "").strip()

    notes_qs = ReleaseNote.objects.all()
    if env:
        notes_qs = notes_qs.filter(environment__iexact=env)
    if q:
        notes_qs = notes_qs.filter(Q(title__icontains=q) | Q(notes__icontains=q) | Q(build_version__icontains=q) | Q(build_sha__icontains=q))

    notes = list(notes_qs[:100])

    if request.method == "POST":
        form = ReleaseNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            user_email = getattr(getattr(request, "user", None), "email", "") or ""
            note.created_by_email = (user_email or "").strip()[:254]
            # If staff didn't fill build metadata, default to current settings.
            note.environment = (note.environment or getattr(settings, "APP_ENVIRONMENT", "") or "").strip()[:24]
            note.build_version = (note.build_version or getattr(settings, "BUILD_VERSION", "") or "").strip()[:64]
            note.build_sha = (note.build_sha or getattr(settings, "BUILD_SHA", "") or "").strip()[:64]
            note.save()

            log_event(
                request,
                action="ops.release_note.created",
                message=f"Release note created: {note.title}",
                company=None,
                data={"environment": note.environment, "build_version": note.build_version, "build_sha": note.build_sha},
            )
            messages.success(request, "Release note saved.")
            return redirect("ops:releases")
        messages.error(request, "Please fix the errors below.")
    else:
        form = ReleaseNoteForm(
            initial={
                "environment": getattr(settings, "APP_ENVIRONMENT", ""),
                "build_version": getattr(settings, "BUILD_VERSION", ""),
                "build_sha": getattr(settings, "BUILD_SHA", ""),
                "is_published": True,
            }
        )

    ctx = {
        "q": q,
        "env": env,
        "notes": notes,
        "form": form,
        "build": {
            "environment": getattr(settings, "APP_ENVIRONMENT", ""),
            "version": getattr(settings, "BUILD_VERSION", ""),
            "sha": getattr(settings, "BUILD_SHA", ""),
            "date": getattr(settings, "BUILD_DATE", ""),
            "debug": bool(getattr(settings, "DEBUG", False)),
        },
    }
    return render(request, "ops/releases.html", ctx)


@login_required
@user_passes_test(_is_staff)
def ops_pii_export(request: HttpRequest) -> HttpResponse:
    """Staff-only PII export tooling (DSAR / portability).

    Exports company-scoped business records as CSVs inside a ZIP.
    Best-effort: never intended to be a perfect archival backup (use backups for that).
    """
    company_id = request.GET.get("company_id") or request.POST.get("company_id")
    company: Company | None
    if company_id:
        company = get_object_or_404(Company, id=int(company_id))
    else:
        company = get_active_company(request)

    if not company:
        messages.error(request, "No company selected.")
        return redirect("ops:dashboard")

    if request.method != "POST":
        companies = Company.objects.all().order_by("name")[:200]
        return render(
            request,
            "ops/pii_export.html",
            {"company": company, "companies": companies},
        )

    # --- Build ZIP in memory ---
    from crm.models import Client
    from projects.models import Project
    from documents.models import Document
    from payments.models import Payment
    from expenses.models import Expense
    from timetracking.models import TimeEntry

    def _rows_for_model(model, qs):
        field_names = [f.name for f in model._meta.fields]
        for obj in qs.values(*field_names):
            yield field_names, obj

    def _write_csv(zf: zipfile.ZipFile, name: str, model, qs):
        # Stream to string buffer then write
        field_names = [f.name for f in model._meta.fields]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=field_names)
        w.writeheader()
        for row in qs.values(*field_names).iterator():
            w.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in field_names})
        zf.writestr(name, buf.getvalue())

    buf = io.BytesIO()
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"ez360pm_pii_export_company_{company.id}_{timestamp}.zip"

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Metadata
        zf.writestr(
            "README.txt",
            (
                "EZ360PM PII/Portability Export\n"
                f"Company: {company.name} (id={company.id})\n"
                f"Generated: {timezone.now().isoformat()}\n\n"
                "Contains business records as CSV. This is not a full media backup.\n"
            ),
        )

        _write_csv(zf, "company.csv", Company, Company.objects.filter(id=company.id))
        _write_csv(zf, "employees.csv", EmployeeProfile, EmployeeProfile.objects.filter(company=company))
        _write_csv(zf, "clients.csv", Client, Client.objects.filter(company=company))
        _write_csv(zf, "projects.csv", Project, Project.objects.filter(company=company))
        _write_csv(zf, "documents.csv", Document, Document.objects.filter(company=company))
        _write_csv(zf, "payments.csv", Payment, Payment.objects.filter(company=company))
        _write_csv(zf, "expenses.csv", Expense, Expense.objects.filter(company=company))
        _write_csv(zf, "time_entries.csv", TimeEntry, TimeEntry.objects.filter(company=company))

    buf.seek(0)
    resp = HttpResponse(buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{zip_name}"'
    return resp
