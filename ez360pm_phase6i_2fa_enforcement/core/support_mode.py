from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.utils import timezone
from django.http import HttpRequest

SUPPORT_MODE_ACTIVE_KEY = "support_mode_active"
SUPPORT_MODE_COMPANY_ID_KEY = "support_mode_company_id"
SUPPORT_MODE_EXPIRES_AT_KEY = "support_mode_expires_at"
SUPPORT_MODE_REASON_KEY = "support_mode_reason"

DEFAULT_SUPPORT_MINUTES = 30
MAX_SUPPORT_MINUTES = 120


@dataclass(frozen=True)
class SupportModeState:
    is_active: bool
    company_id: str | None
    expires_at: timezone.datetime | None
    reason: str


def get_support_mode(request: HttpRequest) -> SupportModeState:
    active = bool(request.session.get(SUPPORT_MODE_ACTIVE_KEY, False))
    company_id = request.session.get(SUPPORT_MODE_COMPANY_ID_KEY) or None
    reason = str(request.session.get(SUPPORT_MODE_REASON_KEY) or "").strip()
    expires_raw = request.session.get(SUPPORT_MODE_EXPIRES_AT_KEY)
    expires_at = None
    if expires_raw:
        try:
            expires_at = timezone.datetime.fromisoformat(str(expires_raw))
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at)
        except Exception:
            expires_at = None
    if active and expires_at and timezone.now() >= expires_at:
        # expired
        clear_support_mode(request)
        return SupportModeState(False, None, None, "")
    return SupportModeState(active, str(company_id) if company_id else None, expires_at, reason)


def set_support_mode(
    request: HttpRequest,
    *,
    company_id: str,
    minutes: int = DEFAULT_SUPPORT_MINUTES,
    reason: str = "",
) -> SupportModeState:
    minutes = int(minutes or DEFAULT_SUPPORT_MINUTES)
    if minutes < 5:
        minutes = 5
    if minutes > MAX_SUPPORT_MINUTES:
        minutes = MAX_SUPPORT_MINUTES

    expires_at = timezone.now() + timedelta(minutes=minutes)

    request.session[SUPPORT_MODE_ACTIVE_KEY] = True
    request.session[SUPPORT_MODE_COMPANY_ID_KEY] = str(company_id)
    request.session[SUPPORT_MODE_EXPIRES_AT_KEY] = expires_at.isoformat()
    request.session[SUPPORT_MODE_REASON_KEY] = (reason or "").strip()[:500]
    request.session.modified = True

    return SupportModeState(True, str(company_id), expires_at, (reason or "").strip()[:500])


def clear_support_mode(request: HttpRequest) -> None:
    request.session.pop(SUPPORT_MODE_ACTIVE_KEY, None)
    request.session.pop(SUPPORT_MODE_COMPANY_ID_KEY, None)
    request.session.pop(SUPPORT_MODE_EXPIRES_AT_KEY, None)
    request.session.pop(SUPPORT_MODE_REASON_KEY, None)
    request.session.modified = True
