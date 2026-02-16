from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import mail_admins

from core.email_utils import format_email_subject


logger = logging.getLogger(__name__)


def alert_admins(subject: str, message: str, *, fail_silently: bool = True, extra: dict[str, Any] | None = None) -> None:
    """Send an ops alert email to configured ADMINS.

    This is intentionally best-effort: we never want alerts to break the request path.
    """

    if not getattr(settings, "ADMINS", None):
        return

    if extra:
        try:
            message = message + "\n\n" + "\n".join([f"{k}: {v}" for k, v in extra.items()])
        except Exception:
            pass

    try:
        mail_admins(subject=format_email_subject(subject), message=message, fail_silently=fail_silently)
    except Exception:
        logger.exception("ops_alert_failed subject=%s", subject)
