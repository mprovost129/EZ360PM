from __future__ import annotations

import os
import re
import io
import csv
import zipfile
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import models
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.management import call_command
from django.core.paginator import Paginator
from django.core.mail import EmailMultiAlternatives
from django.core.mail import get_connection

from core.email_utils import format_email_subject

from audit.services import log_event
from billing.models import BillingWebhookEvent, CompanySubscription, PlanCode, SubscriptionStatus
from billing.services import seats_limit_for
from companies.models import Company, EmployeeProfile
from accounts.models import AccountLockout
from companies.services import set_active_company_id
from companies.services import get_active_company
from core.support_mode import get_support_mode, set_support_mode
from billing.stripe_service import fetch_and_sync_subscription_from_stripe
from core.launch_checks import run_launch_checks
from core.retention import get_retention_days, run_prune_jobs

from .forms import ReleaseNoteForm, OpsChecksForm, OpsEmailTestForm, OpsAlertRoutingForm

from .services_alerts import create_ops_alert

from .models import (
    OpsAlertEvent,
    OpsAlertSource,
    OpsAlertLevel,
    LaunchGateItem,
    BackupRun,
    BackupRestoreTest,
    BackupRunStatus,
    RestoreTestOutcome,
    ReleaseNote,
    UserPresence,
    OpsEmailTest,
    OpsEmailTestStatus,
    OpsProbeEvent,
    OpsProbeKind,
    OpsProbeStatus,
    OpsCheckRun,
    OpsCheckKind,
    SiteConfig,
)


def _sentry_enabled() -> bool:
    return bool(getattr(settings, "SENTRY_DSN", "") or "")


def _is_staff(user) -> bool:
    return bool(user and user.is_authenticated and user.is_staff)

from functools import wraps


def staff_only(view_func):
    """Decorator: staff-only view (login required)."""

    @login_required
    @user_passes_test(_is_staff)
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped



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
    company_id = (request.GET.get("company_id") or "").strip()

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
                "seats_limit": (seats_limit_for(s) if s else 1),
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

    cron_commands = "\n".join(
        [
            "python manage.py ez360_run_ops_checks_daily",
            "python manage.py ez360_send_statement_reminders",
            "python manage.py ez360_prune_ops_check_runs --days 30",
            "python manage.py ez360_prune_ops_alerts",
        ]
    )

    scheduler_warnings: list[str] = []
    if not bool(getattr(settings, "DEBUG", False)):
        app_base_url = (getattr(settings, "APP_BASE_URL", "") or "").strip()
        if not app_base_url:
            scheduler_warnings.append("APP_BASE_URL is not set. Scheduled emails will omit deep links.")

        email_backend = (getattr(settings, "EMAIL_BACKEND", "") or "")
        if "console" in email_backend.lower():
            scheduler_warnings.append("EMAIL_BACKEND is console backend in production settings. Scheduled emails will not deliver.")

        email_host = (getattr(settings, "EMAIL_HOST", "") or "").strip()
        if email_host in {"localhost", "127.0.0.1"}:
            scheduler_warnings.append("EMAIL_HOST is set to localhost in production. Verify SMTP provider settings for scheduled emails.")

        from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
        if not from_email or "example" in from_email.lower():
            scheduler_warnings.append("DEFAULT_FROM_EMAIL is missing or looks like a placeholder.")

        # Stripe readiness (subscriptions)
        stripe_secret = (getattr(settings, "STRIPE_SECRET_KEY", "") or "").strip()
        stripe_pub = (getattr(settings, "STRIPE_PUBLISHABLE_KEY", "") or "").strip()
        stripe_whsec = (getattr(settings, "STRIPE_WEBHOOK_SECRET", "") or "").strip()
        if not stripe_secret or "example" in stripe_secret.lower():
            scheduler_warnings.append("STRIPE_SECRET_KEY is missing or looks like a placeholder.")
        if not stripe_pub or "example" in stripe_pub.lower():
            scheduler_warnings.append("STRIPE_PUBLISHABLE_KEY is missing or looks like a placeholder.")
        if not stripe_whsec or "example" in stripe_whsec.lower():
            scheduler_warnings.append("STRIPE_WEBHOOK_SECRET is missing or looks like a placeholder.")

        # Storage readiness (media/backups)
        if bool(getattr(settings, "USE_S3", False)):
            bucket = (
                (getattr(settings, "S3_PUBLIC_MEDIA_BUCKET", "") or "").strip()
                or (getattr(settings, "AWS_STORAGE_BUCKET_NAME", "") or "").strip()
            )
            if not bucket:
                scheduler_warnings.append("USE_S3 is enabled but no S3 public media bucket is configured.")

            aws_key = (getattr(settings, "AWS_ACCESS_KEY_ID", "") or "").strip()
            aws_secret = (getattr(settings, "AWS_SECRET_ACCESS_KEY", "") or "").strip()
            if not aws_key or not aws_secret:
                scheduler_warnings.append("USE_S3 is enabled but AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY are missing.")

        if bool(getattr(settings, "BACKUP_ENABLED", False)) and (getattr(settings, "BACKUP_STORAGE", "") or "").strip().lower() == "s3":
            b = (getattr(settings, "BACKUP_S3_BUCKET", "") or "").strip()
            if not b:
                scheduler_warnings.append("BACKUP_ENABLED is true with BACKUP_STORAGE=s3, but BACKUP_S3_BUCKET is not set.")

        # Domain readiness: APP_BASE_URL should align with ALLOWED_HOSTS + CSRF_TRUSTED_ORIGINS
        if app_base_url:
            try:
                parsed = urlparse(app_base_url)
                host = (parsed.hostname or "").strip()
                scheme = (parsed.scheme or "").strip()

                if not host:
                    scheduler_warnings.append("APP_BASE_URL is set but could not parse a hostname.")
                else:
                    allowed_hosts = set(getattr(settings, "ALLOWED_HOSTS", []) or [])
                    if host not in allowed_hosts and f".{host}" not in allowed_hosts:
                        scheduler_warnings.append("APP_BASE_URL host is not present in ALLOWED_HOSTS.")

                    csrf = set(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
                    expected_origin = f"{scheme or 'https'}://{host}"
                    if expected_origin not in csrf:
                        scheduler_warnings.append("APP_BASE_URL origin is not present in CSRF_TRUSTED_ORIGINS.")
            except Exception:
                scheduler_warnings.append("APP_BASE_URL parsing failed. Verify it is a full URL like https://ez360pm.com")

    metrics = {
        "companies_total": Company.objects.count(),
        "companies_with_subscription": CompanySubscription.objects.count(),
        "active_subscriptions": CompanySubscription.objects.filter(
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE]
        ).count(),
        "open_alerts": OpsAlertEvent.objects.filter(is_resolved=False).count(),
    }

    # Phase 7H43: fast triage summary for open alerts grouped by source/company.
    open_alert_groups = (
        OpsAlertEvent.objects.filter(is_resolved=False)
        .values("source", "company_id", "company__name")
        .annotate(total=Count("id"))
        .order_by("-total", "source")
    )[:25]

    open_alert_by_source = (
        OpsAlertEvent.objects.filter(is_resolved=False)
        .values("source")
        .annotate(total=Count("id"))
        .order_by("-total", "source")
    )[:20]


    # Phase 7H45/7H46: show active snoozes on the Ops Dashboard grouping tables.
    # We store both the latest `snoozed_until` and the snooze row id so the UI can clear it.
    snooze_map: dict[str, dict[str, object]] = {}
    try:
        from .models import OpsAlertSnooze

        active_snoozes = (
            OpsAlertSnooze.objects.filter(snoozed_until__gt=timezone.now())
            .order_by("source", "company_id", "-snoozed_until")
        )
        for s in active_snoozes:
            key = f"{s.source}:{s.company_id or 'platform'}"
            # Keep the *latest* snooze per key.
            if key not in snooze_map:
                snooze_map[key] = {"until": s.snoozed_until, "id": s.id}
    except Exception:
        snooze_map = {}

    return render(
        request,
        "ops/dashboard.html",
        {
            "q": q,
            "company_id": company_id,
            "rows": rows,
            "metrics": metrics,
            "system_status": system_status,
            "open_alerts": OpsAlertEvent.objects.filter(is_resolved=False).count(),
            "recent_alerts": OpsAlertEvent.objects.select_related("company").order_by("-created_at")[:20],
            "site_config": (SiteConfig.get_solo() if hasattr(SiteConfig, "get_solo") else None),
            "cron_commands": cron_commands,
            "scheduler_warnings": scheduler_warnings,
            "open_alert_groups": list(open_alert_groups),
            "open_alert_by_source": list(open_alert_by_source),
            "snooze_map": snooze_map,
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_alert_snooze_clear(request: HttpRequest) -> HttpResponse:
    """Clear active snoozes for a source and optional company.

    Phase 7H46:
    - Expose a one-click "clear snooze" action from dashboard groupings.

    Input:
      POST source=<OpsAlertSource>
      POST company_id=<uuid> (optional; when omitted clears platform snoozes for the source)
    """

    if request.method != "POST":
        return HttpResponse(status=405)

    source = (request.POST.get("source") or "").strip()
    company_id = (request.POST.get("company_id") or "").strip()
    now = timezone.now()

    if not source:
        messages.error(request, "Missing source.")
        return redirect("ops:dashboard")

    try:
        from .models import OpsAlertSnooze
        qs = OpsAlertSnooze.objects.filter(source=source, snoozed_until__gt=now)
        if company_id:
            qs = qs.filter(company_id=company_id)
        else:
            qs = qs.filter(company__isnull=True)

        deleted, _ = qs.delete()
        if deleted:
            messages.success(request, "Snooze cleared.")
        else:
            messages.info(request, "No active snooze to clear.")
    except Exception:
        messages.error(request, "Could not clear snooze.")

    return redirect("ops:dashboard")

@staff_only
def ops_alert_snoozes(request: HttpRequest) -> HttpResponse:
    """List alert snoozes (active + expired) for audit visibility.

    Phase 7H47:
    - Provide a dedicated snooze list/detail so staff can see what is suppressed and why.
    """

    from .models import OpsAlertSnooze

    now = timezone.now()
    status = (request.GET.get("status") or "active").strip().lower()
    q = (request.GET.get("q") or "").strip()

    qs = OpsAlertSnooze.objects.select_related("company").all()

    if status == "expired":
        qs = qs.filter(snoozed_until__lte=now)
    elif status == "all":
        pass
    else:
        status = "active"
        qs = qs.filter(snoozed_until__gt=now)

    if q:
        qs = qs.filter(
            Q(source__icontains=q)
            | Q(reason__icontains=q)
            | Q(created_by_email__icontains=q)
            | Q(company__name__icontains=q)
        )

    qs = qs.order_by("-snoozed_until", "-created_at")

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    return render(
        request,
        "ops/alert_snoozes.html",
        {
            "status": status,
            "q": q,
            "page_obj": page_obj,
            "now": now,
        },
    )


@staff_only
def ops_alert_snooze_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Snooze detail view (audit)."""
    from .models import OpsAlertSnooze

    snooze = get_object_or_404(OpsAlertSnooze.objects.select_related("company"), pk=pk)
    now = timezone.now()
    is_active = snooze.snoozed_until > now
    return render(request, "ops/alert_snooze_detail.html", {"snooze": snooze, "now": now, "is_active": is_active})


@staff_only
@require_POST
def ops_alert_snooze_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """Delete a snooze record."""
    from .models import OpsAlertSnooze

    snooze = get_object_or_404(OpsAlertSnooze, pk=pk)
    try:
        snooze.delete()
        messages.success(request, "Snooze deleted.")
    except Exception:
        messages.error(request, "Could not delete snooze.")

    return redirect("ops:alert_snoozes")




@login_required
@user_passes_test(_is_staff)


@login_required
@user_passes_test(_is_staff)
def ops_alerts_export_csv(request: HttpRequest) -> HttpResponse:
    """Export unresolved Ops alerts as CSV.

    Phase 7H42: quick export for triage/reconciliation.
    """
    source = (request.GET.get("source") or "").strip()
    level = (request.GET.get("level") or "").strip()
    q = (request.GET.get("q") or "").strip()
    company_id = (request.GET.get("company_id") or "").strip()

    qs = OpsAlertEvent.objects.filter(is_resolved=False).select_related("company").order_by("-created_at")

    if source:
        qs = qs.filter(source=source)
    if level:
        qs = qs.filter(level=level)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(message__icontains=q) | Q(company__name__icontains=q))

    # Hard cap to keep exports reasonable.
    rows = list(qs[:2000])

    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="ops_alerts_unresolved.csv"'

    w = csv.writer(resp)
    w.writerow(["created_at", "source", "level", "company", "title", "message", "dedup_count", "request_id"])

    for a in rows:
        details = a.details or {}
        dedup = int(details.get("dedup_count") or 1)
        request_id = (
            details.get("request_id")
            or details.get("requestID")
            or details.get("rid")
            or details.get("requestId")
            or details.get("x_request_id")
            or ""
        )
        request_id = str(request_id).strip()[:128]
        w.writerow([
            a.created_at.isoformat(),
            a.source,
            a.level,
            a.company.name if a.company else "",
            a.title,
            (a.message or "")[:500],
            dedup,
            request_id,
        ])

    return resp
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

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
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

@login_required
@user_passes_test(_is_staff)
def ops_email_test(request: HttpRequest) -> HttpResponse:
    """Staff-only email diagnostics.

    Purpose: validate outbound email configuration in each environment.
    """

    initial_to = getattr(getattr(request, "user", None), "email", "") or ""
    if request.method == "POST":
        form = OpsEmailTestForm(request.POST)
        if form.is_valid():
            to_email = form.cleaned_data["to_email"].strip()
            subject = (form.cleaned_data.get("subject") or "").strip() or "EZ360PM test email"
            body = (form.cleaned_data.get("message") or "").strip() or "This is a test email from EZ360PM Ops Console."

            from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
            backend = str(getattr(settings, "EMAIL_BACKEND", "") or "")

            started = timezone.now()
            status = OpsEmailTestStatus.SENT
            error = ""

            try:
                # Explicit connection open to surface config errors deterministically.
                conn = get_connection(fail_silently=False)
                conn.open()

                email = EmailMultiAlternatives(
                    subject=format_email_subject(subject),
                    body=body,
                    from_email=from_email or None,
                    to=[to_email],
                )
                email.send(fail_silently=False)
                conn.close()
                messages.success(request, f"Test email sent to {to_email}.")
            except Exception as exc:
                status = OpsEmailTestStatus.FAILED
                error = str(exc)[:4000]
                messages.error(request, f"Email send failed: {exc}")
                create_ops_alert(
                    title="Email test failed",
                    message=error,
                    level=OpsAlertLevel.ERROR,
                    source=OpsAlertSource.EMAIL,
                    company=None,
                )
            finally:
                latency_ms = int((timezone.now() - started).total_seconds() * 1000)
                try:
                    OpsEmailTest.objects.create(
                        to_email=to_email,
                        subject=format_email_subject(subject)[:200],
                        backend=backend[:255],
                        from_email=from_email[:254],
                        status=status,
                        latency_ms=max(latency_ms, 0),
                        error=error,
                        initiated_by_email=(getattr(request.user, "email", "") or "")[:254],
                    )
                except Exception:
                    pass

            return redirect("ops:email_test")
    else:
        form = OpsEmailTestForm(initial={"to_email": initial_to, "subject": "EZ360PM test email"})

    recent = OpsEmailTest.objects.all()[:25]

    diag = {
        "email_backend": getattr(settings, "EMAIL_BACKEND", ""),
        "default_from_email": getattr(settings, "DEFAULT_FROM_EMAIL", ""),
        "server_email": getattr(settings, "SERVER_EMAIL", ""),
        "email_host": getattr(settings, "EMAIL_HOST", ""),
        "email_port": getattr(settings, "EMAIL_PORT", ""),
        "email_use_tls": getattr(settings, "EMAIL_USE_TLS", False),
        "email_use_ssl": getattr(settings, "EMAIL_USE_SSL", False),
        "email_timeout": getattr(settings, "EMAIL_TIMEOUT", ""),
    }

    return render(
        request,
        "ops/email_test.html",
        {
            "form": form,
            "recent": recent,
            "diag": diag,
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

@login_required
@user_passes_test(_is_staff)
def ops_checks(request: HttpRequest) -> HttpResponse:
    """Run ops-grade checks that are otherwise CLI-only (staff-only).

    Stores results in OpsCheckRun for launch evidence and regression tracking.
    """
    output: dict[str, str] = {}
    form = OpsChecksForm(request.POST or None)

    recent_runs = OpsCheckRun.objects.select_related("company").all()[:25]

    # Quick actions (staff-only): run daily checks and prune old runs.
    action = (request.POST.get("action") or "").strip() if request.method == "POST" else ""
    if action in {"run_daily_checks", "prune_ops_runs"}:
        import io
        import time as _time

        buf = io.StringIO()
        started = _time.time()
        ok = False
        try:
            if action == "run_daily_checks":
                company = form.cleaned_data.get("company") if form.is_valid() else None
                kwargs = {}
                if company:
                    kwargs["company_id"] = str(company.id)
                call_command("ez360_run_ops_checks_daily", stdout=buf, stderr=buf, **kwargs)
            elif action == "prune_ops_runs":
                days = int(request.POST.get("days") or 30)
                keep_per_kind = int(request.POST.get("keep_per_kind") or 200)
                call_command(
                    "ez360_prune_ops_check_runs",
                    stdout=buf,
                    stderr=buf,
                    days=days,
                    keep_per_kind=keep_per_kind,
                )
            ok = True
        except SystemExit as e:
            code = getattr(e, "code", 1)
            ok = (code == 0)
            buf.write(f"\n(exit {code})")
        except Exception as e:
            buf.write(f"\n(exception) {e!r}")
            ok = False
        finally:
            duration_ms = int((_time.time() - started) * 1000)

        msg = buf.getvalue() or "(no output)"
        if action == "run_daily_checks":
            messages.success(request, "Daily checks executed." if ok else "Daily checks failed; see output below.")
            output["Daily checks now"] = msg
        else:
            messages.success(request, "Prune completed." if ok else "Prune failed; see output below.")
            output["Prune ops runs"] = msg

        # Refresh recent runs after actions.
        recent_runs = OpsCheckRun.objects.select_related("company").all()[:25]

        return render(
            request,
            "ops/checks.html",
            {
                "form": form,
                "output": output,
                "recent_runs": recent_runs,
            },
        )

    if request.method == "POST" and form.is_valid():
        company = form.cleaned_data.get("company")
        company_id = str(company.id) if company else ""
        fail_fast = bool(form.cleaned_data.get("fail_fast"))
        quiet = bool(form.cleaned_data.get("quiet"))

        def _run(label: str, kind: str, cmd: str, **kwargs):
            import io
            import time as _time

            buf = io.StringIO()
            started = _time.time()
            ok = False
            try:
                call_command(cmd, stdout=buf, stderr=buf, **kwargs)
                ok = True
            except SystemExit as e:
                code = getattr(e, "code", 1)
                ok = (code == 0)
                buf.write(f"\n(exit {code})")
            except Exception as e:
                buf.write(f"\n(exception) {e!r}")
                ok = False
            finally:
                duration_ms = int((_time.time() - started) * 1000)

            text = buf.getvalue() or "(no output)"
            max_chars = 200000
            stored_text = text
            if len(stored_text) > max_chars:
                stored_text = stored_text[:max_chars] + "\n\n[output truncated]"

            output[label] = stored_text

            # Persist run
            try:
                OpsCheckRun.objects.create(
                    created_by_email=(getattr(request.user, "email", "") or "")[:254],
                    company=company if company_id else None,
                    kind=kind,
                    args=kwargs or {},
                    is_ok=ok,
                    duration_ms=duration_ms,
                    output_text=stored_text,  # guardrail
                )
            except Exception:
                # Never break staff UI due to logging persistence issues
                pass

            return ok

        ran_any = False

        if form.cleaned_data.get("run_smoke"):
            ran_any = True
            kwargs = {}
            if company_id:
                kwargs["company_id"] = company_id
            _run("Smoke Test", OpsCheckKind.SMOKE, "ez360_smoke_test", **kwargs)

        if form.cleaned_data.get("run_invariants"):
            ran_any = True
            kwargs = {}
            if company_id:
                kwargs["company_id"] = company_id
            if fail_fast:
                kwargs["fail_fast"] = True
            if quiet:
                kwargs["quiet"] = True
            _run("Invariants", OpsCheckKind.INVARIANTS, "ez360_invariants_check", **kwargs)

        if form.cleaned_data.get("run_idempotency"):
            ran_any = True
            kwargs = {}
            if company_id:
                kwargs["company_id"] = company_id
            if fail_fast:
                kwargs["fail_fast"] = True
            if quiet:
                kwargs["quiet"] = True
            _run("Idempotency Scan", OpsCheckKind.IDEMPOTENCY, "ez360_idempotency_scan", **kwargs)

        if form.cleaned_data.get("run_template_sanity"):
            ran_any = True
            kwargs = {}
            if fail_fast:
                kwargs["fail_fast"] = True
            if quiet:
                kwargs["quiet"] = True
            _run("Template Sanity", OpsCheckKind.TEMPLATE_SANITY, "ez360_template_sanity_check", **kwargs)

        if form.cleaned_data.get("run_url_sanity"):
            ran_any = True
            kwargs = {}
            if fail_fast:
                kwargs["fail_fast"] = True
            if quiet:
                kwargs["quiet"] = True
            _run("URL Sanity", OpsCheckKind.URL_SANITY, "ez360_url_sanity_check", **kwargs)

        if form.cleaned_data.get("run_readiness"):
            ran_any = True
            _run("Readiness Check", OpsCheckKind.READINESS, "ez360_readiness_check")
        if not ran_any:
            messages.info(request, "Select at least one check to run.")

        recent_runs = OpsCheckRun.objects.select_related("company").all()[:25]

    return render(
        request,
        "ops/checks.html",
        {
            "form": form,
            "output": output,
            "recent_runs": recent_runs,
        },
    )

@login_required
@user_passes_test(_is_staff)
def ops_check_run_download(request: HttpRequest, run_id: int) -> HttpResponse:
    """Download an OpsCheckRun output as a text file (staff-only)."""
    run = get_object_or_404(OpsCheckRun.objects.select_related("company"), pk=run_id)

    company_label = run.company.name if run.company_id else "GLOBAL"
    filename = f"ez360pm_ops_check_{run.kind}_{company_label}_{run.created_at:%Y%m%d_%H%M%S}.txt"
    filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)[:180]

    header = [
        f"kind: {run.kind}",
        f"company: {company_label}",
        f"created_at: {run.created_at.isoformat()}",
        f"created_by: {run.created_by_email}",
        f"ok: {run.is_ok}",
        f"duration_ms: {run.duration_ms}",
        f"args: {run.args}",
        "",
        "----- OUTPUT -----",
        "",
    ]
    body = "\n".join(header) + (run.output_text or "")

    resp = HttpResponse(body, content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


@login_required
@user_passes_test(_is_staff)
def ops_check_runs_export(request: HttpRequest) -> HttpResponse:
    """Export recent OpsCheckRun evidence as a ZIP (staff-only).

    Contains:
      - runs.csv (summary)
      - outputs/<run_id>_<kind>_<company>.txt
    """

    try:
        days = int(request.GET.get("days", "7"))
    except Exception:
        days = 7
    days = max(1, min(days, 90))

    try:
        limit = int(request.GET.get("limit", "200"))
    except Exception:
        limit = 200
    limit = max(1, min(limit, 1000))

    since = timezone.now() - timedelta(days=days)
    qs = OpsCheckRun.objects.select_related("company").filter(created_at__gte=since).order_by("-created_at")
    runs = list(qs[:limit])

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        # CSV summary
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow([
            "id",
            "created_at",
            "kind",
            "company_id",
            "company_name",
            "is_ok",
            "duration_ms",
            "created_by_email",
            "args",
        ])
        for r in runs:
            writer.writerow([
                r.id,
                r.created_at.isoformat(),
                r.kind,
                str(r.company_id or ""),
                (r.company.name if r.company_id else ""),
                "1" if r.is_ok else "0",
                r.duration_ms,
                r.created_by_email or "",
                r.args or "",
            ])
        z.writestr("runs.csv", csv_buf.getvalue())

        # Individual outputs
        for r in runs:
            company_label = r.company.name if r.company_id else "GLOBAL"
            safe_company = re.sub(r"[^A-Za-z0-9_.-]+", "_", company_label)[:60] or "GLOBAL"
            safe_kind = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(r.kind))[:40]
            path = f"outputs/{r.id}_{safe_kind}_{safe_company}.txt"

            header = [
                f"kind: {r.kind}",
                f"company: {company_label}",
                f"created_at: {r.created_at.isoformat()}",
                f"created_by: {r.created_by_email}",
                f"ok: {r.is_ok}",
                f"duration_ms: {r.duration_ms}",
                f"args: {r.args}",
                "",
                "----- OUTPUT -----",
                "",
            ]
            body = "\n".join(header) + (r.output_text or "")
            z.writestr(path, body)

    mem.seek(0)
    filename = f"ez360pm_ops_runs_{days}d_{timezone.now():%Y%m%d_%H%M%S}.zip"
    resp = HttpResponse(mem.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp





@login_required
@user_passes_test(_is_staff)
def ops_probes(request: HttpRequest) -> HttpResponse:
    """Staff-only probes to validate monitoring/alerting in each environment."""

    recent = OpsProbeEvent.objects.all()[:25]
    context = {
        "recent": recent,
        "sentry_enabled": _sentry_enabled(),
    }
    return render(request, "ops/probes.html", context)


@login_required
@user_passes_test(_is_staff)
def ops_probe_test_error(request: HttpRequest) -> HttpResponse:
    """Intentionally raise an exception so Sentry/500 handling can be verified."""

    try:
        OpsProbeEvent.objects.create(
            kind=OpsProbeKind.SENTRY_TEST_ERROR,
            status=OpsProbeStatus.TRIGGERED,
            initiated_by_email=(getattr(request.user, "email", "") or "")[:254],
            details={
                "sentry_enabled": _sentry_enabled(),
                "path": request.path,
            },
        )
    except Exception:
        pass

    # This should be caught by Sentry middleware if enabled, and should render a 500.
    raise RuntimeError("EZ360PM Ops probe: intentional test error (safe to ignore).")


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_probe_test_alert(request: HttpRequest) -> HttpResponse:
    """Create a visible Ops alert so staff can verify alert routing."""

    title = "Ops probe: test alert"
    msg = "Staff-triggered probe alert. Safe to resolve."

    try:
        create_ops_alert(
            title=title,
            message=msg,
            level=OpsAlertLevel.INFO,
            source=OpsAlertSource.PROBE,
            company=None,
        )
    except Exception:
        pass

    try:
        OpsProbeEvent.objects.create(
            kind=OpsProbeKind.ALERT_TEST,
            status=OpsProbeStatus.COMPLETED,
            initiated_by_email=(getattr(request.user, "email", "") or "")[:254],
            details={"created_alert": True},
        )
    except Exception:
        pass

    messages.success(request, "Probe alert created. Check Ops → Alerts.")
    return redirect("ops:probes")


@login_required
@user_passes_test(_is_staff)
def ops_alerts(request: HttpRequest) -> HttpResponse:
    """Ops alerts (staff-only).

    Phase 7H35:
      - Paginates alerts to avoid huge pages.
      - Adds lightweight bulk-resolve workflow for noisy sources.
    """
    status = (request.GET.get("status") or "open").strip().lower()
    source = (request.GET.get("source") or "").strip()
    level = (request.GET.get("level") or "").strip()
    q = (request.GET.get("q") or "").strip()
    company_id = (request.GET.get("company_id") or "").strip()

    base_qs = OpsAlertEvent.objects.all().select_related("company").order_by("-created_at")

    if status == "open":
        base_qs = base_qs.filter(is_resolved=False)
    elif status == "resolved":
        base_qs = base_qs.filter(is_resolved=True)

    if source:
        base_qs = base_qs.filter(source=source)
    if level:
        base_qs = base_qs.filter(level=level)
    if company_id:
        try:
            base_qs = base_qs.filter(company_id=company_id)
        except Exception:
            pass

    if q:
        base_qs = base_qs.filter(
            Q(title__icontains=q)
            | Q(message__icontains=q)
            | Q(company__name__icontains=q)
        )

    # Bulk resolve (POST)
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action == "bulk_resolve":
            resolved_count = 0
            now = timezone.now()
            actor_email = (getattr(request.user, "email", "") or "")[:254]

            # Resolve filtered results (capped) OR selected IDs.
            resolve_filtered = request.POST.get("resolve_filtered") == "1"
            if resolve_filtered:
                target_qs = base_qs.filter(is_resolved=False)
                ids = list(target_qs.values_list("id", flat=True)[:500])
            else:
                ids = []
                for raw in request.POST.getlist("alert_ids"):
                    try:
                        ids.append(int(raw))
                    except Exception:
                        continue
                ids = ids[:500]

            if ids:
                resolved_count = OpsAlertEvent.objects.filter(id__in=ids, is_resolved=False).update(
                    is_resolved=True,
                    resolved_at=now,
                    resolved_by_email=actor_email,
                )

            if resolved_count:
                messages.success(request, f"Resolved {resolved_count} alert(s).")
            else:
                messages.info(request, "No alerts were resolved.")

        # redirect back to the list with the same GET filters
        qs = request.GET.urlencode()
        return redirect(f"{reverse('ops:alerts')}{('?' + qs) if qs else ''}")

    # Pagination (GET)
    paginator = Paginator(base_qs, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    # Summary cards should reflect open totals (not filtered).
    summary = {
        "open_total": OpsAlertEvent.objects.filter(is_resolved=False).count(),
        "open_webhooks": OpsAlertEvent.objects.filter(is_resolved=False, source=OpsAlertSource.STRIPE_WEBHOOK).count(),
        "open_email": OpsAlertEvent.objects.filter(is_resolved=False, source=OpsAlertSource.EMAIL).count(),
        "open_slow": OpsAlertEvent.objects.filter(is_resolved=False, source=OpsAlertSource.SLOW_REQUEST).count(),
    }

    # Preserve filters in pagination links (drop "page" from current query).
    qs_no_page = request.GET.copy()
    qs_no_page.pop("page", None)
    qs_no_page_str = qs_no_page.urlencode()

    return render(
        request,
        "ops/alerts.html",
        {
            "items": list(page_obj.object_list),
            "page_obj": page_obj,
            "paginator": paginator,
            "qs_no_page": qs_no_page_str,
            "status": status,
            "source": source,
            "level": level,
            "q": q,
            "company_id": company_id,
            "summary": summary,
            "sources": OpsAlertSource.choices,
            "levels": OpsAlertLevel.choices,
            "companies": list(Company.objects.order_by("name")[:200]),
        },
    )
@login_required
@user_passes_test(_is_staff)
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

@login_required
@user_passes_test(_is_staff)
@require_POST


@staff_only
def ops_alert_detail(request: HttpRequest, alert_id: int) -> HttpResponse:
    alert = get_object_or_404(OpsAlertEvent, id=alert_id)
    # Active snooze info (for UI).
    snooze_until = None
    try:
        from .models import OpsAlertSnooze

        now = timezone.now()
        qs = OpsAlertSnooze.objects.filter(source=alert.source, snoozed_until__gt=now)
        if alert.company_id:
            qs = qs.filter(Q(company__isnull=True) | Q(company=alert.company))
        else:
            qs = qs.filter(company__isnull=True)
        snooze = qs.order_by("-snoozed_until").first()
        snooze_until = snooze.snoozed_until if snooze else None
    except Exception:
        snooze_until = None
    details = alert.details or {}
    # Best-effort request-id extraction for correlation (common keys seen in logs).
    request_id = (
        details.get("request_id")
        or details.get("requestID")
        or details.get("rid")
        or details.get("requestId")
        or details.get("x_request_id")
        or ""
    )
    request_id = str(request_id).strip()[:128]
    return render(
        request,
        "ops/alert_detail.html",
        {"alert": alert, "request_id": request_id, "snooze_until": snooze_until},
    )


@staff_only
@require_POST
def ops_alert_snooze(request: HttpRequest) -> HttpResponse:
    """Snooze a source (optionally company-scoped) for a short window."""
    from datetime import timedelta

    src = (request.POST.get("source") or "").strip()
    minutes_raw = (request.POST.get("minutes") or "").strip()
    company_id_raw = (request.POST.get("company_id") or "").strip()

    try:
        minutes = int(minutes_raw or 60)
    except Exception:
        minutes = 60
    minutes = max(5, min(minutes, 7 * 24 * 60))

    if src not in dict(OpsAlertSource.choices):
        messages.error(request, "Invalid alert source.")
        return redirect("ops:alerts")

    company = None
    if company_id_raw:
        try:
            company = Company.objects.filter(id=company_id_raw).first()
        except Exception:
            company = None

    until = timezone.now() + timedelta(minutes=minutes)
    try:
        from .models import OpsAlertSnooze

        OpsAlertSnooze.objects.update_or_create(
            source=src,
            company=company,
            defaults={
                "snoozed_until": until,
                "created_by_email": (getattr(getattr(request, "user", None), "email", "") or "")[:254],
                "reason": (request.POST.get("reason") or "").strip()[:200],
            },
        )
        scope = f"{company.name}" if company else "platform"
        messages.success(request, f"Snoozed {dict(OpsAlertSource.choices).get(src, src)} alerts for {scope} until {until:%Y-%m-%d %H:%M}.")
    except Exception:
        messages.error(request, "Could not snooze alerts.")

    back = (request.POST.get("next") or "").strip()
    if back:
        return redirect(back)
    return redirect("ops:alerts")


@staff_only
def ops_alert_details_json(request: HttpRequest, alert_id: int) -> HttpResponse:
    """Download alert details JSON as a file."""
    alert = get_object_or_404(OpsAlertEvent, id=alert_id)
    data = {
        "id": alert.id,
        "created_at": alert.created_at.isoformat(),
        "level": alert.level,
        "source": alert.source,
        "company_id": str(alert.company_id) if alert.company_id else None,
        "title": alert.title,
        "message": alert.message,
        "details": alert.details or {},
        "is_resolved": bool(alert.is_resolved),
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "resolved_by_email": alert.resolved_by_email or "",
    }
    resp = JsonResponse(data, json_dumps_params={"indent": 2, "sort_keys": True})
    resp["Content-Disposition"] = f'attachment; filename="ops_alert_{alert.id}_details.json"'
    return resp


@staff_only
def ops_alert_send_test(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return redirect("ops:dashboard")

    level = (request.POST.get("level") or OpsAlertLevel.WARN).strip() or OpsAlertLevel.WARN
    message = (request.POST.get("message") or "Test alert").strip()

    create_ops_alert(
        title="Test alert (manual)",
        message=message,
        level=level if level in dict(OpsAlertLevel.choices) else OpsAlertLevel.WARN,
        source=OpsAlertSource.OPS_DASHBOARD,
        company=None,
        details={"kind": "test"},
    )

    messages.success(request, "Test alert created. If routing is enabled, it should deliver to your configured webhook/email.")
    return redirect("ops:dashboard")

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
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

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
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

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
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

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
            "seats_limit": seats_limit_for(subscription) if subscription else 1,
            "support": get_support_mode(request),
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

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
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

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
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

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
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

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
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

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
        "backup_s3_bucket": str(getattr(settings, "BACKUP_S3_BUCKET", "")),
        "backup_s3_prefix": str(getattr(settings, "BACKUP_S3_PREFIX", "")),
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
def ops_alert_routing(request: HttpRequest) -> HttpResponse:
    """Configure where Ops alerts route (email/webhook)."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Alert routing updated.")
            return redirect("ops:alert_routing")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/alert_routing.html", {"form": form, "config": config})

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
@require_POST
def ops_backup_run_now(request: HttpRequest) -> HttpResponse:
    """Run a DB backup now (staff-only).

    This executes the management command synchronously. It is intended for
    small environments and occasional manual use.
    """

    notes = (request.POST.get("notes") or "").strip()
    storage = (request.POST.get("storage") or getattr(settings, "BACKUP_STORAGE", "host_managed") or "host_managed").strip()

    try:
        call_command("ez360_backup_db", gzip=True, notes=notes, storage=storage)
        messages.success(request, "Backup started and completed. See the latest Backup Runs below.")
    except Exception as e:
        messages.error(request, f"Backup failed: {str(e)[:200]}")
    return redirect("ops:backups")


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_backup_prune(request: HttpRequest) -> HttpResponse:
    storage = (request.POST.get("storage") or getattr(settings, "BACKUP_STORAGE", "host_managed") or "host_managed").strip()
    try:
        call_command("ez360_prune_backups", storage=storage)
        messages.success(request, "Backup prune executed.")
    except Exception as e:
        messages.error(request, f"Prune failed: {str(e)[:200]}")
    return redirect("ops:backups")


@login_required
@user_passes_test(_is_staff)
def ops_releases(request: HttpRequest) -> HttpResponse:
    """Staff release notes + current build metadata."""

    q = (request.GET.get("q") or "").strip()
    company_id = (request.GET.get("company_id") or "").strip()
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
            "company_id": company_id,
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
