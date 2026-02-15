from __future__ import annotations

import logging
import json
import urllib.request
from typing import Any

from django.conf import settings
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

    created = None
    try:
        created = OpsAlertEvent.objects.create(
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
        return

    # Optional: send to external webhook (Slack/Discord/custom).
    # Best-effort and never raises.
    try:
        url = str(getattr(settings, "OPS_ALERT_WEBHOOK_URL", "") or "").strip()
        if not url:
            return
        timeout = float(getattr(settings, "OPS_ALERT_WEBHOOK_TIMEOUT_SECONDS", 2.5) or 2.5)

        payload = {
            "created_at": created.created_at.isoformat() if created else timezone.now().isoformat(),
            "title": str(title)[:200],
            "message": str(message or "")[:2000],
            "level": str(level),
            "source": str(source),
            "company": {
                "id": company.id if company else None,
                "name": company.name if company else None,
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout):
            pass
    except Exception:
        # Do not recurse into create_ops_alert; just log locally.
        logger.exception("ops_alert_webhook_failed title=%s", str(title)[:200])
