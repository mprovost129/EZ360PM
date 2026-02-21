from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, mail_admins

from core.email_utils import format_email_subject

logger = logging.getLogger(__name__)


def _ops_config_recipients() -> list[str]:
    try:
        from ops.models import SiteConfig  # local import to avoid circulars

        cfg = SiteConfig.get_solo()
        if cfg.ops_alert_email_enabled:
            return cfg.email_recipients_list()
    except Exception:
        return []
    return []


def alert_admins(subject: str, message: str, *, fail_silently: bool = True, extra: dict[str, Any] | None = None) -> None:
    """Send an ops alert email.

    Routing rules:
    1) If Ops SiteConfig has email routing enabled + recipients, send there.
    2) Else, fall back to Django settings.ADMINS via mail_admins.

    Best-effort: never raises.
    """

    if extra:
        try:
            message = message + "\n\n" + "\n".join([f"{k}: {v}" for k, v in extra.items()])
        except Exception:
            pass

    subject = format_email_subject(subject)

    try:
        recipients = _ops_config_recipients()
        if recipients:
            msg = EmailMultiAlternatives(subject=subject, body=message[:10000], to=recipients)
            msg.send(fail_silently=fail_silently)
            return

        if not getattr(settings, "ADMINS", None):
            return

        mail_admins(subject=subject, message=message[:10000], fail_silently=fail_silently)
    except Exception:
        logger.exception("ops_alert_failed subject=%s", subject[:200])
