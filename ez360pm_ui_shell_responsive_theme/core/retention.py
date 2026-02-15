from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


@dataclass
class PruneResult:
    label: str
    retention_days: int
    cutoff: timezone.datetime
    eligible_count: int
    deleted_count: int


def _cutoff(days: int) -> timezone.datetime:
    return timezone.now() - timedelta(days=max(int(days), 0))


def get_retention_days() -> dict[str, int]:
    return {
        "audit": int(getattr(settings, "EZ360_AUDIT_RETENTION_DAYS", 365)),
        "stripe_webhooks": int(getattr(settings, "EZ360_STRIPE_WEBHOOK_RETENTION_DAYS", 90)),
    }


def prune_audit_events(*, dry_run: bool = True, retention_days: int | None = None) -> PruneResult:
    from audit.models import AuditEvent

    days = int(retention_days if retention_days is not None else get_retention_days()["audit"])
    cutoff = _cutoff(days)

    qs = AuditEvent.objects.filter(created_at__lt=cutoff)
    eligible = qs.count()
    deleted = 0
    if not dry_run and eligible:
        # Bulk delete: bypasses SyncModel soft-delete and removes rows permanently.
        deleted, _ = qs.delete()

    return PruneResult(
        label="audit",
        retention_days=days,
        cutoff=cutoff,
        eligible_count=eligible,
        deleted_count=deleted,
    )


def prune_stripe_webhook_events(*, dry_run: bool = True, retention_days: int | None = None) -> PruneResult:
    from billing.models import BillingWebhookEvent

    days = int(retention_days if retention_days is not None else get_retention_days()["stripe_webhooks"])
    cutoff = _cutoff(days)

    qs = BillingWebhookEvent.objects.filter(received_at__lt=cutoff)
    eligible = qs.count()
    deleted = 0
    if not dry_run and eligible:
        deleted, _ = qs.delete()

    return PruneResult(
        label="stripe_webhooks",
        retention_days=days,
        cutoff=cutoff,
        eligible_count=eligible,
        deleted_count=deleted,
    )


def run_prune_jobs(*, dry_run: bool = True) -> list[PruneResult]:
    """Run all retention prune jobs.

    Returns one PruneResult per job.
    """
    return [
        prune_audit_events(dry_run=dry_run),
        prune_stripe_webhook_events(dry_run=dry_run),
    ]
