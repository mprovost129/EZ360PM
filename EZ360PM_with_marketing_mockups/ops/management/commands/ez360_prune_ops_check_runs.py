from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ops.models import OpsCheckRun


class Command(BaseCommand):
    help = "Prune old OpsCheckRun evidence rows (retention management)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete runs older than N days (default: 30).",
        )
        parser.add_argument(
            "--keep-per-kind",
            type=int,
            default=200,
            help="Also keep at least the most recent N runs per kind (default: 200).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting.")

    def handle(self, *args, **opts):
        days = int(opts.get("days") or 30)
        keep_per_kind = int(opts.get("keep_per_kind") or 200)
        dry_run = bool(opts.get("dry_run"))

        cutoff = timezone.now() - timedelta(days=max(days, 1))

        # Primary delete set: older than cutoff.
        qs_old = OpsCheckRun.objects.filter(created_at__lt=cutoff)
        old_count = qs_old.count()

        # Secondary protection: keep last N per kind even if old.
        protect_ids: set[int] = set()
        if keep_per_kind > 0:
            kinds = OpsCheckRun.objects.values_list("kind", flat=True).distinct()
            for k in kinds:
                ids = list(
                    OpsCheckRun.objects.filter(kind=k)
                    .order_by("-created_at")
                    .values_list("id", flat=True)[:keep_per_kind]
                )
                protect_ids.update(ids)

        qs_delete = qs_old
        if protect_ids:
            qs_delete = qs_delete.exclude(id__in=protect_ids)

        delete_count = qs_delete.count()

        if dry_run:
            self.stdout.write(
                f"DRY RUN: {old_count} runs older than {days}d; would delete {delete_count} after protecting {len(protect_ids)} recent-per-kind."
            )
            return

        deleted = qs_delete.delete()
        # deleted is (count, details)
        self.stdout.write(
            f"OK: deleted {deleted[0]} OpsCheckRun rows (older than {days}d; protected {len(protect_ids)} recent-per-kind)."
        )
