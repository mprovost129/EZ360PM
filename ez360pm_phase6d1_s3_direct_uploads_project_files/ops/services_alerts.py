from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from companies.models import Company

from .models import OpsAlertEvent, OpsAlertLevel, OpsAlertSource


logger = logging.getLogger(__name__)


def create_ops_alert(
    *,
    title: str,
    message: str = "",
    level: str = OpsAlertLevel.ERROR,
    source: str = OpsAlertSource.EMAIL,
    company: Company | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Best-effort alert creation.

    Never raises. Safe to call inside exception handlers.
    """

    try:
        OpsAlertEvent.objects.create(
            created_at=timezone.now(),
            title=str(title)[:200],
            message=str(message or "")[:10000],
            level=level,
            source=source,
            company=company,
            details=details or {},
        )
    except Exception:
        logger.exception("ops_alert_create_failed title=%s", str(title)[:200])
