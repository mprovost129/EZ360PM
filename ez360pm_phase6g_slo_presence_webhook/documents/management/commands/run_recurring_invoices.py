from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from companies.models import Company

from documents.services_recurring import generate_due_invoices_for_company


class Command(BaseCommand):
    help = "Generate due invoices for all companies that have active recurring plans."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company-id",
            dest="company_id",
            default=None,
            help="Optional: run for a single company id.",
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        company_id = options.get("company_id")
        qs = Company.objects.all().order_by("created_at")
        if company_id:
            qs = qs.filter(id=company_id)

        total_created = 0
        total_skipped = 0

        for company in qs:
            results = generate_due_invoices_for_company(company, run_date=today)
            for r in results:
                if r.skipped:
                    total_skipped += 1
                else:
                    total_created += 1

        self.stdout.write(self.style.SUCCESS(f"Recurring invoices complete: created={total_created} skipped={total_skipped}"))
