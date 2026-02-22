from __future__ import annotations

import os
import re
import io
import csv
import zipfile
from datetime import timedelta, datetime
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.forms import modelformset_factory
from django.db import models
from django.db.models import Count, Q, Sum
from django.db.models import Max
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.core.management import call_command
from django.core.paginator import Paginator
from django.core.mail import EmailMultiAlternatives
from django.core.mail import get_connection

from core.email_utils import format_email_subject

from audit.services import log_event
from billing.models import (
    BillingWebhookEvent,
    CompanySubscription,
    PlanCode,
    SubscriptionStatus,
    PlanCatalog,
    SeatAddonConfig,
)
from billing.services import seats_limit_for
from companies.models import Company, EmployeeProfile
from accounts.models import AccountLockout
from companies.services import set_active_company_id
from companies.services import get_active_company
from core.support_mode import get_support_mode, set_support_mode
from core.support_mode import clear_support_mode
from billing.stripe_service import fetch_and_sync_subscription_from_stripe
from core.launch_checks import run_launch_checks
from core.retention import get_retention_days, run_prune_jobs

from .forms import (
    ReleaseNoteForm,
    OpsChecksForm,
    OpsEmailTestForm,
    OpsAlertRoutingForm,
    QAIssueForm,
    PlanCatalogForm,
    SeatAddonConfigForm,
)

from .services_alerts import create_ops_alert
from .permissions import require_ops_role
from .models import OpsRole, OutboundEmailLog, OutboundEmailStatus



def _confirm_matches(value: str, expected: str) -> bool:
    try:
        return (value or "").strip().lower() == (expected or "").strip().lower()
    except Exception:
        return False


def _require_typed_confirm(request: HttpRequest, *, expected: str, label: str = "") -> bool:
    """Return True if confirmation passes; otherwise flashes a message and returns False."""
    provided = (request.POST.get("confirm") or "").strip()
    if not provided:
        messages.error(request, f"Confirmation required{(': ' + label) if label else ''}.")
        return False
    if not _confirm_matches(provided, expected):
        messages.error(request, f"Confirmation did not match. Type: {expected}")
        return False
    return True


def _require_ops_2fa_if_configured(request: HttpRequest, *, label: str = "") -> bool:
    """Enforce 2FA for critical ops actions when enabled in SiteConfig.

    This is an operator safety control. We keep it best-effort and non-destructive:
    if enforcement is enabled and the session is not 2FA-verified, we block the action.
    """
    try:
        cfg = SiteConfig.get_solo()
        if not getattr(cfg, "ops_require_2fa_for_critical_actions", False):
            return True

        from accounts.services_2fa import is_session_2fa_verified

        if is_session_2fa_verified(request):
            return True

        messages.error(
            request,
            f"2FA is required for this action{(': ' + label) if label else ''}. Please verify 2FA and try again.",
        )
        return False
    except Exception:
        # Never block ops if config lookup fails.
        return True


def _client_ip(request: HttpRequest) -> str:
    # X-Forwarded-For may contain multiple IPs; take the first.
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return xff or (request.META.get("REMOTE_ADDR") or "")


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
    QAIssue,
    QAIssueStatus,
    PlatformRevenueSnapshot,
    CompanyLifecycleEvent,
    LifecycleEventType,
)


def _money_to_decimal(value, default="0"):
    """Best-effort conversion for numeric values that may be None."""
    from decimal import Decimal

    if value is None:
        return Decimal(str(default))
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(str(default))


def _subscription_monthly_equivalent(sub: CompanySubscription | None) -> tuple[object, object]:
    """Return (mrr, arr) as Decimal for a CompanySubscription.

    Rules (v1):
    - Comped subscriptions contribute 0 revenue.
    - Trialing contributes 0 revenue.
    - ACTIVE and PAST_DUE contribute revenue based on PlanCatalog + SeatAddonConfig.
    - Annual plans are normalized to monthly by /12 for MRR, and ARR is the annualized value.
    - Discounts apply to the combined base + seat add-on total.
    """
    from decimal import Decimal

    if not sub:
        return Decimal("0"), Decimal("0")

    if sub.is_comped_active():
        return Decimal("0"), Decimal("0")

    if sub.status == SubscriptionStatus.TRIALING:
        return Decimal("0"), Decimal("0")

    if sub.status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE}:
        return Decimal("0"), Decimal("0")

    plan = PlanCatalog.objects.filter(code=sub.plan).first()
    seat_cfg = SeatAddonConfig.objects.filter(pk=1).first()

    if not plan:
        return Decimal("0"), Decimal("0")

    base_monthly = _money_to_decimal(plan.monthly_price)
    base_annual = _money_to_decimal(plan.annual_price)

    seat_monthly = _money_to_decimal(getattr(seat_cfg, "monthly_price", None), default="0")
    seat_annual = _money_to_decimal(getattr(seat_cfg, "annual_price", None), default="0")

    extra_seats = int(sub.extra_seats or 0)

    if sub.billing_interval == "year":
        total_annual = base_annual + (seat_annual * extra_seats)
        mrr = (total_annual / Decimal("12"))
        arr = total_annual
    else:
        total_monthly = base_monthly + (seat_monthly * extra_seats)
        mrr = total_monthly
        arr = (total_monthly * Decimal("12"))

    pct = int(sub.discount_percent or 0)
    if pct > 0 and sub.discount_is_active():
        discount_mult = (Decimal("100") - Decimal(str(pct))) / Decimal("100")
        mrr = (mrr * discount_mult)
        arr = (arr * discount_mult)

    # Round to cents for display stability.
    mrr = mrr.quantize(Decimal("0.01"))
    arr = arr.quantize(Decimal("0.01"))
    return mrr, arr


def _go_live_runbook_snapshot() -> dict:
    """Collect a lightweight go-live snapshot for exports.

    This intentionally avoids calling external services. It focuses on:
    - Launch Gate checklist state
    - Pending migrations (common drift failure)
    - Core environment identifiers
    """
    from django.db import connections
    from django.db.migrations.executor import MigrationExecutor

    items = list(LaunchGateItem.objects.all())
    total = len(items)
    complete = sum(1 for i in items if i.is_complete)
    remaining = max(0, total - complete)

    # Pending migrations
    conn = connections["default"]
    pending: list[tuple[str, str]] = []
    pending_error = ""
    try:
        executor = MigrationExecutor(conn)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        pending = [(m.app_label, m.name) for (m, backwards) in plan if not backwards]
    except Exception as exc:  # pragma: no cover
        pending_error = str(exc)

    return {
        "items": items,
        "summary": {"total": total, "complete": complete, "remaining": remaining},
        "pending_migrations": pending,
        "pending_migrations_error": pending_error,
        "environment": os.environ.get("ENVIRONMENT", os.environ.get("DJANGO_ENV", "")),
        "version": os.environ.get("GIT_SHA") or os.environ.get("RENDER_GIT_COMMIT") or "",
        "debug": settings.DEBUG,
    }


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
    if not require_ops_role(request, OpsRole.VIEWER):
        return redirect('core:dashboard')
    tab = (request.GET.get("tab") or "actions").strip()

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
        site_base_url = (getattr(settings, "SITE_BASE_URL", "") or "").strip()
        if not site_base_url:
            scheduler_warnings.append("SITE_BASE_URL is not set. Scheduled emails will omit deep links.")

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

        # Domain readiness: SITE_BASE_URL should align with ALLOWED_HOSTS + CSRF_TRUSTED_ORIGINS
        if site_base_url:
            try:
                parsed = urlparse(site_base_url)
                host = (parsed.hostname or "").strip()
                scheme = (parsed.scheme or "").strip()

                if not host:
                    scheduler_warnings.append("SITE_BASE_URL is set but could not parse a hostname.")
                else:
                    allowed_hosts = set(getattr(settings, "ALLOWED_HOSTS", []) or [])
                    if host not in allowed_hosts and f".{host}" not in allowed_hosts:
                        scheduler_warnings.append("SITE_BASE_URL host is not present in ALLOWED_HOSTS.")

                    csrf = set(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
                    expected_origin = f"{scheme or 'https'}://{host}"
                    if expected_origin not in csrf:
                        scheduler_warnings.append("SITE_BASE_URL origin is not present in CSRF_TRUSTED_ORIGINS.")
            except Exception:
                scheduler_warnings.append("SITE_BASE_URL parsing failed. Verify it is a full URL like https://ez360pm.com")

    # Executive metrics (best-effort, DB-backed only)
    subs_qs = CompanySubscription.objects.select_related("company").all()
    mrr_total = 0
    arr_total = 0
    for s in subs_qs:
        mrr, arr = _subscription_monthly_equivalent(s)
        mrr_total += float(mrr)
        arr_total += float(arr)

    metrics = {
        "companies_total": Company.objects.count(),
        "companies_with_subscription": CompanySubscription.objects.count(),
        "active_subscriptions": CompanySubscription.objects.filter(
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE]
        ).count(),
        "active_paid": CompanySubscription.objects.filter(status=SubscriptionStatus.ACTIVE).count(),
        "trialing": CompanySubscription.objects.filter(status=SubscriptionStatus.TRIALING).count(),
        "past_due": CompanySubscription.objects.filter(status=SubscriptionStatus.PAST_DUE).count(),
        "mrr_total": round(mrr_total, 2),
        "arr_total": round(arr_total, 2),
        "open_alerts": OpsAlertEvent.objects.filter(is_resolved=False).count(),
        "open_qa_issues": QAIssue.objects.filter(status__in=[QAIssueStatus.OPEN, QAIssueStatus.IN_PROGRESS]).count(),
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


@login_required
@user_passes_test(_is_staff)
def ops_reports(request: HttpRequest) -> HttpResponse:
    if not require_ops_role(request, OpsRole.VIEWER):
        return redirect('core:dashboard')
    """Operational reporting for the EZ360PM SaaS.

    This is an operator-facing dashboard focused on high-signal, actionable metrics
    (billing health, churn, trials, and webhook processing).
    """
    now = timezone.now()
    start_30 = now - timedelta(days=30)
    start_7 = now - timedelta(days=risk_trial_days)
    start_1 = now - timedelta(days=1)

    subs_qs = CompanySubscription.objects.select_related("company")

    cfg = SiteConfig.get_solo()
    stale_hours = int(getattr(cfg, "stripe_mirror_stale_after_hours", 48) or 48)
    stale_cutoff = now - timedelta(hours=max(1, stale_hours))
    stale_level = getattr(cfg, "stripe_mirror_stale_alert_level", "warn") or "warn"

    stale_subs = subs_qs.filter(status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE]).filter(
        Q(last_stripe_event_at__lt=stale_cutoff) | Q(last_stripe_event_at__isnull=True)
    )
    stale_sub_count = stale_subs.count()
    stale_sub_sample = list(stale_subs.order_by("last_stripe_event_at").values("company_id", "company__name", "status", "last_stripe_event_at")[:10])

    # Lifecycle events (authoritative as we log them consistently).
    churn_30 = CompanyLifecycleEvent.objects.filter(event_type=LifecycleEventType.SUBSCRIPTION_CANCELED, occurred_at__gte=start_30).count()
    conversions_30 = CompanyLifecycleEvent.objects.filter(event_type=LifecycleEventType.TRIAL_CONVERTED, occurred_at__gte=start_30).count()
    trials_active_30 = CompanyLifecycleEvent.objects.filter(event_type=LifecycleEventType.TRIAL_STARTED, occurred_at__gte=start_30).count()
    reactivations_30 = CompanyLifecycleEvent.objects.filter(event_type=LifecycleEventType.SUBSCRIPTION_REACTIVATED, occurred_at__gte=start_30).count()
    starts_30 = CompanyLifecycleEvent.objects.filter(event_type=LifecycleEventType.SUBSCRIPTION_STARTED, occurred_at__gte=start_30).count()
    lifecycle_recent = list(
        CompanyLifecycleEvent.objects.select_related("company")
        .order_by("-occurred_at")[:25]
    )

    # Stripe webhook processing health (system reliability)
    wh_total_24h = BillingWebhookEvent.objects.filter(received_at__gte=start_1).count()
    wh_failed_24h = BillingWebhookEvent.objects.filter(received_at__gte=start_1, ok=False).count()

    last_wh = BillingWebhookEvent.objects.order_by('-received_at').first()
    last_wh_received_at = last_wh.received_at if last_wh else None
    last_wh_ok = bool(last_wh.ok) if last_wh else None

    wh_total_7d = BillingWebhookEvent.objects.filter(received_at__gte=start_7).count()
    wh_failed_7d = BillingWebhookEvent.objects.filter(received_at__gte=start_7, ok=False).count()

    # Payment failure signals (business health) from Stripe event types
    payment_fail_types = [
        "invoice.payment_failed",
        "payment_intent.payment_failed",
        "charge.failed",
    ]
    payment_failed_7d = BillingWebhookEvent.objects.filter(
        received_at__gte=start_7,
        event_type__in=payment_fail_types,
    ).count()

    payment_failed_30d = BillingWebhookEvent.objects.filter(
        received_at__gte=start_30,
        event_type__in=payment_fail_types,
    ).count()

    # Revenue intelligence is sourced from daily PlatformRevenueSnapshot (Stripe-authoritative mirror).
    latest_snapshot = PlatformRevenueSnapshot.objects.order_by('-date').first()
    recent_snapshots = list(PlatformRevenueSnapshot.objects.order_by('-date')[:30])
    recent_snapshots.reverse()

    recent_snapshots_display = [
        {
            'date': s.date,
            'mrr': (s.mrr_cents / 100.0),
            'arr': (s.arr_cents / 100.0),
            'at_risk': (s.revenue_at_risk_cents / 100.0),
        }
        for s in recent_snapshots
    ]

    total_mrr = (latest_snapshot.mrr_cents / 100.0) if latest_snapshot else 0.0
    total_arr = (latest_snapshot.arr_cents / 100.0) if latest_snapshot else 0.0
    paid_count = (latest_snapshot.active_subscriptions if latest_snapshot else 0)
    conversion_rate_30 = (conversions_30 / trials_active_30) if trials_active_30 else 0.0
    churn_rate_30 = (churn_30 / paid_count) if paid_count else 0.0
    net_growth_30 = int(starts_30 + reactivations_30 - churn_30)
    revenue_at_risk = (latest_snapshot.revenue_at_risk_cents / 100.0) if latest_snapshot else 0.0

    # Alerts: unresolved counts by source over 7d
    alerts_7d = (
        OpsAlertEvent.objects.filter(created_at__gte=start_7, is_resolved=False)
        .values("source")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    ctx = {
        "now": now,
        "churn_30": churn_30,
        "conversions_30": conversions_30,
        "trials_started_30": trials_active_30,
        "reactivations_30": reactivations_30,
        "starts_30": starts_30,
        "conversion_rate_30": conversion_rate_30,
        "churn_rate_30": churn_rate_30,
        "net_growth_30": net_growth_30,
        "wh_total_24h": wh_total_24h,
        "wh_failed_24h": wh_failed_24h,
        "wh_total_7d": wh_total_7d,
        "wh_failed_7d": wh_failed_7d,
        "payment_failed_7d": payment_failed_7d,
        "payment_failed_30d": payment_failed_30d,
        "total_mrr": total_mrr,
        "total_arr": total_arr,
        "revenue_at_risk": revenue_at_risk,
        "latest_snapshot": latest_snapshot,
        "recent_snapshots": recent_snapshots,
        "recent_snapshots_display": recent_snapshots_display,
        "paid_count": paid_count,
        "alerts_7d": alerts_7d,

        "lifecycle_recent": lifecycle_recent,

        "stripe_mirror_stale_after_hours": stale_hours,
        "stripe_mirror_stale_alert_level": stale_level,
        "stripe_mirror_stale_cutoff": stale_cutoff,
        "stripe_mirror_stale_sub_count": stale_sub_count,
        "stripe_mirror_stale_sub_sample": stale_sub_sample,
        "last_wh_received_at": last_wh_received_at,
        "last_wh_ok": last_wh_ok,

        "sentry_enabled": bool(getattr(settings, "SENTRY_DSN", "") or ""),
        "sentry_dashboard_url": getattr(settings, "SENTRY_DASHBOARD_URL", "") or "",

    }
    return render(request, "ops/reports.html", ctx)


def ops_webhook_health(request: HttpRequest) -> HttpResponse:
    if not require_ops_role(request, OpsRole.VIEWER):
        return redirect('core:dashboard')
    """Stripe webhook health & mirror drift dashboard (operator-facing)."""
    now = timezone.now()
    cfg = SiteConfig.get_solo()
    stale_hours = int(getattr(cfg, "stripe_mirror_stale_after_hours", 48) or 48)
    stale_cutoff = now - timedelta(hours=max(1, stale_hours))

    start_24h = now - timedelta(days=1)
    start_7d = now - timedelta(days=risk_trial_days)

    wh_qs = BillingWebhookEvent.objects.all()
    wh_total_24h = wh_qs.filter(received_at__gte=start_24h).count()
    wh_failed_24h = wh_qs.filter(received_at__gte=start_24h, ok=False).count()
    wh_total_7d = wh_qs.filter(received_at__gte=start_7d).count()
    wh_failed_7d = wh_qs.filter(received_at__gte=start_7d, ok=False).count()

    last_wh = wh_qs.order_by("-received_at").first()

    # Top event types (7d)
    top_types_7d = (
        wh_qs.filter(received_at__gte=start_7d)
        .values("event_type")
        .annotate(count=Count("id"))
        .order_by("-count")[:15]
    )

    recent_failures = list(wh_qs.filter(ok=False).order_by("-received_at")[:50])

    subs_qs = CompanySubscription.objects.select_related("company")
    stale_subs = subs_qs.filter(status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE]).filter(
        Q(last_stripe_event_at__lt=stale_cutoff) | Q(last_stripe_event_at__isnull=True)
    )
    stale_sub_count = stale_subs.count()
    stale_sub_sample = list(
        stale_subs.order_by("last_stripe_event_at").values(
            "company_id", "company__name", "status", "last_stripe_event_at", "stripe_subscription_id", "stripe_customer_id"
        )[:20]
    )

    ctx = {
        "now": now,
        "stale_hours": stale_hours,
        "stale_cutoff": stale_cutoff,
        "wh_total_24h": wh_total_24h,
        "wh_failed_24h": wh_failed_24h,
        "wh_total_7d": wh_total_7d,
        "wh_failed_7d": wh_failed_7d,
        "last_wh": last_wh,
        "top_types_7d": top_types_7d,
        "recent_failures": recent_failures,
        "stale_sub_count": stale_sub_count,
        "stale_sub_sample": stale_sub_sample,
    }
    return render(request, "ops/webhook_health.html", ctx)


def _compute_tenant_risk(
    company: Company,
    sub: CompanySubscription | None,
    *,
    cfg: SiteConfig,
    now: datetime,
    failed_customer_ids: set[str],
    failed_subscription_ids: set[str],
) -> dict:
    # Wrapper retained for this module; implementation lives in services_risk.
    from .services_risk import compute_tenant_risk

    return compute_tenant_risk(
        company,
        sub,
        cfg=cfg,
        now=now,
        failed_customer_ids=failed_customer_ids,
        failed_subscription_ids=failed_subscription_ids,
    )


def ops_companies(request: HttpRequest) -> HttpResponse:
    if not require_ops_role(request, OpsRole.VIEWER):
        return redirect('core:dashboard')
    """Company directory for SaaS operations.

    Filters are subscription-aware (best-effort) and designed for day-to-day ops:
    - status: active|trialing|past_due|canceled|ended|all
    - comped: 1
    - q: name/email search
    """
    # Saved presets (per-operator)
    presets_qs = OpsCompanyViewPreset.objects.filter(is_active=True).filter(Q(owner=request.user) | Q(owner__isnull=True)).order_by("name")
    preset_id = (request.GET.get("preset") or "").strip()
    selected_preset = None
    params = request.GET.copy()
    if preset_id.isdigit():
        selected_preset = presets_qs.filter(id=int(preset_id)).first()
        if selected_preset:
            for k, v in (selected_preset.query_params or {}).items():
                if not params.get(k):
                    params[k] = str(v)

    # Save preset
    if request.method == "POST" and (request.POST.get("action") or "").strip().lower() == "save_preset":
        if not require_ops_role(request, OpsRole.SUPPORT):
            return redirect("ops:companies")
        name = (request.POST.get("preset_name") or "").strip()
        make_default = (request.POST.get("make_default") or "") == "1"
        if not name:
            messages.error(request, "Preset name is required.")
            return redirect(request.path)

        qp_source = params if params else request.POST
        qp = {k: qp_source.get(k) for k in {"segment", "status", "comped", "q"} if qp_source.get(k)}
        preset, _created = OpsCompanyViewPreset.objects.update_or_create(
            owner=request.user,
            name=name,
            defaults={"query_params": qp, "is_active": True},
        )
        if make_default:
            OpsCompanyViewPreset.objects.filter(owner=request.user).update(is_default=False)
            preset.is_default = True
            preset.save(update_fields=["is_default"])
        messages.success(request, f"Saved preset: {preset.name}")
        return redirect(f"{request.path}?preset={preset.id}")

    q = (params.get("q") or "").strip()
    segment = (params.get("segment") or "active").strip().lower()
    status = (params.get("status") or "").strip().lower()
    comped = (params.get("comped") or "").strip()
    export = (params.get("export") or "").strip().lower()

    companies = (
        Company.objects.all()
        .annotate(
            employee_count=Count("employees", filter=Q(employees__deleted_at__isnull=True), distinct=True),
            last_login=Max("employees__user__last_login"),
        )
        .select_related("owner")
        .order_by("name")
    )

    if q:
        companies = companies.filter(
            Q(name__icontains=q)
            | Q(owner__email__icontains=q)
            | Q(employees__user__email__icontains=q)
        ).distinct()

    subs = {s.company_id: s for s in CompanySubscription.objects.select_related("company")}

    # Risk inputs
    now = timezone.now()
    cfg = SiteConfig.get_solo()

    stale_hours = int(getattr(cfg, "stripe_mirror_stale_after_hours", 48) or 48)
    stale_cutoff = now - timedelta(hours=max(1, stale_hours))

    risk_payment_days = int(getattr(cfg, "risk_payment_failed_window_days", 14) or 14)
    risk_payment_days = max(1, min(90, risk_payment_days))
    start_fail_window = now - timedelta(days=risk_payment_days)

    risk_trial_days = int(getattr(cfg, "risk_trial_ends_within_days", 7) or 7)
    risk_trial_days = max(1, min(30, risk_trial_days))

    # Risk weights (operator-tunable, clamped)
    w_past_due = int(getattr(cfg, "risk_weight_past_due", 60) or 0)
    w_mirror_stale = int(getattr(cfg, "risk_weight_mirror_stale", 25) or 0)
    w_payment_failed = int(getattr(cfg, "risk_weight_payment_failed", 25) or 0)
    w_payment_failed_sub_only = int(getattr(cfg, "risk_weight_payment_failed_sub_only", 10) or 0)
    w_canceling = int(getattr(cfg, "risk_weight_canceling", 15) or 0)
    w_trial_ends_soon = int(getattr(cfg, "risk_weight_trial_ends_soon", 15) or 0)

    w_past_due = max(0, min(100, w_past_due))
    w_mirror_stale = max(0, min(100, w_mirror_stale))
    w_payment_failed = max(0, min(100, w_payment_failed))
    w_payment_failed_sub_only = max(0, min(100, w_payment_failed_sub_only))
    w_canceling = max(0, min(100, w_canceling))
    w_trial_ends_soon = max(0, min(100, w_trial_ends_soon))

    medium_threshold = int(getattr(cfg, "risk_level_medium_threshold", 40) or 40)
    high_threshold = int(getattr(cfg, "risk_level_high_threshold", 80) or 80)
    medium_threshold = max(0, min(100, medium_threshold))
    high_threshold = max(0, min(100, high_threshold))
    if high_threshold < medium_threshold:
        high_threshold = min(100, medium_threshold + 1)

    payment_fail_types = ["invoice.payment_failed", "payment_intent.payment_failed", "charge.failed"]
    failed_customer_ids_14d: set[str] = set()
    failed_sub_ids_14d: set[str] = set()
    for e in BillingWebhookEvent.objects.filter(received_at__gte=start_fail_window, event_type__in=payment_fail_types).only("payload_json", "event_type"):
        try:
            obj = (e.payload_json or {}).get("data", {}).get("object", {}) or {}
            cust = obj.get("customer") or obj.get("customer_id") or ""
            subid = obj.get("subscription") or obj.get("subscription_id") or ""
            if isinstance(cust, str) and cust:
                failed_customer_ids_14d.add(cust)
            if isinstance(subid, str) and subid:
                failed_sub_ids_14d.add(subid)
        except Exception:
            continue


    # Segment presets (exec-ops friendly)
    # Segment sets defaults but still allows manual override via status/comped controls.
    if not status:
        status = "active" if segment == "active" else segment

    if segment == "suspended":
        companies = companies.filter(is_suspended=True)
        status = "all"
    elif segment == "comped":
        comped = "1"
        status = "all"
    elif segment == "discounted":
        status = "all"
    elif segment in {"trialing", "past_due", "canceled", "ended", "all", "active"}:
        # Handled by subscription status logic below.
        pass
    else:
        segment = "active"
        status = "active"

    rows = []
    for c in companies:
        sub = subs.get(c.id)

        # Segment-specific filters that depend on subscription
        if segment == "discounted":
            if not sub or not sub.discount_is_active() or int(sub.discount_percent or 0) <= 0:
                continue
        if status and status != "all":
            st = (getattr(sub, "status", "") or "").lower()
            if status == "active":
                if st not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE}:
                    continue
            elif status == "trialing":
                if st != SubscriptionStatus.TRIALING:
                    continue
            elif status == "past_due":
                if st != SubscriptionStatus.PAST_DUE:
                    continue
            elif status == "canceled":
                if st != SubscriptionStatus.CANCELED:
                    continue
            elif status == "ended":
                if st != SubscriptionStatus.ENDED:
                    continue

        if comped == "1":
            if not sub or not sub.is_comped_active():
                continue

        mrr, arr = _subscription_monthly_equivalent(sub)
        seats_limit = seats_limit_for(sub) if sub else 1

        # Tenant risk scoring (ops triage)
        risk = _compute_tenant_risk(
            c,
            sub,
            cfg=cfg,
            now=now,
            failed_customer_ids=failed_customer_ids_14d,
            failed_subscription_ids=failed_sub_ids_14d,
        )
        risk_score = risk["score"]
        risk_level = risk["level"]
        risk_flags = risk["flags"]
        rows.append(
            {
                "company": c,
                "subscription": sub,
                "employee_count": getattr(c, "employee_count", 0) or 0,
                "last_login": getattr(c, "last_login", None),
                "mrr": mrr,
                "arr": arr,
                "seats_limit": seats_limit,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "risk_flags": risk_flags,
            }
        )

    # Export (CSV) for ops workflows
    if export == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "company_id",
                "company_name",
                "owner_email",
                "is_suspended",
                "subscription_status",
                "plan",
                "interval",
                "extra_seats",
                "comped",
                "discount_percent",
                "mrr",
                "arr",
                "users",
                "last_login",
            ]
        )
        for r in rows:
            c = r["company"]
            sub = r["subscription"]
            writer.writerow(
                [
                    str(c.id),
                    c.name,
                    getattr(c.owner, "email", ""),
                    "1" if c.is_suspended else "0",
                    getattr(sub, "status", "") if sub else "",
                    getattr(sub, "plan", "") if sub else "",
                    getattr(sub, "billing_interval", "") if sub else "",
                    str(getattr(sub, "extra_seats", "") if sub else ""),
                    "1" if (sub and sub.is_comped_active()) else "0",
                    str(getattr(sub, "discount_percent", "") if sub else ""),
                    str(r["mrr"]),
                    str(r["arr"]),
                    str(r["employee_count"]),
                    r["last_login"].isoformat() if r["last_login"] else "",
                ]
            )

        resp = HttpResponse(output.getvalue(), content_type="text/csv")
        resp["Content-Disposition"] = "attachment; filename=ez360pm_companies.csv"
        return resp

    paginator = Paginator(rows, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)


    return render(
        request,
        "ops/companies.html",
        {
            "q": q,
            "segment": segment,
            "status": status,
            "comped": comped,
            "page_obj": page_obj,
            "support_mode": get_support_mode(request),
            "presets": presets_qs,
            "selected_preset": selected_preset,
            "preset_id": preset_id,
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_company_presets(request: HttpRequest) -> HttpResponse:
    """Manage saved company directory presets (exec ops workflow)."""
    if not require_ops_role(request, OpsRole.SUPPORT):
        return redirect("ops:dashboard")

    from .models import OpsCompanyViewPreset

    can_manage_global = require_ops_role(request, OpsRole.SUPEROPS)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        try:
            preset_id = int(request.POST.get("preset_id") or 0)
        except Exception:
            preset_id = 0

        preset = get_object_or_404(OpsCompanyViewPreset, pk=preset_id)

        # Ownership guard: users can manage their own presets; SUPEROPS can manage global presets.
        if preset.owner_id and preset.owner_id != request.user.id:
            messages.error(request, "You can only manage your own presets.")
            return redirect("ops:company_presets")
        if preset.owner_id is None and not can_manage_global:
            messages.error(request, "Only SUPEROPS can manage global presets.")
            return redirect("ops:company_presets")

        if action == "rename":
            name = (request.POST.get("name") or "").strip()
            if not name:
                messages.error(request, "Preset name is required.")
            else:
                preset.name = name[:64]
                preset.save(update_fields=["name", "updated_at"])
                messages.success(request, "Preset renamed.")

        elif action == "toggle_active":
            preset.is_active = not bool(preset.is_active)
            preset.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Preset updated.")

        elif action == "set_default":
            # Clear default on other presets for this owner scope.
            if preset.owner_id:
                OpsCompanyViewPreset.objects.filter(owner=request.user, is_default=True).exclude(pk=preset.id).update(is_default=False)
            else:
                OpsCompanyViewPreset.objects.filter(owner__isnull=True, is_default=True).exclude(pk=preset.id).update(is_default=False)
            preset.is_default = True
            preset.save(update_fields=["is_default", "updated_at"])
            messages.success(request, "Default preset set.")

        elif action == "delete":
            preset.delete()
            messages.success(request, "Preset deleted.")

        else:
            messages.error(request, "Invalid action.")

        return redirect("ops:company_presets")

    my_presets = list(OpsCompanyViewPreset.objects.filter(owner=request.user).order_by("-is_default", "name"))
    global_presets = list(OpsCompanyViewPreset.objects.filter(owner__isnull=True, is_active=True).order_by("-is_default", "name"))

    return render(
        request,
        "ops/company_presets.html",
        {
            "my_presets": my_presets,
            "global_presets": global_presets,
            "can_manage_global": can_manage_global,
        },
    )


@staff_only
def ops_settings_home(request: HttpRequest) -> HttpResponse:
    if not require_ops_role(request, OpsRole.SUPEROPS):
        return redirect('ops:dashboard')
    """Staff settings hub (keeps operational configuration out of Django admin)."""
    return render(request, "ops/settings_home.html")


@staff_only
def ops_settings_site(request: HttpRequest) -> HttpResponse:
    if not require_ops_role(request, OpsRole.SUPEROPS):
        return redirect('ops:dashboard')
    """Platform-level settings (SiteConfig), managed from Ops UI."""
    config = SiteConfig.get_solo()

    if request.method == "POST":
        form = OpsAlertRoutingForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Site settings updated.")
            return redirect("ops:settings_site")
    else:
        form = OpsAlertRoutingForm(instance=config)

    return render(request, "ops/settings_site.html", {"form": form, "config": config})


@staff_only
def ops_settings_billing(request: HttpRequest) -> HttpResponse:
    if not require_ops_role(request, OpsRole.SUPEROPS):
        return redirect('ops:dashboard')
    """Edit plan catalog + seat add-on pricing in-app (not Django admin)."""

    PlanFormSet = modelformset_factory(
        PlanCatalog,
        form=PlanCatalogForm,
        extra=0,
        can_delete=False,
    )

    seat_cfg, _ = SeatAddonConfig.objects.get_or_create(pk=1)
    plans_qs = PlanCatalog.objects.all().order_by("sort_order", "monthly_price")

    if request.method == "POST":
        plan_formset = PlanFormSet(request.POST, queryset=plans_qs, prefix="plans")
        seat_form = SeatAddonConfigForm(request.POST, instance=seat_cfg, prefix="seat")
        if plan_formset.is_valid() and seat_form.is_valid():
            plan_formset.save()
            seat_form.save()
            messages.success(request, "Billing catalog updated.")
            return redirect("ops:settings_billing")
        messages.error(request, "Please correct the errors below.")
    else:
        plan_formset = PlanFormSet(queryset=plans_qs, prefix="plans")
        seat_form = SeatAddonConfigForm(instance=seat_cfg, prefix="seat")


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


    return render(
        request,
        "ops/settings_billing.html",
        {
            "plan_formset": plan_formset,
            "seat_form": seat_form,
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
    tab = (request.GET.get("tab") or "actions").strip()

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


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


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
    tab = (request.GET.get("tab") or "actions").strip()

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
    if not require_ops_role(request, OpsRole.SUPEROPS):
        return redirect('ops:dashboard')
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
@staff_only
def ops_system_status(request: HttpRequest) -> HttpResponse:
    """Staff-only system status page: migrations + runtime info."""
    from django.db import connections
    from django.db.migrations.executor import MigrationExecutor

    db_alias = "default"
    conn = connections[db_alias]
    pending = []
    try:
        executor = MigrationExecutor(conn)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        # plan is list of (Migration, backwards)
        pending = [(m.app_label, m.name) for (m, backwards) in plan if not backwards]
    except Exception as exc:
        pending = [("error", str(exc))]

    context = {
        "pending_migrations": pending,
        "db_vendor": getattr(conn, "vendor", ""),
        "db_name": conn.settings_dict.get("NAME", ""),
        "db_host": conn.settings_dict.get("HOST", ""),
        "debug": settings.DEBUG,
        "version": os.environ.get("GIT_SHA") or os.environ.get("RENDER_GIT_COMMIT") or "",
        "environment": os.environ.get("ENVIRONMENT", os.environ.get("DJANGO_ENV", "")),
    }
    return render(request, "ops/system_status.html", context)
@login_required
@user_passes_test(_is_staff)
@staff_only
def ops_smoke_tests(request: HttpRequest) -> HttpResponse:
    """Staff-only smoke test page.

    Goal: one place to verify the environment is runnable after deploy/reset.
    This intentionally avoids hitting external services; it's a local runtime + DB sanity check.
    """
    from django.db import connections
    from django.db.migrations.executor import MigrationExecutor
    from django.db.utils import ProgrammingError

    checks = []

    # 1) Pending migrations
    db_alias = "default"
    conn = connections[db_alias]
    pending = []
    pending_error = ""
    try:
        executor = MigrationExecutor(conn)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        pending = [(mig.app_label, mig.name) for (mig, backwards) in plan if not backwards]
    except Exception as exc:  # pragma: no cover
        pending_error = str(exc)

    checks.append(
        {
            "name": "Database migrations applied",
            "ok": (not pending) and (not pending_error),
            "details": "No pending migrations."
            if (not pending and not pending_error)
            else (pending_error or f"Pending: {len(pending)}"),
            "data": pending[:50],
        }
    )

    # 2) Singleton tables exist (common post-reset failure)
    singleton_ok = True
    singleton_details = []
    try:
        # Ops SiteConfig is the most common missing-table failure surface.
        SiteConfig.get_solo()
        singleton_details.append("ops.SiteConfig OK")
    except ProgrammingError as exc:
        singleton_ok = False
        singleton_details.append(f"ops.SiteConfig missing table: {exc.__class__.__name__}")
    except Exception as exc:  # pragma: no cover
        singleton_ok = False
        singleton_details.append(f"ops.SiteConfig error: {exc}")

    checks.append(
        {
            "name": "Singleton tables present",
            "ok": singleton_ok,
            "details": "; ".join(singleton_details) if singleton_details else "",
            "data": [],
        }
    )

    # 3) Basic auth sanity (can we read the user model)
    auth_ok = True
    auth_details = ""
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        _ = User.objects.count()
        auth_details = "User model OK."
    except Exception as exc:  # pragma: no cover
        auth_ok = False
        auth_details = str(exc)

    checks.append({"name": "Auth model readable", "ok": auth_ok, "details": auth_details, "data": []})

    # 4) Active company context can resolve (session-based)
    active_company = None
    active_company_ok = True
    active_company_details = ""
    try:
        from companies.services import get_active_company

        active_company = get_active_company(request)
        if not active_company:
            active_company_details = "No active company selected (ok if new user)."
    except Exception as exc:  # pragma: no cover
        active_company_ok = False
        active_company_details = str(exc)

    checks.append(
        {
            "name": "Active company context",
            "ok": active_company_ok,
            "details": active_company_details,
            "data": [],
        }
    )


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


    return render(
        request,
        "ops/smoke_tests.html",
        {
            "checks": checks,
            "active_company": active_company,
        },
    )



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


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


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


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


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


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


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
    tab = (request.GET.get("tab") or "actions").strip()

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


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


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

    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


    return render(
        request,
        "ops/alert_detail.html",
        {"alert": alert, "request_id": request_id, "snooze_until": snooze_until},
    )


@staff_only
@require_POST
def ops_alert_snooze(request: HttpRequest) -> HttpResponse:
    """Snooze a source (optionally company-scoped) for a short window."""
    from datetime import timedelta, datetime

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
def ops_launch_gate(request: HttpRequest) -> HttpResponse:
    items = LaunchGateItem.objects.all()
    total = items.count()
    complete = items.filter(is_complete=True).count()

    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


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
def ops_go_live_runbook(request: HttpRequest) -> HttpResponse:
    """Go-live runbook view.

    This is the final staff-facing launch prep page that aggregates:
    - Launch Gate checklist
    - Pending migrations
    - Quick verification checklist (manual)
    """
    snap = _go_live_runbook_snapshot()

    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


    return render(
        request,
        "ops/go_live_runbook.html",
        {
            **snap,
            "support_mode": get_support_mode(request),
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_go_live_runbook_export_csv(request: HttpRequest) -> HttpResponse:
    import csv

    snap = _go_live_runbook_snapshot()
    items = snap["items"]

    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="ez360pm_go_live_runbook.csv"'

    w = csv.writer(resp)
    w.writerow(["generated_at", timezone.now().isoformat()])
    w.writerow(["environment", snap.get("environment", "")])
    w.writerow(["version", snap.get("version", "")])
    w.writerow(["debug", str(bool(snap.get("debug")))])
    w.writerow([])

    w.writerow(["launch_gate_total", snap["summary"]["total"]])
    w.writerow(["launch_gate_complete", snap["summary"]["complete"]])
    w.writerow(["launch_gate_remaining", snap["summary"]["remaining"]])
    w.writerow([])

    w.writerow(["pending_migrations", len(snap.get("pending_migrations") or [])])
    if snap.get("pending_migrations_error"):
        w.writerow(["pending_migrations_error", snap["pending_migrations_error"]])
    else:
        for app, name in (snap.get("pending_migrations") or [])[:500]:
            w.writerow(["pending", app, name])
    w.writerow([])

    w.writerow(["Launch Gate Items"])
    w.writerow(["key", "title", "is_complete", "completed_at", "completed_by", "notes"])
    for it in items:
        w.writerow(
            [
                it.key,
                it.title,
                "yes" if it.is_complete else "no",
                it.completed_at.isoformat() if it.completed_at else "",
                getattr(it.completed_by, "email", "") if it.completed_by else "",
                (it.notes or "")[:500],
            ]
        )

    return resp


@login_required
@user_passes_test(_is_staff)
def ops_go_live_runbook_export_pdf(request: HttpRequest) -> HttpResponse:
    """PDF export of the go-live runbook.

    Uses ReportLab (server-side) so we do not depend on WeasyPrint system deps.
    """
    from io import BytesIO

    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    snap = _go_live_runbook_snapshot()
    items = snap["items"]

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    def draw_line(y, text, *, bold=False):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if not bold else 11)
        c.drawString(0.75 * inch, y, text)

    y = height - 0.75 * inch
    c.setTitle("EZ360PM Go-Live Runbook")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(0.75 * inch, y, "EZ360PM — Go-Live Runbook")
    y -= 0.35 * inch

    draw_line(y, f"Generated: {timezone.now():%Y-%m-%d %H:%M %Z}")
    y -= 0.22 * inch
    draw_line(y, f"Environment: {snap.get('environment','') or '—'}")
    y -= 0.22 * inch
    draw_line(y, f"Version: {snap.get('version','') or '—'}")
    y -= 0.22 * inch
    draw_line(y, f"DEBUG: {'ON' if snap.get('debug') else 'OFF'}")
    y -= 0.35 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.75 * inch, y, "Launch Gate Summary")
    y -= 0.28 * inch
    draw_line(y, f"Total: {snap['summary']['total']}   Complete: {snap['summary']['complete']}   Remaining: {snap['summary']['remaining']}")
    y -= 0.30 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.75 * inch, y, "Database")
    y -= 0.28 * inch
    pending = snap.get("pending_migrations") or []
    if snap.get("pending_migrations_error"):
        draw_line(y, "Pending migrations: ERROR")
        y -= 0.22 * inch
        draw_line(y, (snap.get("pending_migrations_error") or "")[:120])
        y -= 0.28 * inch
    else:
        draw_line(y, f"Pending migrations: {len(pending)}")
        y -= 0.30 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.75 * inch, y, "Quick Verification Checklist")
    y -= 0.26 * inch
    c.setFont("Helvetica", 10)
    checklist = [
        "Health check loads (/ops/healthz/) and returns OK",
        "Pending migrations = 0 (Ops → System status)",
        "Can log in and reach Dashboard",
        "Email test passes (Ops → Email test)",
        "Stripe mode correct (test vs live) and webhooks configured",
        "Static/media serving OK",
    ]
    for line in checklist:
        c.drawString(0.85 * inch, y, f"□ {line}")
        y -= 0.20 * inch
        if y < 1.25 * inch:
            c.showPage()
            y = height - 0.75 * inch

    y -= 0.15 * inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(0.75 * inch, y, "Launch Gate Items")
    y -= 0.28 * inch
    c.setFont("Helvetica", 9)
    for it in items:
        status = "✓" if it.is_complete else "□"
        title = (it.title or "").strip()
        c.drawString(0.80 * inch, y, f"{status} {it.key} — {title}")
        y -= 0.18 * inch
        if it.description:
            desc = (it.description or "").strip().replace("\n", " ")
            c.setFont("Helvetica", 8)
            c.drawString(1.05 * inch, y, (desc[:140] + ("…" if len(desc) > 140 else "")))
            y -= 0.16 * inch
            c.setFont("Helvetica", 9)
        if y < 1.0 * inch:
            c.showPage()
            y = height - 0.75 * inch
            c.setFont("Helvetica", 9)

    c.showPage()
    c.save()
    pdf = buf.getvalue()
    buf.close()

    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="ez360pm_go_live_runbook.pdf"'
    resp.write(pdf)
    return resp


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_launch_gate_seed(request: HttpRequest) -> HttpResponse:
    """Seed default Launch Gate items (safe/no-overwrite)."""
    from .launch_gate_defaults import DEFAULT_LAUNCH_GATE_ITEMS

    existing = set(LaunchGateItem.objects.values_list("key", flat=True))
    created = 0
    for item in DEFAULT_LAUNCH_GATE_ITEMS:
        key = item["key"]
        if key in existing:
            continue
        LaunchGateItem.objects.create(
            key=key,
            title=item.get("title", ""),
            description=item.get("description", ""),
        )
        created += 1

    if created:
        messages.success(request, f"Seeded {created} launch gate items.")
    else:
        messages.info(request, "Launch gate already has items.")
    return redirect("ops:launch_gate")


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


@login_required
@user_passes_test(_is_staff)
def ops_company_detail(request: HttpRequest, company_id: int) -> HttpResponse:
    if not require_ops_role(request, OpsRole.VIEWER):
        return redirect('ops:dashboard')
    company = get_object_or_404(Company, pk=company_id)
    subscription = getattr(company, "subscription", None)

    tab = (request.GET.get("tab") or "overview").strip().lower()
    if tab not in {"overview", "billing", "users", "audit", "activity"}:
        tab = "overview"

    employees = (
        EmployeeProfile.objects.filter(company=company, deleted_at__isnull=True)
        .select_related("user")
        .order_by("role", "user__email")
    )

    last_login = (
        EmployeeProfile.objects.filter(company=company, deleted_at__isnull=True)
        .aggregate(last=Max("user__last_login"))
        .get("last")
    )

    mrr, arr = _subscription_monthly_equivalent(subscription)
    recent_webhooks = _recent_webhooks_for_company(company, limit=12)

    cfg = SiteConfig.get_solo()
    now = timezone.now()

    # Risk drill-down (uses same operator-tunable weights as Companies directory)
    payment_fail_types = ["invoice.payment_failed", "payment_intent.payment_failed", "charge.failed"]
    risk_payment_days = int(getattr(cfg, "risk_payment_failed_window_days", 14) or 14)
    risk_payment_days = max(1, min(90, risk_payment_days))
    start_fail_window = now - timedelta(days=risk_payment_days)
    failed_customer_ids: set[str] = set()
    failed_subscription_ids: set[str] = set()
    for e in BillingWebhookEvent.objects.filter(received_at__gte=start_fail_window, event_type__in=payment_fail_types).only("payload_json", "event_type"):
        try:
            obj = (e.payload_json or {}).get("data", {}).get("object", {}) or {}
            cust = obj.get("customer") or obj.get("customer_id") or ""
            subid = obj.get("subscription") or obj.get("subscription_id") or ""
            if isinstance(cust, str) and cust:
                failed_customer_ids.add(cust)
            if isinstance(subid, str) and subid:
                failed_subscription_ids.add(subid)
        except Exception:
            continue

    risk = _compute_tenant_risk(
        company,
        subscription,
        cfg=cfg,
        now=now,
        failed_customer_ids=failed_customer_ids,
        failed_subscription_ids=failed_subscription_ids,
    )

    # Risk trend (best-effort daily snapshots)
    try:
        from .models import CompanyRiskSnapshot

        risk_history = list(
            CompanyRiskSnapshot.objects.filter(company=company)
            .order_by("-date")
            .only("date", "risk_score", "risk_level")[:30]
        )
    except Exception:
        risk_history = []


    def _ops_log(action: str, *, summary: str = "", meta: dict | None = None) -> None:
        try:
            from .models import OpsActionLog

            OpsActionLog.objects.create(
                actor=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
                actor_email=getattr(request.user, "email", "") if getattr(request, "user", None) else "",
                company=company,
                action=action,
                summary=(summary or "")[:240],
                meta=meta or {},
                ip_address=_client_ip(request),
                user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
            )
        except Exception:
            pass

    # Support mode + company controls
    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()

        # Ops role enforcement (separation of duties)
        if action in {"enter_support", "exit_support"}:
            if not require_ops_role(request, OpsRole.SUPPORT):
                return redirect('ops:company_detail', company_id=company.id)
        if action in {"disable_user", "enable_user", "force_logout"}:
            if not require_ops_role(request, OpsRole.SUPPORT):
                return redirect('ops:company_detail', company_id=company.id)
        if action in {"suspend_company", "reactivate_company"}:
            if not require_ops_role(request, OpsRole.SUPEROPS):
                return redirect('ops:company_detail', company_id=company.id)

        # Support mode shortcuts: staff can enter/exit support mode for this company.
        if action in {"enter_support", "exit_support"}:
            if action == "exit_support":
                clear_support_mode(request)
                log_event(request, "ops.support_mode_disabled", company=company)
                _ops_log("support_mode.exit", summary="Support mode disabled")
                messages.success(request, "Support mode disabled.")
            else:
                try:
                    minutes = int(request.POST.get("minutes") or 30)
                except Exception:
                    minutes = 30
                minutes = max(5, min(240, minutes))

                reason_preset = (request.POST.get("reason_preset") or "").strip()
                reason_custom = (request.POST.get("reason_custom") or "").strip()

                if reason_preset == "custom":
                    reason = reason_custom
                else:
                    reason = reason_preset

                reason = (reason or "").strip()[:200]
                if not reason:
                    messages.error(request, "Support mode requires a reason.")
                    return redirect("ops:company_detail", company_id=company.id)

                set_support_mode(request, company_id=str(company.id), minutes=minutes, reason=reason)
                set_active_company_id(request, str(company.id))
                log_event(request, "ops.support_mode_enabled", company=company)
                _ops_log("support_mode.enter", summary=f"Support mode enabled ({minutes}m)", meta={"minutes": minutes, "reason": reason})
                messages.success(request, "Support mode enabled.")
            return redirect("ops:company_detail", company_id=company.id)

        # Tenant status controls
        if action == "suspend_company":
            if not _require_ops_2fa_if_configured(request, label="Suspend company"):
                return redirect("ops:company_detail", company_id=company.id)
            if not _require_typed_confirm(request, expected=company.name, label="Suspend company"):
                return redirect("ops:company_detail", company_id=company.id)

            reason = (request.POST.get("reason") or "").strip()[:255]
            company.is_suspended = True
            company.suspended_at = timezone.now()
            company.suspended_reason = reason
            company.save(update_fields=["is_suspended", "suspended_at", "suspended_reason"])
            try:
                CompanyLifecycleEvent.objects.create(company=company, event_type=LifecycleEventType.COMPANY_SUSPENDED, details={'reason': reason})
            except Exception:
                pass
            _ops_log("company.suspend", summary="Company suspended", meta={"reason": reason})
            messages.success(request, "Company suspended.")
            return redirect("ops:company_detail", company_id=company.id)

        if action == "reactivate_company":
            if not _require_ops_2fa_if_configured(request, label="Reactivate company"):
                return redirect("ops:company_detail", company_id=company.id)
            if not _require_typed_confirm(request, expected=company.name, label="Reactivate company"):
                return redirect("ops:company_detail", company_id=company.id)

            company.is_suspended = False
            company.suspended_at = None
            company.suspended_reason = ""
            company.save(update_fields=["is_suspended", "suspended_at", "suspended_reason"])
            try:
                CompanyLifecycleEvent.objects.create(company=company, event_type=LifecycleEventType.COMPANY_REACTIVATED)
            except Exception:
                pass
            _ops_log("company.reactivate", summary="Company reactivated")
            messages.success(request, "Company reactivated.")
            return redirect("ops:company_detail", company_id=company.id)

        if action == "force_logout":
            if not _require_ops_2fa_if_configured(request, label="Force logout"):
                return redirect("ops:company_detail", company_id=company.id)
            if not _require_typed_confirm(request, expected="LOGOUT", label="Force logout"):
                return redirect("ops:company_detail", company_id=company.id)

            now = timezone.now()
            user_ids = list(employees.values_list("user_id", flat=True))
            from accounts.models import User
            User.objects.filter(id__in=user_ids).update(force_logout_at=now)
            _ops_log("company.force_logout", summary="Forced logout for all company users", meta={"user_count": len(user_ids)})
            messages.success(request, "Forced logout requested. Users will be required to sign in again.")
            return redirect("ops:company_detail", company_id=company.id)

        # Per-user controls
        if action in {"disable_user", "enable_user"}:
            user_id = (request.POST.get("user_id") or "").strip()
            try:
                from accounts.models import User
                u = User.objects.get(pk=user_id)
            except Exception:
                messages.error(request, "User not found.")
                return redirect("ops:company_detail", company_id=company.id)

            if action == "disable_user":
                u.is_active = False
                u.save(update_fields=["is_active"])
                _ops_log("company.user_disable", summary="User disabled", meta={"user_id": str(u.id), "email": u.email})
                messages.success(request, "User disabled.")
            else:
                u.is_active = True
                u.save(update_fields=["is_active"])
                _ops_log("company.user_enable", summary="User enabled", meta={"user_id": str(u.id), "email": u.email})
                messages.success(request, "User enabled.")
            return redirect(f"{reverse('ops:company_detail', kwargs={'company_id': company.id})}?tab=users")

        # Billing overrides (app-side; Stripe remains source of truth for actual billing)
        if action in {"set_comped", "clear_comped"}:
            if not _require_ops_2fa_if_configured(request, label="Billing override"):
                return redirect(f"{reverse('ops:company_detail', kwargs={'company_id': company.id})}?tab=billing")
            if not subscription:
                messages.error(request, "No subscription row found for this company.")
                return redirect(f"{reverse('ops:company_detail', kwargs={'company_id': company.id})}?tab=billing")

            if action == "clear_comped":
                subscription.is_comped = False
                subscription.comped_until = None
                subscription.comped_reason = ""
                subscription.save(update_fields=["is_comped", "comped_until", "comped_reason"])
                _ops_log("billing.comped_clear", summary="Comped cleared")
                messages.success(request, "Comped cleared.")
            else:
                until = (request.POST.get("comped_until") or "").strip()
                reason = (request.POST.get("comped_reason") or "").strip()[:200]
                comped_until = None
                if until:
                    try:
                        comped_until = datetime.fromisoformat(until)
                        if comped_until.tzinfo is None:
                            comped_until = timezone.make_aware(comped_until)
                    except Exception:
                        comped_until = None
                subscription.is_comped = True
                subscription.comped_until = comped_until
                subscription.comped_reason = reason
                subscription.save(update_fields=["is_comped", "comped_until", "comped_reason"])
                _ops_log("billing.comped_set", summary="Comped set", meta={"comped_until": until, "reason": reason})
                messages.success(request, "Comped updated.")
            return redirect(f"{reverse('ops:company_detail', kwargs={'company_id': company.id})}?tab=billing")

        if action in {"set_discount", "clear_discount"}:
            if not subscription:
                messages.error(request, "No subscription row found for this company.")
                return redirect(f"{reverse('ops:company_detail', kwargs={'company_id': company.id})}?tab=billing")

            if action == "clear_discount":
                subscription.discount_percent = 0
                subscription.discount_ends_at = None
                subscription.discount_note = ""
                subscription.save(update_fields=["discount_percent", "discount_ends_at", "discount_note"])
                _ops_log("billing.discount_clear", summary="Discount cleared")
                messages.success(request, "Discount cleared.")
            else:
                pct_raw = (request.POST.get("discount_percent") or "0").strip()
                ends_raw = (request.POST.get("discount_ends_at") or "").strip()
                note = (request.POST.get("discount_note") or "").strip()[:200]

                try:
                    pct = int(pct_raw)
                except Exception:
                    pct = 0
                pct = max(0, min(100, pct))

                ends_at = None
                if ends_raw:
                    try:
                        ends_at = datetime.fromisoformat(ends_raw)
                        if ends_at.tzinfo is None:
                            ends_at = timezone.make_aware(ends_at)
                    except Exception:
                        ends_at = None

                subscription.discount_percent = pct
                subscription.discount_ends_at = ends_at
                subscription.discount_note = note
                subscription.save(update_fields=["discount_percent", "discount_ends_at", "discount_note"])
                _ops_log("billing.discount_set", summary=f"Discount set ({pct}%)", meta={"percent": pct, "ends_at": ends_raw, "note": note})
                messages.success(request, "Discount updated.")
            return redirect(f"{reverse('ops:company_detail', kwargs={'company_id': company.id})}?tab=billing")


        # Stripe actions (queued + auditable). Stripe remains authority.
        if action in {"queue_stripe_cancel", "queue_stripe_resume", "queue_stripe_change_plan"}:
            if not subscription or not subscription.stripe_subscription_id:
                messages.error(request, "No Stripe subscription is linked to this company.")
                return redirect(f"{reverse('ops:company_detail', kwargs={'company_id': company.id})}?tab=billing")

            try:
                from .models import OpsStripeAction, OpsStripeActionType, OpsStripeActionStatus
                action_type = ""
                payload: dict = {}
                if action == "queue_stripe_cancel":
                    action_type = OpsStripeActionType.CANCEL_AT_PERIOD_END
                elif action == "queue_stripe_resume":
                    action_type = OpsStripeActionType.RESUME
                elif action == "queue_stripe_change_plan":
                    action_type = OpsStripeActionType.CHANGE_PLAN
                    payload = {
                        "plan": (request.POST.get("plan") or "").strip(),
                        "interval": (request.POST.get("interval") or "").strip(),
                    }

                OpsStripeAction.objects.create(
                    company=company,
                    subscription_id_snapshot=str(subscription.stripe_subscription_id or ""),
                    action_type=action_type,
                    status=OpsStripeActionStatus.PENDING,
                    payload=payload,
                    requested_by=request.user if request.user.is_authenticated else None,
                    requested_by_email=getattr(request.user, "email", "") or "",
                    requires_approval=True,
                )
                _ops_log("billing.stripe_action.queue", summary=f"Queued {action_type}", meta={"action_type": action_type, "payload": payload})
                messages.success(request, "Stripe action queued (pending approval).")
                return redirect(f"{reverse('ops:company_detail', kwargs={'company_id': company.id})}?tab=billing")
            except Exception as e:
                messages.error(request, f"Could not queue action: {e}")
                return redirect(f"{reverse('ops:company_detail', kwargs={'company_id': company.id})}?tab=billing")

        messages.error(request, "Unknown action.")
        return redirect("ops:company_detail", company_id=company.id)

    # Tab data
    ops_actions = []
    if tab == "audit":
        try:
            from .models import OpsActionLog
            ops_actions = OpsActionLog.objects.filter(company=company).select_related("actor").order_by("-created_at")[:250]
        except Exception:
            ops_actions = []

    recent_docs = []
    recent_payments = []
    if tab == "activity":
        try:
            from documents.models import Document
            recent_docs = Document.objects.filter(company=company).select_related("client", "project").order_by("-created_at")[:25]
        except Exception:
            recent_docs = []
        try:
            from payments.models import Payment
            recent_payments = Payment.objects.filter(company=company).select_related("client", "invoice").order_by("-created_at")[:25]
        except Exception:
            recent_payments = []


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


    return render(
        request,
        "ops/company_detail.html",
        {
            "company": company,
            "subscription": subscription,
            "employees": employees,
            "seats_limit": seats_limit_for(subscription) if subscription else 1,
            "support": get_support_mode(request),
            "support_for_company": (lambda s: getattr(s, "is_active", False) and str(getattr(s, "company_id", "")) == str(company.id))(get_support_mode(request)),
            "last_login": last_login,
            "mrr": mrr,
            "arr": arr,
            "recent_webhooks": recent_webhooks,
            "stripe_actions": stripe_actions,
            "stripe_actions_pending": stripe_actions_pending,
            "plan_rows": plan_rows,
            "tab": tab,
            "ops_actions": ops_actions,
            "recent_docs": recent_docs,
            "recent_payments": recent_payments,
            "risk": risk,
            "risk_history": risk_history,
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_company_jump(request: HttpRequest, company_id: str, dest: str) -> HttpResponse:
    """Set active company (support context) then deep-link into the tenant workspace.

    This keeps the Ops Center as the control plane while allowing staff to
    operate inside the tenant UI in a scoped, auditable manner.

    Requirements:
    - Staff only
    - Ops SUPPORT (or SUPEROPS) role
    - Support mode must be active for this company
    """
    from companies.services import set_active_company_id

    # Role gate (customer data access)
    if not require_ops_role(request, OpsRole.SUPPORT):
        return redirect('ops:company_detail', company_id=company_id)

    try:
        company = Company.objects.get(pk=company_id)
    except Exception:
        messages.error(request, 'Company not found.')
        return redirect('ops:companies')

    support = get_support_mode(request)
    if not getattr(support, 'is_active', False) or str(getattr(support, 'company_id', '')) != str(company.id):
        messages.warning(request, 'Enable Support Mode for this company to access the tenant workspace.')
        return redirect('ops:company_detail', company_id=company.id)

    # Set active company for tenant UI routing
    set_active_company_id(request, str(company.id))

    # Destination routing
    dest = (dest or '').strip().lower()
    dest_map = {
        'dashboard': 'core:app_dashboard',
        'clients': 'crm:client_list',
        'projects': 'projects:project_list',
        'invoices': 'documents:invoice_list',
        'payments': 'payments:payment_list',
        'time': 'timetracking:entry_list',
                'expenses': 'expenses:expense_list',
    }

    url_name = dest_map.get(dest)
    if not url_name:
        # Fallback to app dashboard
        url_name = 'core:app_dashboard'

    try:
        target = reverse(url_name)
    except Exception:
        target = reverse('core:app_dashboard')

    # Best-effort audit log
    try:
        from .models import OpsActionLog
        OpsActionLog.objects.create(
            actor=request.user if request.user.is_authenticated else None,
            actor_email=getattr(request.user, 'email', '')[:254],
            company=company,
            action='ops.company_jump',
            summary=f'Jump to tenant workspace: {dest}',
            meta={'dest': dest, 'target': target},
            ip_address=_client_ip(request),
            user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
        )
    except Exception:
        pass

    return redirect(target)


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_support_mode_clear(request: HttpRequest) -> HttpResponse:
    """Global 'panic button' to clear support mode."""
    state = get_support_mode(request)
    clear_support_mode(request)
    if state.company_id:
        try:
            company = Company.objects.filter(pk=state.company_id).first()
        except Exception:
            company = None
        if company:
            log_event(request, "ops.support_mode_disabled", company=company)
    messages.success(request, "Support mode cleared.")
    return redirect("ops:dashboard")


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


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


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


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


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


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


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


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


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
@login_required
@user_passes_test(_is_staff)
def ops_backups(request: HttpRequest) -> HttpResponse:
    """Backups/restore status page.

    This page exists to make **recoverability** visible and enforceable:
    - show the latest backup evidence (BackupRun)
    - show restore test evidence (BackupRestoreTest)
    - show the latest automated verification run (OpsCheckRun: backup_verify)
    """

    cfg = {
        "backup_enabled": bool(getattr(settings, "BACKUP_ENABLED", False)),
        "backup_retention_days": int(getattr(settings, "BACKUP_RETENTION_DAYS", 14)),
        "backup_storage": str(getattr(settings, "BACKUP_STORAGE", "host_managed")),
        "backup_notify_emails": list(getattr(settings, "BACKUP_NOTIFY_EMAILS", [])),
        "backup_s3_bucket": str(getattr(settings, "BACKUP_S3_BUCKET", "")),
        "backup_s3_prefix": str(getattr(settings, "BACKUP_S3_PREFIX", "")),
        "verify_max_age_hours": int(getattr(settings, "BACKUP_VERIFY_MAX_AGE_HOURS", 26) or 26),
        "verify_min_size_bytes": int(getattr(settings, "BACKUP_VERIFY_MIN_SIZE_BYTES", 1024) or 1024),
        "restore_test_required_days": int(getattr(settings, "BACKUP_RESTORE_TEST_REQUIRED_DAYS", 30) or 30),
    }

    backup_runs = BackupRun.objects.all()[:25]
    restore_tests = BackupRestoreTest.objects.all()[:10]
    latest_restore = restore_tests[0] if restore_tests else None

    latest_verify = None
    try:
        from ops.models import OpsCheckRun, OpsCheckKind

        latest_verify = OpsCheckRun.objects.filter(kind=OpsCheckKind.BACKUP_VERIFY).order_by("-created_at").first()
    except Exception:
        latest_verify = None

    return render(
        request,
        "ops/backups.html",
        {
            "cfg": cfg,
            "backup_runs": backup_runs,
            "restore_tests": restore_tests,
            "latest_restore": latest_restore,
            "latest_verify": latest_verify,
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

    tab = (request.GET.get("tab") or "actions").strip()

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


# --------------------------------------------------------------------------------------
# Phase 8S2 — V1 Launch Manual + End-to-End QA Punchlist
# --------------------------------------------------------------------------------------


@staff_only
def ops_qa_issues(request: HttpRequest) -> HttpResponse:
    tab = (request.GET.get("tab") or "actions").strip()

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    severity = (request.GET.get("severity") or "").strip()
    area = (request.GET.get("area") or "").strip()

    qs = QAIssue.objects.select_related("company").all()

    if status:
        qs = qs.filter(status=status)
    if severity:
        qs = qs.filter(severity=severity)
    if area:
        qs = qs.filter(area__icontains=area)
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(steps_to_reproduce__icontains=q)
            | Q(company__name__icontains=q)
            | Q(discovered_by_email__icontains=q)
            | Q(assigned_to_email__icontains=q)
        )

    counts = {
        "open": QAIssue.objects.filter(status=QAIssueStatus.OPEN).count(),
        "in_progress": QAIssue.objects.filter(status=QAIssueStatus.IN_PROGRESS).count(),
        "resolved": QAIssue.objects.filter(status=QAIssueStatus.RESOLVED).count(),
        "wont_fix": QAIssue.objects.filter(status=QAIssueStatus.WONT_FIX).count(),
    }

    paginator = Paginator(qs.order_by("-created_at"), 25)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    ctx = {
        "q": q,
        "status": status,
        "severity": severity,
        "area": area,
        "counts": counts,
        "page_obj": page_obj,
        "statuses": QAIssueStatus.choices,
        "severities": QAIssue._meta.get_field("severity").choices,
    }
    return render(request, "ops/qa_issues_list.html", ctx)


@staff_only
def ops_qa_issue_new(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = QAIssueForm(request.POST)
        if form.is_valid():
            obj: QAIssue = form.save(commit=False)
            obj.created_at = timezone.now()
            obj.updated_at = timezone.now()
            if not obj.discovered_by_email:
                obj.discovered_by_email = (getattr(request.user, "email", "") or "").strip()[:254]
            obj.save()
            messages.success(request, "QA issue created.")
            return redirect("ops:qa_issue_detail", pk=obj.pk)
    else:
        initial = {
            "discovered_by_email": (getattr(request.user, "email", "") or "").strip(),
        }

        # Optional prefill from querystring (used by the topbar "Report issue" shortcut).
        # We keep this intentionally conservative to avoid surprise values.
        related_url = (request.GET.get("related_url") or "").strip()
        area = (request.GET.get("area") or "").strip()
        company_id = (request.GET.get("company") or "").strip()

        if related_url:
            initial["related_url"] = related_url
        if area:
            initial["area"] = area[:64]
        if company_id.isdigit():
            initial["company"] = int(company_id)

        form = QAIssueForm(initial=initial)

    return render(request, "ops/qa_issue_form.html", {"form": form, "mode": "new"})


@staff_only
def ops_qa_issue_detail(request: HttpRequest, pk: int) -> HttpResponse:
    issue = get_object_or_404(QAIssue.objects.select_related("company"), pk=pk)
    return render(request, "ops/qa_issue_detail.html", {"issue": issue})


@staff_only
def ops_qa_issue_edit(request: HttpRequest, pk: int) -> HttpResponse:
    issue = get_object_or_404(QAIssue.objects.select_related("company"), pk=pk)
    if request.method == "POST":
        form = QAIssueForm(request.POST, instance=issue)
        if form.is_valid():
            obj: QAIssue = form.save(commit=False)
            obj.updated_at = timezone.now()
            # Auto-set resolved_at when moving to resolved.
            if obj.status in {QAIssueStatus.RESOLVED, QAIssueStatus.WONT_FIX} and obj.resolved_at is None:
                obj.resolved_at = timezone.now()
            if obj.status in {QAIssueStatus.OPEN, QAIssueStatus.IN_PROGRESS}:
                obj.resolved_at = None
            obj.save()
            messages.success(request, "QA issue updated.")
            return redirect("ops:qa_issue_detail", pk=issue.pk)
    else:
        form = QAIssueForm(instance=issue)

    return render(request, "ops/qa_issue_form.html", {"form": form, "mode": "edit", "issue": issue})


@staff_only
@require_POST
def ops_qa_issue_close(request: HttpRequest, pk: int) -> HttpResponse:
    issue = get_object_or_404(QAIssue, pk=pk)
    outcome = (request.POST.get("outcome") or "resolved").strip()
    notes = (request.POST.get("notes") or "").strip()

    if outcome == "wont_fix":
        issue.status = QAIssueStatus.WONT_FIX
    else:
        issue.status = QAIssueStatus.RESOLVED
    issue.resolved_at = timezone.now()
    if notes:
        issue.resolution_notes = notes
    issue.updated_at = timezone.now()
    issue.save(update_fields=["status", "resolved_at", "resolution_notes", "updated_at"])
    messages.success(request, "QA issue closed.")
    return redirect("ops:qa_issue_detail", pk=issue.pk)


# --------------------------------------------------------------------------------------
# Ops: Security dashboard (lockouts + auth/throttle alerts)
# --------------------------------------------------------------------------------------

@user_passes_test(_is_staff)
def ops_security(request):
    """Security ops view.

    Never blocks ops navigation. Shows recent account lockouts and open auth/throttle alerts.
    """
    from accounts.models import AccountLockout
    from .models import OpsAlertEvent, OpsAlertSource

    lockouts = (
        AccountLockout.objects.order_by("-updated_at")[:50]
    )

    auth_alerts = (
        OpsAlertEvent.objects.filter(source=OpsAlertSource.AUTH, is_resolved=False)
        .select_related("company")
        .order_by("-created_at")[:50]
    )
    throttle_alerts = (
        OpsAlertEvent.objects.filter(source=OpsAlertSource.THROTTLE, is_resolved=False)
        .select_related("company")
        .order_by("-created_at")[:50]
    )

    counts = {
        "open_auth": OpsAlertEvent.objects.filter(source=OpsAlertSource.AUTH, is_resolved=False).count(),
        "open_throttle": OpsAlertEvent.objects.filter(source=OpsAlertSource.THROTTLE, is_resolved=False).count(),
    }


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


    return render(
        request,
        "ops/security.html",
        {
            "lockouts": lockouts,
            "auth_alerts": auth_alerts,
            "throttle_alerts": throttle_alerts,
            "counts": counts,
        },
    )




# =========================
# Billing Control (Pack 4)
# =========================

@login_required
@user_passes_test(_is_staff)
def ops_billing_actions(request: HttpRequest) -> HttpResponse:
    if not require_ops_role(request, OpsRole.FINANCE):
        return redirect('ops:dashboard')
    """Queued Stripe actions.

    Purpose: provide a professional-grade, auditable control surface for subscription operations.
    Stripe is the authority; this page records intent + approvals + execution results.
    """
    from .models import OpsStripeAction, OpsStripeActionStatus, OpsStripeActionType, OpsCompanyViewPreset
    from companies.models import Company
    from billing.models import CompanySubscription

    status = (request.GET.get("status") or "").strip().lower()
    company_id = (request.GET.get("company") or "").strip()
    tab = (request.GET.get("tab") or "actions").strip()

    q = (request.GET.get("q") or "").strip()

    qs = OpsStripeAction.objects.select_related("company").all()
    if status in {s for s, _ in OpsStripeActionStatus.choices}:
        qs = qs.filter(status=status)
    if company_id:
        qs = qs.filter(company_id=company_id)
    if q:
        qs = qs.filter(models.Q(company__name__icontains=q) | models.Q(requested_by_email__icontains=q) | models.Q(approved_by_email__icontains=q))

    actions = qs.order_by("-created_at")[:250]

    presets = OpsCompanyViewPreset.objects.filter(is_active=True).order_by("name")


    stripe_actions = []
    stripe_actions_pending = 0
    if tab in {"billing", "overview"}:
        try:
            from .models import OpsStripeAction, OpsStripeActionStatus
            stripe_actions = OpsStripeAction.objects.filter(company=company).order_by("-created_at")[:25]
            stripe_actions_pending = OpsStripeAction.objects.filter(company=company, status=OpsStripeActionStatus.PENDING).count()
        except Exception:
            stripe_actions = []
            stripe_actions_pending = 0

    plan_rows = []
    if tab == "billing":
        try:
            plan_rows = list(PlanCatalog.objects.filter(is_active=True).order_by("sort_order", "code"))
        except Exception:
            plan_rows = []


    return render(
        request,
        "ops/billing_actions.html",
        {
            "actions": actions,
            "filters": {"status": status, "company": company_id, "q": q},
            "presets": presets,
        },
    )


@login_required
@user_passes_test(_is_staff)
def ops_billing_action_detail(request: HttpRequest, pk: int) -> HttpResponse:
    if not require_ops_role(request, OpsRole.FINANCE):
        return redirect('ops:dashboard')
    from .models import OpsStripeAction
    action = get_object_or_404(OpsStripeAction.objects.select_related("company", "requested_by", "approved_by", "executed_by"), pk=pk)
    return render(request, "ops/billing_action_detail.html", {"action": action})


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_billing_action_approve(request: HttpRequest, pk: int) -> HttpResponse:
    if not require_ops_role(request, OpsRole.FINANCE):
        return redirect('ops:billing_actions')
    from .models import OpsStripeAction, OpsStripeActionStatus, OpsActionLog

    action = get_object_or_404(OpsStripeAction, pk=pk)
    cfg = SiteConfig.get_solo()
    if getattr(cfg, "ops_two_person_approval_enabled", False) and action.requested_by_id and action.requested_by_id == request.user.id:
        messages.error(request, "Two-person approval is enabled: the requester cannot approve this Stripe action.")
        return redirect("ops:billing_action_detail", pk=action.id)
    if not _require_ops_2fa_if_configured(request, label="Approve Stripe action"):
        return redirect("ops:billing_action_detail", pk=action.id)
    if not _require_typed_confirm(request, expected=action.company.name, label="Approve Stripe action"):
        return redirect("ops:billing_action_detail", pk=action.id)


    if action.status != OpsStripeActionStatus.PENDING:
        messages.info(request, "This action is not pending.")
        return redirect("ops:billing_action_detail", pk=action.id)

    action.status = OpsStripeActionStatus.APPROVED
    action.approved_at = timezone.now()
    action.approved_by = request.user
    action.approved_by_email = getattr(request.user, "email", "") or ""
    action.save(update_fields=["status", "approved_at", "approved_by", "approved_by_email", "updated_at"])

    # Audit
    try:
        OpsActionLog.objects.create(
            actor=request.user,
            actor_email=getattr(request.user, "email", "") or "",
            company=action.company,
            action="billing.stripe_action.approve",
            summary=f"Approved {action.action_type}",
            meta={"ops_stripe_action_id": action.id, "action_type": action.action_type},
            ip_address=_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
        )
    except Exception:
        pass

    messages.success(request, "Action approved.")
    return redirect("ops:billing_action_detail", pk=action.id)


def _stripe_idempotency_key(action_id: int) -> str:
    return f"ez360pm_ops_{action_id}"


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_billing_action_run(request: HttpRequest, pk: int) -> HttpResponse:
    if not require_ops_role(request, OpsRole.FINANCE):
        return redirect('ops:billing_actions')
    """Execute a queued Stripe action immediately."""
    from .models import OpsStripeAction, OpsStripeActionStatus, OpsStripeActionType, OpsActionLog
    from billing.stripe_service import stripe_client, get_base_plan_price_id, fetch_and_sync_subscription_from_stripe
    from billing.services import ensure_company_subscription

    action = get_object_or_404(OpsStripeAction, pk=pk)
    cfg = SiteConfig.get_solo()
    if getattr(cfg, "ops_two_person_approval_enabled", False) and action.requested_by_id and action.requested_by_id == request.user.id:
        messages.error(request, "Two-person approval is enabled: the requester cannot run this Stripe action.")
        return redirect("ops:billing_action_detail", pk=action.id)
    if not _require_ops_2fa_if_configured(request, label="Run Stripe action"):
        return redirect("ops:billing_action_detail", pk=action.id)
    if not _require_typed_confirm(request, expected=action.company.name, label="Run Stripe action"):
        return redirect("ops:billing_action_detail", pk=action.id)


    if action.status not in {OpsStripeActionStatus.PENDING, OpsStripeActionStatus.APPROVED}:
        messages.info(request, "This action is not runnable.")
        return redirect("ops:billing_action_detail", pk=action.id)

    if action.requires_approval and action.status != OpsStripeActionStatus.APPROVED:
        messages.error(request, "Approval required before running this action.")
        return redirect("ops:billing_action_detail", pk=action.id)

    sub = ensure_company_subscription(action.company)
    if not sub.stripe_subscription_id:
        messages.error(request, "Company has no Stripe subscription id.")
        return redirect("ops:billing_action_detail", pk=action.id)

    # Mark running
    action.status = OpsStripeActionStatus.RUNNING
    action.executed_at = timezone.now()
    action.executed_by = request.user
    action.executed_by_email = getattr(request.user, "email", "") or ""
    action.subscription_id_snapshot = str(sub.stripe_subscription_id or "")
    action.idempotency_key = _stripe_idempotency_key(action.id)
    action.error = ""
    action.save(update_fields=["status", "executed_at", "executed_by", "executed_by_email", "subscription_id_snapshot", "idempotency_key", "error", "updated_at"])

    stripe = stripe_client()

    try:
        if action.action_type == OpsStripeActionType.CANCEL_AT_PERIOD_END:
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                cancel_at_period_end=True,
                idempotency_key=action.idempotency_key,
            )

        elif action.action_type == OpsStripeActionType.RESUME:
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                cancel_at_period_end=False,
                idempotency_key=action.idempotency_key,
            )

        elif action.action_type == OpsStripeActionType.CHANGE_PLAN:
            plan = str((action.payload or {}).get("plan") or "").strip()
            interval = str((action.payload or {}).get("interval") or "").strip()

            price_id = get_base_plan_price_id(plan, interval)
            if not price_id:
                raise RuntimeError("Could not resolve Stripe price_id for requested plan/interval.")

            stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
            items = (stripe_sub.get("items") or {}).get("data") or []
            if not items:
                raise RuntimeError("Stripe subscription has no items to update.")

            # Best-effort: update the first subscription item (base plan item).
            item_id = str(items[0].get("id") or "")
            if not item_id:
                raise RuntimeError("Stripe subscription item id missing.")

            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                items=[{"id": item_id, "price": price_id}],
                proration_behavior="create_prorations",
                idempotency_key=action.idempotency_key,
            )

        else:
            raise RuntimeError("Unsupported action type in Pack 4.")

        # Sync local subscription after mutation
        try:
            fetch_and_sync_subscription_from_stripe(company=action.company)
        except Exception:
            # Do not fail the action if sync fails; it can be resynced separately.
            pass

        action.status = OpsStripeActionStatus.SUCCEEDED
        action.save(update_fields=["status", "updated_at"])

        try:
            OpsActionLog.objects.create(
                actor=request.user,
                actor_email=getattr(request.user, "email", "") or "",
                company=action.company,
                action="billing.stripe_action.run",
                summary=f"Executed {action.action_type}",
                meta={"ops_stripe_action_id": action.id, "action_type": action.action_type},
                ip_address=_client_ip(request),
                user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
            )
        except Exception:
            pass

        messages.success(request, "Stripe action executed.")
        return redirect("ops:billing_action_detail", pk=action.id)

    except Exception as e:
        action.status = OpsStripeActionStatus.FAILED
        action.error = str(e)[:2000]
        action.save(update_fields=["status", "error", "updated_at"])
        messages.error(request, f"Stripe action failed: {e}")
        return redirect("ops:billing_action_detail", pk=action.id)


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_billing_action_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    if not require_ops_role(request, OpsRole.FINANCE):
        return redirect('ops:billing_actions')
    from .models import OpsStripeAction, OpsStripeActionStatus, OpsActionLog

    action = get_object_or_404(OpsStripeAction, pk=pk)
    if not _require_ops_2fa_if_configured(request, label="Cancel Stripe action"):
        return redirect("ops:billing_action_detail", pk=action.id)
    if not _require_typed_confirm(request, expected=action.company.name, label="Cancel Stripe action"):
        return redirect("ops:billing_action_detail", pk=action.id)
    if action.status not in {OpsStripeActionStatus.PENDING, OpsStripeActionStatus.APPROVED}:
        messages.info(request, "This action cannot be canceled.")
        return redirect("ops:billing_action_detail", pk=action.id)

    action.status = OpsStripeActionStatus.CANCELED
    action.save(update_fields=["status", "updated_at"])

    try:
        OpsActionLog.objects.create(
            actor=request.user,
            actor_email=getattr(request.user, "email", "") or "",
            company=action.company,
            action="billing.stripe_action.cancel",
            summary=f"Canceled {action.action_type}",
            meta={"ops_stripe_action_id": action.id, "action_type": action.action_type},
            ip_address=_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
        )
    except Exception:
        pass

    messages.success(request, "Action canceled.")
    return redirect("ops:billing_actions")


# =========================
# Ops Access Control (Pack 13)
# =========================

@login_required
@user_passes_test(_is_staff)
def ops_access(request: HttpRequest) -> HttpResponse:
    """Manage Ops Center role assignments (enterprise governance)."""
    from accounts.models import User
    from .models import OpsRoleAssignment, OpsRole

    if not require_ops_role(request, OpsRole.SUPEROPS):
        return redirect("ops:dashboard")

    assignments = (
        OpsRoleAssignment.objects.select_related("user", "granted_by")
        .order_by("role", "user__email")
    )

    from .forms import OpsRoleGrantForm

    if request.method == "POST":
        form = OpsRoleGrantForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            role = form.cleaned_data["role"]
            notes = (form.cleaned_data.get("notes") or "").strip()[:240]

            try:
                u = User.objects.get(email__iexact=email)
            except User.DoesNotExist:
                messages.error(request, "No user found with that email.")
                return redirect("ops:access")

            if not u.is_staff:
                messages.error(request, "User must be staff to receive ops roles.")
                return redirect("ops:access")

            obj, created = OpsRoleAssignment.objects.get_or_create(
                user=u,
                role=role,
                defaults={
                    "granted_by": request.user,
                    "granted_by_email": getattr(request.user, "email", "") or "",
                    "notes": notes,
                },
            )
            if not created:
                # Update notes/granting metadata
                obj.granted_by = request.user
                obj.granted_by_email = getattr(request.user, "email", "") or ""
                obj.notes = notes
                obj.save(update_fields=["granted_by", "granted_by_email", "notes"])  # created_at stays original

            try:
                from .models import OpsActionLog
                OpsActionLog.objects.create(
                    actor=request.user,
                    actor_email=getattr(request.user, "email", "") or "",
                    company=None,
                    action="ops.access.grant",
                    summary=f"Granted {role} to {u.email}",
                    meta={"user_id": str(u.id), "role": role},
                    ip_address=_client_ip(request),
                    user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
                )
            except Exception:
                pass

            messages.success(request, "Role assignment saved.")
            return redirect("ops:access")
    else:
        form = OpsRoleGrantForm()

    return render(
        request,
        "ops/access.html",
        {
            "assignments": assignments,
            "form": form,
            "roles": OpsRole,
        },
    )


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_access_revoke(request: HttpRequest, pk: int) -> HttpResponse:
    from .models import OpsRoleAssignment, OpsRole

    if not require_ops_role(request, OpsRole.SUPEROPS):
        return redirect("ops:dashboard")

    assignment = get_object_or_404(OpsRoleAssignment, pk=pk)
    target_email = getattr(assignment.user, "email", "")
    role = assignment.role
    assignment.delete()

    try:
        from .models import OpsActionLog
        OpsActionLog.objects.create(
            actor=request.user,
            actor_email=getattr(request.user, "email", "") or "",
            company=None,
            action="ops.access.revoke",
            summary=f"Revoked {role} from {target_email}",
            meta={"role": role, "target_email": target_email},
            ip_address=_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
        )
    except Exception:
        pass

    messages.success(request, "Role assignment revoked.")
    return redirect("ops:access")


@login_required
@user_passes_test(_is_staff)
def ops_activity(request: HttpRequest) -> HttpResponse:
    """Executive activity feed.

    This is the operator's "what just happened" view across:
    - OpsActionLog (staff actions)
    - OpsCheckRun (readiness/smoke evidence)

    We keep it intentionally simple + fast (server-rendered, filterable, exportable).
    """

    if not require_ops_role(request, OpsRole.VIEWER):
        return redirect("core:dashboard")

    from datetime import timedelta
    from django.core.paginator import Paginator
    from django.utils import timezone

    from .models import OpsActionLog, OpsCheckRun

    tab = (request.GET.get("tab") or "actions").strip()  # actions | checks | stripe
    tab = (request.GET.get("tab") or "actions").strip()

    q = (request.GET.get("q") or "").strip()
    company_id = (request.GET.get("company_id") or "").strip()
    actor_email = (request.GET.get("actor") or "").strip()
    action = (request.GET.get("action") or "").strip()
    status = (request.GET.get("status") or "").strip()
    action_type = (request.GET.get("action_type") or "").strip()
    kind = (request.GET.get("kind") or "").strip()
    ok = (request.GET.get("ok") or "").strip()  # true | false

    try:
        days = int((request.GET.get("days") or "30").strip())
    except ValueError:
        days = 30
    days = max(1, min(days, 365))
    since = timezone.now() - timedelta(days=days)

    context: dict = {
        "tab": tab,
        "q": q,
        "company_id": company_id,
        "actor": actor_email,
        "action": action,
        "kind": kind,
        "ok": ok,
        "days": days,
    }

    if tab == "checks":
        runs = OpsCheckRun.objects.select_related("company").filter(created_at__gte=since)
        if company_id:
            runs = runs.filter(company_id=company_id)
        if kind:
            runs = runs.filter(kind=kind)
        if ok.lower() in {"true", "false"}:
            runs = runs.filter(is_ok=(ok.lower() == "true"))
        if q:
            runs = runs.filter(
                Q(created_by_email__icontains=q)
                | Q(output_text__icontains=q)
                | Q(company__name__icontains=q)
            )

        paginator = Paginator(runs.order_by("-created_at"), 50)
        page_obj = paginator.get_page(request.GET.get("page"))
        context["checks"] = page_obj
        context["checks_total"] = runs.count()
    elif tab == "stripe":
        from django.core.paginator import Paginator
        from .models import OpsStripeAction

        qs = OpsStripeAction.objects.select_related("company").filter(created_at__gte=since)
        if company_id:
            qs = qs.filter(company_id=company_id)
        if status:
            qs = qs.filter(status__icontains=status)
        if action_type:
            qs = qs.filter(action_type__icontains=action_type)
        if q:
            qs = qs.filter(
                Q(company__name__icontains=q)
                | Q(requested_by_email__icontains=q)
                | Q(action_type__icontains=q)
                | Q(status__icontains=q)
            )

        paginator = Paginator(qs.order_by("-created_at"), 50)
        page_obj = paginator.get_page(request.GET.get("page"))
        context["stripe_actions"] = page_obj
        context["stripe_total"] = qs.count()

    else:
        logs = OpsActionLog.objects.select_related("company", "actor").filter(created_at__gte=since)
        if company_id:
            logs = logs.filter(company_id=company_id)
        if actor_email:
            logs = logs.filter(actor_email__icontains=actor_email)
        if action:
            logs = logs.filter(action__icontains=action)
        if q:
            logs = logs.filter(
                Q(action__icontains=q)
                | Q(summary__icontains=q)
                | Q(actor_email__icontains=q)
                | Q(company__name__icontains=q)
            )

        paginator = Paginator(logs.order_by("-created_at"), 50)
        page_obj = paginator.get_page(request.GET.get("page"))
        context["actions"] = page_obj
        context["actions_total"] = logs.count()

    return render(request, "ops/activity.html", context)


@login_required
@user_passes_test(_is_staff)
def ops_activity_export_csv(request: HttpRequest) -> HttpResponse:
    """CSV export for Ops activity (filtered)."""

    if not require_ops_role(request, OpsRole.VIEWER):
        return redirect("core:dashboard")

    from datetime import timedelta
    from django.utils import timezone

    from .models import OpsActionLog

    tab = (request.GET.get("tab") or "actions").strip()

    q = (request.GET.get("q") or "").strip()
    company_id = (request.GET.get("company_id") or "").strip()
    actor_email = (request.GET.get("actor") or "").strip()
    action = (request.GET.get("action") or "").strip()
    status = (request.GET.get("status") or "").strip()
    action_type = (request.GET.get("action_type") or "").strip()
    try:
        days = int((request.GET.get("days") or "30").strip())
    except ValueError:
        days = 30
    days = max(1, min(days, 365))
    since = timezone.now() - timedelta(days=days)

    
    if tab == "stripe":
        from .models import OpsStripeAction
        qs = OpsStripeAction.objects.select_related("company").filter(created_at__gte=since)
        if company_id:
            qs = qs.filter(company_id=company_id)
        if status:
            qs = qs.filter(status__icontains=status)
        if action_type:
            qs = qs.filter(action_type__icontains=action_type)
        if q:
            qs = qs.filter(
                Q(company__name__icontains=q)
                | Q(requested_by_email__icontains=q)
                | Q(action_type__icontains=q)
                | Q(status__icontains=q)
            )

        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = 'attachment; filename="ops_stripe_actions.csv"'
        w = csv.writer(resp)
        w.writerow(["created_at", "company", "subscription_id", "action_type", "status", "requested_by", "approved_by", "executed_by", "error"])
        for row in qs.order_by("-created_at")[:50000]:
            w.writerow([
                row.created_at.isoformat(),
                getattr(row.company, "name", ""),
                row.subscription_id_snapshot,
                row.action_type,
                row.status,
                row.requested_by_email,
                row.approved_by_email,
                row.executed_by_email,
                (row.error or "")[:2000],
            ])
        return resp

    logs = OpsActionLog.objects.select_related("company").filter(created_at__gte=since)
    if company_id:
        logs = logs.filter(company_id=company_id)
    if actor_email:
        logs = logs.filter(actor_email__icontains=actor_email)
    if action:
        logs = logs.filter(action__icontains=action)
    if q:
        logs = logs.filter(
            Q(action__icontains=q)
            | Q(summary__icontains=q)
            | Q(actor_email__icontains=q)
            | Q(company__name__icontains=q)
        )

    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="ops_activity.csv"'
    w = csv.writer(resp)
    w.writerow(["created_at", "actor_email", "company", "action", "summary", "ip", "user_agent"])
    for row in logs.order_by("-created_at")[:50000]:
        w.writerow([
            row.created_at.isoformat(),
            row.actor_email,
            getattr(row.company, "name", ""),
            row.action,
            row.summary,
            row.ip_address,
            row.user_agent,
        ])
    return resp


# --------------------------------------------------------------------
# Executive Ops Tools (QuickBooks-style operator console actions)
# --------------------------------------------------------------------

@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_run_snapshot_now(request: HttpRequest) -> HttpResponse:
    """Run the daily platform revenue snapshot command on-demand.

    Note: In production this is typically executed via cron. This button is for
    operator triage / verification.
    """
    if not require_ops_role(request, OpsRole.SUPEROPS):
        return redirect(request.META.get("HTTP_REFERER") or "ops:dashboard")

    try:
        call_command("ez360_snapshot_platform_revenue")
        log_event(
            request,
            company=None,
            action="ops.run_snapshot_now",
            summary="Ran platform revenue snapshot on-demand.",
            meta={},
        )
        messages.success(request, "Revenue snapshot completed.")
    except Exception as e:
        log_event(
            request,
            company=None,
            action="ops.run_snapshot_now_failed",
            summary="Revenue snapshot failed.",
            meta={"error": str(e)},
        )
        messages.error(request, f"Revenue snapshot failed: {e}")
    return redirect(request.META.get("HTTP_REFERER") or "ops:dashboard")


@login_required
@user_passes_test(_is_staff)
@require_POST
def ops_run_desync_scan(request: HttpRequest) -> HttpResponse:
    """Run the Stripe mirror staleness/desync scan on-demand."""
    if not require_ops_role(request, OpsRole.SUPEROPS):
        return redirect(request.META.get("HTTP_REFERER") or "ops:dashboard")

    hours = 0
    try:
        hours = int((request.POST.get("hours") or "0").strip() or "0")
    except Exception:
        hours = 0

    try:
        call_command("ez360_stripe_desync_scan", hours=hours)
        log_event(
            request,
            company=None,
            action="ops.run_desync_scan",
            summary="Ran Stripe desync scan on-demand.",
            meta={"hours": hours},
        )
        messages.success(request, "Stripe desync scan completed.")
    except Exception as e:
        log_event(
            request,
            company=None,
            action="ops.run_desync_scan_failed",
            summary="Stripe desync scan failed.",
            meta={"hours": hours, "error": str(e)},
        )
        messages.error(request, f"Stripe desync scan failed: {e}")

    return redirect(request.META.get("HTTP_REFERER") or "ops:dashboard")


@login_required
def ops_email_health(request: HttpRequest) -> HttpResponse:
    """Outbound email delivery observability dashboard."""
    if not require_ops_role(request, OpsRole.VIEWER):
        return redirect('core:dashboard')

    now = timezone.now()
    start_24h = now - timedelta(days=1)
    start_7d = now - timedelta(days=7)

    qs = OutboundEmailLog.objects.all()

    sent_24h = qs.filter(created_at__gte=start_24h, status=OutboundEmailStatus.SENT).count()
    fail_24h = qs.filter(created_at__gte=start_24h, status=OutboundEmailStatus.ERROR).count()
    total_24h = sent_24h + fail_24h
    fail_rate_24h = (fail_24h / total_24h) if total_24h else 0.0
    fail_rate_24h_pct = fail_rate_24h * 100.0

    sent_7d = qs.filter(created_at__gte=start_7d, status=OutboundEmailStatus.SENT).count()
    fail_7d = qs.filter(created_at__gte=start_7d, status=OutboundEmailStatus.ERROR).count()

    last_error_row = qs.filter(status=OutboundEmailStatus.ERROR).order_by('-created_at').first()
    last_error_at = last_error_row.created_at if last_error_row else None
    last_error_msg = (last_error_row.error_message[:500] if last_error_row else "")

    failures_by_template = list(
        qs.filter(created_at__gte=start_7d, status=OutboundEmailStatus.ERROR)
        .values('template_type')
        .annotate(count=Count('id'))
        .order_by('-count')[:12]
    )

    recent_failures = list(
        qs.filter(created_at__gte=start_7d, status=OutboundEmailStatus.ERROR)
        .select_related('company')
        .order_by('-created_at')[:50]
    )

    # Simple executive health color
    if fail_24h == 0:
        health = 'green'
    elif fail_rate_24h >= 0.20:
        health = 'red'
    else:
        health = 'yellow'

    ctx = {
        'now': now,
        'health': health,
        'sent_24h': sent_24h,
        'fail_24h': fail_24h,
        'total_24h': total_24h,
        'fail_rate_24h_pct': fail_rate_24h_pct,
        'sent_7d': sent_7d,
        'fail_7d': fail_7d,
        'last_error_at': last_error_at,
        'last_error_msg': last_error_msg,
        'failures_by_template': failures_by_template,
        'recent_failures': recent_failures,
    }
    return render(request, 'ops/email_health.html', ctx)
