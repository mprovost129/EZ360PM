from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ops.models import OpsAlertEvent, SiteConfig


class Command(BaseCommand):
    help = "Prune resolved Ops Alerts older than N days (best-effort)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None, help="Override retention days (default from Ops SiteConfig).")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting.")

    def handle(self, *args, **options):
        cfg = SiteConfig.get_solo()
        days = options.get("days")
        if not days:
            days = int(cfg.ops_alert_prune_resolved_after_days or 30)
        days = max(1, int(days))

        cutoff = timezone.now() - timedelta(days=days)
        qs = OpsAlertEvent.objects.filter(is_resolved=True, resolved_at__isnull=False, resolved_at__lt=cutoff)
        count = qs.count()

        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING(f"DRY RUN: would delete {count} resolved alerts older than {days} days"))
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} resolved alerts older than {days} days"))
