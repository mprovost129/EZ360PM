from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.support_mode import get_support_mode


def _health_color(*, failures_24h: int, failure_rate_24h: float, last_failure_at) -> str:
    """Return green/yellow/red for operator chips."""
    try:
        if failures_24h <= 0:
            return "green"
        if failure_rate_24h >= 0.20:
            return "red"
        if last_failure_at and (timezone.now() - last_failure_at) <= timedelta(hours=1):
            return "red"
        return "yellow"
    except Exception:
        return "yellow"


def ops_status(request):
    """Global context for the Executive Ops Center shell.

    Keep this lightweight and safe in production.
    """

    # Environment label
    if getattr(settings, "DEBUG", False):
        env_label = "DEV"
    elif getattr(settings, "IS_RENDER", False):
        env_label = "PROD"
    else:
        env_label = "APP"

    # Stripe mode (best-effort)
    sk = (getattr(settings, "STRIPE_SECRET_KEY", "") or "").strip()
    if sk.startswith("sk_live_"):
        stripe_mode = "LIVE"
    elif sk.startswith("sk_test_"):
        stripe_mode = "TEST"
    else:
        stripe_mode = "OFF"

    # Unresolved ops alerts count (safe fallback)
    open_alerts = None
    try:
        from ops.models import OpsAlertEvent  # local import to avoid app-loading edge cases

        open_alerts = OpsAlertEvent.objects.filter(is_resolved=False).count()
    except Exception:
        open_alerts = None

    # Recent ops actions (ops pages only; best-effort)
    recent_ops_actions = []
    try:
        path = (getattr(request, "path", "") or "")
        user = getattr(request, "user", None)
        is_ops_page = path.startswith("/ops")
        if is_ops_page and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False):
            from ops.models import OpsActionLog

            qs = OpsActionLog.objects.select_related("company").all().order_by("-created_at")[:8]
            recent_ops_actions = [
                {
                    "created_at": a.created_at,
                    "actor_email": a.actor_email,
                    "action": a.action,
                    "summary": a.summary,
                    "company_id": str(a.company_id) if a.company_id else "",
                    "company_name": a.company.name if a.company else "Platform",
                }
                for a in qs
            ]
    except Exception:
        recent_ops_actions = []

    # Support mode strip
    support = get_support_mode(request)
    support_active = bool(getattr(support, "is_active", False))

    support_remaining_min = None
    try:
        expires_at = getattr(support, "expires_at", None)
        if support_active and expires_at:
            delta = expires_at - timezone.now()
            support_remaining_min = max(0, int(delta.total_seconds() // 60))
    except Exception:
        support_remaining_min = None

    # ------------------------------------------------------------
    # Executive telemetry chips (best-effort, never fail page render)
    # ------------------------------------------------------------
    webhook = {
        "health": "unknown",
        "failed_24h": None,
        "failed_7d": None,
        "last_failure_at": None,
    }
    email = {
        "health": "unknown",
        "failed_24h": None,
        "failed_7d": None,
        "last_failure_at": None,
    }
    latest_snapshot_at = None
    mirror_drift_count = None
    backup = {
        "health": "unknown",
        "last_success_at": None,
        "failed_24h": None,
    }

    try:
        now = timezone.now()
        start_24h = now - timedelta(days=1)
        start_7d = now - timedelta(days=7)

        # Webhook health
        from billing.models import BillingWebhookEvent

        wh_failed_24h = BillingWebhookEvent.objects.filter(received_at__gte=start_24h, ok=False).count()
        wh_failed_7d = BillingWebhookEvent.objects.filter(received_at__gte=start_7d, ok=False).count()
        last_wh_fail = BillingWebhookEvent.objects.filter(ok=False).order_by("-received_at").first()
        webhook.update(
            {
                "failed_24h": wh_failed_24h,
                "failed_7d": wh_failed_7d,
                "last_failure_at": (last_wh_fail.received_at if last_wh_fail else None),
            }
        )
        wh_total_24h = BillingWebhookEvent.objects.filter(received_at__gte=start_24h).count()
        wh_rate = (wh_failed_24h / wh_total_24h) if wh_total_24h else 0.0
        webhook["health"] = _health_color(failures_24h=wh_failed_24h, failure_rate_24h=wh_rate, last_failure_at=webhook["last_failure_at"])

        # Email health
        from ops.models import OutboundEmailLog, OutboundEmailStatus

        em_failed_24h = OutboundEmailLog.objects.filter(created_at__gte=start_24h, status=OutboundEmailStatus.ERROR).count()
        em_failed_7d = OutboundEmailLog.objects.filter(created_at__gte=start_7d, status=OutboundEmailStatus.ERROR).count()
        last_em_fail = OutboundEmailLog.objects.filter(status=OutboundEmailStatus.ERROR).order_by("-created_at").first()
        email.update(
            {
                "failed_24h": em_failed_24h,
                "failed_7d": em_failed_7d,
                "last_failure_at": (last_em_fail.created_at if last_em_fail else None),
            }
        )
        em_sent_24h = OutboundEmailLog.objects.filter(created_at__gte=start_24h, status=OutboundEmailStatus.SENT).count()
        em_total_24h = em_sent_24h + em_failed_24h
        em_rate = (em_failed_24h / em_total_24h) if em_total_24h else 0.0
        email["health"] = _health_color(failures_24h=em_failed_24h, failure_rate_24h=em_rate, last_failure_at=email["last_failure_at"])

        # Latest revenue snapshot timestamp
        from ops.models import PlatformRevenueSnapshot

        snap = PlatformRevenueSnapshot.objects.order_by("-date").first()
        latest_snapshot_at = snap.created_at if snap else None

        # Mirror drift count (stale subscription mirror)
        from ops.models import SiteConfig
        from billing.models import CompanySubscription, SubscriptionStatus
        from django.db.models import Q

        cfg = SiteConfig.get_solo()
        stale_hours = int(getattr(cfg, "stripe_mirror_stale_after_hours", 48) or 48)
        cutoff = now - timedelta(hours=max(1, stale_hours))
        mirror_drift_count = CompanySubscription.objects.filter(
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE]
        ).filter(Q(last_stripe_event_at__lt=cutoff) | Q(last_stripe_event_at__isnull=True)).count()

        # Backup health (latest success + 24h failures)
        from ops.models import BackupRun, BackupRunStatus

        last_ok = BackupRun.objects.filter(status=BackupRunStatus.SUCCESS).order_by("-created_at").first()
        failed_24h = BackupRun.objects.filter(created_at__gte=start_24h, status=BackupRunStatus.FAILED).count()
        backup["failed_24h"] = failed_24h
        backup["last_success_at"] = last_ok.created_at if last_ok else None

        # Color policy: green if success within window; red if no success or failure in last hour; yellow otherwise.
        max_age = int(getattr(settings, "BACKUP_VERIFY_MAX_AGE_HOURS", 26) or 26)
        cutoff_backup = now - timedelta(hours=max(1, max_age))
        if not last_ok:
            backup["health"] = "red"
        elif last_ok.created_at < cutoff_backup:
            backup["health"] = "red"
        elif failed_24h > 0:
            backup["health"] = "yellow"
        else:
            backup["health"] = "green"

    except Exception:
        pass

    return {
        "ops_status": {
            "env_label": env_label,
            "stripe_mode": stripe_mode,
            "open_alerts": open_alerts,
            "support": support,
            "support_active": support_active,
            "support_remaining_min": support_remaining_min,
            "recent_ops_actions": recent_ops_actions,
            "webhook": webhook,
            "email": email,
            "latest_snapshot_at": latest_snapshot_at,
            "mirror_drift_count": mirror_drift_count,
            "backup": backup,
        }
    }
