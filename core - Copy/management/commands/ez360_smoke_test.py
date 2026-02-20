from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from companies.models import Company, EmployeeProfile
from crm.models import Client
from projects.models import Project, ProjectBillingType
from timetracking.models import TimeEntry, TimeStatus
from documents.models import Document, DocumentType, DocumentStatus
from payments.models import Payment, PaymentMethod, PaymentStatus


class Command(BaseCommand):
    help = "Run a lightweight end-to-end smoke test (DB only; no Stripe calls)."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", required=True, help="Company ID (UUID) to run the smoke test under.")
        parser.add_argument("--keep", action="store_true", help="Keep the created smoke-test records (default deletes).")

    @transaction.atomic
    def handle(self, *args, **options):
        company_id = int(options["company_id"])
        keep = bool(options["keep"])

        company = Company.objects.filter(id=company_id).first()
        if not company:
            raise CommandError(f"Company {company_id} not found.")

        employee = EmployeeProfile.objects.filter(company=company, deleted_at__isnull=True).order_by("id").first()
        if not employee:
            raise CommandError("No EmployeeProfile found for this company. Create a user/employee first.")

        marker = f"SMOKE-{timezone.now().strftime('%Y%m%d-%H%M%S')}"

        self.stdout.write(self.style.MIGRATE_HEADING("EZ360PM Smoke Test"))
        self.stdout.write(f"Company: {company.id} — {company.name}")
        self.stdout.write(f"Employee: {employee.id} — {employee.user.email}")
        self.stdout.write(f"Marker: {marker}")

        # 1) Client
        client = Client.objects.create(
            company=company,
            first_name="Smoke",
            last_name=f"Test {marker}",
            email=f"smoke+{marker.lower()}@example.com",
        )
        self.stdout.write(self.style.SUCCESS(f"Created Client #{client.id}"))

        # 2) Project
        project = Project.objects.create(
            company=company,
            client=client,
            name=f"Smoke Project {marker}",
            billing_type=ProjectBillingType.HOURLY,
        )
        self.stdout.write(self.style.SUCCESS(f"Created Project #{project.id}"))

        # 3) Time Entry
        start = timezone.now() - timedelta(hours=1)
        end = timezone.now()
        te = TimeEntry.objects.create(
            company=company,
            employee=employee,
            project=project,
            status=TimeStatus.DRAFT,
            started_at=start,
            ended_at=end,
            minutes=60,
            description=f"Smoke time entry {marker}",
            billable=True,
        )
        self.stdout.write(self.style.SUCCESS(f"Created TimeEntry #{te.id}"))

        # 4) Invoice (draft)
        doc = Document.objects.create(
            company=company,
            doc_type=DocumentType.INVOICE,
            status=DocumentStatus.DRAFT,
            project=project,
            title=f"Smoke Invoice {marker}",
            issue_date=timezone.localdate(),
        )
        self.stdout.write(self.style.SUCCESS(f"Created Invoice Document #{doc.id}"))

        # 5) Payment (manual, succeeded)
        pay = Payment.objects.create(
            company=company,
            invoice=doc,
            client=client,
            amount_cents=10000,
            payment_date=timezone.localdate(),
            status=PaymentStatus.SUCCEEDED,
            method=PaymentMethod.CASH,
            notes=f"Smoke payment {marker}",
        )
        self.stdout.write(self.style.SUCCESS(f"Created Payment #{pay.id}"))

        # Invoice immutability check (Phase 6B)
        try:
            from django.core.exceptions import ValidationError
            from documents.models import InvoiceLockedError

            doc.refresh_from_db()
            doc.total_cents = int(doc.total_cents or 0) + 1
            try:
                doc.save()
                raise CommandError("Expected locked invoice mutation to fail, but save() succeeded.")
            except (InvoiceLockedError, ValidationError):
                self.stdout.write(self.style.SUCCESS("Invoice immutability: PASS (blocked document mutation)"))

            from documents.models import DocumentLineItem
            try:
                DocumentLineItem.objects.create(
                    document=doc,
                    sort_order=9999,
                    name="Should fail",
                    qty=1,
                    unit_price_cents=100,
                    line_subtotal_cents=100,
                    tax_cents=0,
                    line_total_cents=100,
                    is_taxable=False,
                )
                raise CommandError("Expected locked invoice line-item creation to fail, but it succeeded.")
            except (InvoiceLockedError, ValidationError):
                self.stdout.write(self.style.SUCCESS("Invoice immutability: PASS (blocked line-item mutation)"))
        except Exception as e:
            raise CommandError(f"Invoice immutability check failed unexpectedly: {e}")

        # Basic assertions
        assert Client.objects.filter(id=client.id, company=company).exists()
        assert Project.objects.filter(id=project.id, company=company).exists()
        assert TimeEntry.objects.filter(id=te.id, company=company).exists()
        assert Document.objects.filter(id=doc.id, company=company).exists()
        assert Payment.objects.filter(id=pay.id, company=company).exists()

        self.stdout.write(self.style.SUCCESS("Smoke test created core records successfully."))

        if not keep:
            # Delete in reverse dependency order
            pay.delete()
            doc.delete()
            te.delete()
            project.delete()
            client.delete()
            self.stdout.write(self.style.WARNING("Deleted smoke-test records (default behavior)."))

        self.stdout.write(self.style.SUCCESS("Smoke test complete."))
