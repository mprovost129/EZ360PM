from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from companies.models import Company


@dataclass(frozen=True)
class OnboardingStep:
    key: str
    title: str
    description: str
    url_name: str
    done: bool


def _company_profile_done(company: Company) -> bool:
    return bool(
        company.email_from_address.strip()
        or company.address1.strip()
        or company.city.strip()
        or company.state.strip()
        or company.zip_code.strip()
        or company.logo
    )


def build_onboarding_checklist(company: Company) -> List[OnboardingStep]:
    """Compute a simple v1 onboarding checklist from live data.

    This is intentionally *computed* rather than stored so it stays correct even if
    customers import data in bulk.
    """

    # Local imports to avoid app import cycles.
    from crm.models import Client
    from projects.models import Project
    from timetracking.models import TimeEntry
    from documents.models import Document, DocumentType
    from payments.models import Payment, PaymentStatus

    alive = {"deleted_at__isnull": True}

    clients_count = Client.objects.filter(company=company, **alive).count()
    projects_count = Project.objects.filter(company=company, **alive).count()
    time_count = TimeEntry.objects.filter(company=company, **alive).count()
    invoices_count = Document.objects.filter(
        company=company, doc_type=DocumentType.INVOICE, **alive
    ).count()
    payments_count = Payment.objects.filter(
        company=company, status=PaymentStatus.SUCCEEDED, **alive
    ).count()

    steps: List[OnboardingStep] = [
        OnboardingStep(
            key="company_profile",
            title="Complete company profile",
            description="Add your address, logo, and email-from details.",
            url_name="companies:settings",
            done=_company_profile_done(company),
        ),
        OnboardingStep(
            key="clients",
            title="Add your first client",
            description="Create a client or import from CSV.",
            url_name="crm:client_create",
            done=clients_count > 0,
        ),
        OnboardingStep(
            key="projects",
            title="Create a project",
            description="Projects organize time, documents, and billing.",
            url_name="projects:project_create",
            done=projects_count > 0,
        ),
        OnboardingStep(
            key="time",
            title="Log time",
            description="Track time so you can bill accurately.",
            url_name="timetracking:entry_create",
            done=time_count > 0,
        ),
        OnboardingStep(
            key="invoice",
            title="Create an invoice",
            description="Use the wizard to generate a professional invoice.",
            url_name="documents:invoice_wizard",
            done=invoices_count > 0,
        ),
        OnboardingStep(
            key="payment",
            title="Record a payment",
            description="Enter a payment or accept one via Stripe Checkout.",
            url_name="payments:payment_create",
            done=payments_count > 0,
        ),
    ]

    return steps


def build_onboarding_checklist_fast(company: Company) -> List[OnboardingStep]:
    """Like build_onboarding_checklist(), but optimized for global context.

    This function is used by the app-wide context processor to power lightweight
    onboarding UI in the sidebar/topbar.

    It uses `.exists()` instead of `.count()` to avoid unnecessary work.
    """

    # Local imports to avoid app import cycles.
    from crm.models import Client
    from projects.models import Project
    from timetracking.models import TimeEntry
    from documents.models import Document, DocumentType
    from payments.models import Payment, PaymentStatus

    alive = {"deleted_at__isnull": True}

    has_client = Client.objects.filter(company=company, **alive).exists()
    has_project = Project.objects.filter(company=company, **alive).exists()
    has_time = TimeEntry.objects.filter(company=company, **alive).exists()
    has_invoice = Document.objects.filter(company=company, doc_type=DocumentType.INVOICE, **alive).exists()
    has_payment = Payment.objects.filter(company=company, status=PaymentStatus.SUCCEEDED, **alive).exists()

    return [
        OnboardingStep(
            key="company_profile",
            title="Complete company profile",
            description="Add your address, logo, and email-from details.",
            url_name="companies:settings",
            done=_company_profile_done(company),
        ),
        OnboardingStep(
            key="clients",
            title="Add your first client",
            description="Create a client or import from CSV.",
            url_name="crm:client_create",
            done=has_client,
        ),
        OnboardingStep(
            key="projects",
            title="Create a project",
            description="Projects organize time, documents, and billing.",
            url_name="projects:project_create",
            done=has_project,
        ),
        OnboardingStep(
            key="time",
            title="Log time",
            description="Track time so you can bill accurately.",
            url_name="timetracking:entry_create",
            done=has_time,
        ),
        OnboardingStep(
            key="invoice",
            title="Create an invoice",
            description="Use the wizard to generate a professional invoice.",
            url_name="documents:invoice_wizard",
            done=has_invoice,
        ),
        OnboardingStep(
            key="payment",
            title="Record a payment",
            description="Enter a payment or accept one via Stripe Checkout.",
            url_name="payments:payment_create",
            done=has_payment,
        ),
    ]


def onboarding_progress(steps: List[OnboardingStep]) -> dict:
    total = len(steps) or 1
    done = sum(1 for s in steps if s.done)
    pct = int(round((done / total) * 100))
    next_step: Optional[OnboardingStep] = next((s for s in steps if not s.done), None)
    return {
        "total": total,
        "done": done,
        "pct": pct,
        "next": next_step,
    }
