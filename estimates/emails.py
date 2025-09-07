# estimates/emails.py
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def send_estimate_email(est, to_email: str, *, note: str = "", mode: str = "initial") -> int:
    """
    Send an estimate email (optionally with attached PDF).
    mode: "initial" | "reminder"

    Returns: number of successfully delivered messages (0 or 1).
    """
    app_name = getattr(settings, "APP_NAME", "EZ360PM")
    prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", f"[{app_name}] ")

    if mode == "reminder":
        subject = f"{prefix}Reminder: Estimate {est.number} from {est.company.name}"
    else:
        subject = f"{prefix}Estimate {est.number} from {est.company.name}"

    site_url = getattr(settings, "SITE_URL", "").rstrip("/")
    public_url = f"{site_url}{reverse('estimates:estimate_public', kwargs={'token': str(est.public_token)})}"

    ctx = {
        "est": est,
        "note": note,
        "mode": mode,
        "APP_NAME": app_name,
        "site_url": site_url,
        "public_url": public_url,
    }

    text_body = render_to_string("estimates/email/estimate.txt", ctx)
    html_body = render_to_string("estimates/email/estimate.html", ctx)

    msg = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [to_email])
    msg.attach_alternative(html_body, "text/html")

    # Optional: attach PDF if renderer exists
    try:
        from core.pdf import render_estimate_pdf  # type: ignore
        pdf_bytes = render_estimate_pdf(est)
        if pdf_bytes:
            msg.attach(f"estimate_{est.number}.pdf", pdf_bytes, "application/pdf")
    except Exception as e:
        logger.warning("Estimate PDF attach failed: %s", e, exc_info=True)

    return msg.send()
