from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailSpec:
    subject: str
    to: list[str]
    context: dict[str, Any]
    template_html: str
    template_txt: str | None = None
    from_email: str | None = None
    reply_to: list[str] | None = None


def _subject_with_prefix(subject: str) -> str:
    prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "") or ""
    if prefix and not subject.startswith(prefix):
        return f"{prefix}{subject}"
    return subject


def send_templated_email(spec: EmailSpec, *, fail_silently: bool = False) -> int:
    """Send a multipart email (text + html) with logging + Sentry-friendly behavior."""
    subject = _subject_with_prefix(spec.subject)
    from_email = spec.from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)

    html_body = render_to_string(spec.template_html, spec.context)
    if spec.template_txt:
        text_body = render_to_string(spec.template_txt, spec.context)
    else:
        text_body = strip_tags(html_body)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=spec.to,
        reply_to=spec.reply_to or None,
    )
    msg.attach_alternative(html_body, "text/html")

    try:
        sent = msg.send(fail_silently=fail_silently)
        logger.info("email_sent subject=%s to=%s sent=%s", subject, spec.to, sent)
        return sent
    except Exception as e:
        logger.exception("email_send_failed subject=%s to=%s err=%s", subject, spec.to, str(e)[:500])
        try:
            from ops.services_alerts import create_ops_alert
            from ops.models import OpsAlertLevel, OpsAlertSource

            create_ops_alert(
                title="Email send failed",
                message="An email failed to send.",
                level=OpsAlertLevel.ERROR,
                source=OpsAlertSource.EMAIL,
                company=None,
                details={
                    "subject": subject[:200],
                    "to": ",".join(spec.to)[:500],
                    "error": str(e)[:500],
                    "template_html": spec.template_html,
                },
            )
        except Exception:
            pass
        try:
            if getattr(settings, "EZ360_ALERT_ON_EMAIL_FAILURE", False):
                from core.ops_alerts import alert_admins
                alert_admins(
                    "EZ360PM: email delivery failed",
                    "An email failed to send.",
                    extra={"subject": subject, "to": ",".join(spec.to)[:500], "error": str(e)[:500]},
                )
        except Exception:
            pass
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(e)
        except Exception:
            pass
        if fail_silently:
            return 0
        raise
