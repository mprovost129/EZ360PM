from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from audit.services import log_event
from core.email_utils import EmailSpec, send_templated_email

from crm.models import Client
from companies.models import Company, EmployeeProfile

from .models import ClientStatementActivity


@dataclass(frozen=True)
class StatementEmailResult:
    sent: bool
    message: str
    to: str | None = None


@dataclass(frozen=True)
class StatementEmailPreview:
    ok: bool
    to: str | None
    subject: str
    html: str
    text: str
    warnings: list[str]
    errors: list[str]


def _company_from_email(company: Company) -> str | None:
    name = (company.email_from_name or "").strip()
    addr = (company.email_from_address or "").strip()
    if addr and name:
        return f"{name} <{addr}>"
    if addr:
        return addr
    return None


def send_statement_to_client(
    *,
    company: Company,
    client: Client,
    actor=None,
    to_email: str | None = None,
    date_from=None,
    date_to=None,
    attach_pdf: bool = False,
    template_variant: str = "sent",
) -> StatementEmailResult:
    if client.deleted_at is not None:
        return StatementEmailResult(sent=False, message="Client is deleted")

    to_addr = (to_email or client.email or "").strip()
    if not to_addr:
        return StatementEmailResult(sent=False, message="Client has no email address")

    spec_or_err = _build_statement_email_spec(
        company=company,
        client=client,
        to_addr=to_addr,
        date_from=date_from,
        date_to=date_to,
        attach_pdf=attach_pdf,
        template_variant=template_variant,
    )
    if isinstance(spec_or_err, str):
        return StatementEmailResult(sent=False, message=spec_or_err)
    spec = spec_or_err

    send_templated_email(spec, fail_silently=False)

    log_event(
        company=company,
        actor=actor,
        event_type="statement.emailed",
        object_type="Client",
        object_id=str(client.id),
        summary=f"Emailed statement to {client.display_label()}",
        payload={"to": to_addr},
    )

    # Phase 7H44: record per-client statement history (best-effort; never blocks).
    try:
        activity, _ = ClientStatementActivity.objects.get_or_create(company=company, client=client)
        activity.last_sent_at = timezone.now()
        activity.last_sent_to = (to_addr or "")[:254]
        activity.last_sent_by = actor if isinstance(actor, EmployeeProfile) else None
        activity.save(update_fields=["last_sent_at", "last_sent_to", "last_sent_by", "updated_at"])
    except Exception:
        pass

    return StatementEmailResult(sent=True, message="Email sent", to=to_addr)


def send_statement_copy_to_actor(
    *,
    company: Company,
    client: Client,
    actor=None,
    to_email: str,
    date_from=None,
    date_to=None,
    attach_pdf: bool = False,
) -> StatementEmailResult:
    """Send a copy of a statement email to the acting user (best-effort).

    This is intentionally separate from the primary client send so:
    - it never blocks collections workflows
    - it can use a slightly different subject line
    """

    to_addr = (to_email or "").strip()
    if not to_addr:
        return StatementEmailResult(sent=False, message="Actor has no email address")

    spec_or_err = _build_statement_email_spec(
        company=company,
        client=client,
        to_addr=to_addr,
        date_from=date_from,
        date_to=date_to,
        attach_pdf=attach_pdf,
        template_variant="sent",
    )
    if isinstance(spec_or_err, str):
        return StatementEmailResult(sent=False, message=spec_or_err)
    spec = spec_or_err
    spec.subject = f"Copy · {spec.subject}"[:200]

    send_templated_email(spec, fail_silently=True)

    log_event(
        company=company,
        actor=actor,
        event_type="statement.emailed_copy",
        object_type="Client",
        object_id=str(client.id),
        summary=f"Emailed statement copy for {client.display_label()}",
        payload={"to": to_addr},
    )

    return StatementEmailResult(sent=True, message="Copy email sent", to=to_addr)


def build_statement_email_preview(
    *,
    company: Company,
    client: Client,
    to_email: str | None = None,
    date_from=None,
    date_to=None,
    attach_pdf: bool = False,
    template_variant: str = "sent",
) -> StatementEmailPreview:
    """Build a statement email preview without sending."""
    warnings: list[str] = []
    errors: list[str] = []

    to_addr = (to_email or client.email or "").strip()
    if not to_addr:
        errors.append("Client has no email address")
        to_addr = ""

    spec_or_err = _build_statement_email_spec(
        company=company,
        client=client,
        to_addr=to_addr or "preview@example.com",
        date_from=date_from,
        date_to=date_to,
        attach_pdf=attach_pdf,
        template_variant=template_variant,
        for_preview=True,
    )
    if isinstance(spec_or_err, str):
        errors.append(spec_or_err)
        return StatementEmailPreview(
            ok=False,
            to=to_addr or None,
            subject=f"Statement · {client.display_label()}",
            html="",
            text="",
            warnings=warnings,
            errors=errors,
        )

    spec = spec_or_err
    try:
        html = render_to_string(spec.template_html, spec.context) if spec.template_html else ""
        text = render_to_string(spec.template_txt, spec.context) if spec.template_txt else ""
    except Exception:
        errors.append("Could not render email templates.")
        html = ""
        text = ""

    # WeasyPrint warnings
    if attach_pdf:
        pdf_bytes = _render_statement_pdf_for_email(company=company, client=client, date_from=date_from, date_to=date_to)
        if not pdf_bytes:
            warnings.append(
                "PDF attachment requires WeasyPrint and system dependencies (Cairo/Pango). Install WeasyPrint to enable attachments."
            )

    site_base_url = (getattr(settings, "SITE_BASE_URL", "") or "").strip()
    if not site_base_url:
        warnings.append("SITE_BASE_URL is not set. The email will not include a 'View statement' link.")

    return StatementEmailPreview(
        ok=not errors,
        to=to_addr or None,
        subject=spec.subject,
        html=html,
        text=text,
        warnings=warnings,
        errors=errors,
    )


def _build_statement_email_spec(
    *,
    company: Company,
    client: Client,
    to_addr: str,
    date_from=None,
    date_to=None,
    attach_pdf: bool = False,
    template_variant: str = "sent",
    for_preview: bool = False,
) -> EmailSpec | str:
    """Build the EmailSpec for statement emails.

    Returns EmailSpec on success; otherwise returns an error string.
    """
    variant = (template_variant or "sent").strip().lower()
    if variant not in {"sent", "friendly", "past_due"}:
        variant = "sent"

    if variant == "friendly":
        subject = f"Friendly reminder · Statement · {client.display_label()}"
        template_html = "emails/statements/statement_friendly.html"
        template_txt = "emails/statements/statement_friendly.txt"
    elif variant == "past_due":
        subject = f"Past due · Statement · {client.display_label()}"
        template_html = "emails/statements/statement_past_due.html"
        template_txt = "emails/statements/statement_past_due.txt"
    else:
        subject = f"Statement · {client.display_label()}"
        template_html = "emails/statements/statement_sent.html"
        template_txt = "emails/statements/statement_sent.txt"

    attachments = None
    if attach_pdf and not for_preview:
        pdf_bytes = _render_statement_pdf_for_email(company=company, client=client, date_from=date_from, date_to=date_to)
        if not pdf_bytes:
            return "PDF attachment requires WeasyPrint and system dependencies (Cairo/Pango). Install WeasyPrint in this environment to enable PDF attachments."
        attachments = [(f"statement_{client.id}.pdf", pdf_bytes, "application/pdf")]

    ctx: dict[str, Any] = {
        "client": client,
        "company": company,
        "site_name": getattr(settings, "SITE_NAME", "EZ360PM"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", "support@ez360pm.com"),
        "statement_url": _build_statement_url(client_id=client.id, date_from=date_from, date_to=date_to),
    }

    return EmailSpec(
        subject=subject,
        to=[to_addr],
        context=ctx,
        template_html=template_html,
        template_txt=template_txt,
        from_email=_company_from_email(company),
        attachments=attachments,
    )


def send_statement_to_client_from_request(
    request,
    *,
    company: Company,
    client: Client,
    to_email: str | None = None,
    date_from=None,
    date_to=None,
    attach_pdf: bool = False,
    template_variant: str = "sent",
) -> StatementEmailResult:
    return send_statement_to_client(
        company=company,
        client=client,
        actor=getattr(request, 'active_employee', None),
        to_email=to_email,
        date_from=date_from,
        date_to=date_to,
        attach_pdf=attach_pdf,
        template_variant=template_variant,
    )


def _render_statement_pdf_for_email(*, company: Company, client: Client, date_from=None, date_to=None) -> bytes | None:
    """Best-effort PDF rendering for email attachments.

    Returns PDF bytes when WeasyPrint is installed; otherwise returns None.
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        return None

    # Import lazily to avoid heavy imports at module load.
    from .views import _money, _statement_rows  # local import; safe for this use

    rows, total_due = _statement_rows(company, client, date_from=date_from, date_to=date_to)

    site_base_url = (getattr(settings, "SITE_BASE_URL", "") or "").strip()
    statement_path = reverse("documents:client_statement", kwargs={"client_pk": client.id})

    html = render_to_string(
        "documents/client_statement_pdf.html",
        {
            "client": client,
            "company": company,
            "rows": rows,
            "total_due_cents": total_due,
            "total_due": _money(total_due),
            "date_from": date_from,
            "date_to": date_to,
            "generated_at": timezone.now(),
            "site_base_url": site_base_url,
            "statement_path": statement_path,
        },
    )

    try:
        return HTML(string=html).write_pdf()
    except Exception:
        return None
