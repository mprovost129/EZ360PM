from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand, CommandError

from companies.models import Company
from payables.services_recurring import run_due_recurring_bills


class Command(BaseCommand):
    help = "Generate due bills for active RecurringBillPlans."

    def add_arguments(self, parser):
        parser.add_argument(
            "--company",
            dest="company",
            default=None,
            help="Optional company UUID. If provided, only runs plans for that company.",
        )

    def handle(self, *args, **options):
        company_raw = options.get("company")
        company = None

        if company_raw:
            try:
                company_uuid = uuid.UUID(str(company_raw))
            except Exception as exc:
                raise CommandError("Invalid company UUID.") from exc
            company = Company.objects.filter(id=company_uuid).first()
            if company is None:
                raise CommandError("Company not found.")

        created = run_due_recurring_bills(company=company, actor=None)

        if company is not None:
            self.stdout.write(self.style.SUCCESS(f"Created {created} bills for company {company.id}."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Created {created} bills."))
