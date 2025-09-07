# helpcenter/views.py
"""
Public Help Center FAQ.
Accessible to both authenticated and anonymous users.
"""

from __future__ import annotations

from typing import Any
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _


def index(request: HttpRequest) -> HttpResponse:
    sections: list[dict[str, Any]] = [
        {
            "slug": "getting-started",
            "title": _("Getting Started"),
            "items": [
                {
                    "q": _("How do I create my first project?"),
                    "a": _("Go to <em>Projects</em> → <em>New Project</em>, then fill in name, client, and budget."),
                },
                {
                    "q": _("How do I invite a team member?"),
                    "a": _("Go to <em>Company</em> → <em>Team</em> → <em>Invite</em>, and enter their email."),
                },
            ],
        },
        {
            "slug": "billing",
            "title": _("Billing & Subscriptions"),
            "items": [
                {
                    "q": _("How do I pick a plan?"),
                    "a": _("Open <em>Plans</em> under Billing and choose the tier that fits."),
                },
                {
                    "q": _("How do I cancel or change my plan?"),
                    "a": _("Use the <em>Customer Portal</em> from the Plans page."),
                },
            ],
        },
        {
            "slug": "invoices",
            "title": _("Invoices & Payments"),
            "items": [
                {
                    "q": _("How do I email an invoice?"),
                    "a": _("Open an invoice and click <em>Email</em>."),
                },
                {
                    "q": _("How do I record a payment?"),
                    "a": _("Open an invoice and click <em>Add Payment</em>."),
                },
            ],
        },
    ]
    return render(request, "helpcenter/index.html", {"sections": sections})
