from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from companies.models import Company, EmployeeProfile, EmployeeRole
from companies.services import ACTIVE_COMPANY_SESSION_KEY


class CompanyContextAutoSelectTests(TestCase):
    """Regression tests for active-company session behavior.

    These protect a launch-blocking invariant: any company-scoped page should
    auto-select a valid active company for a logged-in employee.
    """

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="pass12345",
        )
        # Email verification is commonly enforced in middleware.
        if hasattr(self.user, "email_verified"):
            self.user.email_verified = True
            self.user.save(update_fields=["email_verified"])

        self.company = Company.objects.create(name="Acme Co")
        self.emp = EmployeeProfile.objects.create(
            company=self.company,
            user=self.user,
            username_public="testuser",
            role=EmployeeRole.OWNER,
        )

    def test_company_context_auto_selects_company_when_missing(self):
        self.client.force_login(self.user)

        # Ensure session starts without an active company.
        session = self.client.session
        session.pop(ACTIVE_COMPANY_SESSION_KEY, None)
        session.save()

        url = reverse("documents:invoice_list")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        # After hitting a company-scoped page, session should be set.
        session = self.client.session
        self.assertEqual(str(session.get(ACTIVE_COMPANY_SESSION_KEY)), str(self.company.id))
