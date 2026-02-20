from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from companies.models import Company, EmployeeProfile, EmployeeRole
from companies.services import ACTIVE_COMPANY_SESSION_KEY
from documents.models import Document, DocumentType


class DocumentCompanyIsolationTests(TestCase):
    """Ensure document routes cannot leak across companies."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="isolation@example.com",
            username="isolation",
            password="pass12345",
        )
        if hasattr(self.user, "email_verified"):
            self.user.email_verified = True
            self.user.save(update_fields=["email_verified"])

        self.company_a = Company.objects.create(name="Company A")
        self.company_b = Company.objects.create(name="Company B")

        self.emp_a = EmployeeProfile.objects.create(
            company=self.company_a,
            user=self.user,
            username_public="isolation",
            role=EmployeeRole.OWNER,
        )

        # A document in Company B (user is NOT a member of Company B)
        self.doc_b = Document.objects.create(company=self.company_b, doc_type=DocumentType.INVOICE)

    def _login_and_set_active_company(self, company):
        self.client.force_login(self.user)
        session = self.client.session
        session[ACTIVE_COMPANY_SESSION_KEY] = str(company.id)
        session.save()

    def test_invoice_edit_returns_404_for_other_company_document(self):
        self._login_and_set_active_company(self.company_a)
        url = reverse("documents:invoice_edit", kwargs={"pk": self.doc_b.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_invoice_print_returns_404_for_other_company_document(self):
        self._login_and_set_active_company(self.company_a)
        url = reverse("documents:invoice_print", kwargs={"pk": self.doc_b.id})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


from decimal import Decimal

from documents.models import DocumentLineItem
from documents.services import recalc_document_totals


class DocumentTaxRecalcTests(TestCase):
    def test_sales_tax_percent_recomputes_taxable_lines_server_side(self):
        company = Company.objects.create(name="Tax Co")
        doc = Document.objects.create(
            company=company,
            doc_type=DocumentType.INVOICE,
            sales_tax_percent=Decimal("5.000"),
        )

        li = DocumentLineItem.objects.create(
            document=doc,
            sort_order=1,
            name="Service A",
            qty=Decimal("2.00"),
            unit_price_cents=10000,  # $100.00
            line_subtotal_cents=20000,
            tax_cents=0,
            line_total_cents=20000,
            is_taxable=True,
        )

        recalc_document_totals(doc)
        li.refresh_from_db()
        doc.refresh_from_db()

        # 5% of $200.00 = $10.00
        self.assertEqual(li.tax_cents, 1000)
        self.assertEqual(li.line_total_cents, 21000)
        self.assertEqual(doc.tax_cents, 1000)
        self.assertEqual(doc.total_cents, 21000)
