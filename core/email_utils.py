from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
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
    # Optional attachments: (filename, bytes, mimetype)
    attachments: list[tuple[str, bytes, str]] | None = None


def format_email_subject(subject: str) -> str:
    """Normalize and prefix outbound email subjects.

    Rules:
    - Trim whitespace.
    - Prepend EMAIL_SUBJECT_PREFIX when present (unless the subject already appears prefixed).
    - Optional EMAIL_SUBJECT_SEPARATOR allows controlled joining (e.g. " — ").
    - Truncate to 200 chars (safe for common SMTP providers).
    """

    raw = (subject or "").strip()

    prefix = getattr(settings, "EMAIL_SUBJECT_PREFIX", "") or ""
    sep = getattr(settings, "EMAIL_SUBJECT_SEPARATOR", "") or ""

    if prefix:
        prefix_stripped = str(prefix).strip()
        if raw.lower().startswith(prefix_stripped.lower()):
            out = raw
        else:
            if sep:
                out = f"{prefix_stripped}{sep}{raw}"
            else:
                # Backwards compatible: many deployments set EMAIL_SUBJECT_PREFIX with trailing space already.
                out = f"{prefix}{raw}"
    else:
        out = raw

    return (out or "").strip()[:200]


def _subject_with_prefix(subject: str) -> str:
    # Backwards-compat shim (older call-sites).
    return format_email_subject(subject)


def send_templated_email(spec: EmailSpec, *, fail_silently: bool = False) -> int:
    """Send a multipart email (text + html) with logging + Sentry-friendly behavior."""
    subject = format_email_subject(spec.subject)
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

    # Best-effort: infer company for observability logging.
    company = None
    try:
        ctx = spec.context or {}
        candidate = ctx.get("company") or ctx.get("active_company")
        if candidate is not None and getattr(candidate, "pk", None):
            company = candidate
    except Exception:
        company = None

    # Attachments (optional)
    if spec.attachments:
        for filename, content, mimetype in spec.attachments:
            try:
                msg.attach(filename, content, mimetype)
            except Exception:
                logger.exception("email_attach_failed filename=%s subject=%s", filename, subject)

    try:
        sent = msg.send(fail_silently=fail_silently)
        logger.info("email_sent subject=%s to=%s sent=%s", subject, spec.to, sent)

        # Observability log (best-effort, never blocks delivery)
        try:
            from ops.models import OutboundEmailLog, OutboundEmailStatus

            OutboundEmailLog.objects.create(
                template_type=(spec.template_html or "")[:120],
                to_email=",".join(spec.to)[:254],
                company=company,
                provider_response_id="",
                status=OutboundEmailStatus.SENT,
                error_message="",
                subject=subject[:200],
                created_at=timezone.now(),
            )
        except Exception:
            pass

        return sent
    except Exception as e:
        logger.exception("email_send_failed subject=%s to=%s err=%s", subject, spec.to, str(e)[:500])

        # Observability log (best-effort)
        try:
            from ops.models import OutboundEmailLog, OutboundEmailStatus

            OutboundEmailLog.objects.create(
                template_type=(spec.template_html or "")[:120],
                to_email=",".join(spec.to)[:254],
                company=company,
                provider_response_id="",
                status=OutboundEmailStatus.ERROR,
                error_message=str(e)[:1000],
                subject=subject[:200],
                created_at=timezone.now(),
            )
        except Exception:
            pass

        try:
            from ops.services_alerts import create_ops_alert
            from ops.models import OpsAlertLevel, OpsAlertSource

            create_ops_alert(
                title="Email send failed",
                message="An email failed to send.",
                level=OpsAlertLevel.ERROR,
                source=OpsAlertSource.EMAIL,
                company=company,
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
