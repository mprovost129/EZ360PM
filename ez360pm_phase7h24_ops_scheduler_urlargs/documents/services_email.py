from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings

from audit.services import log_event
from core.email_utils import EmailSpec, send_templated_email

from .models import Document, DocumentType


@dataclass(frozen=True)
class DocumentEmailResult:
    sent: bool
    message: str
    to: str | None = None


def _company_from_email(doc: Document) -> str | None:
    """Build a friendly 'From' header using Company branding when available."""
    company = doc.company
    name = (company.email_from_name or "").strip()
    addr = (company.email_from_address or "").strip()
    if addr and name:
        return f"{name} <{addr}>"
    if addr:
        return addr
    return None


def _doc_label(doc: Document) -> str:
    if doc.doc_type == DocumentType.INVOICE:
        return "Invoice"
    if doc.doc_type == DocumentType.ESTIMATE:
        return "Estimate"
    if doc.doc_type == DocumentType.PROPOSAL:
        return "Proposal"
    return "Document"


def send_document_to_client(doc: Document, *, actor=None, to_email: str | None = None) -> DocumentEmailResult:
    """Send a document email to the client using templates.

    Notes:
    - This is an outbound *notification* email (not a portal).
    - Uses Company.email_from_* if set; otherwise DEFAULT_FROM_EMAIL.
    """
    if doc.deleted_at is not None:
        return DocumentEmailResult(sent=False, message="Document is deleted")

    client = doc.client
    if not client:
        return DocumentEmailResult(sent=False, message="No client selected")

    to_addr = (to_email or client.email or "").strip()
    if not to_addr:
        return DocumentEmailResult(sent=False, message="Client has no email address")

    if not doc.number:
        # Caller should have allocated number prior to send.
        return DocumentEmailResult(sent=False, message="Document has no number yet (save first)")

    label = _doc_label(doc)
    subject = f"{label} {doc.number}"
    if doc.title:
        subject = f"{label} {doc.number} · {doc.title}".strip()

    ctx: dict[str, Any] = {
        "doc": doc,
        "client": client,
        "company": doc.company,
        "label": label,
        "site_name": getattr(settings, "SITE_NAME", "EZ360PM"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", "support@ez360pm.com"),
    }

    spec = EmailSpec(
        subject=subject,
        to=[to_addr],
        context=ctx,
        template_html="emails/documents/document_sent.html",
        template_txt="emails/documents/document_sent.txt",
        from_email=_company_from_email(doc),
    )

    send_templated_email(spec, fail_silently=False)

    # Audit log
    log_event(
        company=doc.company,
        actor=actor,
        event_type=f"{doc.doc_type}.emailed",
        object_type="Document",
        object_id=str(doc.id),
        summary=f"Emailed {label.lower()} {doc.number}",
        payload={"to": to_addr},
    )

    return DocumentEmailResult(sent=True, message="Email sent", to=to_addr)


def send_document_to_client_from_request(request, doc: Document, *, to_email: str | None = None) -> DocumentEmailResult:
    """Convenience wrapper for views where request has active_employee."""
    return send_document_to_client(doc, actor=getattr(request, "active_employee", None), to_email=to_email)
