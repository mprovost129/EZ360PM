from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from companies.models import Company
from crm.models import Client
from projects.models import Project, ProjectBillingType
from catalog.models import CatalogItem, CatalogItemType, TaxBehavior
from documents.models import Document, DocumentLineItem, DocumentType, DocumentStatus
from expenses.models import Expense, ExpenseStatus, Merchant


class Command(BaseCommand):
    help = "Seed minimal QA data for manual testing (safe to run multiple times)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--company",
            default="EZ360PM Demo Co",
            help="Company name to create/use.",
        )
        parser.add_argument(
            "--owner-email",
            default="owner@example.com",
            help="Owner user email.",
        )
        parser.add_argument(
            "--staff-email",
            default="staff@example.com",
            help="Staff user email.",
        )
        parser.add_argument(
            "--password",
            default="Password123!",
            help="Password to set for created users.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing seeded objects for this company name before reseeding.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        company_name: str = options["company"]
        owner_email: str = options["owner_email"]
        staff_email: str = options["staff_email"]
        password: str = options["password"]
        reset: bool = bool(options["reset"])

        User = get_user_model()

        company, _created = Company.objects.get_or_create(name=company_name)

        if reset:
            # Delete by company scope; keep the company row to preserve FK constraints elsewhere.
            DocumentLineItem.objects.filter(document__company=company).delete()
            Document.objects.filter(company=company).delete()
            Expense.objects.filter(company=company).delete()
            Project.objects.filter(company=company).delete()
            Client.objects.filter(company=company).delete()
            CatalogItem.objects.filter(company=company).delete()

        owner, _ = User.objects.get_or_create(
            email=owner_email,
            defaults={"username": "owner", "is_staff": True, "is_superuser": True},
        )
        if not owner.has_usable_password():
            owner.set_password(password)
        else:
            owner.set_password(password)
        owner.is_active = True
        owner.save()

        staff, _ = User.objects.get_or_create(
            email=staff_email,
            defaults={"username": "staff", "is_staff": False, "is_superuser": False},
        )
        staff.set_password(password)
        staff.is_active = True
        staff.save()

        # Note: employee profile / company membership model varies by project.
        # We keep this seed minimal and company-scoped. If your project enforces
        # membership linking, you can extend this command to create memberships.

        client1, _ = Client.objects.get_or_create(
            company=company,
            email="client1@example.com",
            defaults={"first_name": "Jane", "last_name": "Client", "company_name": "Client Co"},
        )
        client2, _ = Client.objects.get_or_create(
            company=company,
            email="client2@example.com",
            defaults={"first_name": "John", "last_name": "Buyer", "company_name": "Buyer LLC"},
        )

        project1, _ = Project.objects.get_or_create(
            company=company,
            project_number="2401-001",
            defaults={
                "name": "Kitchen Remodel",
                "client": client1,
                "billing_type": ProjectBillingType.HOURLY,
                "hourly_rate_cents": 12500,
            },
        )
        project2, _ = Project.objects.get_or_create(
            company=company,
            project_number="2401-002",
            defaults={
                "name": "Deck Addition",
                "client": client2,
                "billing_type": ProjectBillingType.FLAT,
                "flat_fee_cents": 950000,
            },
        )

        service, _ = CatalogItem.objects.get_or_create(
            company=company,
            name="Design Services",
            defaults={
                "item_type": CatalogItemType.SERVICE,
                "tax_behavior": TaxBehavior.NON_TAXABLE,
                "unit_price_cents": 12500,
            },
        )

        # Create a draft invoice with 2 line items.
        invoice, _ = Document.objects.get_or_create(
            company=company,
            doc_type=DocumentType.INVOICE,
            number="INV-0001",
            defaults={
                "status": DocumentStatus.DRAFT,
                "client": client1,
                "project": project1,
                "issue_date": timezone.localdate(),
                "due_date": timezone.localdate(),
                "notes": "Thanks for your business!",
            },
        )

        if invoice.line_items.count() == 0:
            DocumentLineItem.objects.create(
                document=invoice,
                sort_order=1,
                catalog_item=service,
                name="Initial consultation",
                description="Scope, measurements, and design kickoff.",
                qty=Decimal("2.00"),
                unit_price_cents=12500,
            )
            DocumentLineItem.objects.create(
                document=invoice,
                sort_order=2,
                catalog_item=service,
                name="Design drafting",
                description="Drafting and revisions.",
                qty=Decimal("6.00"),
                unit_price_cents=12500,
            )

        Expense.objects.get_or_create(
            company=company,
            status=ExpenseStatus.SUBMITTED,
            # merchant_name is not a field; must use merchant ForeignKey
            # This assumes a Merchant object for 'Home Depot' exists or is created above
            # You may need to fetch or create the Merchant first
            merchant=Merchant.objects.get_or_create(company=company, name="Home Depot")[0],
            amount_cents=4599,
            defaults={
                "date": timezone.localdate(),
                "description": "Seeded QA expense",
            },
        )

        self.stdout.write(self.style.SUCCESS("Seeded QA data."))
        self.stdout.write("Login credentials:")
        self.stdout.write(f"  Owner: {owner_email} / {password}")
        self.stdout.write(f"  Staff: {staff_email} / {password}")
        self.stdout.write(f"Company: {company_name}")
