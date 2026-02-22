from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing.models import CompanySubscription, SubscriptionStatus
from ops.models import OpsAlertSource, SiteConfig
from ops.services_alerts import create_ops_alert


class Command(BaseCommand):
    help = "Scan mirrored Stripe subscription projection for staleness/desync signals and raise ops alerts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=0,
            help="Optional staleness window in hours. If omitted/0, uses Ops Site Config.",
        )

    def handle(self, *args, **opts):
        cfg = SiteConfig.get_solo()
        hours = int(opts.get("hours") or 0)
        if hours <= 0:
            hours = int(getattr(cfg, "stripe_mirror_stale_after_hours", 48) or 48)
        window = timedelta(hours=max(1, hours))
        cutoff = timezone.now() - window

        level = getattr(cfg, "stripe_mirror_stale_alert_level", "warn") or "warn"

        qs = CompanySubscription.objects.select_related("company").filter(
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE]
        )

        stale_count = 0
        missing_subid = 0

        for sub in qs.iterator():
            co = sub.company

            if sub.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE} and not (sub.stripe_subscription_id or "").strip():
                missing_subid += 1
                create_ops_alert(
                    title="Stripe mirror missing subscription_id",
                    message="CompanySubscription is ACTIVE/PAST_DUE but has no stripe_subscription_id; billing mirror is incomplete.",
                    level="error",
                    source=OpsAlertSource.STRIPE_WEBHOOK,
                    company=co,
                    details={
                        "company_id": str(co.id),
                        "status": str(sub.status),
                        "stripe_customer_id": str(sub.stripe_customer_id or ""),
                    },
                )

            last = getattr(sub, "last_stripe_event_at", None)
            if not last or last < cutoff:
                stale_count += 1
                create_ops_alert(
                    title="Stripe mirror stale",
                    message=f"No Stripe subscription event has updated the mirror within the last {hours} hours.",
                    level=level,
                    source=OpsAlertSource.STRIPE_WEBHOOK,
                    company=co,
                    details={
                        "company_id": str(co.id),
                        "status": str(sub.status),
                        "stripe_subscription_id": str(sub.stripe_subscription_id or ""),
                        "stripe_customer_id": str(sub.stripe_customer_id or ""),
                        "last_stripe_event_at": (last.isoformat() if last else ""),
                        "cutoff": cutoff.isoformat(),
                    },
                )

        self.stdout.write(self.style.SUCCESS(f"Stripe desync scan complete. stale={stale_count} missing_subid={missing_subid}"))
