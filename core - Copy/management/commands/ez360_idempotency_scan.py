from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from accounting.models import JournalEntry


class Command(BaseCommand):
    help = "Scan for idempotency/provenance issues (duplicate or missing JournalEntry sources)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", default=None, help="Optional Company ID (UUID) to scope scan.")
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--fail-fast", action="store_true")
        parser.add_argument("--quiet", action="store_true")

    def handle(self, *args, **opts):
        company_id = (str(opts.get("company_id") or "").strip() or None)
        limit = int(opts.get("limit") or 50)
        fail_fast = bool(opts.get("fail_fast"))
        quiet = bool(opts.get("quiet"))

        qs = JournalEntry.objects.all()
        if company_id:
            qs = qs.filter(company_id=company_id)

        failures: list[str] = []
        warnings: list[str] = []

        # 1) Missing provenance: source_type set but source_id missing
        missing_source_id = qs.filter(~Q(source_type=""), source_id__isnull=True).count()
        if missing_source_id:
            failures.append(f"JournalEntry rows with source_type set but source_id is NULL: {missing_source_id}")

        # 2) Missing provenance: blank source_type (allowed for manual journals, but should be rare)
        blank_source_type = qs.filter(source_type="").count()
        if blank_source_type:
            warnings.append(f"JournalEntry rows with blank source_type (manual/legacy): {blank_source_type}")

        # 3) Duplicate provenance where source_id is NULL: unique_together won't protect NULL
        dup_null = (
            qs.filter(~Q(source_type=""), source_id__isnull=True)
            .values("company_id", "source_type")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .order_by("-n")
        )
        if dup_null.exists():
            top = list(dup_null[: min(limit, 20)])
            failures.append(f"Duplicate JournalEntry provenance for NULL source_id detected in {len(top)} groups (showing up to 20).")
            if not quiet:
                for row in top:
                    self.stdout.write(f"  - company={row['company_id']} source_type={row['source_type']} count={row['n']}")
            if fail_fast:
                raise SystemExit(2)

        # 4) Duplicate provenance with non-null source_id (should be prevented, but scan anyway)
        dup_nonnull = (
            qs.filter(~Q(source_type=""), source_id__isnull=False)
            .values("company_id", "source_type", "source_id")
            .annotate(n=Count("id"))
            .filter(n__gt=1)
            .order_by("-n")
        )
        if dup_nonnull.exists():
            top = list(dup_nonnull[: min(limit, 20)])
            failures.append(f"Duplicate JournalEntry provenance detected (non-null source_id) in {len(top)} groups (showing up to 20).")
            if not quiet:
                for row in top:
                    self.stdout.write(
                        f"  - company={row['company_id']} source_type={row['source_type']} source_id={row['source_id']} count={row['n']}"
                    )

        # Summary
        if not quiet:
            self.stdout.write("\nIdempotency scan summary")
            self.stdout.write(f"  - failures: {len(failures)}")
            self.stdout.write(f"  - warnings: {len(warnings)}")

        for msg in warnings:
            self.stdout.write(self.style.WARNING(f"WARN: {msg}"))
        for msg in failures:
            self.stdout.write(self.style.ERROR(f"ERROR: {msg}"))

        if failures:
            raise SystemExit(2)
