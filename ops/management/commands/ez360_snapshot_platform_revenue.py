from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from billing.models import BillingInterval, CompanySubscription, PlanCatalog, SeatAddonConfig, SubscriptionStatus, BillingWebhookEvent
from ops.models import CompanyLifecycleEvent, LifecycleEventType, PlatformRevenueSnapshot, CompanyRiskSnapshot, SiteConfig
from ops.services_risk import compute_tenant_risk


def _to_cents(amount: Decimal) -> int:
    if amount is None:
        return 0
    q = (amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    return int(q * 100)


def _plan_price_cents(plan: str, interval: str) -> int:
    try:
        cat = PlanCatalog.objects.get(code=plan)
    except Exception:
        return 0
    if interval == BillingInterval.YEAR:
        return _to_cents(cat.annual_price)
    return _to_cents(cat.monthly_price)


def _seat_price_cents(interval: str) -> int:
    try:
        seat = SeatAddonConfig.objects.get(pk=1)
    except Exception:
        seat = None
    if not seat:
        return 0
    if interval == BillingInterval.YEAR:
        return _to_cents(seat.annual_price)
    return _to_cents(seat.monthly_price)


def compute_subscription_mrr_arr_cents(sub: CompanySubscription) -> tuple[int, int]:
    """Compute MRR/ARR (cents) for a mirrored subscription.

    Stripe is the authority; this uses the mirrored fields + DB-backed pricing catalog.

    Rules:
    - Only ACTIVE contributes to MRR/ARR.
    - Exclude trialing.
    - Exclude cancel_at_period_end (counts as revenue-at-risk instead, elsewhere).
    - Exclude comped.
    """

    if not sub:
        return (0, 0)
    if sub.is_comped_active():
        return (0, 0)
    if (sub.status or "") != SubscriptionStatus.ACTIVE:
        return (0, 0)
    if sub.stripe_cancel_at_period_end:
        return (0, 0)

    interval = sub.billing_interval or BillingInterval.MONTH
    base = _plan_price_cents(sub.plan, interval)
    seats = _seat_price_cents(interval) * int(sub.extra_seats or 0)
    total = base + seats

    if interval == BillingInterval.YEAR:
        # total is annual cents; convert to monthly for MRR.
        mrr = int(Decimal(total) / Decimal(12))
        arr = total
    else:
        mrr = total
        arr = total * 12

    # Apply informational discount tracking if present (Stripe promo codes should
    # already be reflected in Stripe invoices, but v1 uses this for ops reporting).
    try:
        if sub.discount_is_active():
            pct = int(sub.discount_percent or 0)
            pct = max(0, min(100, pct))
            if pct:
                mrr = int(Decimal(mrr) * (Decimal(100 - pct) / Decimal(100)))
                arr = int(Decimal(arr) * (Decimal(100 - pct) / Decimal(100)))
    except Exception:
        pass

    return (max(0, mrr), max(0, arr))


class Command(BaseCommand):
    help = "Create (or refresh) today's PlatformRevenueSnapshot from mirrored Stripe subscription state."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, default="", help="Snapshot date YYYY-MM-DD (default: today)")
        parser.add_argument("--force", action="store_true", help="Overwrite existing snapshot for the date")

    @transaction.atomic
    def handle(self, *args, **options):
        date_str = (options.get("date") or "").strip()
        force = bool(options.get("force"))

        if date_str:
            snap_date = timezone.datetime.fromisoformat(date_str).date()
        else:
            snap_date = timezone.localdate()

        if not force and PlatformRevenueSnapshot.objects.filter(date=snap_date).exists():
            self.stdout.write(self.style.WARNING(f"Snapshot already exists for {snap_date}. Use --force to overwrite."))
            return

        if force:
            PlatformRevenueSnapshot.objects.filter(date=snap_date).delete()

        now = timezone.now()
        start_30 = now - timedelta(days=30)

        subs = CompanySubscription.objects.select_related("company").all()

        # Risk scoring inputs (shared with ops companies directory)
        cfg = SiteConfig.get_solo()
        payment_fail_types = ["invoice.payment_failed", "payment_intent.payment_failed", "charge.failed"]
        risk_payment_days = int(getattr(cfg, "risk_payment_failed_window_days", 14) or 14)
        risk_payment_days = max(1, min(90, risk_payment_days))
        start_fail_window = now - timedelta(days=risk_payment_days)
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

        active = subs.filter(status=SubscriptionStatus.ACTIVE).count()
        trialing = subs.filter(status=SubscriptionStatus.TRIALING).count()
        past_due = subs.filter(status=SubscriptionStatus.PAST_DUE).count()
        canceled = subs.filter(status__in=[SubscriptionStatus.CANCELED, SubscriptionStatus.ENDED]).count()

        mrr_cents = 0
        arr_cents = 0
        revenue_at_risk_cents = 0

        # Risk rules: past_due + cancel_at_period_end + trials ending soon.
        soon = timezone.now() + timedelta(days=7)

        for sub in subs:
            mrr, arr = compute_subscription_mrr_arr_cents(sub)
            mrr_cents += mrr
            arr_cents += arr

            if sub.is_comped_active():
                continue

            # Revenue at risk signals
            if sub.status == SubscriptionStatus.PAST_DUE:
                revenue_at_risk_cents += max(0, mrr)
            if sub.status == SubscriptionStatus.ACTIVE and sub.stripe_cancel_at_period_end:
                # Use computed MRR ignoring cancel flag
                # (recompute quickly by temporarily treating as not canceled)
                try:
                    original = sub.stripe_cancel_at_period_end
                    sub.stripe_cancel_at_period_end = False
                    mrr2, _ = compute_subscription_mrr_arr_cents(sub)
                    revenue_at_risk_cents += max(0, mrr2)
                finally:
                    sub.stripe_cancel_at_period_end = original
            if sub.status == SubscriptionStatus.TRIALING and sub.trial_ends_at and sub.trial_ends_at <= soon:
                # Estimate the risk based on intended plan/interval.
                interval = sub.billing_interval or BillingInterval.MONTH
                est = _plan_price_cents(sub.plan, interval)
                if interval == BillingInterval.YEAR:
                    est = int(Decimal(est) / Decimal(12))
                revenue_at_risk_cents += max(0, est)

        # Lifecycle metrics (30d). These will become authoritative as we log them in webhooks.
        new_30 = CompanyLifecycleEvent.objects.filter(
            event_type=LifecycleEventType.SUBSCRIPTION_STARTED,
            occurred_at__gte=start_30,
        ).count()
        churn_30 = CompanyLifecycleEvent.objects.filter(
            event_type=LifecycleEventType.SUBSCRIPTION_CANCELED,
            occurred_at__gte=start_30,
        ).count()
        react_30 = CompanyLifecycleEvent.objects.filter(
            event_type=LifecycleEventType.SUBSCRIPTION_REACTIVATED,
            occurred_at__gte=start_30,
        ).count()

        snap = PlatformRevenueSnapshot.objects.create(
            date=snap_date,
            active_subscriptions=active,
            trialing_subscriptions=trialing,
            past_due_subscriptions=past_due,
            canceled_subscriptions=canceled,
            mrr_cents=mrr_cents,
            arr_cents=arr_cents,
            new_subscriptions_30d=new_30,
            churned_30d=churn_30,
            reactivations_30d=react_30,
            net_growth_30d=(new_30 + react_30 - churn_30),
            revenue_at_risk_cents=revenue_at_risk_cents,
        )

        # Company risk snapshots (best-effort). This supports risk trend charts in Ops.
        try:
            CompanyRiskSnapshot.objects.filter(date=snap_date).delete()
            batch = []
            for sub in subs:
                company = sub.company
                risk = compute_tenant_risk(
                    company,
                    sub,
                    cfg=cfg,
                    now=now,
                    failed_customer_ids=failed_customer_ids_14d,
                    failed_subscription_ids=failed_sub_ids_14d,
                )
                batch.append(
                    CompanyRiskSnapshot(
                        date=snap_date,
                        company=company,
                        risk_score=int(risk.get("score") or 0),
                        risk_level=str(risk.get("level") or ""),
                        flags=list(risk.get("flags") or []),
                        breakdown=list(risk.get("breakdown") or []),
                    )
                )
            if batch:
                CompanyRiskSnapshot.objects.bulk_create(batch, batch_size=500)
        except Exception:
            pass

        # Best-effort: raise ops alerts if the Stripe mirror looks stale (webhook drift).
        try:
            from datetime import timedelta
            from ops.services_alerts import create_ops_alert
            from ops.models import OpsAlertSource, SiteConfig

            cfg = SiteConfig.get_solo()
            hours = int(getattr(cfg, "stripe_mirror_stale_after_hours", 48) or 48)
            level = getattr(cfg, "stripe_mirror_stale_alert_level", "warn") or "warn"
            cutoff = timezone.now() - timedelta(hours=max(1, hours))
            drift_qs = subs.filter(status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE])
            for s in drift_qs:
                last = getattr(s, "last_stripe_event_at", None)
                if not last or last < cutoff:
                    create_ops_alert(
                        title="Stripe mirror stale",
                        message=f"No Stripe subscription event has updated the mirror within the last {hours} hours.",
                        level=level,
                        source=OpsAlertSource.STRIPE_WEBHOOK,
                        company=s.company,
                        details={
                            "company_id": str(s.company_id),
                            "status": str(s.status),
                            "stripe_subscription_id": str(s.stripe_subscription_id or ""),
                            "stripe_customer_id": str(s.stripe_customer_id or ""),
                            "last_stripe_event_at": (last.isoformat() if last else ""),
                            "cutoff": cutoff.isoformat(),
                            "stale_after_hours": hours,
                        },
                    )
        except Exception:
            pass

        self.stdout.write(self.style.SUCCESS(f"Created snapshot {snap.date} (MRR ${mrr_cents/100:.2f})"))
