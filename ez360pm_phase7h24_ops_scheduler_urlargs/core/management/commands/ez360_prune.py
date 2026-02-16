from __future__ import annotations

from django.core.management.base import BaseCommand

from core.retention import run_prune_jobs


class Command(BaseCommand):
    help = "Prune old operational data (audit log + Stripe webhook events) per retention policy."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually delete rows. If omitted, runs in dry-run mode and prints counts only.",
        )

    def handle(self, *args, **options):
        dry_run = not bool(options.get("execute"))

        results = run_prune_jobs(dry_run=dry_run)
        for r in results:
            mode = "DRY-RUN" if dry_run else "DELETED"
            self.stdout.write(
                f"[{mode}] {r.label}: retention_days={r.retention_days} cutoff={r.cutoff.isoformat()} eligible={r.eligible_count} deleted={r.deleted_count}"
            )

        # Non-zero exit code not needed; pruning is best-effort.
