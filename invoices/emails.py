# invoices/emails.py
from __future__ import annotations

from typing import Final

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse


def send_invoice_email(inv, to_email: str, *, note: str = "", mode: str = "initial") -> int:
    """
    Send an invoice email (optionally with attached PDF).
    mode: "initial" | "reminder"
    Returns the number of successfully delivered messages (per Django's EmailMessage.send()).
    """
    prefix: Final[str] = getattr(settings, "EMAIL_SUBJECT_PREFIX", "[EZ360PM] ")
    if mode == "reminder":
        subject = f"{prefix}Reminder: Invoice {inv.number} from {inv.company.name}"
    else:
        subject = f"{prefix}Invoice {inv.number} from {inv.company.name}"

    # Build public URL for templates
    try:
        public_url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}{reverse('invoices:invoice_public', kwargs={'token': str(inv.public_token)})}"
    except Exception:
        public_url = ""  # Don't break email if URL reversing fails

    ctx = {
        "inv": inv,
        "note": note,
        "mode": mode,
        "APP_NAME": getattr(settings, "APP_NAME", "EZ360PM"),
        "site_url": getattr(settings, "SITE_URL", ""),
        "public_url": public_url,
    }

    # Render bodies (plain + html)
    text_body = render_to_string("emails/invoice.txt", ctx)
    html_body = render_to_string("emails/invoice.html", ctx)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    msg.attach_alternative(html_body, "text/html")

    # Optional: attach PDF if a renderer is available
    try:
        # Try a dedicated PDF renderer first (if you provide one)
        try:
            from invoices.pdf import render_invoice_pdf  # type: ignore
            pdf_bytes = render_invoice_pdf(inv)
        except Exception:
            # Fallback: render HTML and convert via a helper
            try:
                html = render_to_string("core/pdf/invoice.html", {"inv": inv})
                # Prefer a core.pdf helper if present, otherwise views helper
                try:
                    from core.pdf import _render_pdf_from_html  # type: ignore
                except Exception:
                    from core.views import _render_pdf_from_html  # type: ignore
                base_url = f"{getattr(settings, 'SITE_URL', '').rstrip('/')}/"
                pdf_bytes = _render_pdf_from_html(html, base_url=base_url)
            except Exception:
                pdf_bytes = None

        if pdf_bytes:
            msg.attach(f"invoice_{inv.number}.pdf", pdf_bytes, "application/pdf")
    except Exception:
        # Silently ignore PDF failures so the email still sends
        pass

    return msg.send()
