from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ops.models import OpsAlertSnooze, SiteConfig


class Command(BaseCommand):
    help = "Prune expired Ops Alert Snoozes older than N days (best-effort)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None, help="Override retention days (default from Ops SiteConfig).")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting.")

    def handle(self, *args, **options):
        cfg = SiteConfig.get_solo()
        days = options.get("days")
        if not days:
            days = int(cfg.ops_snooze_prune_after_days or 30)
        days = max(1, int(days))

        cutoff = timezone.now() - timedelta(days=days)
        qs = OpsAlertSnooze.objects.filter(snoozed_until__lt=cutoff)
        count = qs.count()

        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING(f"DRY RUN: would delete {count} snoozes expired before {cutoff:%Y-%m-%d %H:%M}"))
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} snoozes expired before {cutoff:%Y-%m-%d %H:%M}"))
