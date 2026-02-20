from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from companies.models import Company, EmployeeProfile, EmployeeRole
from .models import SiteConfig


@dataclass(frozen=True)
class OpsNotifyContext:
    company: Company
    owner_email: str
    owner_name: str


def _get_ops_notify_context(company: Company) -> OpsNotifyContext:
    owner = (
        EmployeeProfile.objects.filter(company=company, role=EmployeeRole.OWNER, deleted_at__isnull=True)
        .select_related("user")
        .first()
    )
    owner_email = ""
    owner_name = ""
    if owner and owner.user:
        owner_email = (getattr(owner.user, "email", "") or "").strip()
        owner_name = (getattr(owner, "display_name", "") or "").strip() or (getattr(owner.user, "username", "") or "")
    return OpsNotifyContext(company=company, owner_email=owner_email, owner_name=owner_name)


def _send_ops_email(subject: str, body: str) -> None:
    cfg = SiteConfig.get_solo()
    if not cfg.ops_notify_email_enabled:
        return
    recipients = cfg.notify_recipients_list()
    if not recipients:
        return

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    if not from_email:
        from_email = "notifications@ez360pm.com"

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=from_email,
        to=recipients,
    )
    msg.send(fail_silently=True)


def notify_new_company_signup(*, company: Company) -> None:
    cfg = SiteConfig.get_solo()
    if not (cfg.ops_notify_email_enabled and cfg.ops_notify_on_company_signup):
        return

    ctx = _get_ops_notify_context(company)
    created_at = getattr(company, "created_at", None) or timezone.now()

    subject = f"EZ360PM signup: {company.name}"
    body = "\n".join(
        [
            "A new company was created in EZ360PM.",
            "",
            f"Company: {company.name}",
            f"Company ID: {company.id}",
            f"Owner: {ctx.owner_name or '(unknown)'}",
            f"Owner email: {ctx.owner_email or '(unknown)'}",
            f"Created: {created_at.isoformat()}",
        ]
    )
    _send_ops_email(subject, body)


def notify_subscription_became_active(*, company: Company) -> None:
    cfg = SiteConfig.get_solo()
    if not (cfg.ops_notify_email_enabled and cfg.ops_notify_on_subscription_active):
        return

    ctx = _get_ops_notify_context(company)
    subject = f"EZ360PM conversion: {company.name} is ACTIVE"
    body = "\n".join(
        [
            "A company subscription became ACTIVE in EZ360PM.",
            "",
            f"Company: {company.name}",
            f"Company ID: {company.id}",
            f"Owner: {ctx.owner_name or '(unknown)'}",
            f"Owner email: {ctx.owner_email or '(unknown)'}",
        ]
    )
    _send_ops_email(subject, body)
