from __future__ import annotations

import logging
import json
import urllib.request
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from companies.models import Company

from .models import OpsAlertEvent, OpsAlertLevel, OpsAlertSource, OpsAlertSnooze, SiteConfig


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


    # Best-effort filters and controls: noise filters, snooze, and dedup.
    try:
        cfg = SiteConfig.get_solo()
        d = details or {}
        path = str(d.get("path") or "").strip()
        ua = str(d.get("user_agent") or "").strip().lower()

        prefixes = [ln.strip() for ln in (cfg.ops_alert_noise_path_prefixes or "").splitlines() if ln.strip()]
        if path and prefixes and any(path.startswith(pref) for pref in prefixes):
            return

        tokens = [ln.strip().lower() for ln in (cfg.ops_alert_noise_user_agents or "").splitlines() if ln.strip()]
        if ua and tokens and any(tok in ua for tok in tokens):
            return

        # Snooze: skip creating new alerts for a source (optionally company scoped).
        now = timezone.now()
        snooze_qs = OpsAlertSnooze.objects.filter(source=str(source), snoozed_until__gt=now)
        if company is not None:
            snooze_qs = snooze_qs.filter(Q(company__isnull=True) | Q(company=company))
        else:
            snooze_qs = snooze_qs.filter(company__isnull=True)
        if snooze_qs.exists():
            return

        # Dedup: coalesce identical open alerts within a window.
        try:
            minutes = int(getattr(cfg, "ops_alert_dedup_minutes", 10) or 0)
        except Exception:
            minutes = 10
        if minutes > 0:
            from datetime import timedelta

            window_start = now - timedelta(minutes=minutes)
            existing = (
                OpsAlertEvent.objects.filter(
                    is_resolved=False,
                    source=str(source),
                    title=str(title)[:200],
                    created_at__gte=window_start,
                )
                .filter(company=company if company is not None else None)
                .order_by("-created_at")
                .first()
            )
            if existing is not None:
                try:
                    ed = existing.details or {}
                    cnt = int(ed.get("dedup_count") or 1)
                    ed["dedup_count"] = cnt + 1
                    ed["dedup_last_at"] = now.isoformat()
                    existing.details = ed
                    existing.save(update_fields=["details"])
                except Exception:
                    pass
                return
    except Exception:
        # Never block alert creation if filters fail.
        pass

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
        cfg = SiteConfig.get_solo()
        if not cfg.ops_alert_webhook_enabled:
            return
        url = str(cfg.ops_alert_webhook_url or "").strip()
        if not url:
            return
        timeout = float(cfg.ops_alert_webhook_timeout_seconds or 2.5)

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

    # Optional: send alert email to configured recipients.
    try:
        cfg = SiteConfig.get_solo()
        if not cfg.ops_alert_email_enabled:
            return
        recipients = cfg.email_recipients_list()
        if not recipients:
            return

        level_rank = {"info": 10, "warning": 20, "error": 30, "critical": 40}
        min_level = (cfg.ops_alert_email_min_level or OpsAlertLevel.ERROR)
        if level_rank.get(str(level), 30) < level_rank.get(str(min_level), 30):
            return

        from django.core.mail import EmailMultiAlternatives

        subj = f"EZ360PM Ops Alert · {str(level).upper()} · {str(title)[:120]}"
        body_lines = [
            f"Title: {title}",
            f"Level: {level}",
            f"Source: {source}",
            f"Company: {(company.name if company else '—')} ({(company.id if company else '')})",
            "",
            (message or ""),
        ]
        msg = EmailMultiAlternatives(subject=subj[:200], body="\n".join([str(x) for x in body_lines])[:10000], to=recipients)
        msg.send(fail_silently=True)
    except Exception:
        logger.exception("ops_alert_email_failed title=%s", str(title)[:200])
