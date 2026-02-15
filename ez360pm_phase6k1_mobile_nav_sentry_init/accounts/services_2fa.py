from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone


SESSION_KEY_OK = "two_factor_ok"
SESSION_KEY_OK_AT = "two_factor_ok_at"


def _ttl_seconds() -> int:
    # How long a 2FA confirmation is considered valid for the current session.
    return int(getattr(settings, "TWO_FACTOR_SESSION_TTL_SECONDS", 60 * 60 * 12))  # 12h


def mark_session_2fa_verified(request: HttpRequest) -> None:
    request.session[SESSION_KEY_OK] = True
    request.session[SESSION_KEY_OK_AT] = timezone.now().isoformat()


def clear_session_2fa(request: HttpRequest) -> None:
    request.session.pop(SESSION_KEY_OK, None)
    request.session.pop(SESSION_KEY_OK_AT, None)


def is_session_2fa_verified(request: HttpRequest) -> bool:
    if not request.session.get(SESSION_KEY_OK):
        return False

    at = request.session.get(SESSION_KEY_OK_AT)
    if not at:
        return True

    try:
        ts = timezone.datetime.fromisoformat(at)
        if timezone.is_naive(ts):
            ts = timezone.make_aware(ts, timezone.get_current_timezone())
    except Exception:
        return True

    ttl = timedelta(seconds=_ttl_seconds())
    if timezone.now() - ts > ttl:
        clear_session_2fa(request)
        return False
    return True
